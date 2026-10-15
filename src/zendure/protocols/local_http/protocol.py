"""zenSDK local-HTTP implementation of ``DeviceProtocol``."""

from collections.abc import Mapping

import aiohttp

from ...exceptions import WriteRejectedError
from ...state.report import DeviceReport
from ...transport.http import DEFAULT_TIMEOUT, HttpStatusError, HttpTransport
from ..base import DeviceProtocol
from .codec import encode_property
from .messages import parse_report, parse_write_response
from .rest import REPORT_PATH, WRITE_PATH, build_url, build_write_body
from .write_errors import write_error_message


class LocalHttpProtocol(DeviceProtocol):
    """Talks to one device at ``host`` via ``GET/POST /properties/*``."""

    def __init__(
        self,
        host: str,
        session: aiohttp.ClientSession,
        *,
        port: int | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._report_url = build_url(host, REPORT_PATH, port=port)
        self._write_url = build_url(host, WRITE_PATH, port=port)
        self._transport = HttpTransport(session, timeout=timeout)
        self._request_id = 0

    async def async_read(self) -> DeviceReport:
        """Fetch ``properties/report`` and decode it into a ``DeviceReport``."""
        return parse_report(await self._transport.get_json(self._report_url))

    async def async_write(
        self, serial_number: str, values: Mapping[str, int | float]
    ) -> None:
        """Encode and POST validated values to ``properties/write``.

        A success reply (``success: true``, ``code: 200``, matching ``sn``)
        means the device accepted the request; whether it applied the value is
        confirmed by the caller reading state back.

        Raises:
            ValidationError: a value cannot be encoded, or the body is too big.
            WriteRejectedError: non-2xx HTTP status (``code`` is ``None``, the
                ``HttpStatusError`` is the cause), or a failure reply (``code``
                is the device's raw code).
            MalformedResponseError: the reply is empty or not the expected shape.
            DeviceMismatchError: the reply came from a different device.
            ZendureConnectionError: network failure or timeout (outcome unknown).
        """
        raw = {key: encode_property(key, value) for key, value in values.items()}
        self._request_id += 1
        body = build_write_body(serial_number, raw, request_id=self._request_id)
        try:
            reply = await self._transport.post_json(self._write_url, body)
        except HttpStatusError as err:
            payload = err.payload if isinstance(err.payload, dict) else {}
            raw_code = payload.get("code", err.status)
            code = (
                raw_code
                if isinstance(raw_code, int) and not isinstance(raw_code, bool)
                else err.status
            )
            error_text = payload.get("error")
            raise WriteRejectedError(
                write_error_message(
                    code,
                    error_text if isinstance(error_text, str) else None,
                    http_status=err.status,
                ),
                code=code,
            ) from err
        parse_write_response(reply, serial_number)


__all__ = ["LocalHttpProtocol"]
