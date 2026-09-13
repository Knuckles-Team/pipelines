"""RFC-reserved documentation hosts, and internal hostnames that are not reserved.

RFC 2606/6761 documentation domains, RFC 5737/3927/3849 reserved address
blocks and localhost can never resolve to (or disclose) a real host, so a
fixture built on one of these is provably synthetic.
"""

from __future__ import annotations

import ipaddress
import re

_DOCUMENTATION_TLDS = frozenset({"test", "example", "invalid", "localhost"})
_EXAMPLE_DOMAINS = frozenset({"example.com", "example.net", "example.org"})
_IPV4_RESERVED = tuple(
    ipaddress.ip_network(cidr)
    for cidr in ("127.0.0.0/8", "0.0.0.0/32", "192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24", "169.254.0.0/16")
)
_IPV6_RESERVED = tuple(ipaddress.ip_network(cidr) for cidr in ("fe80::/10", "2001:db8::/32"))
_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
BARE_INTERNAL_HOSTNAME_RE = re.compile(
    rf"(?<![A-Za-z0-9_.-])(?:(?:{_LABEL}\.)+(?:arpa|internal|corp|lan)|(?:{_LABEL}\.)*svc\.cluster\.local)(?![A-Za-z0-9_.-])"
)


def _is_reserved_address(candidate: str) -> bool:
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        return False
    networks = _IPV6_RESERVED if address.version == 6 else _IPV4_RESERVED
    return any(address in network for network in networks)


def _is_reserved_name(candidate: str) -> bool:
    labels = candidate.split(".")
    return (
        candidate == "localhost"
        or candidate.endswith(".localhost")
        # Docker's own universal convention; a fixed literal, not a suffix rule.
        or candidate == "host.docker.internal"
        or candidate in _EXAMPLE_DOMAINS
        or any(candidate.endswith(f".{domain}") for domain in _EXAMPLE_DOMAINS)
        # The fleet's fixture convention: the LEADING label names the fake host.
        or labels[0] == "example"
        or labels[0].startswith("example-")
        or labels[-1] in _DOCUMENTATION_TLDS
    )


def is_reserved_hostname(host: str) -> bool:
    """Whether a hostname or address is reserved for documentation."""
    candidate = host.strip().rstrip(".").casefold()
    return bool(candidate) and (_is_reserved_name(candidate) or _is_reserved_address(candidate))


def internal_endpoint_in_line(line: str) -> bool:
    """Whether a line contains a non-reserved internal-hostname literal."""
    return any(not is_reserved_hostname(m.group(0)) for m in BARE_INTERNAL_HOSTNAME_RE.finditer(line))
