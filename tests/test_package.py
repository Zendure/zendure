"""Smoke test for the package skeleton."""

import zendure


def test_version_is_nonempty_string() -> None:
    assert isinstance(zendure.__version__, str)
    assert zendure.__version__
