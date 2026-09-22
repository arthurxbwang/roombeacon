"""Recurring replies must select one positive timestamp and preserve later instances."""
from datetime import timedelta

import httpx
import pytest

from app.core.config import settings
from app.core.exceptions import AppError
from app.room_display_main import app
from app.schemas.room_usage import VerifiedOccurrence, VerifiedRecurringOccurrence
from app.services import room_usage as service
from app.services import room_usage_worker as worker
from tests.services import test_room_usage as support

redis_socket = support.redis_socket
setup_usage = support.setup_usage


def series(snapshot):
    first = snapshot.events[0]
    second = first.model_copy(update={'original_time': 0, 'start_time': first.start_time + timedelta(days=1),
                                      'end_time': first.end_time + timedelta(days=1)})
    snapshot.events.append(second)
    return first, second


@pytest.mark.asyncio
async def test_known_series_cannot_be_registered_as_non_recurring(setup_usage):
    store, _, _, _, _, now, snapshot, _ = setup_usage
    series(snapshot)
    request = await support.request_for(store, now)
    with pytest.raises(AppError):
        await service.verify_occurrence(store, 'omm_one', VerifiedOccurrence(
            occurrence_id=request.occurrence_id, policy_revision=request.policy_revision, non_recurring_verified=True))


@pytest.mark.asyncio
async def test_recurring_registration_resolves_positive_instance_time(setup_usage):
    store, _, _, _, _, now, snapshot, _ = setup_usage
    first, _ = series(snapshot)
    request = await support.request_for(store, now)
    result = await service.verify_occurrence(store, 'omm_one', VerifiedRecurringOccurrence(
        occurrence_id=request.occurrence_id, policy_revision=request.policy_revision, recurring_verified=True))
    record = result['record']
    assert record['release_scope'] == 'recurring_instance'
    assert record['release_original_time'] == int(first.start_time.timestamp()) > 0
    assert record['occurrence']['original_time'] == 0
    assert record['verified']


@pytest.mark.asyncio
async def test_unknown_single_zero_instance_cannot_use_recurring_registration(setup_usage):
    store, _, _, _, _, now, _, _ = setup_usage
    request = await support.request_for(store, now)
    with pytest.raises(AppError):
        await service.verify_occurrence(store, 'omm_one', VerifiedRecurringOccurrence(
            occurrence_id=request.occurrence_id, policy_revision=request.policy_revision, recurring_verified=True))


@pytest.mark.asyncio
@pytest.mark.parametrize('condition', ['ok', 'future_missing', 'target_retained', 'series_evidence_lost', 'wrong_timestamp', 'legacy_zero'])
async def test_recurring_dispatch_and_readback_boundaries(setup_usage, monkeypatch, condition):
    store, client, key, old, _, now, snapshot, epoch = await support.make_due(setup_usage, monkeypatch)
    first, second = series(snapshot)
    old.update(release_scope='recurring_instance', release_original_time=int(first.start_time.timestamp()))
    if condition == 'wrong_timestamp': old['release_original_time'] += 60
    if condition == 'legacy_zero': old.pop('release_scope'); old.pop('release_original_time')
    await store.put(key, old)
    await store.cache.set('rooms:snapshot:omm_one', snapshot.model_dump_json())
    before = [e.model_dump(mode='json') for e in snapshot.events]
    after = [second.model_dump(mode='json')]
    if condition == 'series_evidence_lost': before = before[:1]
    if condition == 'future_missing': after = []
    if condition == 'target_retained': after = before
    client.freebusy.side_effect = [{'free_busy': {'omm_one': before}}, {'free_busy': {'omm_one': after}}]
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    result = await store.get(key)
    if condition in {'series_evidence_lost', 'wrong_timestamp', 'legacy_zero'}:
        assert result['state'] == 'blocked'
        client.release.assert_not_called()
    else:
        client.release.assert_awaited_once()
        assert client.release.call_args.args[1].original_time == int(first.start_time.timestamp()) > 0
        assert result['state'] == ('released' if condition == 'ok' else 'uncertain')
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    assert client.release.await_count <= 1


@pytest.mark.asyncio
async def test_recurring_verify_requires_admin_and_rejects_mixed_attestation(setup_usage):
    store, _, token, _, _, now, snapshot, _ = setup_usage
    series(snapshot)
    request = await support.request_for(store, now)
    body = {'occurrence_id': request.occurrence_id, 'policy_revision': request.policy_revision, 'recurring_verified': True}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as http:
        url = '/api/room-control/usage/omm_one/verify'
        assert (await http.post(url, json=body)).status_code == 401
        assert (await http.post(url, json=body, headers={'Authorization': 'Bearer ' + token})).status_code == 401
        headers = {'Authorization': 'Bearer ' + settings.ROOM_DISPLAY_CONTROL_TOKEN}
        assert (await http.post(url, json={**body, 'non_recurring_verified': True}, headers=headers)).status_code == 422
        assert (await http.post(url, json=body, headers=headers)).status_code == 200


@pytest.mark.parametrize('original,start_delta', [(1770000000, 3600), (1780000000, -86400)])
def test_rescheduled_exception_keeps_original_start(original, start_delta):
    from datetime import UTC, datetime

    from app.schemas.room_usage import Occurrence
    from app.services.room_usage_recurrence import release_target

    start = datetime.fromtimestamp(original + start_delta, UTC)
    event = Occurrence(uid='exception', original_time=original, start_time=start, end_time=start + timedelta(hours=1))
    target = release_target({'release_scope': 'recurring_instance', 'release_original_time': original}, event, [event])
    assert target.original_time == original
    assert target.original_time != int(start.timestamp())


@pytest.mark.asyncio
async def test_signing_one_occurrence_does_not_sign_same_series_next_day(setup_usage):
    store, client, _, actor, _, now, snapshot, _ = setup_usage
    _, next_day = series(snapshot)
    request = await support.request_for(store, now)
    await service.command(store, 'omm_one', actor, request, 'confirm', now)
    next_id = worker.Occurrence.model_validate(next_day.model_dump()).identity('omm_one')
    assert (await store.get('record:' + request.occurrence_id))['state'] == 'confirmed'
    assert await store.get('record:' + next_id) is None
    client.release.assert_not_called()
