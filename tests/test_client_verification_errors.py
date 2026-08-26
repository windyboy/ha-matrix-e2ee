"""Client verification failure-path tests."""

from __future__ import annotations

import pytest

from custom_components.matrix_e2ee.client import MatrixE2EEClient, MatrixE2EEError
from custom_components.matrix_e2ee.const import (
    ERROR_DEVICE_MISSING,
    ERROR_ENCRYPTION_UNAVAILABLE,
    ERROR_FINGERPRINT_MISMATCH,
    ERROR_INVALID_TRANSACTION,
    ERROR_SEND_FAILED,
)
from tests.fakes import FakeNio, FakeSas

USER = "@peer:example.org"
DEVICE = "PEERDEV"
TXN = "txn-peerdev"


async def _client(tmp_path) -> tuple[MatrixE2EEClient, FakeNio]:
    created: dict[str, FakeNio] = {}

    def factory(homeserver, user, **kwargs):
        nio = FakeNio(homeserver, user, **kwargs)
        created["nio"] = nio
        return nio

    client = MatrixE2EEClient(
        config_dir=tmp_path,
        homeserver="https://matrix.example.org",
        username="@bot:example.org",
        password="pw",
        allowed_rooms=[],
        allowed_users=[],
        verification_peer_users=[USER],
        command_prefix="!",
        fire_event=lambda _event, _data: None,
        nio_client_factory=factory,
    )
    await client.async_start()
    return client, created["nio"]


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("missing_device", ERROR_DEVICE_MISSING),
        ("unavailable", ERROR_ENCRYPTION_UNAVAILABLE),
        ("raises", ERROR_SEND_FAILED),
        ("error_response", ERROR_SEND_FAILED),
        ("missing_transaction", ERROR_INVALID_TRANSACTION),
    ],
)
async def test_start_verification_rejects_protocol_failures(
    tmp_path, case: str, expected: str
) -> None:
    """Starting SAS emits a stable public error for every failed prerequisite."""
    client, nio = await _client(tmp_path)

    if case != "missing_device":
        nio.add_device(USER, DEVICE)
    if case == "unavailable":
        nio.start_key_verification = None
    elif case == "raises":

        async def start_raises(_device):
            raise RuntimeError("network unavailable")

        nio.start_key_verification = start_raises
    elif case == "error_response":

        class StartError:
            pass

        async def start_error(_device):
            return StartError()

        nio.start_key_verification = start_error
    elif case == "missing_transaction":

        async def starts_without_sas(_device):
            return object()

        nio.start_key_verification = starts_without_sas

    with pytest.raises(MatrixE2EEError) as err:
        await client.async_start_verification(USER, DEVICE)
    assert err.value.code == expected
    await client.async_stop()


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("missing_device", ERROR_DEVICE_MISSING),
        ("fingerprint_mismatch", ERROR_FINGERPRINT_MISMATCH),
        ("unavailable", ERROR_ENCRYPTION_UNAVAILABLE),
    ],
)
async def test_fingerprint_verification_rejects_invalid_prerequisites(
    tmp_path, case: str, expected: str
) -> None:
    """Local trust changes require a matching known device and an Olm verifier."""
    client, nio = await _client(tmp_path)
    if case != "missing_device":
        nio.add_device(USER, DEVICE)
    if case == "unavailable":
        nio.olm = None
        nio.verify_device = None

    fingerprint = "wrong" if case == "fingerprint_mismatch" else "ED25519_DEVICE_KEY"
    with pytest.raises(MatrixE2EEError) as err:
        await client.async_verify_device_by_fingerprint(USER, DEVICE, fingerprint)
    assert err.value.code == expected
    await client.async_stop()


async def test_fingerprint_verify_notifies_state_listeners(tmp_path) -> None:
    """Fingerprint trust refreshes diagnostic entities via state listeners."""
    client, nio = await _client(tmp_path)
    nio.add_device(USER, DEVICE)
    calls: list[int] = []

    def listener() -> None:
        calls.append(1)

    remove = client.add_state_listener(listener)
    try:
        await client.async_verify_device_by_fingerprint(
            USER, DEVICE, "ED25519_DEVICE_KEY"
        )
    finally:
        remove()
    assert len(calls) == 1
    await client.async_stop()


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("missing_transaction", ERROR_INVALID_TRANSACTION),
        ("unavailable", ERROR_ENCRYPTION_UNAVAILABLE),
        ("raises", ERROR_SEND_FAILED),
        ("error_response", ERROR_SEND_FAILED),
    ],
)
async def test_confirm_verification_rejects_protocol_failures(
    tmp_path, case: str, expected: str
) -> None:
    """Confirming SAS fails closed when the transaction cannot progress."""
    client, nio = await _client(tmp_path)
    if case != "missing_transaction":
        nio.key_verifications[TXN] = FakeSas(TXN, USER, DEVICE)
    if case == "unavailable":
        nio.confirm_short_auth_string = None
        nio.confirm_key_verification = None
    elif case == "raises":

        async def confirm_raises(_transaction_id):
            raise RuntimeError("send failed")

        nio.confirm_short_auth_string = confirm_raises
    elif case == "error_response":

        class ConfirmError:
            pass

        async def confirm_error(_transaction_id):
            return ConfirmError()

        nio.confirm_short_auth_string = confirm_error

    with pytest.raises(MatrixE2EEError) as err:
        await client.async_confirm_verification(TXN)
    assert err.value.code == expected
    await client.async_stop()


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("missing_transaction", ERROR_INVALID_TRANSACTION),
        ("raises", ERROR_SEND_FAILED),
        ("error_response", ERROR_SEND_FAILED),
    ],
)
async def test_cancel_verification_rejects_protocol_failures(
    tmp_path, case: str, expected: str
) -> None:
    """Canceling a SAS reports errors rather than silently swallowing them."""
    client, nio = await _client(tmp_path)
    if case != "missing_transaction":
        nio.key_verifications[TXN] = FakeSas(TXN, USER, DEVICE)
    if case == "raises":

        async def cancel_raises(_transaction_id, reject=False):
            raise RuntimeError("send failed")

        nio.cancel_key_verification = cancel_raises
    elif case == "error_response":

        class CancelError:
            pass

        async def cancel_error(_transaction_id, reject=False):
            return CancelError()

        nio.cancel_key_verification = cancel_error

    with pytest.raises(MatrixE2EEError) as err:
        await client.async_cancel_verification(TXN)
    assert err.value.code == expected
    await client.async_stop()
