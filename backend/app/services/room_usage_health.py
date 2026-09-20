"""Protocol 2 reports explicitly cover each booking; GET never renews health."""
from datetime import UTC, datetime

from ..core.room_usage_auth import KEY
from .room_usage import conflict, fresh_monitor_targets, fresh_target, policy_for

ACTIVE = {'pending', 'waiting', 'checking', 'end_requested'}


def covers_occurrence(hb, ident):
    return hb.get('occurrence_id') == ident or ident in hb.get('monitored_occurrence_ids', [])


def operation_ready(hb, ident=None):
    # Submitting a confirmation for the current booking does not interrupt the
    # next booking. An uncertain page, however, protects every monitored booking.
    return hb.get('operation_state') == 'ready' or (
        ident is not None and hb.get('operation_state') == 'submitting'
        and ident != hb.get('occurrence_id') and covers_occurrence(hb, ident))


async def healthy_terminal(store, room_id, now, record=None, policy=None):
    hb = await store.get('heartbeat:' + room_id)
    if not hb or hb.get('protocol') != 2 or not operation_ready(hb, record['id'] if record else None):
        return False
    if not 0 <= now.timestamp() - hb['time'] < 45:
        return False
    if hb['actor'] != await store.cache.get(KEY + room_id):
        return False
    if policy and hb['policy_revision'] != policy['revision']:
        return False
    return not record or (hb['session_id'] == record.get('session_id') and covers_occurrence(hb, record['id']))


async def heartbeat(store, room_id, actor, request, now=None):
    now = now or datetime.now(UTC)
    policy = await policy_for(store, room_id)
    if policy.get('owner') != 'v5' or policy['mode'] == 'off' or request.policy_revision != policy['revision']:
        raise conflict('房间方案或规则已变化')
    target = await fresh_target(room_id, now)
    ident = target.identity(room_id) if target else None
    if request.occurrence_id != ident:
        raise conflict('预约已变化')
    eligible = {e.identity(room_id) for e in await fresh_monitor_targets(room_id, now, policy)}
    if not set(request.monitored_occurrence_ids) <= eligible:
        raise conflict('待监控预约已变化')
    name = 'heartbeat:' + room_id
    old = await store.get(name)
    if (old and old['actor'] == actor and old.get('session_id') != request.session_id
            and 0 <= now.timestamp() - old['time'] < 45):
        raise conflict('已有另一个 V5 页面会话，请关闭重复页面')
    new = {**request.model_dump(), 'actor': actor, 'time': now.timestamp()}
    if not await store.cas(name, old, new, room_id, policy=policy, action='monitor'):
        raise conflict('健康状态已变化，请重试')
    covered = set(request.monitored_occurrence_ids) | ({ident} if ident else set())
    for current_id in covered:
        record = await store.get('record:' + current_id)
        if not record or record['state'] not in ACTIVE:
            continue
        interrupted = not operation_ready(new, current_id) or record.get('session_id') != request.session_id
        if interrupted:
            await store.cas('record:' + current_id, record,
                            {**record, 'state': 'blocked', 'reason': 'terminal_operation_uncertain'}, room_id)
            continue
        # Challenges are only answered for the displayed/current occurrence.
        if request.challenge_id and current_id == ident:
            if (record['state'] != 'checking' or request.challenge_id != record.get('challenge_id')
                    or not record['challenge_started'] <= now.timestamp() < record['challenge_expires']
                    or record['epoch'] != await store.cache.get('rooms:usage:v1:lease')):
                raise conflict('释放前核验已失效')
            await store.cas('record:' + current_id, record, {**record, 'ack_at': now.timestamp()},
                            room_id, policy=policy, action='monitor')
