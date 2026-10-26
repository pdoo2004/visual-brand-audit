"""Syntax checks for a URL that a server-side fetch is allowed to request."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

# Hostnames that can never be a public website.
_BLOCKED_SUFFIXES = (".local", ".localhost", ".internal", ".lan", ".home", ".corp")


def non_public_reason(url: str) -> str | None:
    """Why `url` cannot be a public website, or None if it looks public.

    A server-side fetch must refuse addresses that point back at this machine or a
    private network. This is a syntax-level check only. Callers that connect have
    to re-check the resolved IP address as well.
    """
    parts = urlsplit(url)
    if parts.username or parts.password:
        return "URLs with embedded credentials are not allowed."
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        return "URL has no host."
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        if host == "localhost" or host.endswith(_BLOCKED_SUFFIXES) or "." not in host:
            return "URL must point to a public website, not a local or internal host."
        return None
    if not ip.is_global:
        return "URL must point to a public website, not a private or reserved IP address."
    return None
