"""Protocol-agnostic periodic refresh with backoff.

Only schedules calls; it does not count failures or decide availability (the
refresh path does that, so polling and caller-driven refreshes agree). Used by
standalone scripts. A Home Assistant integration drives refreshes from its own
coordinator and does not start this poller.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Final

from ..exceptions import UnsupportedDeviceError, ValidationError, ZendureError

_LOGGER = logging.getLogger(__name__)

DEFAULT_SCAN_INTERVAL: Final = 60.0
DEFAULT_MAX_BACKOFF: Final = 300.0


def next_delay(
    interval: float, failures: int, *, backoff_after: int, max_interval: float
) -> float:
    """Seconds to wait before the next poll.

    Normal interval until ``backoff_after`` consecutive failures, then the
    interval doubles per further failure, capped at ``max_interval``.
    """
    if failures < backoff_after:
        return interval
    return min(interval * 2.0 ** (failures - backoff_after + 1), max_interval)


class Poller:
    """Runs ``refresh`` on an interval in a background task."""

    def __init__(
        self,
        refresh: Callable[[], Awaitable[object]],
        *,
        interval: float = DEFAULT_SCAN_INTERVAL,
        max_interval: float = DEFAULT_MAX_BACKOFF,
        backoff_after: int = 3,
    ) -> None:
        if interval <= 0:
            raise ValidationError("interval must be positive")
        if max_interval < interval:
            raise ValidationError("max_interval must be >= interval")
        self._refresh = refresh
        self._interval = interval
        self._max_interval = max_interval
        self._backoff_after = backoff_after
        self._task: asyncio.Task[None] | None = None

    @property
    def running(self) -> bool:
        """Whether the background task is alive."""
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        """Start polling (idempotent). Must be called from a running loop."""
        if self.running:
            return
        self._task = asyncio.create_task(self._run(), name="zendure-poller")
        self._task.add_done_callback(_on_done)

    async def stop(self) -> None:
        """Stop polling and wait for the task to finish (idempotent)."""
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def _run(self) -> None:
        failures = 0
        while True:
            try:
                await self._refresh()
            except UnsupportedDeviceError:
                # Configuration problem, not a transient failure: retrying
                # cannot fix it.
                _LOGGER.error("Polling stopped: device model is not supported")
                return
            except ZendureError:
                failures += 1
            else:
                failures = 0
            await asyncio.sleep(
                next_delay(
                    self._interval,
                    failures,
                    backoff_after=self._backoff_after,
                    max_interval=self._max_interval,
                )
            )


def _on_done(task: asyncio.Task[None]) -> None:
    if task.cancelled():
        return
    if (error := task.exception()) is not None:
        _LOGGER.error("Polling task crashed", exc_info=error)


__all__ = ["DEFAULT_MAX_BACKOFF", "DEFAULT_SCAN_INTERVAL", "Poller", "next_delay"]
