import base64

from app.core.config import settings
from app.services.room_checkin import checkin_qr, render_qr


def test_qr_bound_only_to_configured_room(monkeypatch):
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_CHECKIN_URLS', {
        'omm_beijing': 'https://www.feishu.cn/calendar/pages/resource_qrcode?code=0&resource_token=test-room',
    })
    assert checkin_qr('omm_nanjing') is None
    result = checkin_qr('omm_beijing')
    assert result.startswith('data:image/svg+xml;base64,')
    assert b'<svg' in base64.b64decode(result.split(',')[1])


def test_only_official_checkin_links_are_rendered():
    for url in ['javascript:alert(1)', 'https://evil.test/calendar/pages/resource_qrcode?resource_token=x',
                'https://www.feishu.cn/calendar/pages/resource_qrcode', 'https://www.feishu.cn/other?resource_token=x']:
        assert render_qr(url) is None
