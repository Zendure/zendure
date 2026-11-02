"""Tests for parsing ``properties/error`` replies."""

from typing import Any

import pytest

from zendure.exceptions import MalformedResponseError
from zendure.protocols.local_http.messages import MAX_FAULT_ENTRIES, parse_fault_report

TS = 1793085345


def _payload(*entries: object, **overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "messageId": 30,
        "timestamp": TS,
        "deviceId": "VB2nRuA2",
        "productKey": "vCK12r",
        "offData": 0,
        "eventId": 3,
        "data": list(entries),
    }
    payload.update(overrides)
    return payload


def test_parses_device_sample() -> None:
    report = parse_fault_report(
        _payload(
            {"code": 6, "timestamp": TS},
            {"code": 202, "timestamp": TS},
            {"code": 205, "timestamp": TS},
        )
    )
    assert report.codes == (6, 202, 205)
    assert report.since == {6: TS, 202: TS, 205: TS}
    assert report.message_id == 30
    assert report.timestamp == TS


def test_empty_data_means_no_fault() -> None:
    report = parse_fault_report(_payload())
    assert report.codes == ()
    assert report.since == {}


def test_code_zero_is_skipped() -> None:
    report = parse_fault_report(_payload({"code": 0, "timestamp": TS}))
    assert report.codes == ()


def test_keeps_order_and_first_timestamp_of_duplicates() -> None:
    report = parse_fault_report(
        _payload(
            {"code": 205, "timestamp": TS},
            {"code": 6, "timestamp": TS + 1},
            {"code": 205, "timestamp": TS + 2},
        )
    )
    assert report.codes == (205, 6)
    assert report.since == {205: TS, 6: TS + 1}


@pytest.mark.parametrize("timestamp", [None, "x", -1, 0, 10**12, True])
def test_missing_or_bad_timestamp_keeps_code(timestamp: object) -> None:
    report = parse_fault_report(_payload({"code": 6, "timestamp": timestamp}))
    assert report.codes == (6,)
    assert report.since == {}


def test_no_entry_timestamp_at_all() -> None:
    assert parse_fault_report(_payload({"code": 6})).codes == (6,)


@pytest.mark.parametrize("data", [None, "6", {"code": 6}])
def test_rejects_data_not_a_list(data: object) -> None:
    with pytest.raises(MalformedResponseError):
        parse_fault_report(_payload(data=data))


def test_rejects_missing_data() -> None:
    payload = _payload()
    del payload["data"]
    with pytest.raises(MalformedResponseError):
        parse_fault_report(payload)


@pytest.mark.parametrize(
    "entry",
    [6, None, {}, {"code": -1}, {"code": 6.0}, {"code": "6"}, {"code": True}],
)
def test_rejects_invalid_entry(entry: object) -> None:
    with pytest.raises(MalformedResponseError):
        parse_fault_report(_payload(entry))


def test_rejects_too_many_entries() -> None:
    entries = [{"code": 0}] * (MAX_FAULT_ENTRIES + 1)
    with pytest.raises(MalformedResponseError):
        parse_fault_report(_payload(*entries))
