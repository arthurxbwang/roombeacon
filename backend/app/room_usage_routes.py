"""Opt-in V5 APIs. Every endpoint authenticates before returning room data."""
from fastapi import APIRouter, Depends, Header, Path, Response

from .core.config import settings
from .core.exceptions import AppError
from .core.response import ok
from .core.room_devices import room_cache
from .core.room_usage_auth import authenticate_usage
from .schemas.room_usage import (
    ROOM_PATTERN,
    PauseCommand,
    TerminalCommand,
    UsageCommand,
    UsageHeartbeat,
    UsagePolicy,
    VerifiedOccurrence,
    VerifiedRecurringOccurrence,
)
from .services.room_display_collector import cached_schedule
from .services.room_usage import (
    command,
    confirm_from_control,
    conflict,
    room_writes_enabled,
    save_policy,
    verify_occurrence,
    view,
)
from .services.room_usage_health import heartbeat
from .services.room_usage_store import UsageStore


def usage_router(require_admin):
    router = APIRouter()

    async def store_dep(response: Response):
        response.headers['Cache-Control'] = 'no-store'
        if not settings.ROOM_DISPLAY_USAGE_ENABLED:
            raise AppError(503, 'V5 确认使用功能尚未启用', 503)
        async with room_cache() as cache:
            yield UsageStore(cache)

    async def action_user(authorization: str = Header(default='')):
        token = authorization.removeprefix('Bearer ') if authorization.startswith('Bearer ') else ''
        return await authenticate_usage(token)

    @router.get('/api/meeting-rooms/usage')
    async def status(user=Depends(action_user), store=Depends(store_dep)):
        return ok(await view(store, user[0]))

    @router.post('/api/meeting-rooms/usage/heartbeat')
    async def health(body: UsageHeartbeat, user=Depends(action_user), store=Depends(store_dep)):
        await heartbeat(store, *user, body)
        return ok(await view(store, user[0]))

    @router.post('/api/meeting-rooms/usage/confirm')
    async def confirm(body: TerminalCommand, user=Depends(action_user), store=Depends(store_dep)):
        return ok(await command(store, *user, body, 'confirm'))

    @router.post('/api/meeting-rooms/usage/end')
    async def end(body: TerminalCommand, user=Depends(action_user), store=Depends(store_dep)):
        return ok(await command(store, *user, body, 'end'))

    @router.get('/api/room-control/usage/{room_id}')
    async def inspect(room_id: str = Path(pattern=ROOM_PATTERN), admin=Depends(require_admin), store=Depends(store_dep)):
        return ok({'usage': await view(store, room_id), 'audit': await store.audit(room_id),
                   'global_audit': await store.audit('global'),
                   'writes_enabled': room_writes_enabled(room_id),
                   'control_confirm_enabled': room_id in settings.ROOM_DISPLAY_USAGE_RELEASE_ROOM_IDS})

    @router.post('/api/room-control/usage/{room_id}/confirm')
    async def control_confirm(body: UsageCommand, room_id: str = Path(pattern=ROOM_PATTERN),
                              admin=Depends(require_admin), store=Depends(store_dep)):
        return ok(await confirm_from_control(store, room_id, body))

    @router.put('/api/room-control/usage/{room_id}/policy')
    async def policy(body: UsagePolicy, room_id: str = Path(pattern=ROOM_PATTERN),
                     admin=Depends(require_admin), store=Depends(store_dep)):
        await cached_schedule(room_id)
        return ok(await save_policy(store, room_id, body))

    @router.post('/api/room-control/usage/{room_id}/verify')
    async def verify(body: VerifiedOccurrence | VerifiedRecurringOccurrence, room_id: str = Path(pattern=ROOM_PATTERN),
                     admin=Depends(require_admin), store=Depends(store_dep)):
        return ok(await verify_occurrence(store, room_id, body))

    @router.put('/api/room-control/usage-pause')
    async def pause(body: PauseCommand, admin=Depends(require_admin), store=Depends(store_dep)):
        # Expiry deliberately returns to paused=True.
        old = await store.get('paused')
        if not await store.cas('paused', old, body.paused, 'global', action='pause'):
            raise conflict('全局开关已变化，请刷新')
        return ok({'paused': body.paused})

    return router
