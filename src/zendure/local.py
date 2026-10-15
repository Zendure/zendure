"""Factory wiring ``ZendureClient`` to the zenSDK local-HTTP protocol.

Kept outside ``client.py`` so the client depends only on the abstract protocol
interface; this module is the one place that picks the concrete protocol.
"""

import aiohttp

from .client import ZendureClient
from .protocols.local_http import LocalHttpProtocol
from .state.store import DEFAULT_OFFLINE_THRESHOLD
from .transport.http import DEFAULT_TIMEOUT
from .transport.poller import DEFAULT_MAX_BACKOFF, DEFAULT_SCAN_INTERVAL


def create_local_client(
    host: str,
    session: aiohttp.ClientSession,
    *,
    port: int | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    offline_threshold: int = DEFAULT_OFFLINE_THRESHOLD,
    expected_serial_number: str | None = None,
    scan_interval: float = DEFAULT_SCAN_INTERVAL,
    max_backoff: float = DEFAULT_MAX_BACKOFF,
) -> ZendureClient:
    """Create a client for a device on the LAN at ``host`` (IP or mDNS name).

    ``session`` is shared and never closed by the library. Pass
    ``expected_serial_number`` (e.g. from a config entry) to refuse a different
    device answering on the same host.

    Raises:
        ValidationError: invalid host, port, or threshold.
    """
    protocol = LocalHttpProtocol(host, session, port=port, timeout=timeout)
    return ZendureClient(
        protocol,
        offline_threshold=offline_threshold,
        expected_serial_number=expected_serial_number,
        scan_interval=scan_interval,
        max_backoff=max_backoff,
    )


__all__ = ["create_local_client"]
