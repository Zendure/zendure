"""zenSDK REST endpoints and write-request construction."""

import json
from collections.abc import Mapping
from typing import Final

from yarl import URL

from ...exceptions import ValidationError

REPORT_PATH: Final = "/properties/report"
WRITE_PATH: Final = "/properties/write"

MAX_WRITE_BODY_BYTES: Final = 512
"""Device-side receive limit for the local API (zenSDK README)."""


def build_url(host: str, path: str, *, port: int | None = None) -> URL:
    """Build an ``http://`` URL; IPv6 hosts are bracketed by yarl.

    Raises:
        ValidationError: ``host`` or ``port`` is not valid.
    """
    try:
        return URL.build(scheme="http", host=host, port=port, path=path)
    except ValueError as err:
        raise ValidationError(f"invalid device host {host!r}") from err


def build_write_body(
    serial_number: str,
    properties: Mapping[str, int],
    *,
    request_id: int,
) -> bytes:
    """Serialize a ``properties/write`` request compactly.

    Raises:
        ValidationError: the body exceeds the device's 512-byte limit.
    """
    payload = {"sn": serial_number, "id": request_id, "properties": dict(properties)}
    body = json.dumps(payload, separators=(",", ":")).encode()
    if len(body) > MAX_WRITE_BODY_BYTES:
        raise ValidationError(
            f"write body is {len(body)} bytes; device limit is {MAX_WRITE_BODY_BYTES}"
        )
    return body


__all__ = [
    "MAX_WRITE_BODY_BYTES",
    "REPORT_PATH",
    "WRITE_PATH",
    "build_url",
    "build_write_body",
]
