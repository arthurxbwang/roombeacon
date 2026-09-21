"""Requalify each fresh booking from an explicitly configured readable calendar."""
import asyncio
import hashlib
import time
from datetime import datetime, timedelta

import structlog

from ..core.config import settings
from .room_usage import fresh_monitor_targets, policy_for, write_allowed
from .room_usage_health import healthy_terminal

logger = structlog.get_logger()
FIELDS = ('verification_source', 'verification_calendar', 'release_scope', 'release_original_time')


def configured_calendar(room_id):
    if room_id not in settings.ROOM_DISPLAY_USAGE_RELEASE_ROOM_IDS:
        return None
    return settings.ROOM_DISPLAY_USAGE_AUTO_VERIFY_CALENDARS.get(room_id) or None


def same_times(event, occurrence):
    try:
        return (float(event['start_time']['timestamp']) == occurrence.start_time.timestamp()
                and float(event['end_time']['timestamp']) == occurrence.end_time.timestamp())
    except (KeyError, TypeError, ValueError):
        return False


def live_event(event, event_id):
    return (isinstance(event, dict) and event.get('event_id') == event_id
            and event.get('status') == 'confirmed')


async def calendar_qualification(client, room_id, occurrence):
    calendar = configured_calendar(room_id)
    if not calendar:
        raise ValueError('No authoritative calendar configured')
    async with asyncio.timeout(8):
        event_id = f'{occurrence.uid}_{occurrence.original_time}'
        event = await client.calendar_event(calendar, event_id)
        if not live_event(event, event_id):
            raise ValueError('Calendar event changed or cancelled')
        original = occurrence.original_time
        if original > 0:
            if (event.get('is_exception') is not True or not same_times(event, occurrence)
                    or event.get('recurring_event_id') not in {occurrence.uid, occurrence.uid + '_0'}):
                raise ValueError('Exception metadata does not match')
            scope = 'recurring_instance'
        elif event.get('is_exception') is False and isinstance(event.get('recurrence'), str):
            if event['recurrence']:
                instances = await client.calendar_instances(calendar, event_id, occurrence.start_time, occurrence.end_time)
                matches = [e for e in instances if isinstance(e, dict) and e.get('status') == 'confirmed'
                           and same_times(e, occurrence)]
                if len(matches) != 1:
                    raise ValueError('Recurring instance not unique')
                uid, suffix = matches[0].get('event_id', '').rsplit('_', 1)
                if uid != occurrence.uid or not suffix.isdecimal() or int(suffix) <= 0:
                    raise ValueError('Invalid recurring instance identity')
                original, scope = int(suffix), 'recurring_instance'
            elif same_times(event, occurrence):
                scope = 'non_recurring'
            else:
                raise ValueError('Non-recurring event changed')
        else:
            raise ValueError('Incomplete recurrence metadata')
    return {'verified': True, 'verification_source': 'calendar',
            'verification_calendar': hashlib.sha256(calendar.encode()).hexdigest(),
            'release_scope': scope, 'release_original_time': original}


async def auto_release_target(client, room_id, record, occurrence):
    verified = await calendar_qualification(client, room_id, occurrence)
    if any(record.get(key) != verified[key] for key in FIELDS):
        raise ValueError('Calendar qualification changed')
    return occurrence.model_copy(update={'original_time': verified['release_original_time']})


async def maybe_auto_verify(store, client, room_id, record, policy, occurrence, now):
    if (record['state'] != 'pending' or record.get('verified') or not configured_calendar(room_id)
            or now.timestamp() < record.get('verification_retry_at', 0)
            or not await write_allowed(store, policy, room_id)):
        return False
    started = time.monotonic()
    try:
        qualification = await calendar_qualification(client, room_id, occurrence)
    except Exception as exc:  # noqa: BLE001 — no raw upstream data, retry only a future bounded read.
        logger.warning('room_usage_calendar_verify_failed', error_type=type(exc).__name__)
        new = {**record, 'verification_retry_at': now.timestamp() + 30,
               'verification_error': type(exc).__name__, 'last_seen': now.timestamp()}
        await store.cas('record:' + record['id'], record, new, room_id, policy=policy, action='monitor')
        return True
    checked = now + timedelta(seconds=time.monotonic() - started)
    # Calendar I/O is not heartbeat evidence; recheck all mutable admission state.
    if (checked >= datetime.fromisoformat(record['deadline'])
            or await policy_for(store, room_id) != policy or not await write_allowed(store, policy, room_id)
            or not await healthy_terminal(store, room_id, checked, record, policy)):
        return True
    targets = await fresh_monitor_targets(room_id, checked, policy)
    if not any(e.identity(room_id) == record['id'] for e in targets):
        return True
    updated = {**record, **qualification, 'last_seen': checked.timestamp(), 'verification_error': None}
    await store.cas('record:' + record['id'], record, updated, room_id, policy=policy, action='auto_verify_calendar')
    return True
