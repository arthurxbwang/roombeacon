"""V5 pilot worker: continuous observation, explicit occurrence approval, no write retries."""
import asyncio
import secrets
from datetime import UTC, datetime, timedelta

import structlog

from ..connectors.feishu.room_release import FeishuRoomReleaseClient, ReleaseRejected
from ..core.room_devices import room_cache
from ..core.room_usage_auth import KEY
from ..schemas.room_usage import Occurrence
from .room_usage import fresh_target, policy_for, write_allowed
from .room_usage_health import healthy_terminal
from .room_usage_store import PREFIX, UsageStore

logger = structlog.get_logger()
LEASE = PREFIX + 'lease'
RENEW = "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('expire',KEYS[1],ARGV[2]) else return 0 end"
UNLOCK = "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end"


def acknowledged(record, now):
    return (record['state'] == 'checking' and record.get('ack_at') is not None
            and record['challenge_started'] <= record['ack_at'] <= now.timestamp() < record['challenge_expires'])


async def upstream_events(client, room_id, occurrence):
    start = occurrence.start_time - timedelta(days=1)
    end = occurrence.end_time + timedelta(days=1)
    data = await client.freebusy([room_id], start, end)
    if room_id in data.get('error_room_ids', []) or room_id not in data.get('free_busy', {}):
        raise ValueError('Incomplete freebusy result')
    return [Occurrence.model_validate(row) for row in data['free_busy'][room_id]]


async def execute_release(store, client, room_id, record, policy, epoch):
    if not acknowledged(record, datetime.now(UTC)):
        return
    occurrence = Occurrence.model_validate(record['occurrence'])
    key = 'record:' + record['id']
    claimed = {**record, 'state': 'releasing', 'reason': 'dispatch',
               'claimed_at': datetime.now(UTC).timestamp()}
    # Claim before external I/O: another worker can never dispatch this operation again.
    if not await store.cas(key, record, claimed, room_id, policy=policy, action='claim'):
        return
    final = {**claimed, 'state': 'blocked', 'reason': 'preflight_failed'}
    sent = False
    try:
        events = await upstream_events(client, room_id, occurrence)
        if sum(e.identity(room_id) == record['id'] for e in events) != 1:
            final['reason'] = 'upstream_changed'
        else:
            now = datetime.now(UTC)
            terminal_ok = await healthy_terminal(store, room_id, now, record, policy)
            actor_ok = record.get('release_kind') != 'end' or record.get('actor') == await store.cache.get(KEY + room_id)
            safe = (await store.cache.get(LEASE) == epoch and terminal_ok and actor_ok
                    and await policy_for(store, room_id) == policy and await write_allowed(store, policy, room_id)
                    and occurrence.start_time <= now < occurrence.end_time and acknowledged(record, now))
            # Revalidate cache as well: a room can be deleted or disabled during preflight.
            current = await fresh_target(room_id, now)
            if safe and current and current.identity(room_id) == record['id'] and acknowledged(record, datetime.now(UTC)):
                sent = True
                await client.release(room_id, occurrence,
                                     'ENDED_BEFORE_DUE' if record.get('release_kind') == 'end' else 'NOT_CHECK_IN')
                remaining = await upstream_events(client, room_id, occurrence)
                # A shortened or otherwise transformed instance cannot prove release; leave it for review.
                same_uid = any(e.uid == occurrence.uid and e.start_time < occurrence.end_time
                               and e.end_time > now for e in remaining)
                final = {**claimed, 'state': 'uncertain' if same_uid else 'released',
                         'reason': 'verify_pending' if same_uid else 'verified_release'}
                # Expire the existing snapshot's business validity without fabricating free time.
                raw = await store.cache.get('rooms:snapshot:' + room_id)
                if raw:
                    import json
                    snapshot = json.loads(raw)
                    snapshot['valid_until'] = now.isoformat()
                    # Do not overwrite a snapshot refreshed concurrently by the collector.
                    await store.cache.eval(
                        "if redis.call('get',KEYS[1]) == ARGV[1] then redis.call('set',KEYS[1],ARGV[2],'KEEPTTL'); return 1 end return 0",
                        1, 'rooms:snapshot:' + room_id, raw, json.dumps(snapshot))
    except ReleaseRejected as exc:
        final = {**claimed, 'state': 'failed', 'reason': 'feishu_rejected', 'error_code': exc.code}
    except Exception as exc:  # noqa: BLE001 — log type only; preserve ambiguous write state.
        logger.warning('room_usage_release_failed', error_type=type(exc).__name__)
        final = {**claimed, 'state': 'uncertain' if sent else 'blocked', 'reason': 'verify_pending' if sent else 'preflight_failed'}
    await store.cas(key, claimed, final, room_id, action='result')


