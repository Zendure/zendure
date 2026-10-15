"""zenSDK local-HTTP protocol: discovery, REST, codec, and message parsing."""

from .discovery import build_mdns_hostname, parse_mdns_hostname
from .messages import parse_report
from .protocol import LocalHttpProtocol

__all__ = [
    "LocalHttpProtocol",
    "build_mdns_hostname",
    "parse_mdns_hostname",
    "parse_report",
]
