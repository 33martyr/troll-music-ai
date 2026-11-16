"""API errors. Every error response has the shape
``{"error": {"code": "...", "message": "..."}}``."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from troll_music_ai import (
    FeatureNotAvailableError,
    LyricsParseError,
    ProviderNotConfiguredError,
    ProviderResponseError,
    ProviderUnavailableError,
    TrollMusicError,
)

log = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def not_found(what: str) -> ApiError:
    return ApiError(404, "not_found", f"{what} not found.")


_STATUS_BY_ERROR: dict[type[TrollMusicError], int] = {
    ProviderNotConfiguredError: 503,
    ProviderUnavailableError: 503,
    ProviderResponseError: 502,
    LyricsParseError: 502,
    FeatureNotAvailableError: 501,
}
# Looked up by error code so this module does not import the media layer.
_STATUS_BY_CODE = {"invalid_media": 422, "media_error": 500}


def _body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(_body(exc.code, exc.message), status_code=exc.status_code)

    @app.exception_handler(TrollMusicError)
    async def _toolkit_error(_: Request, exc: TrollMusicError) -> JSONResponse:
        status = _STATUS_BY_ERROR.get(type(exc)) or _STATUS_BY_CODE.get(exc.code, 500)
        return JSONResponse(_body(exc.code, exc.message), status_code=status)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(_body("http_error", str(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(part) for part in first.get("loc", []) if part != "body")
        message = f"{field}: {first.get('msg', 'invalid value')}" if field else "Invalid request."
        return JSONResponse(_body("validation_error", message), status_code=422)
