"""Cache-only V5 confirmation and command admission."""
import secrets
from datetime import UTC, datetime, timedelta

from ..core.config import settings
from ..core.exceptions import AppError
from ..schemas.room_usage import Occurrence, UsagePolicy
from .room_display_collector import cached_schedule


def conflict(message):
    return AppError(409, message, 409)


async def policy_for(store, room_id):
    value = await store.get('policy:' + room_id)
    # Policies written before the protected protocol never authorize new writes.
    if value and 'owner' not in value:
        return {**value, 'owner': 'official', 'mode': 'off', 'release_delay_seconds': 60}
    return value or UsagePolicy().model_dump()


async def fresh_target(room_id, now):
    snapshot = await cached_schedule(room_id)
    if not snapshot.room.enabled or snapshot.valid_until <= now or snapshot.synced_at > now + timedelta(seconds=10):
        raise conflict('会议室状态待核实，请等待同步')
    current = [event for event in snapshot.events if event.start_time <= now < event.end_time]
    if len(current) > 1:
        raise conflict('存在重叠预约，暂停操作')
    upcoming = sorted((event for event in snapshot.events if event.start_time > now), key=lambda e: e.start_time)
    target = (current or upcoming or [None])[0]
    return Occurrence.model_validate(target.model_dump()) if target else None


async def fresh_monitor_targets(room_id, now, policy):
    """Only fresh, non-overlapping bookings whose advance windows have opened."""
    snapshot = await cached_schedule(room_id)
    if not snapshot.room.enabled or snapshot.valid_until <= now or snapshot.synced_at > now + timedelta(seconds=10):
        raise conflict('会议室状态待核实，请等待同步')
    limit = now + timedelta(minutes=policy['early_minutes'])
    events = sorted((e for e in snapshot.events if e.end_time > now), key=lambda e: e.start_time)
    candidates = [e for e in events if e.start_time <= limit]
    if len(candidates) > 64:
        raise conflict('待监控预约过多，请核对日程')
    for candidate in candidates:
        if sum(e.start_time < candidate.end_time and e.end_time > candidate.start_time for e in events) != 1:
            raise conflict('存在重叠预约，暂停操作')
    return [Occurrence.model_validate(event.model_dump()) for event in candidates]


async def save_policy(store, room_id, policy):
    if policy.owner == 'official' and policy.mode != 'off':
        raise conflict('官方方案必须关闭 RoomBeacon 确认与释放')
    if policy.mode == 'auto' and not (policy.native_policy_cleared and policy.release_verified):
        raise conflict('自动模式需先完成原生策略核对和释放验证')
    old = await store.get('policy:' + room_id)
    new = policy.model_copy(update={'revision': secrets.token_hex(12)}).model_dump()
    if not await store.cas('policy:' + room_id, old, new, room_id, action='policy'):
        raise conflict('规则已变化，请刷新')
    # Publish only after a valid policy exists. A failure leaves a disabled room.
    from .room_usage_store import PREFIX
    await store.cache.sadd(PREFIX + 'rooms', room_id)
    return new


def room_writes_enabled(room_id):
    return settings.ROOM_DISPLAY_USAGE_WRITES_ENABLED and room_id in settings.ROOM_DISPLAY_USAGE_RELEASE_ROOM_IDS


async def write_allowed(store, policy, room_id):
    return (room_writes_enabled(room_id) and policy.get('owner') == 'v5' and policy['mode'] == 'auto'
            and policy['native_policy_cleared'] and policy['release_verified']
            and not await store.get('paused', True))


