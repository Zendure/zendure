"""Tests for the stateful device store."""

import logging

import pytest

from zendure.events import (
    BatteryAdded,
    BatteryPropertiesChanged,
    BatteryRemoved,
    DeviceAvailabilityChanged,
    DevicePropertiesChanged,
)
from zendure.exceptions import (
    DeviceMismatchError,
    ValidationError,
    ZendureConnectionError,
)
from zendure.models import Availability
from zendure.state.report import BatteryReport, DeviceReport
from zendure.state.store import DEFAULT_OFFLINE_THRESHOLD, DeviceStore

SERIAL = "TESTDEV00000001"


def _report(**overrides: object) -> DeviceReport:
    defaults: dict[str, object] = {
        "serial_number": SERIAL,
        "model_key": "solarflow_5000_max_pro",
        "product_raw": "SolarFlow5000MaxPro",
        "properties": {"electricLevel": 10},
        "message_id": 1,
        "timestamp": 1791959594,
    }
    defaults.update(overrides)
    return DeviceReport(**defaults)  # type: ignore[arg-type]


def _fail(store: DeviceStore, times: int) -> list[object]:
    events: list[object] = []
    for _ in range(times):
        events.extend(store.record_failure(ZendureConnectionError("timeout")))
    return events


# --- merging -----------------------------------------------------------------
def test_first_merge_online_and_properties() -> None:
    store = DeviceStore()
    snapshot, events = store.merge(_report())
    assert snapshot.availability is Availability.ONLINE
    assert snapshot.properties["electricLevel"] == 10
    kinds = [type(e) for e in events]
    assert kinds[0] is DeviceAvailabilityChanged
    assert DevicePropertiesChanged in kinds


def test_updated_at_from_report_timestamp() -> None:
    store = DeviceStore()
    snapshot, _ = store.merge(_report(timestamp=1791959594))
    assert snapshot.updated_at is not None
    assert snapshot.updated_at.year == 2026


def test_duplicate_report_no_events() -> None:
    store = DeviceStore()
    store.merge(_report())
    _, events = store.merge(_report())
    assert events == []


def test_same_message_id_new_values_applied() -> None:
    # Over HTTP the device may repeat messageId; reports are never dropped by it.
    store = DeviceStore()
    store.merge(_report(message_id=1, properties={"electricLevel": 10}))
    snapshot, _ = store.merge(_report(message_id=1, properties={"electricLevel": 20}))
    assert snapshot.properties["electricLevel"] == 20


def test_lower_message_id_applied() -> None:
    store = DeviceStore()
    store.merge(_report(message_id=500, properties={"electricLevel": 10}))
    snapshot, _ = store.merge(_report(message_id=1, properties={"electricLevel": 42}))
    assert snapshot.properties["electricLevel"] == 42
    assert snapshot.message_id == 1


def test_only_changed_properties_reported() -> None:
    store = DeviceStore()
    store.merge(_report(properties={"electricLevel": 10, "acMode": 2}))
    _, events = store.merge(_report(properties={"electricLevel": 10, "acMode": 1}))
    prop_events = [e for e in events if isinstance(e, DevicePropertiesChanged)]
    assert len(prop_events) == 1
    assert prop_events[0].changed == {"acMode": 1}


def test_absent_key_retained() -> None:
    store = DeviceStore()
    store.merge(_report(properties={"electricLevel": 10, "acMode": 2}))
    snapshot, _ = store.merge(_report(properties={"electricLevel": 20}))
    assert snapshot.properties["acMode"] == 2
    assert snapshot.properties["electricLevel"] == 20


def test_battery_added_and_updated() -> None:
    store = DeviceStore()
    battery = BatteryReport(serial_number="BAT1", properties={"socLevel": 10})
    _, events = store.merge(_report(batteries=(battery,)))
    assert any(isinstance(e, BatteryAdded) for e in events)
    assert any(isinstance(e, BatteryPropertiesChanged) for e in events)


def test_battery_removed_only_when_present() -> None:
    store = DeviceStore()
    battery = BatteryReport(serial_number="BAT1", properties={"socLevel": 10})
    store.merge(_report(batteries=(battery,)))

    snapshot, events = store.merge(_report(batteries=(), batteries_present=False))
    assert not any(isinstance(e, BatteryRemoved) for e in events)
    assert len(snapshot.batteries) == 1

    snapshot, events = store.merge(_report(batteries=(), batteries_present=True))
    assert any(isinstance(e, BatteryRemoved) for e in events)
    assert snapshot.batteries == ()


