"""Prove additions from complete snapshots within one healthy observation session.

First sight after startup/outage is a baseline, never proof of a new booking.
Evidence is cache-only and does not replace calendar release qualification.
"""
import secrets
from datetime import timedelta

from ..schemas.room_usage import Occurrence
from .room_usage_health import healthy_terminal
from .room_usage_store import PREFIX, TTL, encoded


async def invalidate_observation(store, room_id):
    await store.cache.delete(PREFIX + 'observation:' + room_id)


async def observe_arrivals(store, room_id, epoch, now, policy, snapshot, targets):
    start, end = snapshot.query_start, snapshot.query_end
    if (start is None or end is None or start.tzinfo is None or end.tzinfo is None
            or not start < end or snapshot.synced_at > now or len(snapshot.events) > 2048):
        await invalidate_observation(store, room_id)
        return {}
    key = 'observation:' + room_id
    old = await store.get(key)
    hb = await store.get('heartbeat:' + room_id, {})
    healthy = await healthy_terminal(store, room_id, now, policy=policy)
    context = {'epoch': epoch, 'session_id': hb.get('session_id'),
               'actor': hb.get('actor'), 'policy_revision': policy['revision']}
    continuous = bool(old and healthy and old['healthy']
                      and all(old.get(k) == v for k, v in context.items())
                      and 0 <= now.timestamp() - old['checked_at'] < 45
                      and old['snapshot_at'] <= snapshot.synced_at.timestamp()
                      and old['valid_until'] > now.timestamp())
    generation = old['generation'] if continuous else secrets.token_hex(16)
    ids = [Occurrence.model_validate(e.model_dump()).identity(room_id) for e in snapshot.events]
    new = {**context, 'healthy': healthy, 'generation': generation, 'ids': ids,
           'checked_at': now.timestamp(), 'snapshot_at': snapshot.synced_at.timestamp(),
           'valid_until': snapshot.valid_until.timestamp(),
           'query_start': start.timestamp(), 'query_end': end.timestamp()}
    if not await store.cas(key, old, new, room_id, policy=policy, action='monitor'):
        return {}
    result = {}
    for occurrence in targets:
        ident = occurrence.identity(room_id)
        # Both queries must fully cover this exact interval. A widened query or
        # a newly readable initial snapshot cannot manufacture absence evidence.
        added = (continuous and old['snapshot_at'] < new['snapshot_at'] and ident not in old['ids']
                 and max(old['query_start'], new['query_start']) <= occurrence.start_time.timestamp()
                 and occurrence.end_time.timestamp() <= min(old['query_end'], new['query_end']))
        proof_key = 'arrival:' + ident
        if added:
            deadline = min(occurrence.end_time, max(now, occurrence.start_time)
                           + timedelta(minutes=policy['grace_minutes']))
            proof = {'generation': generation, 'first_observed_at': now.isoformat(),
                     'deadline': deadline.isoformat()}
            # Retain the original deadline even after deletion/reappearance or
            # a restart. A mismatched generation can never rearm that proof.
            await store.cache.set(PREFIX + proof_key, encoded(proof), nx=True, ex=TTL)
        proof = await store.get(proof_key)
        if continuous and proof and proof['generation'] == generation:
            result[ident] = proof
    return result
