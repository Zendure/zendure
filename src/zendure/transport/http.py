"""aiohttp transport: the only module that touches the network.

Design rules:
- The aiohttp ``ClientSession`` is injected by the caller and is never closed
  here (Home Assistant shares one session across integrations).
- Every request has an explicit total timeout.
- Response bodies are read with a hard size cap, so a misbehaving device cannot
  exhaust memory.
- Requests to one device are serialized with a lock: embedded HTTP servers
  handle few concurrent connections, and refreshes/writes must not overlap.
"""

import asyncio
import json
import logging
from typing import Any, Final

import aiohttp
from yarl import URL

from ..exceptions import (
    MalformedResponseError,
    ZendureConnectionError,
    ZendureProtocolError,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT: Final = 5.0
"""Seconds per request. The old integration used 2 s; calibrate on hardware."""

DEFAULT_MAX_RESPONSE_BYTES: Final = 64 * 1024
"""A full report is ~2 KB; 64 KB leaves ample room while bounding memory."""

_READ_CHUNK = 4096
_JSON_HEADERS: Final = {"Content-Type": "application/json; charset=UTF-8"}


class HttpStatusError(ZendureProtocolError):
    """The device answered with a non-2xx HTTP status.

    ``payload`` is the JSON object body when it could be parsed; otherwise
    ``None``. Write error mapping uses ``payload["code"]`` / ``payload["error"]``.
    """

    def __init__(
        self,
        status: int,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(f"{method} {path} returned HTTP {status}")
        self.status = status
        self.payload = payload


class HttpTransport:
    """Serialized JSON-over-HTTP access to one device."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    ) -> None:
        self._session = session
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._max_response_bytes = max_response_bytes
        self._lock = asyncio.Lock()

    async def get_json(self, url: URL) -> dict[str, Any]:
        """GET ``url`` and return its JSON object body.

        Raises:
            ZendureConnectionError: network failure or timeout.
            HttpStatusError: non-2xx status.
            MalformedResponseError: body too large, not JSON, or not an object.
        """
        payload = await self._request("GET", url, None)
        if payload is None:
            raise MalformedResponseError(f"GET {url.path} returned an empty body")
        return payload

    async def post_json(self, url: URL, body: bytes) -> dict[str, Any] | None:
        """POST a pre-serialized JSON body; return the JSON object reply, if any.

        Raises:
            ZendureConnectionError: network failure or timeout.
            HttpStatusError: non-2xx status.
            MalformedResponseError: reply too large, or neither empty nor a JSON
                object.
        """
        return await self._request("POST", url, body)

    async def _request(
        self, method: str, url: URL, body: bytes | None
    ) -> dict[str, Any] | None:
        path = url.path
        async with self._lock:
            try:
                async with self._session.request(
                    method,
                    url,
                    data=body,
                    headers=_JSON_HEADERS if body is not None else None,
                    timeout=self._timeout,
                ) as response:
                    raw = await self._read_capped(response, method, path)
                    status = response.status
            except (aiohttp.ClientError, TimeoutError) as err:
                _LOGGER.debug("%s %s failed: %s", method, path, type(err).__name__)
                raise ZendureConnectionError(
                    f"{method} {path} failed: {type(err).__name__}"
                ) from err

        if not 200 <= status < 300:
            payload: dict[str, Any] | None
            try:
                payload = _decode_object(raw, method, path)
            except MalformedResponseError:
                payload = None
            raise HttpStatusError(status, method, path, payload)
        return _decode_object(raw, method, path)

    async def _read_capped(
        self, response: aiohttp.ClientResponse, method: str, path: str
    ) -> bytes:
        buffer = bytearray()
        while chunk := await response.content.read(_READ_CHUNK):
            buffer.extend(chunk)
            if len(buffer) > self._max_response_bytes:
                raise MalformedResponseError(
                    f"{method} {path} response exceeds {self._max_response_bytes} bytes"
                )
        return bytes(buffer)


def _decode_object(raw: bytes, method: str, path: str) -> dict[str, Any] | None:
    if not raw.strip():
        return None
    try:
        decoded = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise MalformedResponseError(f"{method} {path} returned invalid JSON") from err
    if not isinstance(decoded, dict):
        raise MalformedResponseError(f"{method} {path} JSON is not an object")
    return decoded


__all__ = [
    "DEFAULT_MAX_RESPONSE_BYTES",
    "DEFAULT_TIMEOUT",
    "HttpStatusError",
    "HttpTransport",
]