# --- offline rule ------------------------------------------------------------
def test_default_threshold_is_three() -> None:
    assert DEFAULT_OFFLINE_THRESHOLD == 3


def test_below_threshold_stays_online() -> None:
    store = DeviceStore()
    store.merge(_report())
    assert _fail(store, DEFAULT_OFFLINE_THRESHOLD - 1) == []
    assert store.availability is Availability.ONLINE
    assert store.consecutive_failures == DEFAULT_OFFLINE_THRESHOLD - 1
    # Last good values stay available.
    assert store.snapshot().properties["electricLevel"] == 10


def test_threshold_reached_goes_offline_once() -> None:
    store = DeviceStore()
    store.merge(_report())
    events = _fail(store, DEFAULT_OFFLINE_THRESHOLD)
    assert events == [
        DeviceAvailabilityChanged(
            serial_number=SERIAL,
            previous=Availability.ONLINE,
            current=Availability.OFFLINE,
        )
    ]
    assert store.snapshot().availability is Availability.OFFLINE
    # Further failures while offline emit nothing more.
    assert _fail(store, 5) == []


def test_success_resets_count() -> None:
    store = DeviceStore()
    store.merge(_report())
    _fail(store, DEFAULT_OFFLINE_THRESHOLD - 1)
    store.merge(_report())
    assert store.consecutive_failures == 0
    # Count restarts: two more failures are still below the threshold.
    assert _fail(store, DEFAULT_OFFLINE_THRESHOLD - 1) == []
    assert store.availability is Availability.ONLINE


def test_recovery_after_one_success() -> None:
    store = DeviceStore()
    store.merge(_report())
    _fail(store, DEFAULT_OFFLINE_THRESHOLD)
    snapshot, events = store.merge(_report())
    assert snapshot.availability is Availability.ONLINE
    assert events[0] == DeviceAvailabilityChanged(
        serial_number=SERIAL,
        previous=Availability.OFFLINE,
        current=Availability.ONLINE,
    )


def test_custom_threshold() -> None:
    store = DeviceStore(offline_threshold=1)
    store.merge(_report())
    assert len(_fail(store, 1)) == 1
    assert store.availability is Availability.OFFLINE


def test_invalid_threshold_rejected() -> None:
    with pytest.raises(ValidationError):
        DeviceStore(offline_threshold=0)


def test_failures_before_first_contact_emit_nothing() -> None:
    store = DeviceStore()
    assert _fail(store, 10) == []
    assert store.availability is Availability.INITIALIZING
    assert store.has_identity is False


def test_offline_logging_once_and_masked(caplog: pytest.LogCaptureFixture) -> None:
    store = DeviceStore()
    store.merge(_report())
    with caplog.at_level(logging.DEBUG, logger="zendure.state.store"):
        _fail(store, DEFAULT_OFFLINE_THRESHOLD + 3)
        store.merge(_report())
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    infos = [r for r in caplog.records if r.levelno == logging.INFO]
    assert len(warnings) == 1
    assert "ZendureConnectionError" in warnings[0].getMessage()
    assert len(infos) == 1
    assert "back online" in infos[0].getMessage()
    assert all(SERIAL not in r.getMessage() for r in caplog.records)


# --- identity pinning ----------------------------------------------------------
def test_different_device_rejected_after_first_contact() -> None:
    store = DeviceStore()
    store.merge(_report())
    with pytest.raises(DeviceMismatchError) as excinfo:
        store.merge(_report(serial_number="OTHERDEV0000001"))
    assert SERIAL not in str(excinfo.value)
    assert store.snapshot().serial_number == SERIAL


def test_expected_serial_pins_first_contact() -> None:
    store = DeviceStore(expected_serial_number=SERIAL)
    with pytest.raises(DeviceMismatchError):
        store.merge(_report(serial_number="OTHERDEV0000001"))
    assert store.has_identity is False


# --- determinism -----------------------------------------------------------------
def test_determinism_same_sequence_same_result() -> None:
    reports = [
        _report(message_id=1, properties={"electricLevel": 10}),
        _report(message_id=2, properties={"electricLevel": 20, "acMode": 2}),
        _report(message_id=3, properties={"electricLevel": 20, "acMode": 1}),
    ]
    store_a, store_b = DeviceStore(), DeviceStore()
    results_a = [store_a.merge(r) for r in reports]
    results_b = [store_b.merge(r) for r in reports]
    for (snap_a, ev_a), (snap_b, ev_b) in zip(results_a, results_b, strict=True):
        assert snap_a == snap_b
        assert ev_a == ev_b
