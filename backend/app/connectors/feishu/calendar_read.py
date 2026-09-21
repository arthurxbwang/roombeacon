"""Bounded calendar evidence reads; never log private calendar/event paths."""
from urllib.parse import quote

from ...core.exceptions import ExternalAPIError


class CalendarReadMixin:
    async def calendar_read(self, path, *, params=None):
        token = await self._get_tenant_token()
        client = await self._get_client()
        response = await client.get('https://open.feishu.cn/open-apis/calendar/v4/' + path,
                                    headers={'Authorization': 'Bearer ' + token}, params=params, timeout=4)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get('code') != 0 or not isinstance(payload.get('data'), dict):
            raise ExternalAPIError('feishu', 'Calendar evidence unavailable')
        return payload['data']

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
