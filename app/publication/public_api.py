"""公共内容 API 的显式响应 DTO 与领域错误。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class SourcePublic(BaseModel):
    name: str
    display_name: str
    site_url: str | None


class ArticlePublic(BaseModel):
    id: int
    title: str
    original_url: str
    category: str
    topic: str | None
    summary: str
    published_at: str | None
    fetched_at: str
    source: SourcePublic


class DigestItemPublic(BaseModel):
    position: int
    core_summary: str
    importance: str
    trend: str
    topic_label: str | None
    article: ArticlePublic


class GitHubProjectPublic(BaseModel):
    position: int
    full_name: str
    recommendation: str


class DigestPublic(BaseModel):
    date: str
    version: int
    published_at: str
    daily_judgement: str
    items: list[DigestItemPublic]
    github_projects: list[GitHubProjectPublic]


class ArticlePage(BaseModel):
    items: list[ArticlePublic]
    page: int
    page_size: int
    total: int


class ErrorDetail(BaseModel):
    code: Literal["invalid_request", "digest_not_found", "publication_unavailable"]
    message: str


class ErrorResponse(BaseModel):
    detail: ErrorDetail


class PublicApiError(Exception):
    code: Literal["invalid_request", "digest_not_found", "publication_unavailable"]
    message: str
    status_code: int

    def __init__(self) -> None:
        super().__init__(self.code)


class InvalidRequestError(PublicApiError):
    code = "invalid_request"
    message = "请求参数无效"
    status_code = 422


class DigestNotFoundError(PublicApiError):
    code = "digest_not_found"
    message = "指定日期不存在已发布日报"
    status_code = 404


class PublicationUnavailableError(PublicApiError):
    code = "publication_unavailable"
    message = "公共内容服务暂不可用"
    status_code = 503


def public_api_error_response(error: PublicApiError) -> ErrorResponse:
    return ErrorResponse(detail=ErrorDetail(code=error.code, message=error.message))
