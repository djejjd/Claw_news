#!/usr/bin/env python3
"""开发任务门禁：把任务包状态、依赖和文件边界转成可执行检查。"""

from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


class TaskGateError(Exception):
    """任务包不满足实施或提交条件。"""


@dataclass(frozen=True)
class TaskSpec:
    path: Path
    task_id: str
    state: str
    dependencies: tuple[str, ...]
    design_sha: str
    allowed_paths: tuple[str, ...]
    preflight: str
    review: str
    task_commit: str


_TABLE_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|$", re.MULTILINE)
_TASK_ID = re.compile(r"v\d+\.\d+\.\d+-T\d+")
_SHA = re.compile(r"\b[0-9a-f]{40}\b")
_EXACT_SHA = re.compile(r"[0-9a-f]{40}\Z")
_CODE = re.compile(r"`([^`]+)`")

# 门禁上线前已完成且经用户批准迁移的唯一历史提交；不得扩展为可配置开关。
_LEGACY_TRAILER_EXCEPTIONS = {
    ("v1.1.0-T1", "1d0eb92378aa2d028cc8e3141d0d3808aff882ad"),
}


def _metadata(markdown: str) -> dict[str, str]:
    return {key.strip(): value.strip() for key, value in _TABLE_ROW.findall(markdown)}


def _codes(value: str) -> tuple[str, ...]:
    values = tuple(_CODE.findall(value))
    return values or tuple(value.split())


def parse_task(path: Path) -> TaskSpec:
    markdown = path.read_text(encoding="utf-8")
    front_matter = markdown.split("---", 2)
    if len(front_matter) < 3:
        raise TaskGateError(f"任务包缺少 front matter：{path}")
    state_match = re.search(r"^状态:\s*(\S+)\s*$", front_matter[1], re.MULTILINE)
    if state_match is None:
        raise TaskGateError(f"任务包缺少状态：{path}")
    metadata = _metadata(markdown)
    task_ids = _TASK_ID.findall(metadata.get("任务编号", ""))
    if len(task_ids) != 1:
        raise TaskGateError(f"任务包缺少唯一任务编号：{path}")
    sha_match = _SHA.search(metadata.get("设计基线", ""))
    if sha_match is None:
        raise TaskGateError(f"任务包缺少 40 位设计基线 SHA：{path}")
    allowed_paths = _codes(metadata.get("允许修改路径", ""))
    if not allowed_paths:
        raise TaskGateError(f"任务包缺少允许修改路径：{path}")
    dependencies = tuple(_TASK_ID.findall(metadata.get("依赖任务", "")))
    preflight = " ".join(_codes(metadata.get("启动审查结论", ""))).strip()
    review = " ".join(_codes(metadata.get("主审核结论", ""))).strip()
    task_commit = " ".join(_codes(metadata.get("任务提交", ""))).strip()
    return TaskSpec(
        path=path,
        task_id=task_ids[0],
        state=state_match.group(1),
        dependencies=dependencies,
        design_sha=sha_match.group(0),
        allowed_paths=allowed_paths,
        preflight=preflight,
        review=review,
        task_commit=task_commit,
    )


def _git(*args: str) -> str:
    completed = subprocess.run(["git", *args], check=False, text=True, capture_output=True)
    if completed.returncode:
        raise TaskGateError(completed.stderr.strip() or "git command failed")
    return completed.stdout.strip()


def _git_raw(*args: str) -> str:
    completed = subprocess.run(["git", *args], check=False, text=True, capture_output=True)
    if completed.returncode:
        raise TaskGateError(completed.stderr.strip() or "git command failed")
    return completed.stdout


def _plan_root(task: TaskSpec) -> Path | None:
    return next(
        (
            parent
            for parent in task.path.parents
            if parent.name == "计划" and parent.parent.name == "docs"
        ),
        None,
    )


