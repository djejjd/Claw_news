from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_docker_compose_exposes_optional_pypi_build_args() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())

    build = compose["services"]["claw-news"]["build"]

    assert build["context"] == "."
    assert build["args"]["PIP_INDEX_URL"] == "${PIP_INDEX_URL:-}"
    assert build["args"]["PIP_EXTRA_INDEX_URL"] == "${PIP_EXTRA_INDEX_URL:-}"


def test_dockerfile_accepts_optional_pypi_build_args() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()

    assert "ARG PIP_INDEX_URL" in dockerfile
    assert "ARG PIP_EXTRA_INDEX_URL" in dockerfile
    assert 'PIP_INDEX_URL="${PIP_INDEX_URL}"' in dockerfile
    assert 'PIP_EXTRA_INDEX_URL="${PIP_EXTRA_INDEX_URL}"' in dockerfile


def test_deploy_script_sets_remote_pypi_mirror() -> None:
    script = (ROOT / "deploy-prod.sh").read_text()

    assert 'PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"' in script
    assert "docker compose build claw-news" in script
    assert "for attempt in \\$(seq 1 12)" in script


def test_makefile_exposes_one_command_release_target() -> None:
    makefile = (ROOT / "Makefile").read_text()

    phony = "install test lint format run-morning run-evening dry-run clean clean-data"

    assert f".PHONY: {phony} release-prod" in makefile
    assert "release-prod: lint test" in makefile
    assert "\tbash deploy-prod.sh" in makefile
