"""Public-network egress policy for customer webhook destinations.

Registration performs cheap syntactic and IP-literal checks. Delivery resolves
again and pins the validated address for the connection, so a hostname cannot
rebind into the service network between validation and connect.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass

import httpx

BLOCKED_HOST_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home")
BLOCKED_HOSTS = frozenset({"localhost", "metadata", "metadata.google.internal"})


class EgressError(ValueError):
    """A destination is not a public HTTP(S) endpoint."""


def validate_endpoint_url(value: str) -> str:
    """Reject malformed URLs, credentials, and non-public IP literals."""
    try:
        url = httpx.URL(value)
        port = url.port
    except (httpx.InvalidURL, ValueError) as exc:
        raise EgressError("invalid webhook URL") from exc

    if url.scheme not in {"http", "https"}:
        raise EgressError("url must use http:// or https://")
    if not url.host:
        raise EgressError("url must include a host")
    if url.userinfo:
        raise EgressError("url must not include credentials")
    if url.fragment:
        raise EgressError("url must not include a fragment")
    if port is not None and not 1 <= port <= 65535:
        raise EgressError("invalid webhook port")

    host = url.host.lower().rstrip(".")
    if host in BLOCKED_HOSTS or host.endswith(BLOCKED_HOST_SUFFIXES):
        raise EgressError("private webhook destinations are not allowed")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return value
    if not address.is_global:
        raise EgressError("private webhook destinations are not allowed")
    return value


@dataclass(frozen=True)
class OutboundRequest:
    url: httpx.URL
    headers: dict[str, str]
    extensions: dict[str, str]


def prepare_outbound_request(value: str) -> OutboundRequest:
    """Resolve and validate a destination, then pin the connection address."""
    parsed = httpx.URL(validate_endpoint_url(value))
    host = parsed.host.lower().rstrip(".")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise EgressError(f"cannot resolve webhook host: {host}") from exc

    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for _family, _socktype, _proto, _canonname, sockaddr in records:
        try:
            address = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            raise EgressError(f"invalid address for webhook host: {host}") from None
        if not address.is_global:
            raise EgressError("private webhook destinations are not allowed")
        addresses.append(address)
    if not addresses:
        raise EgressError(f"cannot resolve webhook host: {host}")

    # Prefer IPv4 when both are available; all other addresses were validated.
    address = next((item for item in addresses if item.version == 4), addresses[0])
    pinned = parsed.copy_with(host=address.compressed)
    extensions = {"sni_hostname": host} if parsed.scheme == "https" else {}
    return OutboundRequest(
        url=pinned,
        headers={"Host": parsed.netloc.decode("ascii")},
        extensions=extensions,
    )
