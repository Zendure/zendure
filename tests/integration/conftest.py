"""Fixtures for tests that talk HTTP to a fake device on 127.0.0.1."""

from collections.abc import AsyncIterator
from typing import Any

import aiohttp
import pytest
from aiohttp.test_utils import TestServer
from fake_device import FakeDevice


@pytest.fixture
def device(report_max5000pro: dict[str, Any]) -> FakeDevice:
    return FakeDevice(report_max5000pro)


@pytest.fixture
async def server(device: FakeDevice) -> AsyncIterator[TestServer]:
    test_server = TestServer(device.build_app(), host="127.0.0.1")
    await test_server.start_server()
    yield test_server
    await test_server.close()


@pytest.fixture
async def session() -> AsyncIterator[aiohttp.ClientSession]:
    async with aiohttp.ClientSession() as client_session:
        yield client_session
