"""Authenticated catalog authoring and publishing. Never contacts Feishu."""
import json
import secrets
import time

from fastapi import APIRouter, Request

from ..core.exceptions import AppError
from ..core.response import ok
from .catalog_models import CatalogDraft, HardwareTest
from .catalog_store import encode, template_row, template_view, version_row
from .devices import conflict, get_row
from .models import Revision
from .security import actor
from .store import audit, database

router = APIRouter(prefix='/api/v6/admin/catalog')


@router.get('')
def list_templates(request: Request):
    actor(request)
    with database() as db:
        return ok([template_view(db, row) for row in db.execute('SELECT * FROM config_catalog ORDER BY kind,name')])


@router.post('')
def create(body: CatalogDraft, request: Request):
    user = actor(request, write=True)
    identity = secrets.token_hex(12)
    with database() as db:
        db.execute('INSERT INTO config_catalog VALUES (?,?,?,?,1,0,0,?)',
                   (identity, body.kind, body.name, encode(body.spec), 'manual'))
        audit(db, user['subject'], 'catalog-create', identity, {'target_name': body.name, 'kind': body.kind})
        return ok(template_view(db, template_row(db, identity)))


@router.put('/{identity}')
def edit(identity: str, body: CatalogDraft, request: Request):
    user = actor(request, write=True)
    with database() as db:
        row = template_row(db, identity)
        if row['revision'] != body.expected_revision:
            raise conflict()
        if row['kind'] != body.kind or row['archived']:
            raise AppError(422, '已归档模板不可编辑，模板类型不可更改', 422)
        db.execute('UPDATE config_catalog SET name=?,spec=?,revision=revision+1 WHERE id=?',
                   (body.name, encode(body.spec), identity))
        audit(db, user['subject'], 'catalog-edit', identity,
              {'target_name': body.name, 'before': json.loads(row['spec']), 'after': body.spec})
        return ok(template_view(db, template_row(db, identity)))


@router.post('/{identity}/publish')
def publish(identity: str, body: Revision, request: Request):
    user = actor(request, write=True)
    with database() as db:
        row = template_row(db, identity)
        if row['revision'] != body.expected_revision:
            raise conflict()
        if row['archived']:
            raise AppError(422, '归档模板不可发布', 422)
        spec = json.loads(row['spec'])
        for key in ('background_day', 'background_night'):
            if spec.get(key) and not db.execute('SELECT 1 FROM configuration_assets WHERE id=?', (spec[key],)).fetchone():
                raise AppError(422, '背景资源不存在，请重新上传', 422)
        version = row['published_version'] + 1
        db.execute('INSERT INTO config_versions VALUES (?,?,?,?,?,?)',
                   (identity, version, row['name'], row['spec'], user['subject'], int(time.time())))
        db.execute('UPDATE config_catalog SET published_version=?,revision=revision+1 WHERE id=?', (version, identity))
        audit(db, user['subject'], 'catalog-publish', identity, {'target_name': row['name'], 'version': version})
        return ok(template_view(db, template_row(db, identity)))


@router.post('/{identity}/archive')
def archive(identity: str, body: Revision, request: Request):
    user = actor(request, write=True)
    with database() as db:
        row = template_row(db, identity)
        if row['revision'] != body.expected_revision:
            raise conflict()
        linked = db.execute('SELECT 1 FROM device_installations WHERE hardware_id=?', (identity,)).fetchone()
        linked = linked or db.execute('SELECT 1 FROM room_configurations WHERE software_id=?', (identity,)).fetchone()
        if linked:
            raise AppError(422, '仍有设备或会议室使用，解除关联后才能归档', 422)
        db.execute('UPDATE config_catalog SET archived=1,revision=revision+1 WHERE id=?', (identity,))
        audit(db, user['subject'], 'catalog-archive', identity, {'target_name': row['name']})
    return ok({'archived': True})


@router.post('/{identity}/tests')
def record_test(identity: str, body: HardwareTest, request: Request):
    user = actor(request, write=True)
    with database() as db:
        version = version_row(db, identity, body.version, 'hardware')
        device = get_row(db, body.device_id)
        value = body.model_dump() | {'metadata': json.loads(device['metadata']), 'device_code': device['code']}
        if body.result == 'passed' and not (body.colors and body.off and body.orientation):
            raise AppError(422, '通过记录需完成灯色、全灭与安装方向核验', 422)
        db.execute('INSERT INTO hardware_tests VALUES (?,?,?,?,?,?,?)',
                   (secrets.token_hex(12), identity, body.version, body.device_id,
                    encode(value), user['subject'], int(time.time())))
        audit(db, user['subject'], 'hardware-test', identity,
              {'target_name': version['name'], 'device_code': device['code'], 'version': body.version,
               'result': body.result, 'notes': body.notes})
    return ok({'recorded': True})
