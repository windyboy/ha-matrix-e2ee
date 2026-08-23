"""Client request-handshake and to-device edge-path tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.matrix_e2ee import client as client_module
from custom_components.matrix_e2ee.client import MatrixE2EEClient
from custom_components.matrix_e2ee.const import (
    SAS_METHOD_V1,
    VERIFICATION_REQUEST,
)
from tests.fakes import FakeNio, FakeSas

BOT = "@bot:example.org"
PEER = "@peer:example.org"
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
        username=BOT,
        password="pw",
        allowed_rooms=[],
        allowed_users=[],
        verification_peer_users=[PEER],
        command_prefix="!",
        fire_event=lambda _event, _data: None,
        nio_client_factory=factory,
    )
    await client.async_start()
    return client, created["nio"]


def _request(**content) -> SimpleNamespace:
    values = {
        "from_device": DEVICE,
        "transaction_id": TXN,
        "methods": [SAS_METHOD_V1],
        "timestamp": 0,
    }
    values.update(content)
    return SimpleNamespace(
        source={
            "type": VERIFICATION_REQUEST,
            "sender": PEER,
            "content": values,
        }
    )


@pytest.mark.parametrize(
    "event",
    [
        SimpleNamespace(source=None),
        SimpleNamespace(source={"type": "other"}),
        SimpleNamespace(source={"type": VERIFICATION_REQUEST, "content": {}}),
        SimpleNamespace(
            source={"type": VERIFICATION_REQUEST, "sender": PEER, "content": None}
        ),
        _request(from_device=""),
        _request(transaction_id=""),
        _request(methods=["m.reciprocate.v1"]),
        _request(timestamp="not-a-timestamp"),
    ],
)
async def test_verification_request_ignores_malformed_input(tmp_path, event) -> None:
    """Malformed request handshakes must not emit a ready response."""
    client, nio = await _client(tmp_path)
    await client._handle_verification_request(event)
    assert nio.to_device_sent == []
    await client.async_stop()


async def test_verification_request_ignores_disallowed_sender(tmp_path) -> None:
    """Only configured verification peers may initiate the request handshake."""
    client, nio = await _client(tmp_path)
    event = _request()
    event.source["sender"] = "@stranger:example.org"
    await client._handle_verification_request(event)
    assert nio.to_device_sent == []
    await client.async_stop()


async def test_ready_and_done_helpers_handle_missing_transport_and_send_errors(
    tmp_path, monkeypatch
) -> None:
    """Optional to-device transport failures never crash verification handling."""
    client, nio = await _client(tmp_path)
    monkeypatch.setattr(
        client_module,
        "_to_device_message",
        lambda type_, recipient, recipient_device, content: SimpleNamespace(
            type=type_,
            recipient=recipient,
            recipient_device=recipient_device,
            content=content,
        ),
    )

    client.nio = None
    await client._send_verification_ready(PEER, DEVICE, TXN)
    await client._send_verification_done(PEER, DEVICE, TXN)

    client.nio = nio
    nio.to_device = None
    await client._send_verification_ready(PEER, DEVICE, TXN)
    await client._send_verification_done(PEER, DEVICE, TXN)

    async def failing_to_device(_message):
        raise RuntimeError("network down")

    nio.to_device = failing_to_device
    await client._send_verification_ready(PEER, DEVICE, TXN)
    await client._send_verification_done(PEER, DEVICE, TXN)

    nio.to_device = FakeNio.to_device.__get__(nio, FakeNio)
    await client._send_verification_ready(PEER, DEVICE, TXN)
    await client._send_verification_done("", DEVICE, TXN)
    await client._send_verification_done(PEER, "", TXN)
    await client._send_verification_done(PEER, DEVICE, TXN)
    assert len(nio.to_device_sent) == 2
    await client.async_stop()


async def test_to_device_handler_ignores_invalid_events_and_fails_closed(
    tmp_path,
) -> None:
    """Invalid to-device input is ignored or reported without trusting devices."""
    client, nio = await _client(tmp_path)

    await client.handle_to_device_event(SimpleNamespace(type="unknown"))
    await client.handle_to_device_event(
        SimpleNamespace(type="m.key.verification.key", sender=PEER, transaction_id="")
    )
    await client.handle_to_device_event(
        SimpleNamespace(
            type="m.key.verification.key",
            sender="@stranger:example.org",
            transaction_id=TXN,
        )
    )
    await client.handle_to_device_event(
        SimpleNamespace(
            type="m.key.verification.start",
            sender=PEER,
            transaction_id=TXN,
            from_device=DEVICE,
            short_authentication_string=["decimal"],
        )
    )
    await client.handle_to_device_event(
        SimpleNamespace(
            type="m.key.verification.key", sender=PEER, transaction_id="missing"
        )
    )
    assert nio.to_device_sent == []
    await client.async_stop()


async def test_to_device_handler_reports_missing_or_unacceptable_start(
    tmp_path,
) -> None:
    """Starts with no SAS or a failing accept are not treated as verification success."""
    client, nio = await _client(tmp_path)
    start = SimpleNamespace(
        type="m.key.verification.start",
        sender=PEER,
        transaction_id=TXN,
        from_device=DEVICE,
        short_authentication_string=["emoji"],
    )

    await client.handle_to_device_event(start)
    assert TXN not in nio.key_verifications

    nio.key_verifications[TXN] = FakeSas(TXN, PEER, DEVICE)

    async def accept_fails(_transaction_id):
        raise RuntimeError("refused")

    nio.accept_key_verification = accept_fails
    await client.handle_to_device_event(start)
    assert nio.key_verifications[TXN].verified is False
    await client.async_stop()


def test_device_and_sas_helpers_tolerate_incomplete_nio_objects(tmp_path) -> None:
    """Compatibility helpers return safe empty values for malformed SDK objects."""
    client = MatrixE2EEClient(
        config_dir=tmp_path,
        homeserver="https://matrix.example.org",
        username=BOT,
        password="pw",
        allowed_rooms=[],
        allowed_users=[],
        verification_peer_users=[],
        command_prefix="!",
        fire_event=lambda _event, _data: None,
        nio_client_factory=FakeNio,
    )
    assert client._lookup_device(SimpleNamespace(), PEER, DEVICE) is None
    assert client._get_sas(SimpleNamespace(key_verifications=[]), TXN) is None
    assert client._sas_emojis(SimpleNamespace()) is None
    assert client._sas_emojis(SimpleNamespace(get_emoji=lambda: [])) is None

    def emoji_failure():
        raise RuntimeError("not ready")

    assert client._sas_emojis(SimpleNamespace(get_emoji=emoji_failure)) is None
    client.nio = SimpleNamespace(device_store={PEER: "invalid"})
    assert client.list_known_devices() == []
    client.nio = SimpleNamespace(
        device_store={PEER: {DEVICE: SimpleNamespace(verified=True)}}
    )
    assert client.list_known_devices() == [
        {"user_id": PEER, "device_id": DEVICE, "verified": True}
    ]


async def test_client_cleanup_and_session_token_fallbacks(tmp_path) -> None:
    """Cleanup and token recovery work with partially implemented nio clients."""
    client, _nio = await _client(tmp_path)
    session = client.session
    assert session is not None

    bare_nio = SimpleNamespace()
    await client._restore_session_token(bare_nio, session)
    assert (bare_nio.user_id, bare_nio.device_id, bare_nio.access_token) == (
        session.user_id,
        session.device_id,
        session.access_token,
    )

    client.nio = None
    await client._close_nio()
    client.nio = SimpleNamespace()
    await client._close_nio()
    assert client.nio is None


def test_client_safety_helpers_cover_absent_and_failing_sdk_data(
    tmp_path, monkeypatch
) -> None:
    """Diagnostics and fingerprints fail closed when SDK data is unavailable."""
    client = MatrixE2EEClient(
        config_dir=tmp_path,
        homeserver="https://matrix.example.org",
        username=BOT,
        password="pw",
        allowed_rooms=[],
        allowed_users=[],
        verification_peer_users=[],
        command_prefix="!",
        fire_event=lambda _event, _data: None,
        nio_client_factory=FakeNio,
    )
    assert client.safe_fingerprint() is None
    client.nio = SimpleNamespace(olm=SimpleNamespace(account=SimpleNamespace()))
    assert client.safe_fingerprint() is None

    class BrokenStore:
        def is_dir(self):
            raise OSError("unavailable")

    monkeypatch.setattr(client_module, "store_path", lambda _path: BrokenStore())
    assert client.safe_diagnostics()["store_present"] is False

    def failing_listener() -> None:
        raise RuntimeError("listener failed")

    client._notify({failing_listener})


async def test_callback_and_sync_optional_nio_methods_are_safe(tmp_path) -> None:
    """Callbacks and sync gracefully degrade when optional nio APIs are absent."""
    client, nio = await _client(tmp_path)
    client.enable_verification_callbacks()
    before = len(nio.to_device_callbacks)
    client.enable_verification_callbacks()
    assert len(nio.to_device_callbacks) == before

    nio.sync_forever = None
    await client.async_sync_loop()
    await client.async_stop()


async def test_ready_requires_our_device_id(tmp_path, monkeypatch) -> None:
    """No ready message is sent until the client has a valid own device id."""
    client, nio = await _client(tmp_path)
    monkeypatch.setattr(
        client_module, "_to_device_message", lambda *_args: SimpleNamespace()
    )
    nio.device_id = ""
    await client._send_verification_ready(PEER, DEVICE, TXN)
    assert nio.to_device_sent == []
    await client.async_stop()


def test_protocol_error_code_classification_covers_error_families() -> None:
    """SDK exception names are mapped to stable, public integration codes."""

    class LocalProtocolError(Exception):
        pass

    class UnverifiedDeviceError(Exception):
        pass

    class EncryptionError(Exception):
        pass

    class OtherError(Exception):
        pass

    assert (
        client_module._verification_error_code(TimeoutError()) == "verification_timeout"
    )
    assert (
        client_module._verification_error_code(LocalProtocolError())
        == "invalid_transaction"
    )
    assert (
        client_module._verification_error_code(UnverifiedDeviceError())
        == "unverified_device"
    )
    assert client_module._send_error_code(EncryptionError()) == "encryption_unavailable"
    assert client_module._send_error_code(OtherError()) == "send_failed"
