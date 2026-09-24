"""Atomic batch authoring; device acknowledgements remain individually observable."""
from fastapi import APIRouter, Request

from ..core.exceptions import AppError
from ..core.response import ok
from ..services.room_display_collector import cached_directory
from .catalog_models import DeploymentBatch, DeployRequest
from .deployments import commit_deployment, prepare
from .devices import conflict, get_row
from .security import actor
from .store import database

router = APIRouter(prefix='/api/v6/admin')


def validate_batch(db, body):
    targets = [get_row(db, identity) for identity in body.devices]
    for device in targets:
        if device['revision'] != body.devices[device['id']]:
            raise conflict()
        if device['status'] != 'active' or not device['room_id']:
            raise AppError(422, '批量部署仅支持已绑定会议室的设备', 422)
        room = db.execute('SELECT revision FROM room_configurations WHERE room_id=?', (device['room_id'],)).fetchone()
        if body.room_revisions.get(device['room_id']) != (room['revision'] if room else 0):
            raise conflict()
    return targets


def request_for(db, body, identity):
    device = get_row(db, identity)
    room = db.execute('SELECT * FROM room_configurations WHERE room_id=?', (device['room_id'],)).fetchone()
    return DeployRequest(**body.model_dump(exclude={'devices', 'room_revisions'}),
                         device_id=identity, expected_revision=device['revision'], room_id=device['room_id'],
                         expected_room_revision=room['revision'] if room else 0,
                         control_device=not room or room['controller_id'] == identity)


@router.post('/deployment-batches/preview')
async def preview(body: DeploymentBatch, request: Request):
    actor(request, write=True)
    rooms = await cached_directory()
    with database() as db:
        targets = validate_batch(db, body)
        affected = {}
        for device in targets:
            room, _, _, prepared, _ = prepare(db, request_for(db, body, device['id']), rooms)
            for d, hw, _ in prepared:
                affected[d['id']] = {'code': d['code'], 'room_name': room.get('name', room['room_id']), 'hardware': hw['name']}
        return ok({'devices': list(affected.values()), 'selected_count': len(targets)})


@router.post('/deployment-batches')
async def publish(body: DeploymentBatch, request: Request):
    user = actor(request, write=True)
    rooms = await cached_directory()
    with database() as db:
        targets = validate_batch(db, body)
        results = []
        for device in targets:
            results.append(commit_deployment(db, request_for(db, body, device['id']), rooms, user))
        return ok({'updated': len(targets), 'results': results})
