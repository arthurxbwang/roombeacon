"""Original background bytes, bounded decoding and unchanged resource authorization."""
import base64
import hashlib
import struct
import zlib
from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from app.management.security import DEVICE_COOKIE
from app.management.store import database

from . import test_v6_management as v6
from .test_configuration_catalog import create, publish

client = v6.client
UPLOAD = '/api/v6/admin/assets'
FORMATS = [('PNG', 'image/png'), ('JPEG', 'image/jpeg'), ('WEBP', 'image/webp')]
JPEG_TRAILERS = [b'\n', b'\0' * 4, b'\xff\xfe\0\x06note']


def picture(kind='PNG', size=(12, 9), **options):
    output = BytesIO()
    Image.new('RGB', size, (90, 140, 210)).save(output, format=kind, **options)
    return output.getvalue()


def upload(client, data, name='background.png', headers=None):
    return client.post(UPLOAD, headers=v6.admin() if headers is None else headers,
                       json={'name': name, 'data': base64.b64encode(data).decode()})


def chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))


@pytest.mark.parametrize(('kind', 'mime'), FORMATS)
def test_original_bytes_metadata_and_sha_identity(client, kind, mime):
    content = picture(kind)
    # The file name cannot select its format or MIME type.
    result = upload(client, content, 'incorrect-extension.svg')
    assert result.status_code == 200, result.text
    identity = hashlib.sha256(content).hexdigest()
    assert result.json()['data'] == {'id': identity, 'mime': mime, 'size': len(content),
                                     'width': 12, 'height': 9}
    response = client.get('/api/v6/assets/' + identity, headers=v6.admin())
    assert response.status_code == 200
    assert response.headers['content-type'] == mime
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.content == content
    assert upload(client, content, 'repeat.jpeg').json()['data']['id'] == identity
    with database() as db:
        row = db.execute('SELECT mime,content FROM configuration_assets WHERE id=?', (identity,)).fetchone()
        assert tuple(row) == (mime, content)
        assert db.execute('SELECT COUNT(*) FROM configuration_assets').fetchone()[0] == 1


@pytest.mark.parametrize(('kind', 'mime'), FORMATS)
def test_asset_read_remains_scoped_to_assigned_active_device(client, monkeypatch, kind, mime):
    from app.management import deployments

    content = picture(kind)
    identity = upload(client, content).json()['data']['id']
    path = '/api/v6/assets/' + identity
    assert client.get(path).status_code == 401
    assert client.get(path, headers={'Authorization': 'Bearer invalid'}).status_code == 401
    assert client.get('/api/v6/assets/' + 'a' * 64, headers=v6.admin()).status_code == 404
    monkeypatch.setattr(deployments, 'cached_directory', AsyncMock(return_value=[
        {'room_id': v6.ROOM, 'name': '测试'}]))
    token, device = v6.enroll(client)
    hardware = publish(client, create(client, 'hardware'))
    software = publish(client, create(client, spec={'background_day': identity}))
    body = {'device_id': device['id'], 'expected_revision': 1, 'room_id': v6.ROOM,
            'hardware_id': hardware['id'], 'hardware_version': 1, 'software_id': software['id'],
            'software_version': 1, 'expected_room_revision': 0}
    assert client.post('/api/v6/admin/deployments', headers=v6.admin(), json=body).status_code == 200
    client.cookies.set(DEVICE_COOKIE, v6.web_cookie(client, token)['web_session'])
    response = client.get(path)
    assert response.status_code == 200
    assert response.content == content and response.headers['content-type'] == mime
    assert client.get('/api/v6/assets/' + 'a' * 64).status_code == 403
    assert client.get(UPLOAD + '/' + identity).status_code == 401
    assert upload(client, content, headers={}).status_code == 401
    assert client.post(f"/api/v6/admin/devices/{device['id']}/status", headers=v6.admin(),
                       json={'expected_revision': 2, 'status': 'revoked'}).status_code == 200
    assert client.get(path).status_code == 401


def test_upload_requires_admin_write_and_csrf(client):
    content = picture()
    assert upload(client, content, headers={}).status_code == 401
    me = v6.session(client, 'viewer').json()['data']
    assert upload(client, content, headers={'x-rb-csrf': me['csrf']}).status_code == 403
    with database() as db:
        db.execute("UPDATE users SET role='admin' WHERE subject='user'")
    assert upload(client, content, headers={}).status_code == 403
    assert upload(client, content, headers={'x-rb-csrf': me['csrf'],
                                          'Origin': 'https://other.test'}).status_code == 403
    assert upload(client, content, headers={'x-rb-csrf': me['csrf']}).status_code == 200


@pytest.mark.parametrize(('kind', 'mime'), FORMATS)
def test_saved_metadata_read_requires_management_identity_and_allows_viewer(client, kind, mime):
    content = picture(kind)
    identity = upload(client, content).json()['data']['id']
    path = UPLOAD + '/' + identity
    assert client.get(path).status_code == 401
    expected = {'id': identity, 'name': 'background.png', 'mime': mime, 'size': len(content),
                'width': 12, 'height': 9}
    assert client.get(path, headers=v6.admin()).json()['data'] == expected
    v6.session(client, 'viewer')
    assert client.get(path).json()['data'] == expected
    assert client.get(UPLOAD + '/' + 'a' * 64).status_code == 404


