"""Tests for the protocol-agnostic poller."""

import asyncio
import logging

import pytest

from zendure.exceptions import (
    UnsupportedDeviceError,
    ValidationError,
    ZendureConnectionError,
)
from zendure.transport.poller import Poller, next_delay


@pytest.mark.parametrize(
    ("failures", "expected"),
    [(0, 60), (1, 60), (2, 60), (3, 120), (4, 240), (5, 300), (20, 300)],
)
def test_next_delay(failures: int, expected: float) -> None:
    assert next_delay(60, failures, backoff_after=3, max_interval=300) == expected


@pytest.mark.parametrize(("interval", "max_interval"), [(0, 10), (-1, 10), (10, 5)])
def test_invalid_intervals_rejected(interval: float, max_interval: float) -> None:
    async def refresh() -> None:
        return None

    with pytest.raises(ValidationError):
        Poller(refresh, interval=interval, max_interval=max_interval)


class CountingRefresh:
    def __init__(self, target: int, error: Exception | None = None) -> None:
        self.calls = 0
        self.target = target
        self.error = error
        self.reached = asyncio.Event()

    async def __call__(self) -> None:
        self.calls += 1
        if self.calls >= self.target:
            self.reached.set()
        if self.error is not None:
            raise self.error


async def test_polls_repeatedly() -> None:
    refresh = CountingRefresh(target=3)
    poller = Poller(refresh, interval=0.01, max_interval=0.05)
    poller.start()
    await asyncio.wait_for(refresh.reached.wait(), timeout=2)
    await poller.stop()
    assert refresh.calls >= 3
    assert not poller.running


async def test_keeps_polling_through_failures() -> None:
    refresh = CountingRefresh(target=5, error=ZendureConnectionError("down"))
    poller = Poller(refresh, interval=0.01, max_interval=0.02, backoff_after=2)
    poller.start()
    await asyncio.wait_for(refresh.reached.wait(), timeout=2)
    assert poller.running
    await poller.stop()


async def test_unsupported_device_stops_polling(
    caplog: pytest.LogCaptureFixture,
) -> None:
    refresh = CountingRefresh(target=1, error=UnsupportedDeviceError("x"))
    poller = Poller(refresh, interval=0.01, max_interval=0.05)
    with caplog.at_level(logging.ERROR, logger="zendure.transport.poller"):
        poller.start()
        await asyncio.wait_for(refresh.reached.wait(), timeout=2)
        for _ in range(20):
            if not poller.running:
                break
            await asyncio.sleep(0.01)
    assert not poller.running
    assert refresh.calls == 1
    assert any("not supported" in r.getMessage() for r in caplog.records)
    await poller.stop()


async def test_unexpected_error_is_logged_not_swallowed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    refresh = CountingRefresh(target=1, error=RuntimeError("bug"))
    poller = Poller(refresh, interval=0.01, max_interval=0.05)

    def crashed_logged() -> bool:
        return any("crashed" in r.getMessage() for r in caplog.records)

    with caplog.at_level(logging.ERROR, logger="zendure.transport.poller"):
        poller.start()
        await asyncio.wait_for(refresh.reached.wait(), timeout=2)
        # The done-callback logs one loop iteration after the task finishes.
        for _ in range(50):
            if crashed_logged():
                break
            await asyncio.sleep(0.01)
    assert not poller.running
    assert crashed_logged()
    await poller.stop()


async def test_start_and_stop_idempotent() -> None:
    refresh = CountingRefresh(target=1)
    poller = Poller(refresh, interval=0.01, max_interval=0.05)
    poller.start()
    poller.start()
    await asyncio.wait_for(refresh.reached.wait(), timeout=2)
    await poller.stop()
    await poller.stop()
    assert not poller.running
