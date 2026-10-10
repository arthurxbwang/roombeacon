"""Bounded source resolution and pinned rechecks for each individual booking."""
import asyncio
import hashlib
import json
import time

from ..connectors.feishu.calendar_errors import CalendarEvidenceError, evidence_error
from ..core.config import settings
from .room_calendar_evidence import app_scope, current_sources


def dynamic_sources(room_id):
    return (room_id in settings.ROOM_DISPLAY_USAGE_RELEASE_ROOM_IDS
            and room_id in settings.ROOM_DISPLAY_USAGE_ORGANIZER_SOURCE_ROOM_IDS)


def configured_calendar(room_id):
    if room_id in settings.ROOM_DISPLAY_USAGE_RELEASE_ROOM_IDS:
        return settings.ROOM_DISPLAY_USAGE_AUTO_VERIFY_CALENDARS.get(room_id) or None
    return None


def auto_verify_enabled(room_id):
    return bool(configured_calendar(room_id) or dynamic_sources(room_id))


def source_revision(room_id):
    data = [app_scope(), configured_calendar(room_id), dynamic_sources(room_id)]
    return hashlib.sha256(json.dumps(data).encode()).hexdigest()


async def proof_current(store, room_id, occurrence, proof, now):
    organizer, _ = await current_sources(store, room_id, occurrence, now)
    if proof.get('revision') != source_revision(room_id) or proof.get('organizer') != organizer:
        raise CalendarEvidenceError('source_changed')


def cache_for(client):
    cache = client.__dict__.get('_source_cache')
    if cache is None:
        cache = client.__dict__['_source_cache'] = {}
    return cache


def save_cached(client, key, value, seconds):
    cache = cache_for(client)
    cache[key] = (time.monotonic() + seconds, value)
    while len(cache) > 512:
        del cache[next(iter(cache))]


def cached(client, key):
    expiry, value = cache_for(client).get(key, (0, None))
    return (expiry > time.monotonic()), value


async def primary_for(client, organizer, nearby):
    if not organizer:
        return None
    scope = app_scope()
    # One worker shares this client; also coalesce concurrent lookup requests.
    lock = client.__dict__.setdefault('_source_lock', asyncio.Lock())
    async with lock:
        missing = [u for u in nearby if not cached(client, ('primary', scope, u))[0]]
        if missing:
            mapping = await client.primary_calendars(missing)
            for user in missing:
                value = mapping.get(user)
                save_cached(client, ('primary', scope, user), value, 300 if value else 30)
        return cached(client, ('primary', scope, organizer))[1]


async def event_at(client, calendar, event_id, *, fresh=False):
    key = ('missing', app_scope(), calendar, event_id)
    found, error = cached(client, key)
    if found and not fresh:
        raise error
    try:
        event = await client.calendar_event(calendar, event_id)
    except Exception as exc:  # noqa: BLE001 — normalize failures without retaining private URLs or bodies.
        error = evidence_error(exc)
        if error.reason == 'event_not_found':
            save_cached(client, key, error, 30)
        raise error from None
    if not isinstance(event, dict) or event.get('event_id') != event_id or event.get('status') != 'confirmed':
        raise CalendarEvidenceError('event_changed')
    return event


def calendar_id(value):
    if not isinstance(value, str) or not value or len(value) > 512 or any(ord(c) < 33 for c in value):
        raise CalendarEvidenceError('invalid_response')
    return value


async def authoritative_event(client, candidate, event_id, *, pinned=False):
    current, visited = calendar_id(candidate), set()
    for _ in range(3):
        if current in visited:
            raise CalendarEvidenceError('source_conflict')
        visited.add(current)
        event = await event_at(client, current, event_id, fresh=pinned)
        authority = calendar_id(event.get('organizer_calendar_id'))
        if authority == current:
            return current, event
        if pinned:
            raise CalendarEvidenceError('source_changed')
        current = authority
    raise CalendarEvidenceError('source_conflict')


async def resolve_source(client, store, room_id, occurrence, now, *, pinned=None, live_organizer=None):
    if not dynamic_sources(room_id) or store is None:
        raise CalendarEvidenceError('source_unresolved')
    organizer, nearby = await current_sources(store, room_id, occurrence, now)
    event_id = f'{occurrence.uid}_{occurrence.original_time}'
    revision = source_revision(room_id)
    if pinned is not None:
        if (pinned.get('version') != 2 or pinned.get('revision') != revision
                or pinned.get('organizer') != organizer or pinned.get('organizer') != live_organizer):
            raise CalendarEvidenceError('source_changed')
        source, event = await authoritative_event(client, pinned.get('calendar'), event_id, pinned=True)
        return source, event, pinned
    errors, candidates = [], []
    primary_hit, previous_primary = cached(client, ('primary', app_scope(), organizer))
    primary_was_cached = bool(organizer and primary_hit and previous_primary)
    try:
        primary = await primary_for(client, organizer, nearby)
        if primary:
            candidates.append(primary)
    except Exception as exc:  # noqa: BLE001 — an explicit fixed source can remain usable after lookup failure.
        errors.append(evidence_error(exc))
    fixed = configured_calendar(room_id)
    if fixed and fixed not in candidates:
        candidates.append(fixed)
    matches = {}
    for candidate in candidates:
        try:
            source, event = await authoritative_event(client, candidate, event_id)
            matches[source] = event
        except CalendarEvidenceError as exc:
            if exc.reason in {'source_conflict', 'event_changed', 'invalid_response'}:
                raise
            errors.append(exc)
    # A cached primary can become stale. Refresh it once, without re-querying an
    # unchanged missing event; negative caching bounds repeated bad combinations.
    if not matches and primary_was_cached:
        cache_for(client).pop(('primary', app_scope(), organizer), None)
        primary = await primary_for(client, organizer, [organizer])
        if primary and primary not in candidates:
            try:
                source, event = await authoritative_event(client, primary, event_id)
                matches[source] = event
            except CalendarEvidenceError as exc:
                errors.append(exc)
    if len(matches) > 1:
        raise CalendarEvidenceError('source_conflict')
    if not matches:
        # Preserve an actionable denial/transport error instead of burying it in
        # a fallback calendar's unrelated 404.
        raise next((e for e in errors if e.reason != 'event_not_found'),
                   errors[0] if errors else CalendarEvidenceError('source_unresolved'))
    source, event = next(iter(matches.items()))
    proof = {'version': 2, 'revision': revision, 'organizer': organizer, 'calendar': source}
    return source, event, proof
