"""经实机校准的固定接线；远程配置不接受任意 GPIO。"""
import json

from ..core.exceptions import AppError

PROFILES = [
    {'id': 'generic', 'name': '通用屏幕（无灯控）', 'model': '', 'firmware': '',
     'pins': None, 'active_level': None},
    {'id': 'bx68', 'name': 'BX68 · 13.3 寸 1080P', 'model': 'RK3568',
     'firmware': 'RK3568_BX68_Android 11_64-20260331.094925_ZX-keys',
     'pins': {'red': 148, 'green': 154, 'blue': 147}, 'active_level': 0},
    {'id': 'rk3568_r', 'name': 'RK3568_R · 1280×800', 'model': 'rk3568_r',
     'firmware': 'rk3568-11.0-20230426.150223',
     'pins': {'red': 154, 'green': 148, 'blue': 147}, 'active_level': 1},
]


def validate_target(config, row, confirmed=False):
    """只比较型号；特殊设备可由后台二次确认，不用固件或 APK 阻止发布。"""
    profile_id = config.get('device_profile', 'auto')
    if profile_id in ('auto', 'generic'):
        return False
    metadata = json.loads(row['metadata'])
    profile = next(p for p in PROFILES if p['id'] == profile_id)
    mismatch = metadata.get('model', '') != profile['model']
    if mismatch and not confirmed:
        raise AppError(422, f"设备 {row['code']} 与模板型号不同，请二次确认后强制下发", 422)
    return mismatch
