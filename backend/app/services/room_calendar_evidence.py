"""Private organizer evidence paired with the public room snapshot."""
import hashlib
import re
from datetime import datetime, timedelta

from ..connectors.feishu.calendar_errors import CalendarEvidenceError
from ..core.config import settings
from ..schemas.room_usage import Occurrence


def app_scope():
    return hashlib.sha256((settings.FEISHU_APP_ID + '\0' + settings.FEISHU_APP_SECRET).encode()).hexdigest()


def organizers_for(room_id, rows):
    result = {}
    for row in rows:
        ident = Occurrence.model_validate({'original_time': 0, **row}).identity(room_id)
        organizer = (row.get('organizer_info') or {}).get('open_id')
        if not isinstance(organizer, str) or not re.fullmatch(r'ou_[A-Za-z0-9_-]{1,128}', organizer):
            organizer = None
        if ident in result and result[ident] != organizer:
            raise CalendarEvidenceError('source_conflict')
        result[ident] = organizer
    return result


def source_evidence(snapshot, rows):
    return {'app_scope': app_scope(), 'snapshot_at': snapshot.synced_at.isoformat(),
            'valid_until': snapshot.valid_until.isoformat(),
            'organizers': organizers_for(snapshot.room.room_id, rows)}


async def current_sources(store, room_id, occurrence, now):
    from .room_usage import cached_schedule
    snapshot = await cached_schedule(room_id)
    evidence = await store.get('sources:' + room_id)
    if (not snapshot.room.enabled or snapshot.valid_until <= now
            or snapshot.synced_at > now + timedelta(seconds=10) or not isinstance(evidence, dict)
            or evidence.get('app_scope') != app_scope()
            or evidence.get('snapshot_at') != snapshot.synced_at.isoformat()
            or evidence.get('valid_until') != snapshot.valid_until.isoformat()
            or datetime.fromisoformat(evidence['valid_until']) <= now):
        raise CalendarEvidenceError('source_stale')
    ident = occurrence.identity(room_id)
    overlaps = [e for e in snapshot.events if e.start_time < occurrence.end_time and e.end_time > occurrence.start_time]
    if len(overlaps) != 1 or Occurrence.model_validate(overlaps[0].model_dump()).identity(room_id) != ident:
        raise CalendarEvidenceError('event_changed')
    organizers = evidence.get('organizers')
    if not isinstance(organizers, dict) or ident not in organizers:
        raise CalendarEvidenceError('source_stale')
    # Only currently monitored candidates need directory lookup; cap batch size.
    nearby = [Occurrence.model_validate(e.model_dump()).identity(room_id) for e in snapshot.events
              if e.end_time > now and e.start_time <= now + timedelta(minutes=30)]
    selected = [organizers[ident]] + [organizers.get(i) for i in nearby if i != ident]
    return organizers[ident], list(dict.fromkeys(u for u in selected if u))[:50]
