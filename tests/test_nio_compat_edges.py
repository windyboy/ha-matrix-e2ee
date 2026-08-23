"""Edge-case coverage for matrix-nio SAS compatibility patches."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

import custom_components.matrix_e2ee.nio_compat as nio_compat
from custom_components.matrix_e2ee.nio_compat import (
    _apply_sas_commitment_patch,
    _apply_sas_emoji_patch,
    _apply_sas_mac_patch,
    _apply_sas_timeout_patch,
)


class SasState:
    canceled = "canceled"
    key_received = "key_received"
    mac_received = "mac_received"


def _calc_mac(*_args: object) -> bytes:
    return b"MAC"


class ReceiveSas:
    """SAS stand-in with only the values used by MAC error paths."""

    def __init__(self) -> None:
        self.verified = False
        self.state = SasState.key_received
        self.sas_accepted = True
        self.cancel_code = None
        self.cancel_reason = None
        self._unexpected_message_error = ("m.unexpected_message", "unexpected")
        self._key_mismatch_error = ("m.key_mismatch", "mismatch")
        self._invalid_message_error = ("m.invalid_message", "invalid")
        self.other_olm_device = SimpleNamespace(
            user_id="@peer:example.org", id="PEERDEV", ed25519="PEERKEY"
        )
        self.own_user = "@me:example.org"
        self.own_device = "MYDEV"
        self.own_fp_key = "MYKEY"
        self.transaction_id = "txn"
        self.chosen_mac_method = "hkdf-hmac-sha256.v2"
        self.established_sas = SimpleNamespace(calculate_mac=_calc_mac)
        self.verified_devices: list[str] = []

    def _event_ok(self, _event: object) -> bool:
        return True


_apply_sas_mac_patch(ReceiveSas, lambda *_args: None, RuntimeError, SasState)


def _event(key_id: str = "ed25519:PEERDEV") -> SimpleNamespace:
    return SimpleNamespace(keys=b"MAC", mac={key_id: b"MAC"})


def test_timeout_patch_returns_false_for_verified_sas() -> None:
    """Completed SAS verifications cannot time out."""

    class TimeoutSas:
        _max_age = timedelta(minutes=5)
        _timeout_error = ("m.timeout", "timed out")
        verified = True
        canceled = False

        def __init__(self) -> None:
            self.creation_time = datetime.now() - timedelta(minutes=6)

    _apply_sas_timeout_patch(TimeoutSas, SasState.canceled)

    assert TimeoutSas().timed_out is False


@pytest.mark.parametrize(
    ("case", "expected_state", "expected_code"),
    [
        ("verified", SasState.key_received, None),
        ("invalid_event", SasState.key_received, None),
        ("wrong_state", SasState.canceled, "m.unexpected_message"),
        ("mismatched_keys", SasState.canceled, "m.key_mismatch"),
        ("malformed_key_id", SasState.canceled, "m.invalid_message"),
        ("wrong_key_type", SasState.canceled, "m.key_mismatch"),
    ],
)
def test_receive_mac_event_early_returns(
    case: str, expected_state: str, expected_code: str | None
) -> None:
    """MAC protocol early exits preserve state or cancel with the correct reason."""
    sas = ReceiveSas()
    event = _event()

    if case == "verified":
        sas.verified = True
    elif case == "invalid_event":
        sas._event_ok = lambda _event: False
    elif case == "wrong_state":
        sas.state = "accepted"
    elif case == "mismatched_keys":
        event = SimpleNamespace(keys=b"wrong", mac={})
    elif case == "malformed_key_id":
        event = _event("not-a-key-id")
    elif case == "wrong_key_type":
        event = _event("curve25519:PEERDEV")

    sas.receive_mac_event(event)

    assert sas.state == expected_state
    assert sas.cancel_code == expected_code


def test_get_mac_rejects_unaccepted_or_canceled_sas() -> None:
    """MAC generation rejects an unaccepted or canceled verification."""
    sas = ReceiveSas()
    sas.sas_accepted = False
    with pytest.raises(RuntimeError, match="wasn't yet accepted"):
        sas.get_mac()

    sas.sas_accepted = True
    sas.state = SasState.canceled
    with pytest.raises(RuntimeError, match="was canceled"):
        sas.get_mac()


def test_patch_application_is_idempotent() -> None:
    """Each patch function returns immediately when already applied."""

    class TimeoutSas:
        pass

    class CommitmentSas:
        @classmethod
        def from_key_verification_start(cls, *_args):
            return cls()

    class EmojiSas:
        pass

    class MacSas:
        pass

    _apply_sas_timeout_patch(TimeoutSas, SasState.canceled)
    _apply_sas_timeout_patch(TimeoutSas, SasState.canceled)
    _apply_sas_commitment_patch(CommitmentSas, str)
    _apply_sas_commitment_patch(CommitmentSas, str)
    _apply_sas_emoji_patch(EmojiSas)
    _apply_sas_emoji_patch(EmojiSas)
    _apply_sas_mac_patch(MacSas, lambda *_args: None, RuntimeError, SasState)
    _apply_sas_mac_patch(MacSas, lambda *_args: None, RuntimeError, SasState)


def test_installed_version_cache_and_absent_nio_are_safe(monkeypatch) -> None:
    """The version cache avoids metadata rereads and absent nio is a no-op."""
    reads: list[int] = []

    def read_version() -> str:
        reads.append(1)
        return "0.26.0"

    monkeypatch.setattr(nio_compat, "_read_installed_nio_version", read_version)
    monkeypatch.setattr(nio_compat, "_INSTALLED_NIO_VERSION", nio_compat._UNSET)

    assert nio_compat._installed_nio_version() == "0.26.0"
    assert nio_compat._installed_nio_version() == "0.26.0"
    assert reads == [1]

    monkeypatch.setattr(nio_compat, "Sas", None)
    monkeypatch.setattr(nio_compat, "SasState", None)
    monkeypatch.setattr(nio_compat, "Api", None)
    monkeypatch.setattr(nio_compat, "ToDeviceMessage", None)
    monkeypatch.setattr(nio_compat, "LocalProtocolError", None)
    nio_compat.apply_nio_compat_patches()


def test_patch_wrappers_apply_when_nio_is_available(monkeypatch) -> None:
    """Every version-specific wrapper calls its patch when dependencies exist."""

    class Sas:
        @classmethod
        def from_key_verification_start(cls, *_args):
            return cls()

    monkeypatch.setattr(nio_compat, "Sas", Sas)
    monkeypatch.setattr(nio_compat, "SasState", SasState)
    monkeypatch.setattr(
        nio_compat, "Api", SimpleNamespace(to_canonical_json=lambda value: value)
    )
    monkeypatch.setattr(nio_compat, "ToDeviceMessage", lambda *_args: None)
    monkeypatch.setattr(nio_compat, "LocalProtocolError", RuntimeError)

    nio_compat._patch_nio_sas_timeout()
    nio_compat._patch_nio_sas_commitment()
    nio_compat._patch_nio_sas_emoji()
    nio_compat._patch_nio_sas_mac()
