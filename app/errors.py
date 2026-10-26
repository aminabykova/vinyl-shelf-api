"""Единый формат ошибок API: {"code": "...", "message": "..."}."""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        self.message = message


def bad_request(message: str = "Некорректные данные запроса.") -> ApiError:
    return ApiError(400, "BAD_REQUEST", message)


def unauthorized(message: str = "Требуется авторизация.") -> ApiError:
    return ApiError(401, "UNAUTHORIZED", message)


def forbidden(message: str = "Нет доступа к чужому ресурсу.") -> ApiError:
    return ApiError(403, "FORBIDDEN", message)


def not_found(message: str = "Ресурс не найден.") -> ApiError:
    return ApiError(404, "NOT_FOUND", message)


def conflict(message: str) -> ApiError:
    return ApiError(409, "CONFLICT", message)


def _body(code: str, message: str) -> dict:
    return {"code": code, "message": message}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error_handler(_: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status, content=_body(exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError):
        # По схеме API ошибки валидации - это 400, а не 422 (значение по умолчанию в FastAPI).
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", []) if p not in ("body", "query", "path"))
        message = "Некорректные данные запроса."
        if where:
            message = f"Некорректное значение поля «{where}»."
        return JSONResponse(status_code=400, content=_body("BAD_REQUEST", message))

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(_: Request, exc: StarletteHTTPException):
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "ERROR")
        message = "Ресурс не найден." if exc.status_code == 404 else str(exc.detail)
        return JSONResponse(status_code=exc.status_code, content=_body(code, message))