def _dependency_spec(task: TaskSpec, dependency_id: str) -> TaskSpec | None:
    plan_root = _plan_root(task)
    candidates = plan_root.rglob("T*-*.md") if plan_root else task.path.parent.glob("T*-*.md")
    matches: list[TaskSpec] = []
    for candidate in candidates:
        markdown = candidate.read_text(encoding="utf-8")
        if dependency_id not in _TASK_ID.findall(markdown):
            continue
        spec = parse_task(candidate)
        if spec.task_id == dependency_id:
            matches.append(spec)
    if len(matches) > 1:
        raise TaskGateError(f"任务编号重复：{dependency_id}")
    return matches[0] if matches else None


def validate_dependencies(task: TaskSpec) -> None:
    for dependency_id in task.dependencies:
        dependency = _dependency_spec(task, dependency_id)
        if dependency is None:
            raise TaskGateError(f"找不到依赖任务包：{dependency_id}")
        if dependency.state != "completed" or dependency.review != "approved":
            raise TaskGateError(f"依赖任务未完成或未通过审核：{dependency_id}")


def validate_paths(task: TaskSpec, changed_paths: list[str]) -> None:
    validate_combined_paths([task], changed_paths)


def validate_combined_paths(tasks: list[TaskSpec], changed_paths: list[str]) -> None:
    allowed = [pattern for task in tasks for pattern in (*task.allowed_paths, task.path.as_posix())]
    unexpected = [
        path
        for path in changed_paths
        if not any(fnmatch.fnmatch(path, pattern) for pattern in allowed)
    ]
    if unexpected:
        raise TaskGateError(f"存在任务范围外改动：{', '.join(unexpected)}")


def validate_closing_paths(task: TaskSpec, changed_paths: list[str]) -> None:
    version_plan = task.path.parent.parent / f"{task.path.parent.name}-*.md"
    allowed = (task.path.as_posix(), version_plan.as_posix())
    unexpected = [
        path
        for path in changed_paths
        if not any(fnmatch.fnmatch(path, pattern) for pattern in allowed)
    ]
    if unexpected:
        raise TaskGateError(f"存在关闭记录范围外改动：{', '.join(unexpected)}")


def validate_design_baseline(task: TaskSpec) -> None:
    _git("cat-file", "-e", f"{task.design_sha}^{{commit}}")


def validate_preflight(task: TaskSpec) -> None:
    if task.preflight != "approved":
        raise TaskGateError("开始实施前必须记录独立启动审查结论为 approved")


def validate_task_commit(task: TaskSpec) -> None:
    if _EXACT_SHA.fullmatch(task.task_commit) is None:
        raise TaskGateError("已完成任务必须记录 40 位实现提交 SHA")
    _git("cat-file", "-e", f"{task.task_commit}^{{commit}}")
    message = _git("show", "-s", "--format=%B", task.task_commit)
    if f"Task: {task.task_id}" not in message.splitlines():
        if (task.task_id, task.task_commit) in _LEGACY_TRAILER_EXCEPTIONS:
            return
        raise TaskGateError(f"实现提交未声明 Task: {task.task_id}")


def validate_task_commit_in_pr(task: TaskSpec, base: str) -> None:
    validate_task_commit(task)
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", task.task_commit, base], check=False
    )
    if completed.returncode == 0:
        raise TaskGateError(f"任务已在目标分支关闭，不能复用：{task.task_id}")
    if completed.returncode not in {0, 1}:
        raise TaskGateError("无法检查任务提交与目标分支的关系")
    included = subprocess.run(
        ["git", "merge-base", "--is-ancestor", task.task_commit, "HEAD"], check=False
    )
    if included.returncode != 0:
        raise TaskGateError(f"任务实现提交不在当前 PR：{task.task_commit}")


def validate_branch() -> None:
    if _git("branch", "--show-current") == "main":
        raise TaskGateError("禁止在 main 分支实施任务")


def porcelain_paths(output: str) -> list[str]:
    """解析 Git 的 NUL 分隔 porcelain 输出，避免中文路径被引号转义。"""
    paths: list[str] = []
    records = iter(output.split("\0"))
    for record in records:
        if not record:
            continue
        status, path = record[:2], record[3:]
        paths.append(path)
        if "R" in status or "C" in status:
            next(records, None)
    return paths


