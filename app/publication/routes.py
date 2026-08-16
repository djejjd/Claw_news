"""公共内容 API 的只读 HTTP 路由。"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.content.clock import local_now
from app.publication.public_api import (
    DigestNotFoundError,
    DigestPublic,
    InvalidRequestError,
    PublicApiError,
    PublicationUnavailableError,
    public_api_error_response,
)
from app.publication.store import PublicationStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/public", tags=["public"])
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _error_response(error: PublicApiError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content=public_api_error_response(error).model_dump(),
    )


def _parse_date(value: str | None, *, default: date) -> date:
    if value is None:
        return default
    if not _DATE_PATTERN.fullmatch(value):
        raise InvalidRequestError()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise InvalidRequestError() from exc


def _parse_page(value: str | None, *, default: int, maximum: int | None = None) -> int:
    if value is None:
        return default
    if not value.isdecimal():
        raise InvalidRequestError()
    parsed = int(value)
    if parsed < 1 or (maximum is not None and parsed > maximum):
        raise InvalidRequestError()
    return parsed


@router.get("/digests", response_model=DigestPublic)
async def get_digest(request: Request, date: str | None = None):
    """返回指定自然日的已发布日报。"""
    config = request.app.state.config
    local_today = local_now(config.tz).date()

    try:
        digest_date = _parse_date(date, default=local_today)
    except PublicApiError as error:
        return _error_response(error)

    try:
        if not config.publication_enabled or not config.publication_database_url:
            raise PublicationUnavailableError()
        digest = PublicationStore(config.publication_database_url).get_public_digest(
            digest_date, local_today=local_today
        )
    except PublicApiError as error:
        return _error_response(error)
    except Exception as exc:
        # 数据库驱动和连接配置细节只能留在服务日志，不能进入公共响应。
        logger.warning("Public digest query failed: %s", type(exc).__name__)
        return _error_response(PublicationUnavailableError())

    if digest is None:
        return _error_response(DigestNotFoundError())
    return digest


@router.get("/articles")
async def get_articles(
    request: Request,
    date: str | None = None,
    source: str | None = None,
    page: str | None = None,
    page_size: str | None = None,
):
    """返回公共文章的稳定分页，查询路径不触发内容清理。"""
    config = request.app.state.config
    local_today = local_now(config.tz).date()
    try:
        selected_date = _parse_date(date, default=local_today)
        selected_page = _parse_page(page, default=1)
        selected_page_size = _parse_page(page_size, default=20, maximum=50)
    except PublicApiError as error:
        return _error_response(error)

    try:
        if not config.publication_enabled or not config.publication_database_url:
            raise PublicationUnavailableError()
        if date is None:
            start_date = local_today - timedelta(days=9)
            end_date = local_today
        else:
            start_date = end_date = selected_date
        return PublicationStore(config.publication_database_url).list_public_articles(
            start_date=start_date,
            end_date=end_date,
            tz=config.tz,
            page=selected_page,
            page_size=selected_page_size,
            source_name=source,
        )
    except PublicApiError as error:
        return _error_response(error)
    except Exception as exc:
        logger.warning("Public article query failed: %s", type(exc).__name__)
        return _error_response(PublicationUnavailableError())
