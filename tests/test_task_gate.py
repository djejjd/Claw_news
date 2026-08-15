from pathlib import Path

import pytest

from scripts.task_gate import (
    TaskGateError,
    TaskSpec,
    begin,
    ci,
    commit,
    expand_working_paths,
    nul_paths,
    parse_task,
    porcelain_paths,
    tasks_from_pr,
    validate_closing_paths,
    validate_combined_paths,
    validate_dependencies,
    validate_paths,
    validate_task_commit,
)


def _task_markdown(
    *,
    task_id="v1.1.0-T2",
    dependencies="`v1.1.0-T1`",
    state="active",
    preflight="approved",
    review="pending",
    task_commit="pending",
    allowed_paths="`app/example.py`, `tests/test_example.py`",
):
    return f"""---
状态: {state}
---

| 项目 | 内容 |
|---|---|
| 任务编号 | `{task_id}` |
| 依赖任务 | {dependencies} |
| 设计基线 | `610c77cfc927f10564d973c9af4d37c4b38cdf58` |
| 允许修改路径 | {allowed_paths} |
| 启动审查结论 | `{preflight}` |
| 主审核结论 | `{review}` |
| 任务提交 | `{task_commit}` |
"""


def test_parse_task_reads_machine_checked_metadata(tmp_path):
    task_path = tmp_path / "T2-example.md"
    task_path.write_text(_task_markdown(), encoding="utf-8")

    task = parse_task(task_path)

    assert task.task_id == "v1.1.0-T2"
    assert task.dependencies == ("v1.1.0-T1",)
    assert task.allowed_paths == ("app/example.py", "tests/test_example.py")


def test_parse_task_rejects_task_without_explicit_file_boundary(tmp_path):
    task_path = tmp_path / "T2-example.md"
    task_path.write_text(_task_markdown(allowed_paths=""), encoding="utf-8")

    with pytest.raises(TaskGateError, match="允许修改路径"):
        parse_task(task_path)


def test_validate_paths_rejects_unrelated_changes():
    task = TaskSpec(
        path=Path("docs/计划/网站/v1.1.0/T2-example.md"),
        task_id="v1.1.0-T2",
        state="active",
        dependencies=(),
        design_sha="0" * 40,
        allowed_paths=("app/example.py", "tests/test_example.py"),
        preflight="approved",
        review="pending",
        task_commit="pending",
    )

    with pytest.raises(TaskGateError, match="范围外"):
        validate_paths(task, ["app/example.py", "app/main.py"])


def test_validate_combined_paths_allows_only_the_declared_task_union():
    first = TaskSpec(
        path=Path("docs/计划/网站/v1.1.0/T1-example.md"),
        task_id="v1.1.0-T1",
        state="completed",
        dependencies=(),
        design_sha="0" * 40,
        allowed_paths=("app/one.py",),
        preflight="approved",
        review="approved",
        task_commit="a" * 40,
    )
    second = TaskSpec(
        path=Path("docs/计划/网站/v1.1.0/T2-example.md"),
        task_id="v1.1.0-T2",
        state="completed",
        dependencies=(),
        design_sha="0" * 40,
        allowed_paths=("app/two.py",),
        preflight="approved",
        review="approved",
        task_commit="b" * 40,
    )

    validate_combined_paths([first, second], ["app/one.py", "app/two.py"])

    with pytest.raises(TaskGateError, match="范围外"):
        validate_combined_paths([first, second], ["app/three.py"])


def test_validate_closing_paths_rejects_new_implementation_files():
    task = TaskSpec(
        path=Path("docs/计划/网站/v1.1.0/T2-example.md"),
        task_id="v1.1.0-T2",
        state="completed",
        dependencies=(),
        design_sha="0" * 40,
        allowed_paths=("app/example.py",),
        preflight="approved",
        review="approved",
        task_commit="a" * 40,
    )

    validate_closing_paths(
        task,
        [
            "docs/计划/网站/v1.1.0/T2-example.md",
            "docs/计划/网站/v1.1.0-公共内容API.md",
        ],
    )

    with pytest.raises(TaskGateError, match="关闭记录范围外"):
        validate_closing_paths(task, ["app/example.py"])


def test_begin_rejects_an_active_task_without_approved_preflight(monkeypatch):
    task = TaskSpec(
        path=Path("docs/计划/网站/v1.1.0/T2-example.md"),
        task_id="v1.1.0-T2",
        state="active",
        dependencies=(),
        design_sha="0" * 40,
        allowed_paths=("app/example.py",),
        preflight="pending",
        review="pending",
        task_commit="pending",
    )
    monkeypatch.setattr("scripts.task_gate.validate_branch", lambda: None)

    with pytest.raises(TaskGateError, match="独立启动审查"):
        begin(task)


