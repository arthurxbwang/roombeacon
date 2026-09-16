import json
from unittest.mock import AsyncMock

import pytest

from app.connectors.feishu.rooms import FeishuRoomsClient
from app.services import room_display_admin as cli
from app.services.room_display_directory import directory_rows


def sample():
    return directory_rows([
        {'room_id': 'omm_bj', 'name': '创新会议室', 'path': ['root', 'country', 'bj', 'floor']},
        {'room_id': 'omm_sh', 'name': '北京项目会议室', 'path': ['root', 'country', 'sh', 'floor']},
    ], {'root': '企业', 'country': '中国', 'bj': '北京_总部', 'sh': '上海_园区', 'floor': '5F'})


def test_region_uses_location_not_room_name():
    rows = sample()
    assert [r['room_id'] for r in cli.select_rows(rows, '北京', '')] == ['omm_bj']
    assert [r['room_id'] for r in cli.select_rows(rows, '上海', '北京项目')] == ['omm_sh']
    assert cli.select_rows(rows, '深圳', '') == []


@pytest.mark.asyncio
async def test_cli_pages_and_json_keeps_full_location(monkeypatch, capsys):
    monkeypatch.setattr(cli, 'directory', AsyncMock(return_value=sample()))
    await cli.run(cli.parser().parse_args(['list', '--page-size', '1']))
    out = capsys.readouterr().out
    assert '第 1/2 页' in out
    assert sum(room_id in out for room_id in ['omm_bj', 'omm_sh']) == 1
    await cli.run(cli.parser().parse_args(['list', '--region', '北京', '--json']))
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]['location'] == '企业 / 中国 / 北京_总部 / 5F'
    await cli.run(cli.parser().parse_args(['regions']))
    assert '共 2 个地区/园区，2 间会议室' in capsys.readouterr().out


@pytest.mark.parametrize('args', [['list', '--page', '0'], ['list', '--page-size', '101'], ['issue']])
def test_invalid_cli_arguments_fail(args):
    with pytest.raises(SystemExit):
        cli.parser().parse_args(args)


def test_chinese_cell_width_and_terminal_control_removal():
    assert cli.cell('北京', 6) == '北京  '
    assert cli.cell('北京总部', 6) == '北京 …'
    assert '\x1b' not in cli.cell('\x1b[31m名称\n', 20)


@pytest.mark.asyncio
async def test_level_requests_are_deduplicated_and_bounded(monkeypatch):
    client = FeishuRoomsClient()
    api = AsyncMock(return_value={'data': {'items': [{'room_level_id': 'a', 'name': '北京'}]}})
    monkeypatch.setattr(client, '_api', api)
    names = await client.room_levels([str(i) for i in range(21)] + ['0'])
    assert names == {'a': '北京'}
    assert len(api.call_args_list) == 2
    assert len(api.call_args_list[0].kwargs['json']['level_ids']) == 20
