"""Bounded same-origin image resources; device access is scoped to its configuration."""
import base64
import binascii
import hashlib
import time

from fastapi import APIRouter, Request, Response

from ..core.exceptions import AppError
from ..core.response import ok
from .catalog_models import ImageUpload
from .image_validation import stored_image_metadata, validate_image
from .security import DEVICE_COOKIE, actor, authenticate_web
from .store import audit, database

router = APIRouter(prefix='/api/v6')


@router.post('/admin/assets')
def upload(body: ImageUpload, request: Request):
    user = actor(request, write=True)
    try:
        content = base64.b64decode(body.data, validate=True)
        metadata = validate_image(content)
    except (ValueError, binascii.Error) as exc:
        raise AppError(422, '请上传完整的静态 PNG、JPEG 或 WebP 图片，原文件不超过 3 MB，宽高均不超过 4096 像素', 422) from exc
    identity = hashlib.sha256(content).hexdigest()
    with database() as db:
        db.execute('INSERT OR IGNORE INTO configuration_assets VALUES (?,?,?,?,?)',
                   (identity, body.name, metadata['mime'], content, int(time.time())))
        audit(db, user['subject'], 'asset-upload', identity, {'target_name': body.name} | metadata)
    return ok({'id': identity} | metadata)


@router.get('/admin/assets/{identity}')
def metadata(identity: str, request: Request):
    actor(request)
    with database() as db:
        row = db.execute('SELECT name,mime,content FROM configuration_assets WHERE id=?', (identity,)).fetchone()
        if not row:
            raise AppError(404, '资源不存在', 404)
    try:
        details = stored_image_metadata(row['content'], row['mime'])
    except ValueError as exc:
        raise AppError(422, '背景图片元数据无法读取，请重新上传完整图片', 422) from exc
    return ok({'id': identity, 'name': row['name']} | details)


@router.get('/assets/{identity}')
def image(identity: str, request: Request):
    if request.cookies.get(DEVICE_COOKIE):
        user = authenticate_web(request.cookies[DEVICE_COOKIE])
        preferences = user['display_preferences']
        if identity not in (preferences.get('background_day'), preferences.get('background_night')):
            raise AppError(403, '设备无权读取此资源', 403)
    else:
        actor(request)
    with database() as db:
        row = db.execute('SELECT mime,content FROM configuration_assets WHERE id=?', (identity,)).fetchone()
        if not row:
            raise AppError(404, '资源不存在', 404)
        return Response(row['content'], media_type=row['mime'], headers={'X-Content-Type-Options': 'nosniff'})
