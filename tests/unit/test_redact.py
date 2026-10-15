"""Tests for identifier masking."""

from zendure._redact import mask_serial


def test_mask_keeps_prefix() -> None:
    assert mask_serial("TESTDEV00000001") == "TEST***"


def test_mask_short_value_fully_hidden() -> None:
    assert mask_serial("ABCD") == "***"
    assert mask_serial("") == "***"
