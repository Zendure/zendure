"""``ZendureClient``: the public facade (read path).

Depends only on the abstract ``DeviceProtocol``, never on a concrete protocol.
Every read goes through ``async_refresh`` (whether triggered by the built-in
poller or by the caller, e.g. a Home Assistant coordinator), so failure
counting and availability are consistent no matter who drives refreshes.
"""

import asyncio
import logging
from collections.abc import Callable
from typing import Final, Self

from .catalog.controls import control, validate_control
from .events import EventListener, ZendureEvent
from .exceptions import (
    ClientClosedError,
    ValidationError,
    WriteNotConfirmedError,
    ZendureConnectionError,
    ZendureProtocolError,
)
from .models import Availability, DeviceSnapshot, PropertyValue
from .protocols.base import DeviceProtocol
from .state.store import DEFAULT_OFFLINE_THRESHOLD, DeviceStore
from .transport.poller import DEFAULT_MAX_BACKOFF, DEFAULT_SCAN_INTERVAL, Poller

_LOGGER = logging.getLogger(__name__)

# Device reports can lag a successful write. Retry the confirmation GET only;
# the write itself is never retried.
_CONFIRM_ATTEMPTS: Final = 7
_CONFIRM_DELAY_S: Final = 1.0


class ZendureClient:
    """One device, one client. Async context manager; ``close()`` is idempotent."""

    def __init__(
        self,
        protocol: DeviceProtocol,
        *,
        offline_threshold: int = DEFAULT_OFFLINE_THRESHOLD,
        expected_serial_number: str | None = None,
        scan_interval: float = DEFAULT_SCAN_INTERVAL,
        max_backoff: float = DEFAULT_MAX_BACKOFF,
    ) -> None:
        self._protocol = protocol
        self._store = DeviceStore(
            offline_threshold=offline_threshold,
            expected_serial_number=expected_serial_number,
        )
        self._poller = Poller(
            self.async_refresh,
            interval=scan_interval,
            max_interval=max_backoff,
            backoff_after=offline_threshold,
        )
        self._listeners: list[EventListener] = []
        self._inflight: asyncio.Task[DeviceSnapshot] | None = None
        self._closed = False
        self._write_lock = asyncio.Lock()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    @property
    def snapshot(self) -> DeviceSnapshot | None:
        """Latest snapshot, or ``None`` before the first successful read."""
        return self._store.snapshot() if self._store.has_identity else None

    @property
    def availability(self) -> Availability:
        """Current availability."""
        return self._store.availability

    def subscribe(self, listener: EventListener) -> Callable[[], None]:
        """Register a change listener; returns a function that unsubscribes it."""
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    async def async_refresh(self) -> DeviceSnapshot:
        """Read the device once and merge the result.

        Concurrent callers share one in-flight request, so a burst of refreshes
        sends one GET and counts at most one failure.

        Raises:
            ClientClosedError: called after ``close()``.
            ZendureConnectionError / ZendureProtocolError: the read failed
                (counted toward the offline threshold).
            UnsupportedDeviceError: the model is not supported (not counted).
        """
        if self._closed:
            raise ClientClosedError("client is closed")
        # Join only a request that is still running; a finished one (whose
        # done-callback has not run yet) must not hand out a stale result.
        if self._inflight is None or self._inflight.done():
            self._inflight = asyncio.create_task(self._refresh_once())
            self._inflight.add_done_callback(self._clear_inflight)
        return await asyncio.shield(self._inflight)

    def _clear_inflight(self, task: asyncio.Task[DeviceSnapshot]) -> None:
        if self._inflight is task:
            self._inflight = None
        if not task.cancelled():
            task.exception()  # Mark as retrieved; the awaiting caller re-raises.

    async def _refresh_once(self) -> DeviceSnapshot:
        try:
            report = await self._protocol.async_read()
            snapshot, events = self._store.merge(report)
        except (ZendureConnectionError, ZendureProtocolError) as err:
            self._dispatch(self._store.record_failure(err))
            raise
        self._dispatch(events)
        return snapshot

    async def async_set(self, key: str, value: PropertyValue) -> DeviceSnapshot:
        """Validate, write once, then confirm against a fresh device report.

        A timeout is outcome-unknown and never retried. An accepted write whose
        value is not yet reported raises WriteNotConfirmedError, not rejection.
        """
        async with self._write_lock:
            if self._closed:
                raise ClientClosedError("client is closed")
            description = control(key)
            # Reject unknown/read-only/type errors before requesting identity.
            if description is None or not description.writable:
                validate_control(key, value)
            snapshot = await self.async_refresh()
            dynamic_max = None
            if description is not None and description.max_source_key is not None:
                bound = snapshot.properties.get(description.max_source_key)
                if isinstance(bound, bool) or not isinstance(bound, (int, float)):
                    raise ValidationError(f"{key} upper bound is unavailable")
                dynamic_max = float(bound)
            normalized = validate_control(key, value, dynamic_max=dynamic_max)
            await self._protocol.async_write(snapshot.serial_number, {key: normalized})
            if self._inflight is not None and not self._inflight.done():
                await asyncio.shield(self._inflight)
            confirmed = await self._confirm_write(key, normalized)
            if confirmed.properties.get(key) != normalized:
                raise WriteNotConfirmedError(f"{key} write not confirmed by read-back")
            return confirmed

    async def _confirm_write(self, key: str, expected: PropertyValue) -> DeviceSnapshot:
        """Re-read until the device reports ``expected``, or attempts are exhausted."""
        snapshot = await self.async_refresh()
        for _ in range(_CONFIRM_ATTEMPTS - 1):
            if snapshot.properties.get(key) == expected:
                return snapshot
            await asyncio.sleep(_CONFIRM_DELAY_S)
            snapshot = await self.async_refresh()
        return snapshot

    def start(self) -> None:
        """Start the built-in poller (standalone use; HA drives refreshes itself)."""
        if self._closed:
            raise ClientClosedError("client is closed")
        self._poller.start()

    async def close(self) -> None:
        """Stop polling and cancel any in-flight read. Does not close the session."""
        if self._closed:
            return
        self._closed = True
        await self._poller.stop()
        if (task := self._inflight) is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._listeners.clear()

    def _dispatch(self, events: list[ZendureEvent]) -> None:
        if self._closed:
            return
        for event in events:
            for listener in tuple(self._listeners):
                try:
                    listener(event)
                except Exception:
                    # One faulty listener must not stop delivery to the others.
                    _LOGGER.exception("Listener failed on %s", type(event).__name__)


__all__ = ["ZendureClient"]
