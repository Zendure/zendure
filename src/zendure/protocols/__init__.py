"""Protocol implementations.

Each protocol is a subpackage implementing the abstract interface in
``base.py`` (discovery / read / write / parse). Protocol-specific details
(endpoints, encoding, scaling) live only here. The first and only
implementation for now is ``local_http`` (zenSDK over local HTTP).
"""
