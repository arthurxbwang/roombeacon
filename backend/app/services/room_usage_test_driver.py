"""Own-calendar test fixtures only; single-attempt writes and a durable local ledger."""
import argparse
import asyncio
import json
import os
import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from ..connectors.feishu.room_release import FeishuRoomReleaseClient

TEST_ROOM = 'omm_d42ad8a9e50c5ddf9d60fe3d3bc6473b'
CALENDAR_NAME = 'RoomBeacon-Automation-IT灯塔-Test'
RULES = {'none': '', 'daily': 'FREQ=DAILY;COUNT=3',
         'weekly': 'FREQ=WEEKLY;COUNT=3', 'monthly': 'FREQ=MONTHLY;COUNT=3'}


class FixtureDriverError(Exception):
    def __init__(self, stage, code=None):
        self.stage, self.code = stage, code
        super().__init__(stage)


class FixtureDriver:
    def __init__(self, client, ledger_path):
        self.client = client
        self.path = Path(ledger_path)
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {'calendar_id': None, 'cases': {}}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + '.tmp')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as handle:
            json.dump(self.data, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.path)
        os.chmod(self.path, 0o600)

    async def write(self, method, path, body=None, params=None):
        token = await self.client._get_tenant_token()
        http = await self.client._get_client()
        response = await http.request(method, 'https://open.feishu.cn/open-apis/calendar/v4/' + path,
                                      headers={'Authorization': 'Bearer ' + token}, json=body, params=params, timeout=15)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get('code') != 0:
            raise FixtureDriverError('calendar_write_rejected', payload.get('code') if isinstance(payload, dict) else None)
        return payload.get('data', {})

    def base(self):
        value = self.data.get('calendar_id')
        if not isinstance(value, str) or not value:
            raise FixtureDriverError('initialize_test_calendar_first')
        return 'calendars/' + quote(value, safe='')

    async def preflight(self):
        data = await self.client.calendar_read(self.base())
        calendar = data.get('calendar', data)
        if (calendar.get('type') != 'shared' or calendar.get('role') not in {'owner', 'writer'}
                or calendar.get('summary') != CALENDAR_NAME):
            raise FixtureDriverError('calendar_must_be_dedicated_writable_test_calendar')
        return {'calendar_ready': True, 'room_id': TEST_ROOM}

    async def initialize(self, calendar_id=None):
        if self.data.get('initializing'):
            raise FixtureDriverError('prior_calendar_creation_uncertain_review_before_retry')
        if self.data.get('calendar_id'):
            return await self.preflight()
        if calendar_id:
            self.data['calendar_id'] = calendar_id
            result = await self.preflight()
            self.save()
            return result
        self.data['initializing'] = True
        self.save()
        result = await self.write('POST', 'calendars', {
            'summary': CALENDAR_NAME, 'permissions': 'private',
            'description': '仅用于IT灯塔-Test自动化验收，不邀请业务人员。'})
        calendar = result.get('calendar', {})
        if not calendar.get('calendar_id'):
            raise FixtureDriverError('calendar_creation_response_incomplete')
        self.data.update(calendar_id=calendar['calendar_id'], initializing=False)
        self.save()
        return await self.preflight()

    @staticmethod
    def times(start, duration):
        if start.tzinfo is None or start < datetime.now(UTC) + timedelta(minutes=20):
            raise FixtureDriverError('start_requires_timezone_and_twenty_minute_lead')
        if not 15 <= duration <= 60:
            raise FixtureDriverError('duration_must_be_15_to_60_minutes')
        return {'start_time': {'timestamp': str(int(start.timestamp())), 'timezone': 'Asia/Shanghai'},
                'end_time': {'timestamp': str(int((start + timedelta(minutes=duration)).timestamp())), 'timezone': 'Asia/Shanghai'}}

    async def create(self, case, start, duration=30, repeat='none'):
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,48}', case) or repeat not in RULES:
            raise FixtureDriverError('invalid_case_or_repeat')
        if case in self.data['cases']:
            raise FixtureDriverError('case_exists_inspect_before_retry')
        times = self.times(start, duration)
        await self.preflight()
        record = {'repeat': repeat, 'stage': 'creating', 'idempotency_key': str(uuid.uuid4()), 'times': times}
        self.data['cases'][case] = record
        self.save()
        data = await self.write('POST', self.base() + '/events', {
            'summary': 'RoomBeacon-Test-' + case, 'description': '自动化测试预约，仅用于专用测试房间。',
            'need_notification': False, 'recurrence': RULES[repeat], **times},
            {'idempotency_key': record['idempotency_key']})
        event_id = data.get('event', {}).get('event_id')
        if not isinstance(event_id, str) or not event_id.endswith('_0'):
            raise FixtureDriverError('event_creation_response_incomplete')
        record.update(event_id=event_id, stage='adding_room')
        self.save()
        await self.write('POST', self.base() + '/events/' + quote(event_id, safe='') + '/attendees',
                         {'attendees': [{'type': 'resource', 'room_id': TEST_ROOM}],
                          'need_notification': False, 'is_enable_admin': False})
        record['stage'] = 'awaiting_room_acceptance'
        self.save()
        return {'case': case, 'stage': record['stage'], 'room_id': TEST_ROOM}

    def owned(self, case):
        record = self.data['cases'].get(case)
        if not record or not record.get('event_id'):
            raise FixtureDriverError('only_ledger_owned_events_may_be_modified')
        return record

    async def instances(self, case, start, end):
        record = self.owned(case)
        await self.preflight()
        if start.tzinfo is None or end.tzinfo is None or not timedelta(0) < end - start <= timedelta(days=100):
            raise FixtureDriverError('invalid_instance_query_window')
        if record['repeat'] == 'none':
            return [await self.client.calendar_event(self.data['calendar_id'], record['event_id'])]
        return await self.client.calendar_instances(self.data['calendar_id'], record['event_id'], start, end)

    async def target(self, case, original):
        record = self.owned(case)
        if record['repeat'] == 'none':
            if original: raise FixtureDriverError('non_recurring_original_must_be_zero')
            return record, record['event_id']
        if original <= 0:
            raise FixtureDriverError('recurring_write_requires_positive_instance_original')
        uid = record['event_id'].rsplit('_', 1)[0]
        target = f'{uid}_{original}'
        # Read the actual instance before mutation. A guessed timestamp is not enough.
        at = datetime.fromtimestamp(original, UTC)
        events = await self.instances(case, at - timedelta(days=2), at + timedelta(days=2))
        if sum(e.get('event_id') == target and e.get('status') == 'confirmed' for e in events) != 1:
            raise FixtureDriverError('instance_not_found_or_ambiguous')
        return record, target

    async def change(self, case, original=0, start=None, duration=30):
        await self.preflight()
        record, target = await self.target(case, original)
        if record.get('stage') in {'modifying', 'cancelling'}:
            raise FixtureDriverError('prior_write_uncertain_review_before_retry')
        body = {'need_notification': False, **self.times(start, duration)} if start else None
        record['stage'] = 'modifying' if start else 'cancelling'
        self.save()
        await self.write('PATCH' if start else 'DELETE', self.base() + '/events/' + quote(target, safe=''), body)
        record['stage'] = 'changed' if start else 'cancelled'
        self.save()
        return {'case': case, 'stage': record['stage'], 'instance_original': original}

    async def inspect(self, case):
        record = self.owned(case)
        await self.preflight()
        event = await self.client.calendar_event(self.data['calendar_id'], record['event_id'])
        data = await self.client.calendar_read(self.base() + '/events/' + quote(record['event_id'], safe='') + '/attendees')
        if data.get('has_more') or data.get('page_token') or not isinstance(data.get('items'), list):
            raise FixtureDriverError('incomplete_attendees')
        statuses = [e.get('rsvp_status') for e in data['items'] if e.get('type') == 'resource' and e.get('room_id') == TEST_ROOM]
        return {'case': case, 'stage': record['stage'], 'status': event.get('status'),
                'start': event.get('start_time'), 'end': event.get('end_time'),
                'room_accepted': statuses == ['accept'], 'room_statuses': statuses}


