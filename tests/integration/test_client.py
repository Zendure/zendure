"""ZendureClient read path against a fake device over real HTTP."""

import asyncio
from typing import Any

import aiohttp
import pytest
from aiohttp.test_utils import TestServer
from fake_device import FakeDevice

from zendure import (
    Availability,
    ClientClosedError,
    DeviceAvailabilityChanged,
    DeviceMismatchError,
    DevicePropertiesChanged,
    UnsupportedDeviceError,
    ZendureClient,
    ZendureConnectionError,
    ZendureEvent,
    ZendureProtocolError,
    create_local_client,
)

SERIAL = "TESTDEV00000001"


def _client(
    server: TestServer, session: aiohttp.ClientSession, **kwargs: Any
) -> ZendureClient:
    kwargs.setdefault("timeout", 1.0)
    return create_local_client("127.0.0.1", session, port=server.port, **kwargs)


async def _fail_times(client: ZendureClient, times: int) -> None:
    for _ in range(times):
        with pytest.raises(ZendureProtocolError):
            await client.async_refresh()


async def test_refresh_returns_snapshot(
    server: TestServer, session: aiohttp.ClientSession
) -> None:
    async with _client(server, session) as client:
        assert client.snapshot is None
        assert client.availability is Availability.INITIALIZING
        snapshot = await client.async_refresh()
        assert snapshot.serial_number == SERIAL
        assert snapshot.availability is Availability.ONLINE
        assert client.snapshot == snapshot


async def test_concurrent_refreshes_share_one_request(
    server: TestServer, session: aiohttp.ClientSession, device: FakeDevice
) -> None:
    device.delay = 0.05
    async with _client(server, session) as client:
        results = await asyncio.gather(*(client.async_refresh() for _ in range(5)))
    assert device.report_calls == 1
    assert len({id(r) for r in results}) == 1


async def test_sequential_refreshes_each_send_a_request(
    server: TestServer, session: aiohttp.ClientSession, device: FakeDevice
) -> None:
    async with _client(server, session) as client:
        await client.async_refresh()
        await client.async_refresh()
    assert device.report_calls == 2


async def test_offline_after_three_failed_reads(
    server: TestServer, session: aiohttp.ClientSession, device: FakeDevice
) -> None:
    events: list[ZendureEvent] = []
    async with _client(server, session) as client:
        client.subscribe(events.append)
        await client.async_refresh()
        device.report_status = 503

        await _fail_times(client, 2)
        assert client.availability is Availability.ONLINE
        assert client.snapshot is not None
        assert client.snapshot.properties["electricLevel"] == 10

        await _fail_times(client, 1)
        assert client.availability is Availability.OFFLINE

    offline = [e for e in events if isinstance(e, DeviceAvailabilityChanged)]
    assert offline[-1].current is Availability.OFFLINE


async def test_recovers_on_first_success(
    server: TestServer, session: aiohttp.ClientSession, device: FakeDevice
) -> None:
    async with _client(server, session) as client:
        await client.async_refresh()
        device.report_status = 503
        await _fail_times(client, 3)
        device.report_status = 200
        snapshot = await client.async_refresh()
    assert snapshot.availability is Availability.ONLINE


async def test_concurrent_failures_count_once(
    server: TestServer, session: aiohttp.ClientSession, device: FakeDevice
) -> None:
    async with _client(server, session) as client:
        await client.async_refresh()
        device.report_status = 503
        device.delay = 0.05
        results = await asyncio.gather(
            *(client.async_refresh() for _ in range(5)), return_exceptions=True
        )
        assert all(isinstance(r, ZendureProtocolError) for r in results)
        # Five callers, one request, one failure: still below the threshold.
        assert client.availability is Availability.ONLINE


async def test_timeout_counts_as_failure(
    server: TestServer, session: aiohttp.ClientSession, device: FakeDevice
) -> None:
    async with _client(server, session, timeout=0.05, offline_threshold=1) as client:
        await client.async_refresh()
        device.delay = 0.5
        with pytest.raises(ZendureConnectionError):
            await client.async_refresh()
        assert client.availability is Availability.OFFLINE


async def test_unsupported_model_not_counted(
    server: TestServer, session: aiohttp.ClientSession, device: FakeDevice
) -> None:
    async with _client(server, session, offline_threshold=1) as client:
        await client.async_refresh()
        device.report["product"] = "solarFlow800Pro"
        with pytest.raises(UnsupportedDeviceError):
            await client.async_refresh()
        assert client.availability is Availability.ONLINE


async def test_different_device_on_host_is_failure(
    server: TestServer, session: aiohttp.ClientSession, device: FakeDevice
) -> None:
    async with _client(server, session, offline_threshold=1) as client:
        await client.async_refresh()
        device.report["sn"] = "OTHERDEV0000001"
        with pytest.raises(DeviceMismatchError):
            await client.async_refresh()
        assert client.availability is Availability.OFFLINE
        assert client.snapshot is not None
        assert client.snapshot.serial_number == SERIAL


async def test_expected_serial_number_enforced(
    server: TestServer, session: aiohttp.ClientSession
) -> None:
    async with _client(
        server, session, expected_serial_number="OTHERDEV0000001"
    ) as client:
        with pytest.raises(DeviceMismatchError):
            await client.async_refresh()
        assert client.snapshot is None


async def test_listener_error_does_not_block_others(
    server: TestServer, session: aiohttp.ClientSession
) -> None:
    received: list[ZendureEvent] = []

    def broken(_event: ZendureEvent) -> None:
        raise RuntimeError("listener bug")

    async with _client(server, session) as client:
        client.subscribe(broken)
        client.subscribe(received.append)
        await client.async_refresh()
    assert any(isinstance(e, DevicePropertiesChanged) for e in received)


async def test_unsubscribe(server: TestServer, session: aiohttp.ClientSession) -> None:
    received: list[ZendureEvent] = []
    async with _client(server, session) as client:
        unsubscribe = client.subscribe(received.append)
        unsubscribe()
        unsubscribe()
        await client.async_refresh()
    assert received == []


async def test_closed_client_rejects_use(
    server: TestServer, session: aiohttp.ClientSession
) -> None:
    client = _client(server, session)
    await client.close()
    await client.close()
    with pytest.raises(ClientClosedError):
        await client.async_refresh()
    with pytest.raises(ClientClosedError):
        client.start()
    assert not session.closed


async def test_close_cancels_inflight_read(
    server: TestServer, session: aiohttp.ClientSession, device: FakeDevice
) -> None:
    device.delay = 1.0
    client = _client(server, session, timeout=5.0)
    refresh = asyncio.create_task(client.async_refresh())
    await asyncio.sleep(0.05)
    await client.close()
    with pytest.raises(asyncio.CancelledError):
        await refresh


async def test_poller_drives_refreshes(
    server: TestServer, session: aiohttp.ClientSession, device: FakeDevice
) -> None:
    async with _client(server, session, scan_interval=0.02, max_backoff=0.1) as client:
        client.start()
        for _ in range(100):
            if device.report_calls >= 3:
                break
            await asyncio.sleep(0.02)
        assert device.report_calls >= 3
        assert client.availability is Availability.ONLINE
