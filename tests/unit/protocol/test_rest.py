"""Tests for endpoint URLs and write-body construction."""

import json

import pytest

from zendure.exceptions import ValidationError
from zendure.protocols.local_http.rest import (
    MAX_WRITE_BODY_BYTES,
    REPORT_PATH,
    build_url,
    build_write_body,
)


def test_build_url_ipv4() -> None:
    assert str(build_url("192.168.1.50", REPORT_PATH)) == (
        "http://192.168.1.50/properties/report"
    )


def test_build_url_ipv6_bracketed() -> None:
    assert (
        str(build_url("fe80::1", REPORT_PATH)) == "http://[fe80::1]/properties/report"
    )


def test_build_url_with_port() -> None:
    assert build_url("192.168.1.50", REPORT_PATH, port=8080).port == 8080


def test_build_url_invalid_host() -> None:
    with pytest.raises(ValidationError):
        build_url("bad host", REPORT_PATH)


def test_write_body_shape() -> None:
    body = build_write_body("DEVSN", {"acMode": 2}, request_id=7)
    assert json.loads(body) == {"sn": "DEVSN", "id": 7, "properties": {"acMode": 2}}
    assert b" " not in body  # compact separators


def test_write_body_over_limit_rejected() -> None:
    properties = {f"key{i:03d}": 1 for i in range(60)}
    with pytest.raises(ValidationError):
        build_write_body("DEVSN", properties, request_id=1)


def test_write_body_at_typical_size_ok() -> None:
    body = build_write_body(
        "DEVSN",
        {"acMode": 2, "outputLimit": 800, "inputLimit": 0, "smartMode": 1},
        request_id=1,
    )
    assert len(body) <= MAX_WRITE_BODY_BYTES