async def run(args):
    client = FeishuRoomReleaseClient()
    driver = FixtureDriver(client, args.ledger)
    try:
        if args.command == 'init': return await driver.initialize(args.calendar_id)
        if args.command == 'preflight': return await driver.preflight()
        if args.command == 'create': return await driver.create(args.case, datetime.fromisoformat(args.start), args.minutes, args.repeat)
        if args.command == 'inspect': return await driver.inspect(args.case)
        if args.command == 'instances':
            rows = await driver.instances(args.case, datetime.fromisoformat(args.start), datetime.fromisoformat(args.end))
            return [{'original': int(e['event_id'].rsplit('_', 1)[1]), 'start': e.get('start_time'),
                     'end': e.get('end_time'), 'status': e.get('status')} for e in rows]
        start = datetime.fromisoformat(args.start) if args.command == 'move' else None
        return await driver.change(args.case, args.original, start, getattr(args, 'minutes', 30))
    finally:
        await client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger', required=True, help='Private JSON ledger outside the tracked source tree')
    sub = parser.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init'); init.add_argument('--calendar-id')
    sub.add_parser('preflight')
    for command in ['create', 'inspect', 'instances', 'move', 'cancel']:
        p = sub.add_parser(command); p.add_argument('--case', required=True)
        if command in {'create', 'instances', 'move'}: p.add_argument('--start', required=True)
        if command in {'create', 'move'}: p.add_argument('--minutes', type=int, default=30)
        if command == 'create': p.add_argument('--repeat', choices=RULES, default='none')
        if command == 'instances': p.add_argument('--end', required=True)
        if command in {'move', 'cancel'}: p.add_argument('--original', type=int, default=0)
    args = parser.parse_args()
    try:
        print(json.dumps(asyncio.run(run(args)), ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001 — do not expose request URLs, tokens or calendar bodies.
        print(json.dumps({'error_type': type(exc).__name__, 'stage': getattr(exc, 'stage', None),
                          'code': getattr(exc, 'code', None), 'automatic_write_retry': False}))
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
