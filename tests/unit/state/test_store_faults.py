"""Tests for merging fault reports into the device store."""

import logging
from datetime import UTC, datetime

import pytest

from zendure.events import FaultCleared, FaultRaised
from zendure.exceptions import ZendureConnectionError
from zendure.models import Availability
from zendure.state.report import DeviceReport, FaultReport
from zendure.state.store import DeviceStore

SERIAL = "TESTDEV00000001"


def _store(**kwargs: object) -> DeviceStore:
    store = DeviceStore(**kwargs)  # type: ignore[arg-type]
    store.merge(
        DeviceReport(
            serial_number=SERIAL,
            model_key="solarflow_5000_max_pro",
            product_raw="SolarFlow5000MaxPro",
            properties={"electricLevel": 10},
        )
    )
    return store


def _faults(*codes: int, since: dict[int, int] | None = None) -> FaultReport:
    return FaultReport(codes=codes, since=since or {})


def test_faults_unknown_before_first_read() -> None:
    assert _store().snapshot().active_faults is None


def test_first_read_raises_every_active_code() -> None:
    snapshot, events = _store().merge_faults(_faults(6, 202))
    assert snapshot.active_faults == (6, 202)
    assert events == [
        FaultRaised(serial_number=SERIAL, code=6),
        FaultRaised(serial_number=SERIAL, code=202),
    ]


def test_first_read_without_faults_emits_nothing() -> None:
    snapshot, events = _store().merge_faults(_faults())
    assert snapshot.active_faults == ()
    assert events == []


def test_only_changes_are_emitted() -> None:
    store = _store()
    store.merge_faults(_faults(6, 202))
    _, events = store.merge_faults(_faults(202, 205))
    assert events == [
        FaultRaised(serial_number=SERIAL, code=205),
        FaultCleared(serial_number=SERIAL, code=6),
    ]
    _, events = store.merge_faults(_faults(202, 205))
    assert events == []


def test_failure_makes_faults_unknown_without_touching_availability() -> None:
    store = _store()
    store.merge_faults(_faults(6))
    store.record_fault_failure(ZendureConnectionError("timeout"))
    snapshot = store.snapshot()
    assert snapshot.active_faults is None
    assert snapshot.availability is Availability.ONLINE
    assert store.consecutive_failures == 0


def test_recovery_compares_with_last_known_faults() -> None:
    store = _store()
    store.merge_faults(_faults(6))
    store.record_fault_failure(ZendureConnectionError("timeout"))
    snapshot, events = store.merge_faults(_faults(6))
    assert snapshot.active_faults == (6,)
    assert events == []


def test_outage_logs_one_warning_and_one_recovery(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = _store()
    store.merge_faults(_faults())
    with caplog.at_level(logging.DEBUG):
        for _ in range(3):
            store.record_fault_failure(ZendureConnectionError("timeout"))
        store.merge_faults(_faults())
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "readable again" in caplog.text
    assert SERIAL not in caplog.text


def test_failure_before_any_read_only_logs_debug(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = _store()
    with caplog.at_level(logging.DEBUG):
        store.record_fault_failure(ZendureConnectionError("timeout"))
        store.merge_faults(_faults())
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert "readable again" not in caplog.text


def test_fault_changes_log_info_once(caplog: pytest.LogCaptureFixture) -> None:
    store = _store()
    with caplog.at_level(logging.INFO):
        store.merge_faults(_faults(6))
        store.merge_faults(_faults(6))
        store.merge_faults(_faults())
    messages = [r.getMessage() for r in caplog.records]
    assert len(messages) == 2
    assert "fault 6 raised" in messages[0]
    assert "fault 6 cleared" in messages[1]


def test_device_merge_keeps_faults() -> None:
    store = _store()
    store.merge_faults(_faults(6))
    snapshot, _ = store.merge(
        DeviceReport(
            serial_number=SERIAL,
            model_key="solarflow_5000_max_pro",
            product_raw="SolarFlow5000MaxPro",
            properties={"electricLevel": 11},
        )
    )
    assert snapshot.active_faults == (6,)


def test_fault_since_follows_active_faults() -> None:
    store = _store()
    snapshot, _ = store.merge_faults(_faults(6, 202, since={6: 1793085345}))
    assert snapshot.fault_since == {6: datetime(2026, 10, 27, 7, 15, 45, tzinfo=UTC)}
    store.record_fault_failure(ZendureConnectionError("timeout"))
    assert store.snapshot().fault_since == {}
    snapshot, _ = store.merge_faults(_faults())
    assert snapshot.fault_since == {}
