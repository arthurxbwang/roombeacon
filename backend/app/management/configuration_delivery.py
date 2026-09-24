"""Reconcile durable local configuration with Redis. No upstream writes."""
import asyncio
import json

import structlog
from fastapi import APIRouter, Request
from redis.exceptions import RedisError

from ..core.config import settings
from ..core.exceptions import AppError
from ..core.response import ok
from ..core.room_devices import room_cache
from ..schemas.room_usage import UsagePolicy
from ..services.room_usage import policy_for, save_policy
from ..services.room_usage_store import UsageStore
from .catalog_models import Qualification
from .security import actor
from .store import audit, database

log = structlog.get_logger()
router = APIRouter(prefix='/api/v6/admin')


@router.post('/rooms/{room_id}/qualification')
async def qualification(room_id: str, body: Qualification, request: Request):
    user = actor(request, write=True)
    if not settings.ROOM_DISPLAY_USAGE_ENABLED:
        raise AppError(503, 'V5 尚未启用', 503)
    async with room_cache() as cache:
        store = UsageStore(cache)
        with database() as db:
            current = await policy_for(store, room_id)
            if current['revision'] != body.expected_revision:
                raise AppError(409, '房间规则已变化，请刷新', 409)
            room = db.execute('SELECT * FROM room_configurations WHERE room_id=?', (room_id,)).fetchone()
            if not room:
                raise AppError(422, '请先关联软件模板', 422)
            values = current | body.model_dump(exclude={'expected_revision'})
            if values['mode'] == 'auto' and not (values['native_policy_cleared'] and values['release_verified']):
                values['mode'] = 'observe'
            result = await save_policy(store, room_id, UsagePolicy(**values), persist=False)
            audit(db, user['subject'], 'room-policy', room_id,
                  {'target_name': room['room_name'], 'before': current, 'after': result})
    return ok(result)


async def reconcile_room(store, room_id):
    # Serialize desired-state changes while committing local runtime policy.
    # Redis I/O is bounded; there are never upstream requests in this transaction.
    with database() as db:
        room = db.execute('SELECT * FROM room_configurations WHERE room_id=?', (room_id,)).fetchone()
        if not room:
            return
        desired = json.loads(room['rules'])
        current = await policy_for(store, room_id)
        same = all(current.get(k) == v for k, v in desired.items())
        device = db.execute('SELECT * FROM devices WHERE id=?', (room['controller_id'],)).fetchone()
        if desired['owner'] == 'v5' and (not device or device['status'] != 'active' or
                device['room_id'] != room_id or device['error'] or device['revision'] != device['reported_revision']):
            state, error, revision = 'pending', '等待业务主控设备应用配置', current['revision']
        elif same:
            state, error, revision = 'applied', '', current['revision']
        else:
            if desired['mode'] == 'auto' and not (current['native_policy_cleared'] and current['release_verified']):
                state, error, revision = 'blocked', '此房间尚未完成官方规则核对和释放验证；未启用自动释放', current['revision']
            else:
                result = await save_policy(store, room_id, UsagePolicy(**(current | desired)), persist=False)
                state, error, revision = 'applied', '', result['revision']
        if (room['policy_state'], room['error'], room['policy_revision']) != (state, error, revision):
            db.execute('UPDATE room_configurations SET policy_state=?,error=?,policy_revision=? WHERE room_id=?',
                       (state, error, revision, room_id))
            audit(db, 'system', 'policy-apply', room_id,
                  {'target_name': room['room_name'], 'state': state, 'error': error, 'after': desired})


async def configuration_loop():
    while True:
        try:
            if settings.ROOM_DISPLAY_V6_DB and settings.ROOM_DISPLAY_USAGE_ENABLED:
                with database() as db:
                    rooms = [row[0] for row in db.execute('SELECT room_id FROM room_configurations')]
                async with room_cache() as cache:
                    store = UsageStore(cache)
                    for room_id in rooms:
                        await reconcile_room(store, room_id)
        except asyncio.CancelledError:
            raise
        except (AppError, RedisError, OSError, ValueError) as exc:
            log.error('configuration_reconcile_failed', error_type=type(exc).__name__)
        await asyncio.sleep(15)


def ensure_template_rules(room_id, policy):
    if not settings.ROOM_DISPLAY_V6_DB:
        return
    with database() as db:
        room = db.execute('SELECT rules FROM room_configurations WHERE room_id=?', (room_id,)).fetchone()
        if room and any(policy.model_dump().get(k) != v for k, v in json.loads(room['rules']).items()):
            raise AppError(409, '此会议室由软件模板管理，请编辑模板并部署；房间验收记录可单独更新', 409)
