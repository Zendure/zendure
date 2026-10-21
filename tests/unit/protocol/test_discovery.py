"""Tests for mDNS host-name helpers."""

import pytest

from zendure.protocols.local_http.discovery import (
    build_mdns_hostname,
    parse_mdns_hostname,
)


def test_build_strips_spaces() -> None:
    assert build_mdns_hostname("SolarFlow 5000 Max Pro", "DEVSN") == (
        "zendure-SolarFlow5000MaxPro-DEVSN.local"
    )


@pytest.mark.parametrize(
    "hostname",
    [
        "zendure-SolarFlow5000MaxPro-DEVSN.local",
        "zendure-SolarFlow5000MaxPro-DEVSN.local.",
        "ZENDURE-SolarFlow5000MaxPro-DEVSN.LOCAL",
    ],
)
def test_parse_valid(hostname: str) -> None:
    assert parse_mdns_hostname(hostname) == ("SolarFlow5000MaxPro", "DEVSN")


def test_round_trip() -> None:
    name = build_mdns_hostname("SolarFlow5000MaxPro", "DEVSN")
    assert parse_mdns_hostname(name) == ("SolarFlow5000MaxPro", "DEVSN")


@pytest.mark.parametrize(
    "hostname",
    [
        "shelly-plus-1.local",
        "zendure-SolarFlow5000MaxPro.local",
        "zendure--DEVSN.local",
        "zendure-SolarFlow5000MaxPro-DEVSN.lan",
    ],
)
def test_parse_invalid(hostname: str) -> None:
    assert parse_mdns_hostname(hostname) is None
