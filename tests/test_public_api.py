import pytest

from app.publication.public_api import (
    DigestNotFoundError,
    ErrorResponse,
    InvalidRequestError,
    PublicationUnavailableError,
    public_api_error_response,
)


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