def expand_working_paths(paths: list[str], root: Path = Path(".")) -> list[str]:
    """将 Git 为未跟踪目录返回的目录项展开为实际文件路径。"""
    expanded: list[str] = []
    for path in paths:
        candidate = root / path
        if candidate.is_dir():
            expanded.extend(
                item.relative_to(root).as_posix() for item in candidate.rglob("*") if item.is_file()
            )
        else:
            expanded.append(path)
    return expanded


def working_paths() -> list[str]:
    return expand_working_paths(porcelain_paths(_git_raw("status", "--porcelain=v1", "-z")))


def nul_paths(output: str) -> list[str]:
    return [path for path in output.split("\0") if path]


def staged_paths() -> list[str]:
    return nul_paths(_git_raw("diff", "--cached", "--name-only", "-z"))


def begin(task: TaskSpec) -> None:
    validate_branch()
    if task.state != "active":
        raise TaskGateError(f"开始实施要求任务状态为 active，当前为 {task.state}")
    validate_preflight(task)
    validate_design_baseline(task)
    validate_dependencies(task)
    validate_paths(task, working_paths())


def commit(task: TaskSpec) -> None:
    validate_branch()
    validate_preflight(task)
    if task.state not in {"review_pending", "completed"}:
        raise TaskGateError(f"提交要求任务状态为 review_pending 或 completed，当前为 {task.state}")
    if task.review != "approved":
        raise TaskGateError("提交前必须记录主审核结论为 approved")
    validate_design_baseline(task)
    validate_dependencies(task)
    if task.state == "completed":
        validate_task_commit(task)
        validate_closing_paths(task, staged_paths())
    else:
        validate_paths(task, staged_paths())


def ci(tasks: list[TaskSpec], base: str) -> None:
    for task in tasks:
        validate_preflight(task)
        if task.state != "completed" or task.review != "approved":
            raise TaskGateError(
                f"CI 要求任务包已 completed 且主审核结论为 approved：{task.task_id}"
            )
        validate_design_baseline(task)
        validate_dependencies(task)
        validate_task_commit_in_pr(task, base)
    output = _git("diff", "--name-only", f"{base}...HEAD")
    changed_paths = [path for path in output.splitlines() if path]
    try:
        validate_combined_paths(tasks, changed_paths)
    except TaskGateError as error:
        raise TaskGateError(str(error).replace("存在任务", "PR 存在任务")) from error


def tasks_from_pr(body: str) -> tuple[str, ...]:
    match = re.search(r"^- 任务包：\s*(.+?)\s*$", body, re.MULTILINE)
    if match is None:
        raise TaskGateError("PR 描述缺少“任务包：docs/计划/.../T*.md”")
    raw_paths = tuple(_CODE.findall(match.group(1)))
    paths = raw_paths or tuple(path.strip() for path in match.group(1).split(",") if path.strip())
    if not paths:
        raise TaskGateError("PR 描述没有有效任务包路径")
    return paths


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("begin", "commit", "ci"):
        command = subparsers.add_parser(name)
        command.add_argument("--task", type=Path, action="append", required=True)
        if name == "ci":
            command.add_argument("--base", required=True)
    pr_command = subparsers.add_parser("tasks-from-pr")
    pr_command.add_argument("--body-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "tasks-from-pr":
            print(*tasks_from_pr(args.body_file.read_text(encoding="utf-8")), sep="\n")
            return 0
        tasks = [parse_task(path) for path in args.task]
        if args.command == "begin":
            if len(tasks) != 1:
                raise TaskGateError("开始门禁一次只能启用一个任务包")
            task = tasks[0]
            begin(task)
        elif args.command == "commit":
            if len(tasks) != 1:
                raise TaskGateError("提交门禁一次只能校验一个任务包")
            task = tasks[0]
            commit(task)
        else:
            ci(tasks, args.base)
        print(f"任务门禁通过：{', '.join(task.task_id for task in tasks)} ({args.command})")
        return 0
    except (OSError, TaskGateError) as error:
        print(f"任务门禁未通过：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
