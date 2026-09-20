"""Read-only meeting room queries using the existing Feishu credentials."""
import re
from datetime import datetime

from ...core.exceptions import ExternalAPIError
from .client import FeishuClient


class FeishuRoomsClient(FeishuClient):
    async def list_rooms(self) -> list[dict]:
        rooms, seen = [], set()
        token = ""
        for _ in range(100):
            data = (await self._api("GET", "/vc/v1/rooms", params={
                "page_size": 100, "page_token": token,
            }))["data"]
            rooms.extend(data["rooms"])
            if not data.get("has_more"):
                return rooms
            token = data.get("page_token")
            if not token or token in seen:
                break
            seen.add(token)
        raise ExternalAPIError("feishu", "room pagination incomplete")

    async def room_levels(self, level_ids: list[str]) -> dict[str, str]:
        names = {}
        ids = sorted(set(level_ids))
        for offset in range(0, len(ids), 20):
            data = (await self._api("POST", "/vc/v1/room_levels/mget", json={
                "level_ids": ids[offset:offset + 20],
            }))["data"]
            names.update({item["room_level_id"]: item["name"] for item in data["items"]})
        return names

    async def freebusy(self, room_ids: list[str], start: datetime, end: datetime) -> dict:
        if not 1 <= len(room_ids) <= 20:
            raise ValueError("Expected 1–20 room IDs")
        params = [("room_ids", room_id) for room_id in room_ids]
        params.extend([("time_min", start.isoformat()), ("time_max", end.isoformat())])
        data = (await self._api("GET", "/meeting_room/freebusy/batch_get", params=params))["data"]
        # Feishu omits rooms with no busy periods. Only normalize a complete,
        # successful envelope for the exact requested window; failed rooms stay absent.
        if (isinstance(data.get("free_busy"), dict)
                and isinstance(data.get("error_room_ids"), list)
                and data.get("time_min") and data.get("time_max")
                and datetime.fromisoformat(data["time_min"]) == start
                and datetime.fromisoformat(data["time_max"]) == end):
            for room_id in room_ids:
                if room_id not in data["error_room_ids"]:
                    data["free_busy"].setdefault(room_id, [])
        return data

    async def summaries(self, events: list[dict]) -> dict:
        return (await self._api("POST", "/meeting_room/summary/batch_get", json={
            "EventUids": events,
        }))["data"]

    async def organizer_name(self, open_id: str) -> str | None:
        if not isinstance(open_id, str) or not re.fullmatch(r"ou_[A-Za-z0-9_-]{1,128}", open_id):
            raise ValueError("Invalid organizer open_id")
        data = await self._api("GET", f"/contact/v3/users/{open_id}",
                               params={"user_id_type": "open_id"})
        user = data["data"]["user"]
        if not isinstance(user, dict):
            raise TypeError("Invalid organizer response")
        name = user.get("name")
        if name is not None and not isinstance(name, str):
            raise ValueError("Invalid organizer name")
        return name.strip() or None if name else None
