"""Bounded still-image validation without transforming original resource bytes."""
import struct
import warnings
import zlib
from io import BytesIO

from PIL import Image

MAX_IMAGE_BYTES = 3_000_000
MIME_TYPES = {'PNG': 'image/png', 'JPEG': 'image/jpeg', 'WEBP': 'image/webp'}


def png_dimensions(data):
    """Preserve the old PNG chunk/CRC contract, including complete IEND framing."""
    if not data.startswith(b'\x89PNG\r\n\x1a\n') or len(data) < 45:
        raise ValueError('PNG required')
    width, height = struct.unpack('>II', data[16:24])
    bounded_dimensions(width, height)
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


def bounded_dimensions(width, height):
    if not (1 <= width <= 4096 and 1 <= height <= 4096):
        raise ValueError('dimensions')


def display_dimensions(image):
    width, height = image.size
    bounded_dimensions(width, height)
    # CSS image rendering honors EXIF orientation; retain the EXIF bytes and report
    # its displayed dimensions so the administration preview uses the same ratio.
    if image.getexif().get(274) in (5, 6, 7, 8):
        width, height = height, width
    return width, height


def complete_container(content, kind):
    if kind == 'PNG':
        png_dimensions(content)
    elif kind == 'JPEG':
        complete_jpeg(content)
    elif kind == 'WEBP' and (len(content) < 12 or content[:4] != b'RIFF'
                             or int.from_bytes(content[4:8], 'little') + 8 != len(content)):
        raise ValueError('incomplete WebP')


def complete_jpeg(content):
    """Require the image's EOI marker while retaining bytes after that marker."""
    offset, entropy = 2, False
    while offset < len(content):
        if entropy:
            offset = content.find(b'\xff', offset)
            if offset < 0:
                break
        elif content[offset] != 0xff:
            raise ValueError('invalid JPEG marker')
        while offset < len(content) and content[offset] == 0xff:
            offset += 1
        if offset == len(content):
            break
        marker = content[offset]
        offset += 1
        if marker == 0xd9:
            return
        if marker == 1 or entropy and (marker == 0 or 0xd0 <= marker <= 0xd7):
            continue
        if marker in (0, 0xd8) or 0xd0 <= marker <= 0xd7 or offset + 2 > len(content):
            raise ValueError('invalid JPEG marker')
        length = int.from_bytes(content[offset:offset + 2], 'big')
        if length < 2 or offset + length > len(content):
            raise ValueError('incomplete JPEG segment')
        # Skipping segment payloads prevents EXIF thumbnails or comments containing
        # FF D9 from disguising a missing EOI in the main image's entropy stream.
        offset += length
        entropy = marker == 0xda
    raise ValueError('incomplete JPEG')


def validate_image(content):
    """Identify the encoded format, verify structure, then decode every still pixel."""
    if not (1 <= len(content) <= MAX_IMAGE_BYTES):
        raise ValueError('size')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            with Image.open(BytesIO(content), formats=list(MIME_TYPES)) as image:
                kind = image.format
                if kind not in MIME_TYPES or getattr(image, 'n_frames', 1) != 1:
                    raise ValueError('still PNG/JPEG/WebP required')
                bounded_dimensions(*image.size)
                complete_container(content, kind)
                image.verify()
            # verify() invalidates its file handle and JPEG/WebP still need a full
            # decode to detect truncated or corrupt encoded pixel data.
            with Image.open(BytesIO(content), formats=[kind]) as image:
                image.load()
                width, height = display_dimensions(image)
    except (OSError, SyntaxError, struct.error, Image.DecompressionBombError, Warning) as exc:
        raise ValueError('invalid image') from exc
    return {'mime': MIME_TYPES[kind], 'size': len(content), 'width': width, 'height': height}


def stored_image_metadata(content, mime):
    """Read old PNG metadata without introducing a decoder requirement on old bytes."""
    if mime == 'image/png':
        width, height = png_dimensions(content)
        try:
            orientation = png_orientation(content)
        except (OSError, SyntaxError, struct.error, Warning) as exc:
            raise ValueError('invalid PNG EXIF') from exc
        if orientation in (5, 6, 7, 8):
            width, height = height, width
        return {'mime': mime, 'size': len(content), 'width': width, 'height': height}
    return validate_image(content)


def png_orientation(content):
    """Read only the optional EXIF chunk after the legacy chunk validation."""
    offset = 8
    while offset + 12 <= len(content):
        length = int.from_bytes(content[offset:offset + 4], 'big')
        if content[offset + 4:offset + 8] == b'eXIf':
            with warnings.catch_warnings():
                warnings.simplefilter('error')
                exif = Image.Exif()
                exif.load(content[offset + 8:offset + 8 + length])
                return exif.get(274)
        offset += length + 12
    return None
