"""Protocol 2 health reports come from the active page, never from GET polling."""
from datetime import UTC, datetime

from ..core.room_usage_auth import KEY
from .room_usage import conflict, fresh_target, policy_for

ACTIVE = {'pending', 'waiting', 'checking', 'end_requested'}


async def healthy_terminal(store, room_id, now, record=None, policy=None):
    hb = await store.get('heartbeat:' + room_id)
    if not hb or hb.get('protocol') != 2 or hb.get('operation_state') != 'ready':
        return False
    if not 0 <= now.timestamp() - hb['time'] < 45:
        return False
    if hb['actor'] != await store.cache.get(KEY + room_id):
        return False
    if policy and hb['policy_revision'] != policy['revision']:
        return False
    return not record or (hb['session_id'] == record.get('session_id') and hb['occurrence_id'] == record['id'])


async def heartbeat(store, room_id, actor, request, now=None):
    now = now or datetime.now(UTC)
    policy = await policy_for(store, room_id)
    if policy.get('owner') != 'v5' or policy['mode'] == 'off' or request.policy_revision != policy['revision']:
        raise conflict('房间方案或规则已变化')
    target = await fresh_target(room_id, now)
    ident = target.identity(room_id) if target else None
    if request.occurrence_id != ident:
        raise conflict('预约已变化')
    name = 'heartbeat:' + room_id
    old = await store.get(name)
    if (old and old['actor'] == actor and old.get('session_id') != request.session_id
            and 0 <= now.timestamp() - old['time'] < 45):
        raise conflict('已有另一个 V5 页面会话，请关闭重复页面')
    new = {**request.model_dump(), 'actor': actor, 'time': now.timestamp()}
    if not await store.cas(name, old, new, room_id, policy=policy, action='monitor'):
        raise conflict('健康状态已变化，请重试')
    record = await store.get('record:' + ident) if ident else None
    if not record or record['state'] not in ACTIVE:
        return
    interrupted = (request.operation_state != 'ready' or record.get('session_id') != request.session_id)
    if interrupted:
        await store.cas('record:' + ident, record,
                        {**record, 'state': 'blocked', 'reason': 'terminal_operation_uncertain'}, room_id)
        return
    if request.challenge_id:
        if (record['state'] != 'checking' or request.challenge_id != record.get('challenge_id')
                or not record['challenge_started'] <= now.timestamp() < record['challenge_expires']
                or record['epoch'] != await store.cache.get('rooms:usage:v1:lease')):
            raise conflict('释放前核验已失效')
        await store.cas('record:' + ident, record, {**record, 'ack_at': now.timestamp()},
                        room_id, policy=policy, action='monitor')
