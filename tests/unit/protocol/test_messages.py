"""Tests for parsing zenSDK report JSON into DeviceReport."""

from typing import Any

import pytest

from zendure.exceptions import (
    DeviceMismatchError,
    MalformedResponseError,
    WriteRejectedError,
)
from zendure.protocols.local_http.messages import (
    MAX_BATTERIES,
    parse_report,
    parse_write_response,
)


def test_identity_from_top_level(report_max5000pro: dict[str, Any]) -> None:
    report = parse_report(report_max5000pro)
    assert report.serial_number == "TESTDEV00000001"
    assert report.model_key == "max_5000_pro"
    assert report.product_raw == "SolarFlowMax5000Pro"
    assert report.protocol_version == 3
    assert report.message_id == 1
    assert report.timestamp == 1791959594


def test_device_values_decoded(report_max5000pro: dict[str, Any]) -> None:
    props = parse_report(report_max5000pro).properties
    assert props["socSet"] == 100.0
    assert props["minSoc"] == 10.0
    assert props["hyperTmp"] == 34.0
    assert props["remainOutTime"] is None
    assert props["electricLevel"] == 10
    assert props["inverseMaxPower"] == 800


def test_unknown_keys_kept_raw(report_max5000pro: dict[str, Any]) -> None:
    # Not in the catalog: kept as raw values, never turned into entities here.
    assert parse_report(report_max5000pro).properties["acCouplingState"] == 57344


def test_battery_decoded(report_max5000pro: dict[str, Any]) -> None:
    report = parse_report(report_max5000pro)
    assert report.batteries_present is True
    (battery,) = report.batteries
    assert battery.serial_number == "TESTBAT00000001"
    assert battery.pack_type == 500
    assert "sn" not in battery.properties
    assert "packType" not in battery.properties
    assert battery.properties["totalVol"] == 48.10
    assert battery.properties["maxVol"] == 3.21
    assert battery.properties["maxTemp"] == 32.0
    assert battery.properties["softVersion"] == "1.1.3"


def test_real_2400_product_is_supported(report_2400acplus: dict[str, Any]) -> None:
    report = parse_report(report_2400acplus)
    assert report.model_key == "solarflow_2400ac_plus"
    assert report.product_raw == "solarFlow2400AC+"


@pytest.mark.parametrize("field", ["sn", "product"])
def test_missing_identity_rejected(
    report_max5000pro: dict[str, Any], field: str
) -> None:
    del report_max5000pro[field]
    with pytest.raises(MalformedResponseError):
        parse_report(report_max5000pro)


def test_empty_serial_rejected(report_max5000pro: dict[str, Any]) -> None:
    report_max5000pro["sn"] = ""
    with pytest.raises(MalformedResponseError):
        parse_report(report_max5000pro)


def test_properties_not_object_rejected(report_max5000pro: dict[str, Any]) -> None:
    report_max5000pro["properties"] = [1, 2]
    with pytest.raises(MalformedResponseError):
        parse_report(report_max5000pro)


def test_missing_packdata_not_present(report_max5000pro: dict[str, Any]) -> None:
    del report_max5000pro["packData"]
    report = parse_report(report_max5000pro)
    assert report.batteries_present is False
    assert report.batteries == ()


def test_packdata_not_list_rejected(report_max5000pro: dict[str, Any]) -> None:
    report_max5000pro["packData"] = {"sn": "X"}
    with pytest.raises(MalformedResponseError):
        parse_report(report_max5000pro)


def test_too_many_batteries_rejected(report_max5000pro: dict[str, Any]) -> None:
    report_max5000pro["packData"] = [
        {"sn": f"BAT{i}"} for i in range(MAX_BATTERIES + 1)
    ]
    with pytest.raises(MalformedResponseError):
        parse_report(report_max5000pro)


def test_invalid_packs_skipped(report_max5000pro: dict[str, Any]) -> None:
    report_max5000pro["packData"] = ["junk", {"socLevel": 5}, {"sn": "BAT1"}]
    report = parse_report(report_max5000pro)
    assert [b.serial_number for b in report.batteries] == ["BAT1"]


