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


def test_public_deploy_template_has_no_private_target() -> None:
    script = (ROOT / "deploy.example.sh").read_text()

    assert "docker compose up -d --build" in script
    assert "deploy-prod.sh" not in script
    assert "REMOTE_HOST" not in script
    assert "ubuntu@" not in script


def test_makefile_does_not_expose_private_release_target() -> None:
    makefile = (ROOT / "Makefile").read_text()

    assert "release-prod" not in makefile
    assert "deploy-prod.sh" not in makefile


def test_ci_formats_only_python_code_and_tests() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()

    assert "ruff format --check main.py app collectors aggregator infra pusher tests" in workflow
    assert "ruff format --check ." not in workflow
