from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.pipeline.candidate import CandidateItem
from app.publication.public_api import (
    DigestNotFoundError,
    ErrorResponse,
    InvalidRequestError,
    PublicationUnavailableError,
    public_api_error_response,
)
from app.publication.routes import router
from app.publication.store import PublicationStore


def test_publication_unavailable_error_uses_stable_non_sensitive_response():
    response = public_api_error_response(PublicationUnavailableError())

    assert response == ErrorResponse(
        detail={"code": "publication_unavailable", "message": "公共内容服务暂不可用"}
    )
    assert "postgres" not in response.model_dump_json().lower()


@pytest.mark.parametrize(
    ("error", "status_code", "code", "message"),
    [
        (InvalidRequestError(), 422, "invalid_request", "请求参数无效"),
        (DigestNotFoundError(), 404, "digest_not_found", "指定日期不存在已发布日报"),
        (PublicationUnavailableError(), 503, "publication_unavailable", "公共内容服务暂不可用"),
    ],
)
def test_public_api_errors_keep_the_approved_status_and_message(error, status_code, code, message):
    response = public_api_error_response(error)

    assert error.status_code == status_code
    assert response.model_dump() == {"detail": {"code": code, "message": message}}


def _articles_client(tmp_path):
    store = PublicationStore(f"sqlite:///{tmp_path / 'publication.db'}")
    store.create_schema()
    for index, published_at in enumerate(
        ["2026-08-16T12:00:00+00:00", "2026-08-16T12:00:00+00:00", "2026-08-16T10:00:00+00:00"],
        start=1,
    ):
        store.publish_articles(
            [
                CandidateItem(
                    title=f"Article {index}",
                    url=f"https://example.test/{index}",
                    summary="公开摘要",
                    source="example" if index < 3 else "other",
                    category="ai",
                    published_at=published_at,
                    fetched_at="2026-08-16T12:01:00+00:00",
                    canonical_key=f"example/{index}",
                )
            ]
        )
    app = FastAPI()
    app.state.config = type(
        "Config",
        (),
        {
            "publication_enabled": True,
            "publication_database_url": str(store.engine.url),
            "tz": "UTC",
        },
    )()
    app.include_router(router)
    return TestClient(app), store


def test_public_articles_paginate_with_stable_order_and_no_writes(tmp_path):
    client, store = _articles_client(tmp_path)
    before = (store.count_articles(), store.count_digests(), store.count_digest_items())

    first = client.get("/api/public/articles?page=1&page_size=2")
    second = client.get("/api/public/articles?page=2&page_size=2")
    beyond = client.get("/api/public/articles?page=3&page_size=2")

    assert first.json() == {
        "items": [
            {**first.json()["items"][0], "title": "Article 1"},
            {**first.json()["items"][1], "title": "Article 2"},
        ],
        "page": 1,
        "page_size": 2,
        "total": 3,
    }
    assert [item["title"] for item in second.json()["items"]] == ["Article 3"]
    assert beyond.json() == {"items": [], "page": 3, "page_size": 2, "total": 3}
    assert (store.count_articles(), store.count_digests(), store.count_digest_items()) == before


def test_public_articles_filter_by_date_and_stable_source_name(tmp_path):
    client, _ = _articles_client(tmp_path)

    source_response = client.get("/api/public/articles?date=2026-08-16&source=other")
    empty_date_response = client.get("/api/public/articles?date=2026-08-01")

    assert [item["title"] for item in source_response.json()["items"]] == ["Article 3"]
    assert empty_date_response.json() == {"items": [], "page": 1, "page_size": 20, "total": 0}


@pytest.mark.parametrize("query", ["page=0", "page_size=51", "date=20260816"])
def test_public_articles_reject_invalid_parameters(query, tmp_path):
    client, _ = _articles_client(tmp_path)

    response = client.get(f"/api/public/articles?{query}")

    assert response.status_code == 422
    assert response.json() == {"detail": {"code": "invalid_request", "message": "请求参数无效"}}


def test_public_sources_are_windowed_deduplicated_and_whitelisted(tmp_path):
    client, store = _articles_client(tmp_path)
    store.publish_sources(
        [
            {
                "name": "example",
                "display_name": "Zeta 来源",
                "default_category": "ai",
                "site_url": "https://example.test",
                "is_enabled": False,
                "include_in_new_user_defaults": True,
                "feeds": [
                    {
                        "url": "https://example.test/private-feed",
                        "collector_type": "rss",
                        "strategy": {"token": "internal"},
                    }
                ],
            },
            {
                "name": "other",
                "display_name": "Alpha 来源",
                "default_category": "ai",
                "site_url": None,
            },
            {
                "name": "empty",
                "display_name": "Empty 来源",
                "default_category": "ai",
                "site_url": "https://empty.example.test",
            },
            {
                "name": "same-a",
                "display_name": "Same 来源",
                "default_category": "ai",
                "site_url": None,
            },
            {
                "name": "same-b",
                "display_name": "Same 来源",
                "default_category": "ai",
                "site_url": None,
            },
            {
                "name": "expired-window",
                "display_name": "过期来源",
                "default_category": "ai",
                "site_url": None,
            },
        ]
    )
    store.publish_articles(
        [
            CandidateItem(
                title="第十天文章",
                url="https://example.test/tenth-day",
                summary="公开摘要",
                source="same-a",
                category="ai",
                fetched_at="2026-08-07T12:00:00+00:00",
                canonical_key="example/tenth-day",
            ),
            CandidateItem(
                title="同名来源文章",
                url="https://example.test/same-name",
                summary="公开摘要",
                source="same-b",
                category="ai",
                fetched_at="2026-08-16T12:00:00+00:00",
                canonical_key="example/same-name",
            ),
            CandidateItem(
                title="第十一天文章",
                url="https://example.test/expired-window",
                summary="公开摘要",
                source="expired-window",
                category="ai",
                fetched_at="2026-08-06T12:00:00+00:00",
                canonical_key="example/expired-window",
            ),
        ]
    )
    before = (store.count_articles(), store.count_digests(), store.count_digest_items())

    with patch("app.publication.routes.local_now", return_value=datetime(2026, 8, 16)):
        response = client.get("/api/public/sources")

    assert response.status_code == 200
    assert response.json() == [
        {"name": "other", "display_name": "Alpha 来源", "site_url": None},
        {"name": "same-a", "display_name": "Same 来源", "site_url": None},
        {"name": "same-b", "display_name": "Same 来源", "site_url": None},
        {
            "name": "example",
            "display_name": "Zeta 来源",
            "site_url": "https://example.test",
        },
    ]
    assert (store.count_articles(), store.count_digests(), store.count_digest_items()) == before


def test_public_sources_return_empty_list_when_no_published_articles(tmp_path):
    store = PublicationStore(f"sqlite:///{tmp_path / 'publication.db'}")
    store.create_schema()
    store.publish_sources(
        [
            {
                "name": "empty",
                "display_name": "Empty 来源",
                "default_category": "ai",
                "site_url": "https://empty.example.test",
            }
        ]
    )
    app = FastAPI()
    app.state.config = type(
        "Config",
        (),
        {
            "publication_enabled": True,
            "publication_database_url": str(store.engine.url),
            "tz": "UTC",
        },
    )()
    app.include_router(router)

    with patch("app.publication.routes.local_now", return_value=datetime(2026, 8, 16)):
        response = TestClient(app).get("/api/public/sources")

    assert response.status_code == 200
    assert response.json() == []
