"""Mock HTTP, real connector/collector/Redis/state machine/readback as one chain."""
import json
from datetime import datetime, timedelta

import httpx
import pytest

from app.core.config import settings
from app.schemas.room_usage import Occurrence, UsageHeartbeat
from app.services import room_usage as service
from app.services import room_usage_autoverify, room_usage_readback
from app.services import room_usage_worker as worker
from app.services.meeting_rooms import refresh_batch
from app.services.room_display_collector import cached_schedule
from app.services.room_usage_health import heartbeat
from tests.services import test_room_usage as support
from tests.services.test_calendar_evidence_transport import client_for
from tests.services.test_room_usage_autoverify import auto_policy, detail, enable

redis_socket = support.redis_socket
setup_usage = support.setup_usage


@pytest.mark.asyncio
@pytest.mark.parametrize('organizer,sign,recurrence', [
    (user, sign, '') for user in ['ou_a', 'ou_b', 'ou_new_c'] for sign in [True, False]
] + [('ou_a', False, 'FREQ=' + frequency) for frequency in ['DAILY', 'WEEKLY', 'MONTHLY']])
async def test_collector_to_release_with_real_http_contracts(setup_usage, monkeypatch, organizer, sign, recurrence):
    store, _, _, actor, policy, now, snapshot, epoch = setup_usage
    enable(monkeypatch)
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_ORGANIZER_SOURCE_ROOM_IDS', {'omm_one'})
    old_request = await support.request_for(store, now)
    await service.command(store, 'omm_one', actor, old_request, 'confirm', now)
    policy.update(grace_minutes=1, release_delay_seconds=0)
    await auto_policy(store, policy)
    occurrence = Occurrence.model_validate(snapshot.events[0].model_dump()).model_copy(update={
        'uid': 'new-booking', 'start_time': now + timedelta(seconds=20), 'end_time': now + timedelta(minutes=20)})
    row = {**occurrence.model_dump(mode='json'), 'organizer_info': {'open_id': organizer, 'name': '测试组织者'}}
    ident = occurrence.identity('omm_one')
    calendar = 'primary-' + organizer
    requests, writes = [], []
    released = False
    at = now

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return at

    for module in [worker, service, room_usage_autoverify, room_usage_readback]:
        monkeypatch.setattr(module, 'datetime', Clock)
    monkeypatch.setattr(service, 'cached_schedule', cached_schedule)

    def response(request):
        nonlocal released
        path = request.url.path
        requests.append(path)
        if path.endswith('/meeting_room/freebusy/batch_get'):
            data = {'free_busy': {'omm_one': [] if released else [row]}, 'error_room_ids': [],
                    'time_min': request.url.params['time_min'], 'time_max': request.url.params['time_max']}
        elif path.endswith('/meeting_room/summary/batch_get'):
            data = {'EventInfos': [{'uid': occurrence.uid, 'original_time': 0, 'summary': '测试预约'}]}
        elif path.endswith('/calendars/primarys'):
            assert json.loads(request.content) == {'user_ids': [organizer]}
            data = {'calendars': [{'user_id': organizer, 'calendar': {'calendar_id': calendar, 'type': 'primary'}}]}
        elif '/calendars/test-calendar/' in path:
            return httpx.Response(404, json={'code': 193001, 'msg': 'private upstream content'})
        elif path.endswith('/instances'):
            data = {'has_more': False, 'items': [detail(occurrence, event_id=f'{occurrence.uid}_{int(occurrence.start_time.timestamp())}')]}
        elif '/events/' in path:
            assert '/calendars/' + calendar + '/' in path
            data = {'event': detail(occurrence, recurrence=recurrence, organizer_calendar_id=calendar)}
        elif path.endswith('/meeting_room/instance/reply'):
            writes.append(json.loads(request.content))
            released = True
            data = {}
        else:
            raise AssertionError('Unexpected fixture endpoint')
        return httpx.Response(200, json={'code': 0, 'data': data})

    client = client_for(monkeypatch, response)
    try:
        assert await refresh_batch(store.cache, client, [snapshot.room], now, fresh_seconds=300) == 1
        assert (await store.get('sources:omm_one'))['organizers'][ident] == organizer
        for second in range(0, 116, 5):
            at = now + timedelta(seconds=second)
            state = await service.view(store, 'omm_one', at)
            record = state['record'] or {}
            await heartbeat(store, 'omm_one', actor, UsageHeartbeat(
                protocol=2, session_id='a' * 32, occurrence_id=state['target_id'],
                monitored_occurrence_ids=state['monitored_occurrence_ids'], policy_revision=policy['revision'],
                operation_state='ready', challenge_id=record.get('challenge_id') if record.get('state') == 'checking' else None), at)
            await worker.tick_room(store, client, 'omm_one', epoch, at)
            if second == 10:
                public = json.dumps(await service.view(store, 'omm_one', at))
                assert organizer not in public and calendar not in public and '_calendar_source' not in public
            if sign and second == 30:
                await service.command(store, 'omm_one', actor, await support.request_for(store, at), 'confirm', at)
        record = await store.get('record:' + ident)
        assert record['state'] == ('confirmed' if sign else 'released')
        assert record['verified'] and record['_calendar_source']['organizer'] == organizer
        assert record['deadline'] == (occurrence.start_time + timedelta(minutes=1)).isoformat()
        assert (await store.get('record:' + old_request.occurrence_id))['state'] == 'confirmed'
        assert len(writes) == (0 if sign else 1)
        assert sum(p.endswith('/primarys') for p in requests) == 1
        if not sign:
            assert writes[0] == {'room_id': 'omm_one', 'uid': occurrence.uid, 'status': 'NOT_CHECK_IN',
                                 'original_time': int(occurrence.start_time.timestamp()) if recurrence else 0}
            assert (await cached_schedule('omm_one')).events == []
            assert (await store.get('sources:omm_one'))['organizers'] == {}
            assert sum(p.endswith('/freebusy/batch_get') for p in requests) == 3
    finally:
        await client.close()