def test_non_scalar_values_dropped(report_max5000pro: dict[str, Any]) -> None:
    report_max5000pro["properties"]["nested"] = {"a": 1}
    report_max5000pro["properties"]["listy"] = [1]
    props = parse_report(report_max5000pro).properties
    assert "nested" not in props
    assert "listy" not in props


def test_bool_becomes_int(report_max5000pro: dict[str, Any]) -> None:
    report_max5000pro["properties"]["lampSwitch"] = True
    assert parse_report(report_max5000pro).properties["lampSwitch"] == 1


def test_non_int_metadata_ignored(report_max5000pro: dict[str, Any]) -> None:
    report_max5000pro["messageId"] = "1"
    report_max5000pro["version"] = True
    report = parse_report(report_max5000pro)
    assert report.message_id is None
    assert report.protocol_version is None


# --- properties/write response ----------------------------------------------
_SN = "TESTDEV00000001"


def _write_ok() -> dict[str, Any]:
    # Confirmed real-device success reply for POST /properties/write.
    return {
        "timestamp": 1791966822,
        "messageId": 21,
        "success": True,
        "code": 200,
        "sn": _SN,
    }


def test_write_response_success_accepted() -> None:
    assert parse_write_response(_write_ok(), _SN) is None


def test_write_response_ignores_message_id() -> None:
    # messageId is not correlated with the request id (device may reset it).
    payload = _write_ok()
    payload["messageId"] = 999_999
    del payload["timestamp"]
    parse_write_response(payload, _SN)


@pytest.mark.parametrize("payload", [None, {}, [], "ok", 200])
def test_write_response_empty_or_not_object(payload: Any) -> None:
    with pytest.raises(MalformedResponseError):
        parse_write_response(payload, _SN)


@pytest.mark.parametrize("field", ["success", "code", "sn"])
def test_write_response_missing_field(field: str) -> None:
    payload = _write_ok()
    del payload[field]
    with pytest.raises(MalformedResponseError):
        parse_write_response(payload, _SN)


@pytest.mark.parametrize("success", [1, 0, "true", None, "false"])
def test_write_response_success_must_be_bool(success: object) -> None:
    payload = _write_ok()
    payload["success"] = success
    with pytest.raises(MalformedResponseError):
        parse_write_response(payload, _SN)


@pytest.mark.parametrize("code", [True, False, 200.0, "200", None])
def test_write_response_code_must_be_int(code: object) -> None:
    payload = _write_ok()
    payload["code"] = code
    with pytest.raises(MalformedResponseError):
        parse_write_response(payload, _SN)


@pytest.mark.parametrize("sn", ["", None, 123])
def test_write_response_sn_must_be_non_empty_str(sn: object) -> None:
    payload = _write_ok()
    payload["sn"] = sn
    with pytest.raises(MalformedResponseError):
        parse_write_response(payload, _SN)


def test_write_response_sn_mismatch() -> None:
    payload = _write_ok()
    payload["sn"] = "OTHERDEV0000002"
    with pytest.raises(DeviceMismatchError) as excinfo:
        parse_write_response(payload, _SN)
    assert excinfo.value.expected == _SN
    assert excinfo.value.actual == "OTHERDEV0000002"


def test_write_response_mismatch_wins_over_rejection() -> None:
    payload = _write_ok()
    payload.update(sn="OTHERDEV0000002", success=False, code=500)
    with pytest.raises(DeviceMismatchError):
        parse_write_response(payload, _SN)


@pytest.mark.parametrize(
    ("success", "code"),
    [(False, 500), (False, 200), (True, 201), (True, 0), (False, -1)],
)
def test_write_response_rejected_carries_code(success: bool, code: int) -> None:
    payload = _write_ok()
    payload.update(success=success, code=code)
    with pytest.raises(WriteRejectedError) as excinfo:
        parse_write_response(payload, _SN)
    # Unknown codes keep the number in a Chinese fallback; known 400 on HTTP 200
    # is the TLV write failure.
    assert excinfo.value.code == code
    if code == 400:
        assert str(excinfo.value) == "属性写入失败"
    else:
        assert str(code) in str(excinfo.value)