def test_existing_png_resource_and_metadata_remain_readable(client):
    # Resources already inserted by the previous PNG-only uploader keep their identities.
    content = picture()
    identity = hashlib.sha256(content).hexdigest()
    with database() as db:
        db.execute('INSERT INTO configuration_assets VALUES (?,?,?,?,?)',
                   (identity, '旧背景.png', 'image/png', content, 1))
    response = client.get('/api/v6/assets/' + identity, headers=v6.admin())
    assert response.content == content and response.headers['content-type'] == 'image/png'
    metadata = client.get(UPLOAD + '/' + identity, headers=v6.admin()).json()['data']
    assert metadata == {'id': identity, 'name': '旧背景.png', 'mime': 'image/png',
                        'size': len(content), 'width': 12, 'height': 9}


def test_legacy_png_metadata_keeps_the_previous_chunk_contract(client):
    # The old uploader checked chunks only. Reading its saved assets must not start
    # requiring pixel decoding as a side effect of adding a metadata endpoint.
    content = picture()[:33] + chunk(b'IDAT', b'legacy-invalid-pixels') + chunk(b'IEND', b'')
    identity = hashlib.sha256(content).hexdigest()
    with database() as db:
        db.execute('INSERT INTO configuration_assets VALUES (?,?,?,?,?)',
                   (identity, 'legacy.png', 'image/png', content, 1))
    result = client.get(UPLOAD + '/' + identity, headers=v6.admin())
    assert result.status_code == 200
    assert result.json()['data']['size'] == len(content)
    assert client.get('/api/v6/assets/' + identity, headers=v6.admin()).content == content
    assert upload(client, content).status_code == 422


@pytest.mark.parametrize('kind', ['GIF', 'BMP', 'TIFF'])
def test_other_image_formats_rejected_despite_png_file_name(client, kind):
    assert upload(client, picture(kind)).status_code == 422


@pytest.mark.parametrize('content', [b'', b'<svg xmlns="http://www.w3.org/2000/svg"/>', b'not an image'])
def test_non_image_rejected(client, content):
    assert upload(client, content).status_code == 422


@pytest.mark.parametrize('data', ['not base64!', 'AAA', '\u4e2d\u6587'])
def test_invalid_base64_rejected(client, data):
    assert client.post(UPLOAD, headers=v6.admin(), json={'name': 'x', 'data': data}).status_code == 422


@pytest.mark.parametrize('kind', ['PNG', 'JPEG', 'WEBP'])
@pytest.mark.parametrize('cut', [1, 2, 30])
def test_truncated_image_rejected(client, kind, cut):
    assert upload(client, picture(kind)[:-cut]).status_code == 422


@pytest.mark.parametrize('trailer', JPEG_TRAILERS)
def test_complete_jpeg_with_trailing_data_preserves_original_bytes_and_sha(client, trailer):
    content = picture('JPEG') + trailer
    response = upload(client, content, 'with-trailer.jpeg')
    assert response.status_code == 200, response.text
    metadata = response.json()['data']
    assert metadata == {'id': hashlib.sha256(content).hexdigest(), 'mime': 'image/jpeg',
                        'size': len(content), 'width': 12, 'height': 9}
    assert client.get('/api/v6/assets/' + metadata['id'], headers=v6.admin()).content == content
    saved = client.get(UPLOAD + '/' + metadata['id'], headers=v6.admin()).json()['data']
    assert saved == metadata | {'name': 'with-trailer.jpeg'}


@pytest.mark.parametrize('trailer', JPEG_TRAILERS)
@pytest.mark.parametrize('cut', [1, 2, 30])
def test_jpeg_trailing_data_does_not_hide_missing_eoi_or_truncated_pixels(client, trailer, cut):
    assert upload(client, picture('JPEG')[:-cut] + trailer).status_code == 422


@pytest.mark.parametrize('segment', ['exif', 'comment'])
def test_jpeg_metadata_eoi_bytes_do_not_hide_missing_main_image_eoi(client, segment):
    if segment == 'exif':
        exif = Image.Exif()
        exif[37510] = b'embedded EOI \xff\xd9 bytes'
        content = picture('JPEG', exif=exif)
    else:
        content = picture('JPEG', comment=b'embedded EOI \xff\xd9 bytes')
    assert b'\xff\xd9' in content[:-2]
    assert upload(client, content[:-2] + b'\0' * 4).status_code == 422