async def tick_room(store, client, room_id, epoch, now=None):
    now = now or datetime.now(UTC)
    policy = await policy_for(store, room_id)
    if policy.get('owner') != 'v5' or policy['mode'] == 'off':
        return
    occurrence = await fresh_target(room_id, now)
    if not occurrence:
        return
    ident = occurrence.identity(room_id)
    key = 'record:' + ident
    old = await store.get(key)
    opens = occurrence.start_time - timedelta(minutes=policy['early_minutes'])
    deadline = min(occurrence.end_time, occurrence.start_time + timedelta(minutes=policy['grace_minutes']))
    healthy = await healthy_terminal(store, room_id, now, old, policy)
    if old is None:
        if now < opens:
            return
        # Never backfill missed windows, including following data loss.
        epoch_start = await store.get('epoch-start:' + epoch)
        first_seen = await store.cache.set(PREFIX + 'seen:' + ident, '1', nx=True, ex=7 * 86400)
        pending = (now < occurrence.start_time and healthy and first_seen
                   and epoch_start is not None and epoch_start <= opens.timestamp())
        heartbeat = await store.get('heartbeat:' + room_id, {})
        record = {'id': ident, 'room_id': room_id, 'occurrence': occurrence.model_dump(mode='json'),
                  'opens_at': opens.isoformat(), 'deadline': deadline.isoformat(), 'epoch': epoch,
                  'policy_revision': policy['revision'], 'state': 'pending' if pending else 'blocked',
                  'verified': False, 'session_id': heartbeat.get('session_id'), 'last_seen': now.timestamp(),
                  'reason': 'monitoring' if pending else 'missed_window'}
        await store.cas(key, None, record, room_id, policy=policy, action='enroll')
        return
    if old['state'] == 'releasing':
        if old['epoch'] != epoch or now.timestamp() - old.get('claimed_at', 0) > 30:
            await store.cas(key, old, {**old, 'state': 'uncertain', 'reason': 'worker_restarted'}, room_id)
        return
    if old['state'] not in {'pending', 'waiting', 'checking', 'end_requested'}:
        return
    continuous = old['epoch'] == epoch and 0 <= now.timestamp() - old['last_seen'] < 45
    if not continuous or not healthy or old['policy_revision'] != policy['revision']:
        await store.cas(key, old, {**old, 'state': 'blocked', 'reason': 'monitoring_interrupted'}, room_id)
        return
    if old['state'] in {'waiting', 'checking', 'end_requested'}:
        if not old['verified'] or not await write_allowed(store, policy, room_id):
            await store.cas(key, old, {**old, 'state': 'blocked', 'reason': 'release_not_enabled'}, room_id)
            return
        if old['state'] == 'checking':
            if now.timestamp() >= old['challenge_expires']:
                await store.cas(key, old, {**old, 'state': 'blocked', 'reason': 'challenge_expired'}, room_id)
            elif acknowledged(old, now):
                await execute_release(store, client, room_id, old, policy, epoch)
            else:
                await store.cas(key, old, {**old, 'last_seen': now.timestamp()}, room_id, policy=policy, action='monitor')
            return
        if old['state'] == 'end_requested' or now >= datetime.fromisoformat(old['release_at']):
            check = {**old, 'state': 'checking', 'reason': 'terminal_check', 'challenge_id': secrets.token_hex(16),
                     'challenge_started': now.timestamp(), 'challenge_expires': now.timestamp() + 15,
                     'ack_at': None, 'last_seen': now.timestamp(),
                     'release_kind': 'end' if old['state'] == 'end_requested' else 'no_show'}
            await store.cas(key, old, check, room_id, policy=policy)
        else:
            await store.cas(key, old, {**old, 'last_seen': now.timestamp()}, room_id, policy=policy, action='monitor')
        return
    if old['state'] == 'end_requested' or now >= deadline:
        if policy['mode'] == 'observe' and old['state'] == 'pending':
            await store.cas(key, old, {**old, 'state': 'observed', 'reason': 'would_release'}, room_id, policy=policy)
        elif old['verified'] and await write_allowed(store, policy, room_id):
            waiting = {**old, 'state': 'waiting', 'reason': 'grace_before_release', 'last_seen': now.timestamp(),
                       'release_at': min(occurrence.end_time, now + timedelta(seconds=policy['release_delay_seconds'])).isoformat()}
            await store.cas(key, old, waiting, room_id, policy=policy)
        else:
            await store.cas(key, old, {**old, 'state': 'blocked', 'reason': 'release_not_enabled'}, room_id, policy=policy)
    else:
        await store.cas(key, old, {**old, 'last_seen': now.timestamp()}, room_id, policy=policy, action='monitor')


async def usage_loop():
    client = FeishuRoomReleaseClient()
    epoch = None
    try:
        while True:
            try:
                async with room_cache() as cache:
                    store = UsageStore(cache)
                    if epoch is None:
                        candidate = secrets.token_hex(16)
                        if await cache.set(LEASE, candidate, nx=True, ex=30):
                            epoch = candidate
                            await store.put('epoch-start:' + epoch, datetime.now(UTC).timestamp())
                    if epoch:
                        if not await cache.eval(RENEW, 1, LEASE, epoch, 30):
                            epoch = None
                        else:
                            await cache.expire(PREFIX + 'epoch-start:' + epoch, 7 * 86400)
                            for room_id in await store.rooms():
                                if not await cache.eval(RENEW, 1, LEASE, epoch, 30):
                                    epoch = None
                                    break
                                try:
                                    await asyncio.wait_for(tick_room(store, client, room_id, epoch), timeout=25)
                                except Exception as exc:  # noqa: BLE001 — log type only; preserve ambiguous write state.
                                    logger.warning('room_usage_tick_failed', error_type=type(exc).__name__)
            except Exception as exc:  # noqa: BLE001 — log type only; preserve ambiguous write state.
                epoch = None
                logger.warning('room_usage_worker_failed', error_type=type(exc).__name__)
            await asyncio.sleep(2)
    finally:
        await client.close()
        if epoch:
            async with room_cache() as cache:
                await cache.eval(UNLOCK, 1, LEASE, epoch)