async def view(store, room_id, now=None):
    now = now or datetime.now(UTC)
    policy = await policy_for(store, room_id)
    result = {'room_id': room_id, 'enabled': settings.ROOM_DISPLAY_USAGE_ENABLED,
              'policy': policy, 'paused': await store.get('paused', True),
              'server_time': now.isoformat(), 'valid_until': (now + timedelta(seconds=30)).isoformat(),
              'record': None, 'can_confirm': False, 'can_end': False}
    result['target_id'] = None
    result['monitored_occurrence_ids'] = []
    if not settings.ROOM_DISPLAY_USAGE_ENABLED or policy.get('owner') != 'v5' or policy['mode'] == 'off':
        return result
    target = await fresh_target(room_id, now)
    result['monitored_occurrence_ids'] = [e.identity(room_id) for e in await fresh_monitor_targets(room_id, now, policy)]
    if not target:
        return result
    key = target.identity(room_id)
    result['target_id'] = key
    record = await store.get('record:' + key)
    if not record:
        return result
    result['record'] = {k: v for k, v in record.items() if k not in {'actor', 'session_id'}}
    valid = record['policy_revision'] == policy['revision']
    limit = record.get('release_at', record['deadline'])
    inside = datetime.fromisoformat(record['opens_at']) <= now < min(datetime.fromisoformat(limit), target.end_time)
    result['can_confirm'] = valid and inside and record['state'] in {'pending', 'waiting', 'blocked'}
    return result


async def command(store, room_id, actor, request, action, now=None):
    if action != 'confirm':
        raise AppError(403, '门牌不支持提前结束会议', 403)
    now = now or datetime.now(UTC)
    state = await view(store, room_id, now)
    record, policy = state['record'], state['policy']
    if not record or record['id'] != request.occurrence_id or policy['revision'] != request.policy_revision:
        raise conflict('预约或规则已变化，请刷新后重试')
    # Re-read complete stored value for CAS; view intentionally omits actor fingerprints.
    old = await store.get('record:' + record['id'])
    if old is None or old['state'] != record['state']:
        raise conflict('操作状态已变化，请刷新')
    if request.session_id != old.get('session_id'):
        raise conflict('操作页面会话已变化，请等待下一场完整确认窗口')
    if action == 'confirm' and record['state'] == 'confirmed':
        return state
    if not state['can_' + action]:
        raise conflict('当前不可执行该操作，请核对确认窗口与释放开关')
    updated = {**old, 'state': 'confirmed',
               'actor': actor, 'updated_at': now.isoformat(), 'last_seen': now.timestamp(), 'reason': action}
    if not await store.cas('record:' + old['id'], old, updated, room_id, policy=policy, action=action):
        raise conflict('预约状态或规则已变化，请重新查询')
    return await view(store, room_id, now)


async def verify_occurrence(store, room_id, request):
    state = await view(store, room_id)
    record = state['record']
    if not record or record['id'] != request.occurrence_id or state['policy']['revision'] != request.policy_revision:
        raise conflict('预约已变化，请重新核对')
    old = await store.get('record:' + record['id'])
    if not old or old['state'] not in {'pending', 'confirmed', 'observed'}:
        raise conflict('当前实例不可登记')
    if not await store.cas('record:' + old['id'], old, {**old, 'verified': True}, room_id,
                           policy=state['policy'], action='verify_non_recurring'):
        raise conflict('预约状态已变化')
    return await view(store, room_id)


async def confirm_from_control(store, room_id, request, now=None):
    """Explicit admin confirmation does not grant heartbeat, session or release rights."""
    if room_id not in settings.ROOM_DISPLAY_USAGE_RELEASE_ROOM_IDS:
        raise AppError(403, '本房间未开放主控签到测试', 403)
    now = now or datetime.now(UTC)
    state = await view(store, room_id, now)
    record, policy = state['record'], state['policy']
    if not record or record['id'] != request.occurrence_id or policy['revision'] != request.policy_revision:
        raise conflict('预约或规则已变化，请刷新后重试')
    old = await store.get('record:' + record['id'])
    if old is None or old['state'] != record['state']:
        raise conflict('操作状态已变化，请刷新')
    if old['state'] == 'confirmed':
        return state
    if not state['can_confirm']:
        raise conflict('当前不在签到窗口内，或预约已进入释放流程')
    updated = {**old, 'state': 'confirmed', 'actor': 'control',
               'updated_at': now.isoformat(), 'reason': 'control_confirm'}
    if not await store.cas('record:' + old['id'], old, updated, room_id, policy=policy, action='control_confirm'):
        raise conflict('预约状态或规则已变化，请重新查询')
    return await view(store, room_id, now)