@pytest.mark.parametrize('progressive', [False, True])
@pytest.mark.parametrize('restart', [0, 1])
def test_jpeg_marker_validation_accepts_stuffing_restart_and_progressive_scans(client, progressive, restart):
    pixels = bytes((i * 37 + i // 3 * 13) % 256 for i in range(64 * 48 * 3))
    exif = Image.Exif()
    exif[37510] = b'EXIF metadata \xff\xd9 bytes'
    output = BytesIO()
    Image.frombytes('RGB', (64, 48), pixels).save(
        output, format='JPEG', quality=90, progressive=progressive,
        restart_marker_blocks=restart, exif=exif, comment=b'comment \xff\xd9 bytes')
    content = output.getvalue()
    assert b'\xff\x00' in content
    if restart:
        assert any(bytes([255, 208 + i]) in content for i in range(8))
    preserved = content + b'\n'
    response = upload(client, preserved)
    assert response.status_code == 200, response.text
    identity = response.json()['data']['id']
    assert identity == hashlib.sha256(preserved).hexdigest()
    assert client.get('/api/v6/assets/' + identity, headers=v6.admin()).content == preserved
    for cut in (1, 2, 30):
        assert upload(client, content[:-cut] + b'\0' * 4).status_code == 422


def test_corrupt_png_pixels_and_chunk_crc_rejected(client):
    content = picture()
    corrupt_crc = bytearray(content)
    corrupt_crc[-1] ^= 1
    assert upload(client, bytes(corrupt_crc)).status_code == 422
    # Valid chunk CRCs must not disguise an invalid compressed pixel stream.
    invalid_pixels = content[:33] + chunk(b'IDAT', b'not-zlib-data') + chunk(b'IEND', b'')
    assert upload(client, invalid_pixels).status_code == 422


@pytest.mark.parametrize('kind', ['PNG', 'WEBP'])
def test_animated_background_rejected(client, kind):
    output = BytesIO()
    first = Image.new('RGB', (12, 9), 'red')
    first.save(output, format=kind, save_all=True,
               append_images=[Image.new('RGB', (12, 9), 'blue')], duration=100, loop=0)
    assert upload(client, output.getvalue()).status_code == 422


@pytest.mark.parametrize('kind', ['PNG', 'JPEG', 'WEBP'])
@pytest.mark.parametrize('size', [(4096, 1), (1, 4096)])
def test_dimension_limit_is_inclusive(client, kind, size):
    response = upload(client, picture(kind, size))
    assert response.status_code == 200, response.text
    assert (response.json()['data']['width'], response.json()['data']['height']) == size


@pytest.mark.parametrize('kind', ['PNG', 'JPEG', 'WEBP'])
@pytest.mark.parametrize('size', [(4097, 1), (1, 4097)])
def test_dimension_over_limit_rejected(client, kind, size):
    assert upload(client, picture(kind, size)).status_code == 422


def test_original_byte_and_base64_limit_is_inclusive(client):
    content = picture()
    # A valid bounded ancillary chunk fills the PNG exactly to the original byte limit.
    padding = b'padding\0' + b'x' * (3_000_000 - len(content) - 12 - 8)
    content = content[:-12] + chunk(b'tEXt', padding) + content[-12:]
    assert len(content) == 3_000_000
    response = upload(client, content)
    assert response.status_code == 200, response.text
    assert response.json()['data']['size'] == 3_000_000
    assert upload(client, content + b'x').status_code == 422
    assert client.post(UPLOAD, headers=v6.admin(), json={
        'name': 'large.png', 'data': 'A' * 4_000_001}).status_code == 422


def test_decoded_byte_limit_explicitly_rejects_oversize():
    from app.management.image_validation import validate_image

    with pytest.raises(ValueError, match='size'):
        validate_image(b'x' * 3_000_001)


def test_transparent_and_lossless_webp_supported(client):
    output = BytesIO()
    Image.new('RGBA', (12, 9), (90, 140, 210, 120)).save(output, format='WEBP', lossless=True)
    content = output.getvalue()
    response = upload(client, content, 'alpha.webp')
    assert response.status_code == 200, response.text
    identity = response.json()['data']['id']
    assert client.get('/api/v6/assets/' + identity, headers=v6.admin()).content == content


@pytest.mark.parametrize('kind', ['PNG', 'JPEG', 'WEBP'])
@pytest.mark.parametrize('orientation', [2, 5, 6, 7, 8])
def test_exif_display_dimensions_without_changing_bytes(client, kind, orientation):
    exif = Image.Exif()
    exif[274] = orientation
    content = picture(kind, exif=exif)
    response = upload(client, content)
    assert response.status_code == 200, response.text
    data = response.json()['data']
    expected = (9, 12) if orientation in (5, 6, 7, 8) else (12, 9)
    assert (data['width'], data['height']) == expected
    assert client.get('/api/v6/assets/' + data['id'], headers=v6.admin()).content == content
    metadata = client.get(UPLOAD + '/' + data['id'], headers=v6.admin()).json()['data']
    assert (metadata['width'], metadata['height']) == expected


def test_rejected_images_are_not_stored_or_audited(client):
    assert upload(client, picture('JPEG')[:-1]).status_code == 422
    with database() as db:
        assert db.execute('SELECT COUNT(*) FROM configuration_assets').fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM audit WHERE action='asset-upload'").fetchone()[0] == 0
