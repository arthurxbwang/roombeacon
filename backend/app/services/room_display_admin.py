"""通过 SSH 按地区查找会议室并管理门牌凭证。"""
import argparse
import asyncio
import json
import logging
import sys
import unicodedata
from collections import Counter

import structlog

from ..core.exceptions import NotFoundError
from ..core.room_devices import issue_device, revoke_device
from ..core.room_usage_auth import issue_usage, revoke_usage
from .meeting_rooms import list_rooms
from .room_display_directory import directory


def cell(value: object, width: int) -> str:
    text = "".join(c for c in str(value) if not unicodedata.category(c).startswith("C"))
    sizes = [0 if unicodedata.combining(c) else (2 if unicodedata.east_asian_width(c) in "WF" else 1) for c in text]
    if sum(sizes) <= width:
        return text + " " * (width - sum(sizes))
    used, chars = 0, []
    for char, size in zip(text, sizes, strict=True):
        if used + size > width - 1:
            break
        chars.append(char)
        used += size
    return "".join(chars) + " " * (width - used - 1) + "…"



def table(headers: list[str], widths: list[int], rows: list[list]) -> None:
    print(" | ".join(cell(v, w) for v, w in zip(headers, widths, strict=True)))
    print("-+-".join("-" * width for width in widths))
    for row in rows:
        print(" | ".join(cell(v, w) for v, w in zip(row, widths, strict=True)))


def select_rows(rows: list[dict], region: str, name: str) -> list[dict]:
    return [row for row in rows if region.casefold() in row["location"].casefold()
            and name.casefold() in row["name"].casefold()]


async def run(args: argparse.Namespace) -> None:
    if args.action in {"list", "regions"}:
        all_rows = await directory()
        rows = select_rows(all_rows, args.region, args.name)
        if args.action == "regions":
            counts = Counter(row["region"] for row in rows)
            table(["地区 / 园区", "会议室数"], [46, 8], [[key, value] for key, value in sorted(counts.items())])
            print(f"共 {len(counts)} 个地区/园区，{len(rows)} 间会议室。")
            return
        start = (args.page - 1) * args.page_size
        page = rows if args.all else rows[start:start + args.page_size]
        if args.json:
            print(json.dumps(page, ensure_ascii=False, indent=2))
            return
        table(["地区 / 园区", "楼层", "会议室", "容量", "状态", "会议室 ID"],
              [24, 8, 28, 4, 4, max([36] + [len(r["room_id"]) for r in page])],
              [[r["region"], r["floor"], r["name"], r["capacity"], "可用" if r["enabled"] else "停用", r["room_id"]] for r in page])
        pages = max(1, (len(rows) + args.page_size - 1) // args.page_size)
        print(f"匹配 {len(rows)} / 总计 {len(all_rows)} 间；" +
              ("已显示全部。" if args.all else f"第 {args.page}/{pages} 页，每页 {args.page_size} 间。"))
        print("筛选：list --region 北京 --name 关键词 | 下一页：--page N | 全部：--all | 完整路径：--json | 地区汇总：regions")
        return
    if not args.room_id or not any(room.room_id == args.room_id for room in await list_rooms()):
        raise NotFoundError("请选择有效会议室 ID")
    if args.action == "issue":
        print(await issue_device(args.room_id))
    elif args.action == 'issue-usage':
        print(await issue_usage(args.room_id))
    elif args.action == 'revoke-usage':
        await revoke_usage(args.room_id)
        print('usage revoked')
    else:
        await revoke_device(args.room_id)
        print("revoked")


def positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("必须大于 0")
    return number


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="action", required=True)
    for action in ["list", "regions"]:
        command = commands.add_parser(action)
        command.add_argument("--region", default="", help="地区/园区/楼栋关键词，例如：北京")
        command.add_argument("--name", default="", help="会议室名称关键词")
        if action == "list":
            command.add_argument("--page", type=positive, default=1)
            command.add_argument("--page-size", type=int, choices=range(1, 101), metavar="1-100", default=20)
            command.add_argument("--all", action="store_true", help="显示全部匹配结果")
            command.add_argument("--json", action="store_true", help="输出完整名称、位置和 ID")
    for action in ["issue", "revoke", 'issue-usage', 'revoke-usage']:
        commands.add_parser(action).add_argument("room_id")
    return result


if __name__ == "__main__":
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING),
                        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr))
    asyncio.run(run(parser().parse_args()))
