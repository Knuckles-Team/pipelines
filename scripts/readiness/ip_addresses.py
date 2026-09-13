"""Normalize numeric IP address spellings without network access."""

from __future__ import annotations

import ipaddress


def _numeric_form(raw: str) -> tuple[int, str] | None:
    """Return the base and digits for one browser-compatible IP component."""

    if raw[:2].lower() == "0x":
        digits = raw[2:]
        if all(character.lower() in "0123456789abcdef" for character in digits):
            return 16, digits
        return None
    if not raw.isascii() or not raw.isdecimal():
        return None
    if len(raw) > 1 and raw.startswith("0"):
        return 8, raw[1:]
    return 10, raw


def _ipv4_component(raw: str) -> int | None:
    """Parse a bounded component, using -1 for invalid numeric syntax."""

    form = _numeric_form(raw)
    if form is None:
        return None
    base, digits = form
    limits = {8: 11, 10: 10, 16: 8}
    if not digits or len(digits) > limits[base]:
        return -1
    if base == 8 and any(character not in "01234567" for character in digits):
        return -1
    return int(digits, base)


def _valid_components(numbers: list[int]) -> bool:
    """Check the width assigned to each component in legacy IPv4 syntax."""

    last_bits = 8 * (5 - len(numbers))
    return (
        all(0 <= value <= 255 for value in numbers[:-1])
        and 0 <= numbers[-1] < 1 << last_bits
    )


def _legacy_ipv4_address(host: str) -> ipaddress.IPv4Address | None:
    """Resolve the one-to-four component numeric IPv4 forms browsers accept."""

    parts = host.split(".")
    if not 1 <= len(parts) <= 4:
        return None
    values = [_ipv4_component(part) for part in parts]
    if any(value is None for value in values):
        return None
    numbers = [int(value) for value in values]
    if not _valid_components(numbers):
        return ipaddress.IPv4Address(0)
    address = numbers[-1]
    for index, value in enumerate(numbers[:-1]):
        address |= value << (24 - 8 * index)
    return ipaddress.IPv4Address(address)


def _private_address(host: str) -> bool:
    """Return whether a canonical or browser-compatible address is non-public."""

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = _legacy_ipv4_address(host)
    return address is not None and any(
        (
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_reserved,
            address.is_unspecified,
            address.is_multicast,
        )
    )
