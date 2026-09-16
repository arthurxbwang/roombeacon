"""Isolated door-display ASGI app: no platform routes, DB, Celery workers or event listeners."""
import asyncio
import hmac
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, Header, Query, Request, Response

from .core.config import settings
from .core.exceptions import AppError, UnauthorizedError, app_error_handler
from .core.response import R, ok
from .core.room_devices import authenticate_device
from .schemas.meeting_room import RoomSchedule
from .services.room_checkin import checkin_qr
from .services.room_display_collector import cached_directory as directory
from .services.room_display_collector import cached_schedule as schedule_for
from .services.room_display_collector import collector_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    worker = asyncio.create_task(collector_loop())
    try:
        yield
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)


app = FastAPI(lifespan=lifespan, title="Meeting room display", docs_url=None, redoc_url=None, openapi_url=None)
app.add_exception_handler(AppError, app_error_handler)


async def get_current_user(request: Request, authorization: str = Header(default="")) -> dict:
    token = authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else ""
    return await authenticate_device(token, request.url.path, request.method)


@app.get("/api/meeting-rooms/display", response_model=R[RoomSchedule])
async def display(response: Response, user: dict = Depends(get_current_user)):
    response.headers["Cache-Control"] = "no-store"
    snapshot = await schedule_for(user["room_id"])
    return ok(snapshot.model_copy(update={"server_time": datetime.now(UTC), "checkin_qr": checkin_qr(snapshot.room.room_id)}))


async def require_admin(authorization: str = Header(default="")) -> dict:
    candidates = ((settings.ROOM_DISPLAY_CONTROL_TOKEN, 32),
                  (settings.ROOM_DISPLAY_CONTROL_TOKEN_SECONDARY, 1))
    token = authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else ""
    matches = [bool(expected.strip()) and len(expected) >= minimum
               and hmac.compare_digest(token.encode(), expected.encode())
               for expected, minimum in candidates]
    if not any(matches):
        raise UnauthorizedError("请输入有效的测试主控凭证")
    return {"role": "room_control"}


@app.get("/api/room-control/rooms")
async def control_rooms(response: Response, user: dict = Depends(require_admin)):
    response.headers["Cache-Control"] = "no-store"
    return ok(await directory())


@app.get("/api/room-control/preview", response_model=R[RoomSchedule])
async def control_preview(response: Response,
                          room_id: str = Query(pattern=r"^omm_[a-zA-Z0-9]+$", max_length=100),
                          user: dict = Depends(require_admin)):
    response.headers["Cache-Control"] = "no-store"
    snapshot = await schedule_for(room_id)
    return ok(snapshot.model_copy(update={"server_time": datetime.now(UTC), "checkin_qr": checkin_qr(snapshot.room.room_id)}))
