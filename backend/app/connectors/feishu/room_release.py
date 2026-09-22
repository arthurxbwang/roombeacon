"""Single-attempt release transport: never automatically retry an ambiguous write."""
from .calendar_read import CalendarReadMixin
from .rooms import FeishuRoomsClient


class ReleaseRejected(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__('Feishu rejected room release')


class FeishuRoomReleaseClient(CalendarReadMixin, FeishuRoomsClient):
    async def release(self, room_id, occurrence, status):
        if status not in {'NOT_CHECK_IN', 'ENDED_BEFORE_DUE'}:
            raise ValueError('Unsupported room release status')
        token = await self._get_tenant_token()
        client = await self._get_client()
        response = await client.post(
            'https://open.feishu.cn/open-apis/meeting_room/instance/reply',
            headers={'Authorization': f'Bearer {token}'},
            json={'room_id': room_id, 'uid': occurrence.uid,
                  'original_time': occurrence.original_time, 'status': status}, timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get('code'), int):
            raise TypeError('Invalid release response')
        if payload['code'] != 0:
            raise ReleaseRejected(payload['code'])
