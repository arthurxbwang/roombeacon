"""Bounded calendar evidence reads; never log private calendar/event paths."""
from urllib.parse import quote

from .calendar_errors import CalendarEvidenceError, evidence_error, response_error


class CalendarReadMixin:
    async def calendar_read(self, path, *, params=None):
        return await self._calendar_request('GET', path, params=params)

    async def _calendar_request(self, method, path, **kwargs):
        try:
            token = await self._get_tenant_token()
            client = await self._get_client()
            response = await client.request(method, 'https://open.feishu.cn/open-apis/calendar/v4/' + path,
                                            headers={'Authorization': f'Bearer {token}'}, timeout=4, **kwargs)
        except Exception as exc:  # noqa: BLE001 — sanitize token/transport exceptions before crossing the boundary.
            raise evidence_error(exc) from None
        retry = response.headers.get('Retry-After', '')
        retry_after = int(retry) if retry.isdecimal() else 0
        try:
            payload = response.json()
        except ValueError:
            raise response_error(response.status_code, None, retry_after) from None
        code = payload.get('code') if isinstance(payload, dict) else None
        if type(code) is not int:
            raise response_error(response.status_code, None, retry_after)
        if response.status_code != 200 or code != 0:
            raise response_error(response.status_code, code, retry_after)
        if not isinstance(payload.get('data'), dict):
            raise CalendarEvidenceError('invalid_response')
        return payload['data']

    async def primary_calendars(self, user_ids):
        """Read-only batch lookup; response must correspond to the exact requested users."""
        import re
        ids = sorted(set(user_ids))
        if not 1 <= len(ids) <= 50 or any(not re.fullmatch(r'ou_[A-Za-z0-9_-]{1,128}', u) for u in ids):
            raise CalendarEvidenceError('source_unresolved')
        data = await self._calendar_request('POST', 'calendars/primarys',
                                            params={'user_id_type': 'open_id'}, json={'user_ids': ids})
        rows = data.get('calendars')
        if not isinstance(rows, list):
            raise CalendarEvidenceError('invalid_response')
        result = {}
        for row in rows:
            if not isinstance(row, dict) or row.get('user_id') not in ids or row['user_id'] in result:
                raise CalendarEvidenceError('invalid_response')
            calendar = row.get('calendar')
            if (not isinstance(calendar, dict) or calendar.get('type') != 'primary'
                    or not isinstance(calendar.get('calendar_id'), str) or not calendar['calendar_id']):
                raise CalendarEvidenceError('invalid_response')
            result[row['user_id']] = calendar['calendar_id']
        return result

    async def calendar_event(self, calendar_id, event_id):
        path = f'calendars/{quote(calendar_id, safe="")}/events/{quote(event_id, safe="")}'
        data = await self.calendar_read(path)
        if not isinstance(data.get('event'), dict):
            raise TypeError('Missing calendar event')
        return data['event']

    async def calendar_instances(self, calendar_id, event_id, start, end):
        path = f'calendars/{quote(calendar_id, safe="")}/events/{quote(event_id, safe="")}/instances'
        params = {'start_time': str(int(start.timestamp()) - 1), 'end_time': str(int(end.timestamp()) + 1)}
        data = await self.calendar_read(path, params=params)
        if data.get('has_more') or data.get('page_token') or not isinstance(data.get('items'), list):
            raise ValueError('Incomplete calendar instances')
        return data['items']