def test_commit_and_ci_reject_tasks_without_approved_preflight(monkeypatch):
    task = TaskSpec(
        path=Path("docs/计划/网站/v1.1.0/T2-example.md"),
        task_id="v1.1.0-T2",
        state="review_pending",
        dependencies=(),
        design_sha="0" * 40,
        allowed_paths=("app/example.py",),
        preflight="pending",
        review="approved",
        task_commit="pending",
    )
    monkeypatch.setattr("scripts.task_gate.validate_branch", lambda: None)

    with pytest.raises(TaskGateError, match="独立启动审查"):
        commit(task)

    completed = TaskSpec(**{**task.__dict__, "state": "completed", "task_commit": "a" * 40})
    with pytest.raises(TaskGateError, match="独立启动审查"):
        ci([completed], "origin/main")


def test_legacy_migration_allows_only_the_exact_pre_gate_t1_commit(monkeypatch):
    monkeypatch.setattr(
        "scripts.task_gate._git",
        lambda *args: "legacy commit without task trailer" if "show" in args else "",
    )
    legacy_t1 = TaskSpec(
        path=Path("docs/计划/网站/v1.1.0/T1-公共读取仓储与契约.md"),
        task_id="v1.1.0-T1",
        state="completed",
        dependencies=(),
        design_sha="0" * 40,
        allowed_paths=("app/publication/store.py",),
        preflight="approved",
        review="approved",
        task_commit="1d0eb92378aa2d028cc8e3141d0d3808aff882ad",
    )

    validate_task_commit(legacy_t1)

    with pytest.raises(TaskGateError, match="Task"):
        validate_task_commit(TaskSpec(**{**legacy_t1.__dict__, "task_commit": "a" * 40}))
    with pytest.raises(TaskGateError, match="Task"):
        validate_task_commit(TaskSpec(**{**legacy_t1.__dict__, "task_id": "v1.1.0-T2"}))


def test_porcelain_paths_keeps_hidden_and_chinese_paths_unquoted():
    output = " M .github/workflows/ci.yml\0?? docs/规范/开发流程.md\0"

    assert porcelain_paths(output) == [".github/workflows/ci.yml", "docs/规范/开发流程.md"]


def test_nul_paths_keeps_staged_chinese_paths_unquoted():
    assert nul_paths("docs/规范/开发流程.md\0scripts/task_gate.py\0") == [
        "docs/规范/开发流程.md",
        "scripts/task_gate.py",
    ]


def test_expand_working_paths_expands_untracked_directories(tmp_path):
    task_path = tmp_path / "docs" / "计划" / "T1.md"
    task_path.parent.mkdir(parents=True)
    task_path.write_text("task", encoding="utf-8")

    assert expand_working_paths(["docs/计划"], tmp_path) == ["docs/计划/T1.md"]


def test_validate_dependencies_rejects_a_parent_that_is_not_closed(tmp_path):
    parent = tmp_path / "T1-parent.md"
    child = tmp_path / "T2-child.md"
    parent.write_text(
        _task_markdown(task_id="v1.1.0-T1", dependencies="无", state="completed", review="pending"),
        encoding="utf-8",
    )
    child.write_text(_task_markdown(), encoding="utf-8")

    with pytest.raises(TaskGateError, match="未完成或未通过审核"):
        validate_dependencies(parse_task(child))


def test_validate_dependencies_supports_dependencies_in_another_task_directory(tmp_path):
    parent = tmp_path / "docs" / "计划" / "工程治理" / "v0.2.1" / "T1-parent.md"
    child = tmp_path / "docs" / "计划" / "网站" / "v1.1.0" / "T2-child.md"
    parent.parent.mkdir(parents=True)
    child.parent.mkdir(parents=True)
    parent.write_text(
        _task_markdown(
            task_id="v0.2.1-T1",
            dependencies="无",
            state="completed",
            preflight="approved",
            review="approved",
            task_commit="a" * 40,
        ),
        encoding="utf-8",
    )
    child.write_text(_task_markdown(dependencies="`v0.2.1-T1`"), encoding="utf-8")

    validate_dependencies(parse_task(child))


def test_tasks_from_pr_requires_the_task_package_field_and_supports_multiple_tasks():
    assert tasks_from_pr(
        "- 任务包：`docs/计划/网站/v1.1.0/T1-公共读取仓储与契约.md`, "
        "`docs/计划/网站/v1.1.0/T2-日报API.md`"
    ) == (
        "docs/计划/网站/v1.1.0/T1-公共读取仓储与契约.md",
        "docs/计划/网站/v1.1.0/T2-日报API.md",
    )
    with pytest.raises(TaskGateError, match="缺少"):
        tasks_from_pr("- 关联任务/问题：T2")
