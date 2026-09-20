"""Bounded, app-scoped name fallback; never expands calendar title visibility."""
import asyncio
import hashlib
import re
from datetime import datetime

import httpx
import structlog

from ..core.exceptions import ExternalAPIError

logger = structlog.get_logger(__name__)
LOOKUP_SECONDS = 3
MAX_LOOKUPS = 20
NAME_TTL = 300
MISS_TTL = 60


def valid_open_id(value):
    return isinstance(value, str) and re.fullmatch(r'ou_[A-Za-z0-9_-]{1,128}', value)


async def complete_organizers(cache, client, busy, parsed):
    pending = {}
    for room_id, events in parsed.items():
        originals = {(row['uid'], row.get('original_time', 0), datetime.fromisoformat(row['start_time'])):
                     row.get('organizer_info') or {} for row in busy[room_id]}
        for event in events:
            info = originals[(event.uid, event.original_time, event.start_time)]
            open_id = info.get('open_id')
            if not event.organizer and valid_open_id(open_id):
                pending.setdefault(open_id, []).append(event)
    if not pending:
        return
    # open_id belongs to the issuing app; names must never cross app boundaries.
    namespace = hashlib.sha256(client.app_id.encode()).hexdigest()[:24]
    misses = []
    for open_id, events in pending.items():
        key = f'rooms:organizer:v1:{namespace}:{open_id}'
        saved = await cache.get(key)
        if saved is not None:
            for event in events:
                event.organizer = saved or None
        else:
            misses.append((open_id, key, events))

    async def lookup(open_id, key, events):
        try:
            name = await asyncio.wait_for(client.organizer_name(open_id), timeout=LOOKUP_SECONDS)
        except (ExternalAPIError, httpx.HTTPError, TimeoutError, KeyError, TypeError, ValueError) as exc:
            logger.warning('room_organizer_lookup_failed', error_type=type(exc).__name__)
            name = None
        await cache.set(key, name or '', ex=NAME_TTL if name else MISS_TTL)
        for event in events:
            event.organizer = name

    if len(misses) > MAX_LOOKUPS:
        logger.warning('room_organizer_lookup_limited', deferred=len(misses) - MAX_LOOKUPS)
    await asyncio.gather(*(lookup(*item) for item in misses[:MAX_LOOKUPS]))
