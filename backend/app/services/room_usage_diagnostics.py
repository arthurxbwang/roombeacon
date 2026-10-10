"""Admin-only recent verification issues; bounded reads, no private source proof."""
from datetime import UTC, datetime, timedelta


async def verification_issues(store, room_id, audit):
    seen, result = set(), []
    cutoff = datetime.now(UTC) - timedelta(days=1)
    for row in audit:
        ident = row.get('occurrence_id')
        if not ident or ident in seen or not row.get('verification_error'):
            continue
        seen.add(ident)
        record = await store.get('record:' + ident)
        if (record and record.get('room_id') == room_id and record.get('verification_error')
                and record['state'] in {'pending', 'blocked', 'waiting', 'checking'}
                and datetime.fromisoformat(record.get('verification_failed_at', row['time'])) >= cutoff):
            result.append({k: record[k] for k in (
                'id', 'occurrence', 'state', 'reason', 'verification_error', 'verification_http_status',
                'verification_code', 'verification_failures', 'verification_failed_at') if k in record})
        if len(seen) >= 10:
            break
    return result
