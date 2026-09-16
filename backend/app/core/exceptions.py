from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, code: int = -1, message: str = "Internal Error", status_code: int = 500):
        self.code = code
        self.message = message
        self.status_code = status_code


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(code=404, message=message, status_code=404)


class ForbiddenError(AppError):
    def __init__(self, message: str = "Forbidden"):
        super().__init__(code=403, message=message, status_code=403)


class UnauthorizedError(AppError):
    def __init__(self, message: str = "Unauthorized"):
        super().__init__(code=401, message=message, status_code=401)


class BadRequestError(AppError):
    def __init__(self, message: str = "Bad request"):
        super().__init__(code=400, message=message, status_code=400)


class ExternalAPIError(AppError):
    def __init__(self, provider: str, message: str = "External API error"):
        import structlog
        structlog.get_logger().error("external_api_error provider=%s detail=%s", provider, message)
        super().__init__(code=502, message=f"外部服务 [{provider}] 暂不可用", status_code=502)


class ReadOnlyModeError(AppError):
    def __init__(self, message: str = "系统处于只读模式（READ_ONLY_MODE），禁止设备写入或读取操作"):
        super().__init__(code=503, message=message, status_code=503)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message, "data": None},
    )
