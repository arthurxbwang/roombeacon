import httpx
import pytest

from app.connectors.feishu.room_release import FeishuRoomReleaseClient, ReleaseRejected
from app.schemas.room_usage import Occurrence


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['ok', 'timeout', '401', '429', '500', 'business', 'malformed'])
async def test_write_transport_never_retries_or_leaks_body(failure):
    requests = []

    def respond(request):
        requests.append(request)
        if failure == 'timeout': raise httpx.ReadTimeout('fixture')
        if failure.isdigit(): return httpx.Response(int(failure), text='private upstream body')
        if failure == 'business': return httpx.Response(200, json={'code': 105003, 'msg': 'private upstream body'})
        if failure == 'malformed': return httpx.Response(200, json={'code': '0'})
        return httpx.Response(200, json={'code': 0})

    client = FeishuRoomReleaseClient()
    client._tenant_token = 'fixture'
    import time
    client._token_expires = time.time() + 60
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    occurrence = Occurrence(uid='fixture', original_time=0, start_time='2026-09-20T10:00:00Z', end_time='2026-09-20T11:00:00Z')
    try:
        if failure == 'ok':
            await client.release('omm_fixture', occurrence, 'NOT_CHECK_IN')
        else:
            with pytest.raises((httpx.HTTPError, ReleaseRejected, ValueError, TypeError)):
                await client.release('omm_fixture', occurrence, 'NOT_CHECK_IN')
        assert len(requests) == 1
        assert requests[0].url.path.endswith('/meeting_room/instance/reply')
        with pytest.raises(ValueError):
            await client.release('omm_fixture', occurrence, 'ACCEPTED_BY_ADMIN')
        assert len(requests) == 1
    finally:
        await client.close()
