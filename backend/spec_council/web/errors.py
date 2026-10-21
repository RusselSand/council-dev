"""Ошибки нового API — всегда {"error": {"code", "message"}} (docs/api-contract.md, «Ошибки»).

Ручка сообщает об ошибке через ApiError: HTTP-код, code — интерфейс показывает по нему текст из
своего словаря — и message для разработчика и логов. Общие коды — здесь: нет ручки или объекта
(not_found), запрос не разобрать (bad_request), сбой на сервере (internal). Свои коды ручки — у
её модуля.

Ручки нового API — на ContractRoute: кривой запрос у них — bad_request, а не ответ FastAPI
своего вида. Старые ручки (api/) отвечают по-старому — {"detail": …}, пока не уйдут по этапам.
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    """Ответ ошибкой по контракту."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def not_found(message: str) -> ApiError:
    return ApiError(404, "not_found", message)


def bad_request(message: str) -> ApiError:
    return ApiError(400, "bad_request", message)


def answer(status: int, code: str, message: str,
           headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status,
                        headers=headers)


class ContractRoute(APIRoute):
    """Ручка нового API: тело, путь или заголовки не разобрать — bad_request."""

    def get_route_handler(self):
        handle = super().get_route_handler()

        async def handled(request: Request):
            try:
                return await handle(request)
            except RequestValidationError as exc:
                raise bad_request(described(exc)) from None

        return handled


def described(exc: RequestValidationError) -> str:
    """Что не так с запросом: поле и почему — одной строкой."""
    return "; ".join(f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                     for error in exc.errors()) or "запрос не разобрать"


async def on_api_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    return answer(exc.status, exc.code, exc.message)


async def on_http_error(request: Request, exc: Exception):
    """Нет ручки по такому пути или с таким методом — not_found. HTTPException самого FastAPI
    бросают только старые ручки: им — их прежний вид."""
    assert isinstance(exc, StarletteHTTPException)
    if isinstance(exc, HTTPException):
        return await http_exception_handler(request, exc)
    if exc.status_code in (404, 405):
        return answer(404, "not_found", f"Нет ручки {request.method} {request.url.path}")
    code = "internal" if exc.status_code >= 500 else "bad_request"
    return answer(exc.status_code, code, str(exc.detail), exc.headers)


async def on_crash(request: Request, exc: Exception) -> JSONResponse:
    """Сбой на сервере. Подробности — в логе сервера: исключение после ответа идёт дальше, и
    сервер его записывает."""
    return answer(500, "internal", f"Сбой на сервере: {type(exc).__name__}")


def install(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, on_api_error)
    app.add_exception_handler(StarletteHTTPException, on_http_error)
    app.add_exception_handler(Exception, on_crash)
