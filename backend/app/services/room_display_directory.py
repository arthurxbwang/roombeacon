"""Location-enriched catalog for SSH management; separate from display snapshots."""
import asyncio
import json

from ..connectors.feishu.rooms import FeishuRoomsClient
from ..core.room_devices import room_cache


def directory_rows(rooms: list[dict], names: dict[str, str]) -> list[dict]:
    result = []
    for room in rooms:
        path = [names.get(level_id, "未解析层级") for level_id in room.get("path", [])]
        # Current tenant hierarchy: organization / country / region-campus / building / floor.
        # Preserve the full path for filtering/export; never infer geography from room names.
        region = path[2] if len(path) >= 3 else "未分地区"
        result.append({
            "room_id": room["room_id"], "name": room["name"], "region": region,
            "location": " / ".join(path), "floor": path[-1] if len(path) >= 4 else "—",
            "capacity": room.get("capacity", 0),
            "enabled": (room.get("room_status") or {}).get("status", True),
        })
    return sorted(result, key=lambda row: (row["region"], row["location"], row["name"], row["room_id"]))


async def directory() -> list[dict]:
    client = FeishuRoomsClient()
    try:
        async with room_cache() as cache:
            saved = await cache.get("rooms:management-directory:v1")
            if saved:
                return json.loads(saved)
            rooms = await asyncio.wait_for(client.list_rooms(), timeout=30)
            ids = [level for room in rooms for level in room.get("path", [])]
            names = await asyncio.wait_for(client.room_levels(ids), timeout=90)
            rows = directory_rows(rooms, names)
            await cache.set("rooms:management-directory:v1", json.dumps(rows, ensure_ascii=False), ex=300)
            return rows
    finally:
        await client.close()
