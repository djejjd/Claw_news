from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.publication import routes
from tests.frontend_e2e_api_server import TEST_NOW, create_app


@pytest.fixture(autouse=True)
def fixed_test_clock(monkeypatch):
    monkeypatch.setattr(routes, "local_now", lambda _tz: TEST_NOW)


def test_seeded_service_exposes_the_existing_public_router(tmp_path):
    client = TestClient(create_app(tmp_path / "publication.db"))

    digest = client.get("/api/public/digests")
    articles = client.get("/api/public/articles")
    sources = client.get("/api/public/sources")

    assert digest.status_code == 200
    assert digest.json()["date"] == date(2026, 8, 17).isoformat()
    assert [item["title"] for item in articles.json()["items"]] == ["测试公共文章"]
    assert sources.json() == [
        {
            "name": "test-source",
            "display_name": "测试来源",
            "site_url": "https://example.test",
        }
    ]


def test_empty_scenarios_keep_public_response_contract(tmp_path):
    empty_digest = TestClient(create_app(tmp_path / "empty-digest.db", scenario="empty-digest"))
    empty_articles = TestClient(
        create_app(tmp_path / "empty-articles.db", scenario="empty-articles")
    )

    assert empty_digest.get("/api/public/digests").json() == {
        "detail": {"code": "digest_not_found", "message": "指定日期不存在已发布日报"}
    }
    assert empty_articles.get("/api/public/articles").json() == {
        "items": [],
        "page": 1,
        "page_size": 20,
        "total": 0,
    }


def test_unavailable_scenario_returns_the_stable_503_response(tmp_path):
    client = TestClient(create_app(tmp_path / "unavailable.db", scenario="unavailable"))

    response = client.get("/api/public/articles")

    assert response.status_code == 503
    assert response.json() == {
        "detail": {"code": "publication_unavailable", "message": "公共内容服务暂不可用"}
    }


def test_create_app_does_not_replace_the_shared_route_clock(tmp_path):
    original_clock = routes.local_now

    create_app(tmp_path / "publication.db")

    assert routes.local_now is original_clock
