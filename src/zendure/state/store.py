"""The stateful store: feed reports in, get snapshots and change events out.

Holds the merged state for one device and its batteries. Deterministic: the
same sequence of reports and failures always produces the same snapshots and
the same ordered events. Emits only actual changes.

Availability rule: the device goes OFFLINE only after ``offline_threshold``
consecutive failed reads; a single successful read brings it back ONLINE and
resets the count. Below the threshold the last good values stay available.
"""

import logging
from datetime import UTC, datetime
from typing import Final

from .._redact import mask_serial
from ..events import (
    BatteryAdded,
    BatteryPropertiesChanged,
    BatteryRemoved,
    DeviceAvailabilityChanged,
    DevicePropertiesChanged,
    FaultCleared,
    FaultRaised,
    ZendureEvent,
)
from ..exceptions import DeviceMismatchError, ValidationError
from ..models import Availability, BatterySnapshot, DeviceSnapshot, PropertyValue
from .merge import compute_changes, merge_values
from .report import DeviceReport, FaultReport

_LOGGER = logging.getLogger(__name__)

DEFAULT_OFFLINE_THRESHOLD: Final = 3


class DeviceStore:
    """Accumulates reports for a single device into immutable snapshots."""

    def __init__(
        self,
        *,
        offline_threshold: int = DEFAULT_OFFLINE_THRESHOLD,
        expected_serial_number: str | None = None,
    ) -> None:
        if offline_threshold < 1:
            raise ValidationError("offline_threshold must be at least 1")
        self._offline_threshold = offline_threshold
        self._expected_serial_number = expected_serial_number
        self._consecutive_failures = 0
        self._serial_number: str | None = None
        self._model_key: str | None = None
        self._product_raw: str | None = None
        self._availability = Availability.INITIALIZING
        self._properties: dict[str, PropertyValue] = {}
        self._battery_props: dict[str, dict[str, PropertyValue]] = {}
        self._battery_pack_type: dict[str, int | None] = {}
        self._protocol_version: int | None = None
        self._message_id: int | None = None
        self._timestamp: int | None = None
        # None while unknown. The last known codes are kept apart so that a
        # failed read followed by a good one only reports real changes.
        self._active_faults: tuple[int, ...] | None = None
        self._last_known_faults: tuple[int, ...] = ()
        self._fault_since: dict[int, int] = {}
        self._fault_outage = False

    @property
    def availability(self) -> Availability:
        """Current availability."""
        return self._availability

    @property
    def consecutive_failures(self) -> int:
        """Failed reads since the last successful one."""
        return self._consecutive_failures

    @property
    def has_identity(self) -> bool:
        """Whether at least one report has been merged."""
        return self._serial_number is not None

    def merge(self, report: DeviceReport) -> tuple[DeviceSnapshot, list[ZendureEvent]]:
        """Merge a decoded report; return the new snapshot and ordered events.

        Raises:
            DeviceMismatchError: the report comes from a different device than
                the pinned one. Nothing is merged; the caller counts it as a
                failed read.
        """
        pinned = self._expected_serial_number or self._serial_number
        if pinned is not None and report.serial_number != pinned:
            raise DeviceMismatchError(pinned, report.serial_number)

        if self._availability is Availability.OFFLINE:
            _LOGGER.info(
                "Device %s back online after %d failed reads",
                mask_serial(report.serial_number),
                self._consecutive_failures,
            )
        self._consecutive_failures = 0

        self._serial_number = report.serial_number
        self._model_key = report.model_key
        self._product_raw = report.product_raw
        self._protocol_version = report.protocol_version
        self._message_id = report.message_id
        self._timestamp = report.timestamp

        events: list[ZendureEvent] = []
        events.extend(self._apply_availability(Availability.ONLINE))
        events.extend(self._apply_device_properties(report))
        events.extend(self._apply_batteries(report))
        return self.snapshot(), events

    def record_failure(self, error: Exception) -> list[ZendureEvent]:
        """Count one failed read; go OFFLINE once the threshold is reached.

        Logs a single WARNING on the transition and DEBUG otherwise, so a long
        outage does not flood the log.
        """
        self._consecutive_failures += 1
        failures = self._consecutive_failures
        reason = type(error).__name__

        if self._serial_number is None:
            # Never connected: no identity, nothing to mark. Caller surfaces it.
            _LOGGER.debug("Read failed before first contact (%d): %s", failures, reason)
            return []
        if self._availability is Availability.OFFLINE:
            _LOGGER.debug(
                "Device %s still offline (%d): %s",
                mask_serial(self._serial_number),
                failures,
                reason,
            )
            return []
        if failures < self._offline_threshold:
            _LOGGER.debug(
                "Device %s read failed (%d/%d): %s",
                mask_serial(self._serial_number),
                failures,
                self._offline_threshold,
                reason,
            )
            return []

        _LOGGER.warning(
            "Device %s offline after %d consecutive failed reads: %s",
            mask_serial(self._serial_number),
            failures,
            reason,
        )
        return self._apply_availability(Availability.OFFLINE)

    def merge_faults(
        self, report: FaultReport
    ) -> tuple[DeviceSnapshot, list[ZendureEvent]]:
        """Apply a fault report; return the snapshot and raise/clear events.

        Requires a merged device report first: fault reports carry no serial
        number, so the identity checked by that report is the one used here.
        Fault reads never affect availability: they are a separate endpoint
        and a failure there says nothing about the device's state readings.
        """
        assert self._serial_number is not None, "merge_faults() before first merge"
        pinned = self._serial_number

        previous = set(self._last_known_faults)
        current = set(report.codes)
        changes: list[FaultRaised | FaultCleared] = [
            FaultRaised(serial_number=pinned, code=code)
            for code in report.codes
            if code not in previous
        ]
        changes.extend(
            FaultCleared(serial_number=pinned, code=code)
            for code in self._last_known_faults
            if code not in current
        )
        if self._fault_outage:
            _LOGGER.info("Fault codes of device %s readable again", mask_serial(pinned))
            self._fault_outage = False
        for change in changes:
            # Only on change, so a lasting fault does not log every poll.
            _LOGGER.info(
                "Device %s fault %d %s",
                mask_serial(pinned),
                change.code,
                "raised" if isinstance(change, FaultRaised) else "cleared",
            )
        self._active_faults = report.codes
        self._last_known_faults = report.codes
        self._fault_since = dict(report.since)
        return self.snapshot(), list[ZendureEvent](changes)

    def record_fault_failure(self, error: Exception) -> None:
        """Mark faults unknown after a failed fault read.

        Logs a WARNING only when faults go from known to unknown, so a
        lasting outage does not flood the log.
        """
        serial = mask_serial(self._serial_number or "")
        reason = type(error).__name__
        if self._active_faults is not None:
            _LOGGER.warning("Fault codes of device %s unavailable: %s", serial, reason)
            self._fault_outage = True
        else:
            _LOGGER.debug("Fault read for device %s failed: %s", serial, reason)
        self._active_faults = None

    def _apply_availability(self, new: Availability) -> list[ZendureEvent]:
        if self._serial_number is None or self._availability == new:
            return []
        previous = self._availability
        self._availability = new
        return [
            DeviceAvailabilityChanged(
                serial_number=self._serial_number,
                previous=previous,
                current=new,
            )
        ]

    def _apply_device_properties(self, report: DeviceReport) -> list[ZendureEvent]:
        changed = compute_changes(self._properties, report.properties)
        if not changed:
            return []
        self._properties = merge_values(self._properties, report.properties)
        return [
            DevicePropertiesChanged(
                serial_number=report.serial_number,
                changed=changed,
            )
        ]

    def _apply_batteries(self, report: DeviceReport) -> list[ZendureEvent]:
        events: list[ZendureEvent] = []
        seen: set[str] = set()

        for battery in report.batteries:
            seen.add(battery.serial_number)
            if battery.serial_number not in self._battery_props:
                self._battery_props[battery.serial_number] = {}
                self._battery_pack_type[battery.serial_number] = battery.pack_type
                events.append(
                    BatteryAdded(
                        device_serial_number=report.serial_number,
                        battery_serial_number=battery.serial_number,
                    )
                )
            changed = compute_changes(
                self._battery_props[battery.serial_number], battery.properties
            )
            if changed:
                self._battery_props[battery.serial_number] = merge_values(
                    self._battery_props[battery.serial_number], battery.properties
                )
                events.append(
                    BatteryPropertiesChanged(
                        device_serial_number=report.serial_number,
                        battery_serial_number=battery.serial_number,
                        changed=changed,
                    )
                )

        # Removal only when the report actually carried a battery section.
        if report.batteries_present:
            for serial in sorted(set(self._battery_props) - seen):
                del self._battery_props[serial]
                del self._battery_pack_type[serial]
                events.append(
                    BatteryRemoved(
                        device_serial_number=report.serial_number,
                        battery_serial_number=serial,
                    )
                )

        return events

    def snapshot(self) -> DeviceSnapshot:
        """Return the current immutable snapshot (requires a merged report)."""
        assert self._serial_number is not None, "snapshot() before first merge"
        assert self._model_key is not None
        assert self._product_raw is not None

        batteries = tuple(
            BatterySnapshot(
                serial_number=serial,
                properties=self._battery_props[serial],
                pack_type=self._battery_pack_type[serial],
            )
            for serial in sorted(self._battery_props)
        )
        updated_at = (
            datetime.fromtimestamp(self._timestamp, tz=UTC)
            if self._timestamp is not None
            else None
        )
        return DeviceSnapshot(
            serial_number=self._serial_number,
            model_key=self._model_key,
            product_raw=self._product_raw,
            availability=self._availability,
            properties=self._properties,
            batteries=batteries,
            protocol_version=self._protocol_version,
            message_id=self._message_id,
            updated_at=updated_at,
            active_faults=self._active_faults,
            fault_since=(
                {}
                if self._active_faults is None
                else {
                    code: datetime.fromtimestamp(seconds, tz=UTC)
                    for code, seconds in self._fault_since.items()
                }
            ),
        )


__all__ = ["DEFAULT_OFFLINE_THRESHOLD", "DeviceStore"]
