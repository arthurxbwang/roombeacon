"""Bounded same-origin PNG resources; device access is scoped to its configuration."""
import base64
import binascii
import hashlib
import struct
import time
import zlib

from fastapi import APIRouter, Request, Response

from ..core.exceptions import AppError
from ..core.response import ok
from .catalog_models import ImageUpload
from .security import DEVICE_COOKIE, actor, authenticate_web
from .store import audit, database

router = APIRouter(prefix='/api/v6')


def png_dimensions(data):
    if not data.startswith(b'\x89PNG\r\n\x1a\n') or len(data) < 45:
        raise ValueError('PNG required')
    width, height = struct.unpack('>II', data[16:24])
    if not (1 <= width <= 4096 and 1 <= height <= 4096):
        raise ValueError('dimensions')
    offset, ended = 8, False
    while offset + 12 <= len(data):
        length = int.from_bytes(data[offset:offset + 4], 'big')
        end = offset + 12 + length
        if end > len(data) or zlib.crc32(data[offset + 4:end - 4]) != int.from_bytes(data[end - 4:end], 'big'):
            raise ValueError('invalid chunk')
        if data[offset + 4:offset + 8] == b'IEND':
            ended = end == len(data)
            break
        offset = end
    if not ended:
        raise ValueError('incomplete PNG')
    return width, height


@router.post('/admin/assets')
def upload(body: ImageUpload, request: Request):
    user = actor(request, write=True)
    try:
        content = base64.b64decode(body.data, validate=True)
        width, height = png_dimensions(content)
    except (ValueError, binascii.Error, struct.error) as exc:
        raise AppError(422, '请上传完整 PNG 图片，宽高均不超过 4096 像素', 422) from exc
    identity = hashlib.sha256(content).hexdigest()
    with database() as db:
        db.execute('INSERT OR IGNORE INTO configuration_assets VALUES (?,?,?,?,?)',
                   (identity, body.name, 'image/png', content, int(time.time())))
        audit(db, user['subject'], 'asset-upload', identity, {'target_name': body.name, 'width': width, 'height': height})
    return ok({'id': identity, 'width': width, 'height': height})


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
