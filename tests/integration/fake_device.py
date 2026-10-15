"""A configurable stand-in for a zenSDK device's HTTP server."""

import asyncio
import json
from typing import Any

from aiohttp import web


class FakeDevice:
    """Serves ``/properties/report`` and ``/properties/write`` like a device."""

    def __init__(self, report: dict[str, Any]) -> None:
        self.report = report
        self.report_raw: bytes | None = None
        self.report_status = 200
        self.write_status = 200
        self.write_reply = json.dumps(
            {"success": True, "code": 200, "sn": report["sn"]}
        ).encode()
        self.delay = 0.0
        self.writes: list[dict[str, Any]] = []
        self.report_calls = 0
        self.active = 0
        self.peak_active = 0

    def build_app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/properties/report", self.handle_report)
        app.router.add_post("/properties/write", self.handle_write)
        return app

    async def handle_report(self, _request: web.Request) -> web.Response:
        self.report_calls += 1
        self.active += 1
        self.peak_active = max(self.peak_active, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            body = self.report_raw
            if body is None:
                body = json.dumps(self.report).encode()
            return web.Response(
                body=body, status=self.report_status, content_type="application/json"
            )
        finally:
            self.active -= 1

    async def handle_write(self, request: web.Request) -> web.Response:
        self.writes.append(await request.json())
        return web.Response(body=self.write_reply, status=self.write_status)
