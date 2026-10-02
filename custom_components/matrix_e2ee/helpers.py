"""Pure, security-sensitive helpers used by the Matrix client.

Keeping these functions independent from the client makes their fail-closed
rules directly testable and prevents Home Assistant concerns leaking into the
Matrix protocol implementation.
"""

from __future__ import annotations

import re
from typing import Any

_ENCRYPTED_EVENT_TYPES = frozenset(
    {"m.room.encrypted", "MegolmEvent", "OlmEvent", "EncryptedEvent"}
)

# A leading "name:" addressing prefix ("hass:  !cmd") — one word, a colon,
# optional spaces. Users naturally prefix commands with the bot's name in
# chat clients; the command itself must still start with the configured
# prefix after the addressing prefix is stripped.
_ADDRESSING_PREFIX_RE = re.compile(r"[^\s:!@]+:\s*")


def room_allowed(room_id: str, allowed_rooms: list[str]) -> bool:
    """Return whether a room is explicitly allowlisted."""
    return bool(allowed_rooms) and room_id in allowed_rooms


def user_allowed(user_id: str, allowed_users: list[str]) -> bool:
    """Return whether a user is explicitly allowlisted."""
    return bool(allowed_users) and user_id in allowed_users


def parse_command(body: str, prefix: str) -> tuple[str, list[str]] | None:
    """Parse a prefixed command without retaining the raw message body.

    Tolerates a leading addressing prefix ("hass:  !cmd") and leading
    whitespace; the command word itself must still start with the
    configured prefix.
    """
    if not prefix:
        return None
    candidate = body.lstrip()
    if not candidate.startswith(prefix):
        candidate = _ADDRESSING_PREFIX_RE.sub("", candidate, count=1).lstrip()
    if not candidate.startswith(prefix):
        return None
    rest = candidate[len(prefix) :].strip()
    if not rest:
        return None
    parts = rest.split()
    return parts[0], parts[1:]


def requires_verified_sender(room: Any, event: Any) -> bool:
    """Return whether an inbound event must have a verified sender."""
    if getattr(room, "encrypted", False) or getattr(event, "decrypted", False):
        return True
    event_type = getattr(event, "type", None)
    return (
        event_type in _ENCRYPTED_EVENT_TYPES
        or type(event).__name__ in _ENCRYPTED_EVENT_TYPES
    )
