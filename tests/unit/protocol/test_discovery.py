"""Tests for mDNS host-name helpers."""

import pytest

from zendure.protocols.local_http.discovery import (
    build_mdns_hostname,
    parse_mdns_hostname,
)


def test_build_strips_spaces() -> None:
    assert build_mdns_hostname("SolarFlow Max 5000 Pro", "DEVSN") == (
        "zendure-SolarFlowMax5000Pro-DEVSN.local"
    )


@pytest.mark.parametrize(
    "hostname",
    [
        "zendure-SolarFlowMax5000Pro-DEVSN.local",
        "zendure-SolarFlowMax5000Pro-DEVSN.local.",
        "ZENDURE-SolarFlowMax5000Pro-DEVSN.LOCAL",
    ],
)
def test_parse_valid(hostname: str) -> None:
    assert parse_mdns_hostname(hostname) == ("SolarFlowMax5000Pro", "DEVSN")


def test_round_trip() -> None:
    name = build_mdns_hostname("SolarFlowMax5000Pro", "DEVSN")
    assert parse_mdns_hostname(name) == ("SolarFlowMax5000Pro", "DEVSN")


@pytest.mark.parametrize(
    "hostname",
    [
        "shelly-plus-1.local",
        "zendure-SolarFlowMax5000Pro.local",
        "zendure--DEVSN.local",
        "zendure-SolarFlowMax5000Pro-DEVSN.lan",
    ],
)
def test_parse_invalid(hostname: str) -> None:
    assert parse_mdns_hostname(hostname) is None
