"""Render configured official links offline; never submit a check-in."""
import base64
from functools import lru_cache
from urllib.parse import parse_qs, urlsplit

from ..core.config import settings
from .room_checkin_art import art_svg


@lru_cache(maxsize=512)
def render_qr(url: str) -> str | None:
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.netloc != 'www.feishu.cn'
            or parsed.path != '/calendar/pages/resource_qrcode'
            or not parse_qs(parsed.query).get('resource_token')):
        return None
    svg = art_svg(url)
    return 'data:image/svg+xml;base64,' + base64.b64encode(svg).decode('ascii')


def checkin_qr(room_id: str) -> str | None:
    url = settings.ROOM_DISPLAY_CHECKIN_URLS.get(room_id)
    return render_qr(url) if url else None
