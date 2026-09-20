#!/usr/bin/env python3
"""仅回环监听的实机测试服务；通过 adb reverse 使用，绝非真实飞书数据。"""
import argparse
import base64
import json
import mimetypes
import re
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

TOKEN = "room:omm_fixture:" + "A" * 43
TEST_IMAGE = "data:image/svg+xml;base64," + base64.b64encode(
    '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">'
    '<rect width="200" height="200" fill="white"/>'
    '<text x="100" y="90" text-anchor="middle" font-size="24" fill="#854d0e">TEST ONLY</text>'
    '<text x="100" y="125" text-anchor="middle" font-size="20" fill="#854d0e">非签到码</text></svg>'.encode()
).decode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    root = args.dist.resolve()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *values):
            # 不记录 URL、Authorization 或请求内容。
            pass

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            state = json.loads(args.state.read_text()) if args.state.exists() else {}
            path = urlsplit(self.path).path
            if path.startswith("/api/"):
                if path != "/api/meeting-rooms/display":
                    return self.send(404, "application/json", b'{}')
                if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                    return self.send(401, "application/json", b'{}')
                status = int(state.get("api_status", 200))
                if status != 200:
                    return self.send(status, "application/json", b'{}')
                now = datetime.now(timezone.utc)
                data = {
                    "room": {"room_id": "omm_fixture", "name": "测试会议室 · 非真实日程", "capacity": 8, "enabled": True},
                    "server_time": now.isoformat(), "synced_at": now.isoformat(),
                    "valid_until": (now + timedelta(seconds=60)).isoformat(),
                    "titles_available": True, "checkin_qr": TEST_IMAGE, "events": [{
                        "uid": "fixture", "original_time": 0, "summary": "APK 样机验证 · 模拟会议",
                        "organizer": "测试数据", "start_time": (now - timedelta(minutes=10)).isoformat(),
                        "end_time": (now + timedelta(minutes=20)).isoformat(),
                    }],
                }
                return self.send(200, "application/json", json.dumps({"data": data}).encode())
            file = (root / path.lstrip("/")).resolve()
            if path == "/":
                file = root / "index.html"
            if root not in file.parents or not file.is_file():
                return self.send(404, "text/plain", b"Not found")
            content = file.read_bytes()
            mime = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
            if file.suffix == ".html":
                if state.get("page_status", 200) != 200:
                    return self.send(int(state["page_status"]), "text/plain", b"Fixture page failure")
                release = str(state.get("release", "fixture-a"))
                if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", release):
                    return self.send(500, "text/plain", b"Invalid fixture release")
                html = content.decode()
                html = re.sub(r'(<meta name="roombeacon-release" content=")[^"]+', rf'\g<1>{release}', html)
                binding = "" if state.get("skip_binding") else f"<script>localStorage.setItem('argus_room_display','{TOKEN}')</script>"
                banner = f'<div style="position:fixed;bottom:0;left:0;right:0;background:#854d0e;color:white;text-align:center;z-index:9999;font:16px sans-serif">仅样机测试 · 非真实飞书日程 · {release}</div>'
                html = html.replace("<body>", "<body>" + binding + banner)
                content = html.encode()
            self.send(200, mime, content)

        def send(self, status, mime, data):
            self.send_response(status)
            self.send_header("Content-Type", mime + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

    print(f"Fixture only: http://127.0.0.1:{args.port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
