"""Isolated door-display ASGI app: no platform routes, DB, Celery workers or event listeners."""
import asyncio
import hmac
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, Header, Query, Request, Response

from .core.config import settings
from .core.exceptions import AppError, UnauthorizedError, app_error_handler
from .core.response import R, ok
from .core.room_devices import authenticate_device, room_cache
from .management.auth import router as auth_router
from .management.catalog import router as catalog_router
from .management.configuration_assets import router as assets_router
from .management.configuration_delivery import configuration_loop
from .management.configuration_delivery import router as delivery_router
from .management.configuration_migration import router as migration_router
from .management.deployment_batch import router as batch_deployments_router
from .management.deployments import router as deployments_router
from .management.devices import router as devices_router
from .management.security import DEVICE_COOKIE, actor, authenticate_web
from .room_usage_routes import usage_router
from .schemas.meeting_room import DisplayPreferences, RoomSchedule
from .services.room_checkin import checkin_qr
from .services.room_display_collector import cached_directory as directory
from .services.room_display_collector import cached_schedule as schedule_for
from .services.room_display_collector import collector_loop
from .services.room_usage import policy_for
from .services.room_usage_store import UsageStore
from .services.room_usage_worker import usage_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    worker = asyncio.create_task(collector_loop())
    usage_worker = asyncio.create_task(usage_loop()) if settings.ROOM_DISPLAY_USAGE_ENABLED else None
    configuration_worker = asyncio.create_task(configuration_loop())
    try:
        yield
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        configuration_worker.cancel()
        await asyncio.gather(configuration_worker, return_exceptions=True)
        if usage_worker:
            usage_worker.cancel()
            await asyncio.gather(usage_worker, return_exceptions=True)


app = FastAPI(lifespan=lifespan, title="Meeting room display", docs_url=None, redoc_url=None, openapi_url=None)
app.add_exception_handler(AppError, app_error_handler)


async def get_current_user(request: Request, authorization: str = Header(default="")) -> dict:
    if request.cookies.get(DEVICE_COOKIE):
        return authenticate_web(request.cookies[DEVICE_COOKIE])
    token = authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else ""
    return await authenticate_device(token, request.url.path, request.method)


async def decorate(snapshot):
    owner = 'official'
    if settings.ROOM_DISPLAY_USAGE_ENABLED:
        async with room_cache() as cache:
            owner = (await policy_for(UsageStore(cache), snapshot.room.room_id))['owner']
    return snapshot.model_copy(update={'server_time': datetime.now(UTC), 'usage_owner': owner,
                                       'checkin_qr': checkin_qr(snapshot.room.room_id) if owner == 'official' else None})


@app.get("/api/meeting-rooms/display", response_model=R[RoomSchedule])
async def display(response: Response, user: dict = Depends(get_current_user)):
    response.headers["Cache-Control"] = "no-store"
    snapshot = await schedule_for(user["room_id"])
    return ok((await decorate(snapshot)).model_copy(update={
        "display_preferences": DisplayPreferences(**user["display_preferences"]) if "display_preferences" in user else None}))


async def require_admin(request: Request, authorization: str = Header(default="")) -> dict:
    if request.cookies.get('__Host-rb_admin'):
        return actor(request, write=True)
    candidates = ((settings.ROOM_DISPLAY_CONTROL_TOKEN, 32),
                  (settings.ROOM_DISPLAY_CONTROL_TOKEN_SECONDARY, 1))
    token = authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else ""
    matches = [bool(expected.strip()) and len(expected) >= minimum
               and hmac.compare_digest(token.encode(), expected.encode())
               for expected, minimum in candidates]
    if not any(matches):
        raise UnauthorizedError("请输入有效的测试主控凭证")
    return {"role": "room_control"}


async def require_reader(request: Request, authorization: str = Header(default="")) -> dict:
    if request.cookies.get('__Host-rb_admin'):
        return actor(request)
    return await require_admin(request, authorization)


@app.get("/api/room-control/rooms")
async def control_rooms(response: Response, user: dict = Depends(require_reader)):
    response.headers["Cache-Control"] = "no-store"
    return ok(await directory())


@app.get("/api/room-control/preview", response_model=R[RoomSchedule])
async def control_preview(response: Response,
                          room_id: str = Query(pattern=r"^omm_[a-zA-Z0-9]+$", max_length=100),
                          user: dict = Depends(require_reader)):
    response.headers["Cache-Control"] = "no-store"
    snapshot = await schedule_for(room_id)
    result = await decorate(snapshot)
    if settings.ROOM_DISPLAY_V6_DB:
        import json

        from .management.store import database
        with database() as db:
            row = db.execute('SELECT v.spec FROM room_configurations r JOIN config_versions v '
                             'ON v.template_id=r.software_id AND v.version=r.software_version '
                             'WHERE r.room_id=?', (room_id,)).fetchone()
            if row:
                result = result.model_copy(update={'display_preferences': DisplayPreferences(**json.loads(row['spec']))})
    return ok(result)


app.include_router(usage_router(require_admin, require_reader))
app.include_router(auth_router)
app.include_router(devices_router)
app.include_router(catalog_router)
app.include_router(assets_router)
app.include_router(migration_router)
app.include_router(delivery_router)
app.include_router(deployments_router)
app.include_router(batch_deployments_router)


@app.middleware('http')
async def private_responses(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith('/api/v6/'):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
    return response
