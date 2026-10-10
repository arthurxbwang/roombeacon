"""Qualify each fresh booking from a verified source in an explicitly enabled room."""
import asyncio
import hashlib
import time
from datetime import UTC, datetime, timedelta

import structlog

from ..connectors.feishu.calendar_errors import CalendarEvidenceError, evidence_error
from .room_calendar_sources import (
    auto_verify_enabled,
    configured_calendar,
    dynamic_sources,
    proof_current,
    resolve_source,
)
from .room_usage import fresh_monitor_targets, policy_for, write_allowed
from .room_usage_health import healthy_terminal

logger = structlog.get_logger()
FIELDS = ('verification_source', 'verification_calendar', 'release_scope', 'release_original_time')


def same_times(event, occurrence):
    try:
        return (float(event['start_time']['timestamp']) == occurrence.start_time.timestamp()
                and float(event['end_time']['timestamp']) == occurrence.end_time.timestamp())
    except (KeyError, TypeError, ValueError):
        return False


def live_event(event, event_id):
    return (isinstance(event, dict) and event.get('event_id') == event_id
            and event.get('status') == 'confirmed')


async def calendar_qualification(client, room_id, occurrence, *, store=None, now=None,
                                 pinned=None, live_organizer=None, legacy=False):
    calendar = configured_calendar(room_id)
    proof = None
    async with asyncio.timeout(8):
        event_id = f'{occurrence.uid}_{occurrence.original_time}'
        if dynamic_sources(room_id) and not legacy:
            calendar, event, proof = await resolve_source(client, store, room_id, occurrence,
                                                        now or datetime.now(UTC), pinned=pinned,
                                                        live_organizer=live_organizer)
        else:
            if pinned or not calendar:
                raise CalendarEvidenceError('source_unresolved')
            event = await client.calendar_event(calendar, event_id)
        if not live_event(event, event_id):
            raise CalendarEvidenceError('event_changed')
        original = occurrence.original_time
        if original > 0:
            if (event.get('is_exception') is not True or not same_times(event, occurrence)
                    or event.get('recurring_event_id') not in {occurrence.uid, occurrence.uid + '_0'}):
                raise CalendarEvidenceError('event_changed')
            scope = 'recurring_instance'
        elif event.get('is_exception') is False and isinstance(event.get('recurrence'), str):
            if event['recurrence']:
                instances = await client.calendar_instances(calendar, event_id, occurrence.start_time, occurrence.end_time)
                matches = [e for e in instances if isinstance(e, dict) and e.get('status') == 'confirmed'
                           and same_times(e, occurrence)]
                if len(matches) != 1:
                    raise CalendarEvidenceError('event_changed')
                uid, suffix = matches[0].get('event_id', '').rsplit('_', 1)
                if uid != occurrence.uid or not suffix.isdecimal() or int(suffix) <= 0:
                    raise CalendarEvidenceError('invalid_response')
                original, scope = int(suffix), 'recurring_instance'
            elif same_times(event, occurrence):
                scope = 'non_recurring'
            else:
                raise CalendarEvidenceError('event_changed')
        else:
            raise CalendarEvidenceError('invalid_response')
    result = {'verified': True, 'verification_source': 'calendar',
            'verification_calendar': hashlib.sha256(calendar.encode()).hexdigest(),
            'release_scope': scope, 'release_original_time': original}
    if proof is not None:
        result['_calendar_source'] = proof
    return result


async def auto_release_target(client, room_id, record, occurrence, *, store=None, live_organizer=None):
    proof = record.get('_calendar_source')
    try:
        verified = await calendar_qualification(client, room_id, occurrence, store=store, pinned=proof,
                                               live_organizer=live_organizer, legacy=proof is None)
    except Exception as exc:  # noqa: BLE001 — classify total-budget and metadata failures at the dispatch boundary too.
        raise evidence_error(exc) from None
    if any(record.get(key) != verified[key] for key in FIELDS):
        raise CalendarEvidenceError('source_changed')
    if proof:
        await proof_current(store, room_id, occurrence, proof, datetime.now(UTC))
    return occurrence.model_copy(update={'original_time': verified['release_original_time']})


async def maybe_auto_verify(store, client, room_id, record, policy, occurrence, now):
    if (record['state'] != 'pending' or record.get('verified') or not auto_verify_enabled(room_id)
            or now.timestamp() < record.get('verification_retry_at', 0)
            or not await write_allowed(store, policy, room_id)):
        return False
    started = time.monotonic()
    try:
        qualification = await calendar_qualification(client, room_id, occurrence, store=store, now=now)
    except Exception as exc:  # noqa: BLE001 — no raw upstream data, retry only a future bounded read.
        error = evidence_error(exc)
        count = record.get('verification_failures', 0) + 1
        delay = max(min(30 * 2 ** min(count - 1, 3), 120), min(error.retry_after, 86400))
        logger.warning('room_usage_calendar_verify_failed', reason=error.reason,
                       http_status=error.http_status, code=error.code)
        new = {**record, 'verification_retry_at': now.timestamp() + delay,
               'verification_error': error.reason, 'verification_failures': count,
               'verification_failed_at': now.isoformat(), 'verification_http_status': error.http_status,
               'verification_code': error.code, 'last_seen': now.timestamp()}
        action = 'verification_failed' if record.get('verification_error') != error.reason else 'monitor'
        await store.cas('record:' + record['id'], record, new, room_id, policy=policy, action=action)
        return True
    checked = now + timedelta(seconds=time.monotonic() - started)
    if qualification.get('_calendar_source'):
        try:
            await proof_current(store, room_id, occurrence, qualification['_calendar_source'], checked)
        except CalendarEvidenceError:
            return True  # Evidence changed during I/O. No stale proof is published.
    # Calendar I/O is not heartbeat evidence; recheck all mutable admission state.
    if (checked >= datetime.fromisoformat(record['deadline'])
            or await policy_for(store, room_id) != policy or not await write_allowed(store, policy, room_id)
            or not await healthy_terminal(store, room_id, checked, record, policy)):
        return True
    targets = await fresh_monitor_targets(room_id, checked, policy)
    if not any(e.identity(room_id) == record['id'] for e in targets):
        return True
    updated = {**record, **qualification, 'last_seen': checked.timestamp(), 'verification_error': None,
               'verification_succeeded_at': checked.isoformat(), 'verification_retry_at': 0,
               'verification_http_status': None, 'verification_code': None}
    await store.cas('record:' + record['id'], record, updated, room_id, policy=policy, action='auto_verify_calendar')
    return True
