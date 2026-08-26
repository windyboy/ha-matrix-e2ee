"""Additional client.py coverage for helper and edge-path branches."""

from __future__ import annotations

import asyncio
import logging
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from custom_components.matrix_e2ee import client as client_module
from custom_components.matrix_e2ee.client import (
    MatrixE2EEClient,
    MatrixE2EEError,
    SecretRedactFilter,
)
from custom_components.matrix_e2ee.const import (
    ERROR_DEVICE_MISMATCH,
    ERROR_LOGIN_FAILED,
    ERROR_RESTORE_FAILED,
    ERROR_ROOM_NOT_ALLOWED,
    ERROR_SEND_FAILED,
    ERROR_SESSION_MISSING,
    ERROR_UNVERIFIED_DEVICE,
    NIO_DEFAULT_PICKLE_KEY,
    SAS_METHOD_V1,
    VERIFICATION_READY,
)
from custom_components.matrix_e2ee.storage import MatrixSession
from tests.fakes import FakeNio, FakeSas, LoginError

BOT = "@bot:example.org"
PEER = "@peer:example.org"
ROOM = "!room:example.org"
DEVICE = "PEERDEV"
TXN = "txn-peerdev"


def _client(
    tmp_path,
    *,
    fire_event=None,
    factory=FakeNio,
    password="long-password-value",
) -> MatrixE2EEClient:
    return MatrixE2EEClient(
        config_dir=tmp_path,
        homeserver="https://matrix.example.org",
        username=BOT,
        password=password,
        allowed_rooms=[ROOM],
        allowed_users=[PEER],
        verification_peer_users=[PEER],
        command_prefix="!",
        fire_event=fire_event or (lambda _event, _data: None),
        nio_client_factory=factory,
    )


async def _seed_existing_session(tmp_path) -> None:
    client = _client(tmp_path)
    await client.async_start()
    await client.async_stop()


async def _started(tmp_path) -> tuple[MatrixE2EEClient, FakeNio]:
    created: dict[str, FakeNio] = {}

    def factory(homeserver, user, **kwargs):
        nio = FakeNio(homeserver, user, **kwargs)
        nio.user_id = BOT
        created["nio"] = nio
        return nio

    client = _client(tmp_path, factory=factory)
    await client.async_start()
    return client, created["nio"]


def test_secret_redact_filter_without_secrets_passes_through() -> None:
    filt = SecretRedactFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="password is %s",
        args=("long-password-value",),
        exc_info=None,
    )
    assert filt.filter(record) is True
    assert record.msg == "password is %s"


def test_secret_redact_filter_redacts_known_secrets() -> None:
    filt = SecretRedactFilter()
    filt.set_secrets("long-secret-value")
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="token=%s",
        args=("long-secret-value",),
        exc_info=None,
    )
    assert filt.filter(record) is True
    assert record.msg == "token=[redacted]"
    assert record.args == ()


def test_secret_redact_filter_tolerates_getmessage_failure() -> None:
    filt = SecretRedactFilter()
    filt.set_secrets("long-secret-value")
    record = MagicMock(spec=logging.LogRecord)
    record.getMessage.side_effect = RuntimeError("format failed")
    assert filt.filter(record) is True


def test_module_helpers_classify_auth_and_room_lookup() -> None:
    class UnauthorizedError(Exception):
        pass

    class ServerError(Exception):
        pass

    assert client_module._is_auth_failure(SimpleNamespace(errcode="M_UNKNOWN_TOKEN"))
    assert client_module._is_auth_failure(SimpleNamespace(status_code=401))
    assert client_module._is_auth_failure(SimpleNamespace(status_code="401"))
    assert client_module._is_auth_failure(UnauthorizedError("unknown token"))
    assert not client_module._is_auth_failure(ServerError("server unavailable"))

    assert client_module._nio_room(SimpleNamespace(rooms="not-a-dict"), ROOM) is None
    assert (
        client_module._nio_room(SimpleNamespace(rooms={ROOM: "room"}), ROOM) == "room"
    )


@pytest.mark.asyncio
async def test_maybe_await_returns_sync_and_async_values() -> None:
    assert await client_module._maybe_await(42) == 42

    async def value():
        return "async"

    assert await client_module._maybe_await(value()) == "async"


def test_client_state_property_reflects_lifecycle(tmp_path) -> None:
    client = _client(tmp_path)
    assert client.state.value == "stopped"


@pytest.mark.asyncio
async def test_make_nio_without_factory_uses_async_client(tmp_path) -> None:
    client = _client(tmp_path, factory=None)
    fake_client = object()
    fake_config = object()
    async_client = MagicMock(return_value=fake_client)
    async_client_config = MagicMock(return_value=fake_config)
    fake_nio = types.ModuleType("nio")
    fake_nio.AsyncClient = async_client
    fake_nio.AsyncClientConfig = async_client_config

    with (
        patch.object(client_module, "apply_nio_compat_patches"),
        patch.dict(sys.modules, {"nio": fake_nio}),
    ):
        nio = await client._make_nio(
            pickle_key="test-pickle-key-value", device_id="DEV1"
        )
    assert nio is fake_client
    async_client.assert_called_once()


@pytest.mark.asyncio
async def test_first_login_rejects_default_pickle_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        client_module.secrets, "token_urlsafe", lambda _n: NIO_DEFAULT_PICKLE_KEY
    )
    client = _client(tmp_path)
    with pytest.raises(MatrixE2EEError) as err:
        await client.async_start()
    assert err.value.code == ERROR_LOGIN_FAILED


@pytest.mark.asyncio
async def test_first_login_rejects_incomplete_device(tmp_path) -> None:
    class IncompleteLoginNio(FakeNio):
        async def login(self, password, device_name=""):
            self.device_id = "HABOTABC"
            self.access_token = ""
            return object()

    client = _client(tmp_path, factory=IncompleteLoginNio)
    with pytest.raises(MatrixE2EEError) as err:
        await client.async_start()
    assert err.value.code == ERROR_LOGIN_FAILED


@pytest.mark.asyncio
async def test_restore_rejects_default_pickle_key(tmp_path) -> None:
    session = MatrixSession(
        version=1,
        user_id=BOT,
        device_id="HABOTABC",
        access_token="syt_test_access_token_value",
        pickle_key=NIO_DEFAULT_PICKLE_KEY,
    )
    client = _client(tmp_path, password=None)
    with pytest.raises(MatrixE2EEError) as err:
        await client._restore(session)
    assert err.value.code == ERROR_RESTORE_FAILED


@pytest.mark.asyncio
async def test_restore_whoami_non_auth_error_fails_closed(tmp_path) -> None:
    class WhoamiServerError:
        pass

    class WhoamiFailsNio(FakeNio):
        async def whoami(self):
            return WhoamiServerError()

    created: dict[str, FakeNio] = {}

    def factory(homeserver, user, **kwargs):
        nio = WhoamiFailsNio(homeserver, user, **kwargs)
        nio.user_id = BOT
        created["nio"] = nio
        return nio

    await _seed_existing_session(tmp_path)
    client = _client(tmp_path, factory=factory, password=None)
    with pytest.raises(MatrixE2EEError) as err:
        await client.async_start()
    assert err.value.code == ERROR_RESTORE_FAILED
    assert created["nio"].closed is True


@pytest.mark.asyncio
async def test_restore_device_mismatch_fails_closed(tmp_path) -> None:
    class MismatchNio(FakeNio):
        async def whoami(self):
            self.device_id = "OTHERDEV"
            return object()

    created: dict[str, FakeNio] = {}

    def factory(homeserver, user, **kwargs):
        nio = MismatchNio(homeserver, user, **kwargs)
        nio.user_id = BOT
        created["nio"] = nio
        return nio

    await _seed_existing_session(tmp_path)
    client = _client(tmp_path, factory=factory, password=None)
    with pytest.raises(MatrixE2EEError) as err:
        await client.async_start()
    assert err.value.code == ERROR_DEVICE_MISMATCH
    assert created["nio"].closed is True


@pytest.mark.asyncio
async def test_upload_keys_and_query_device_key_paths(tmp_path) -> None:
    client, nio = await _started(tmp_path)
    upload_calls: list[str] = []

    async def keys_upload():
        upload_calls.append("uploaded")

    nio.should_upload_keys = True
    nio.keys_upload = keys_upload
    await client._upload_keys_if_needed()
    assert upload_calls == ["uploaded"]

    client.nio = None
    await client._upload_keys_if_needed()
    await client._query_device_keys(PEER)
    await client._query_device_keys("")

    class BrokenQuery:
        def add(self, _user_id):
            raise AttributeError("broken")

    nio.olm = SimpleNamespace(users_for_key_query=BrokenQuery())
    client.nio = nio
    await client._query_device_keys(PEER)

    nio.keys_query = None
    await client._query_device_keys(PEER)

    async def keys_query_raises():
        raise RuntimeError("query failed")

    nio.keys_query = keys_query_raises
    nio.olm = SimpleNamespace(users_for_key_query=set())
    await client._query_device_keys(PEER)
    await client.async_stop()


@pytest.mark.asyncio
async def test_async_stop_survives_sync_task_failure(tmp_path) -> None:
    client, _nio = await _started(tmp_path)

    async def failing_sync():
        raise RuntimeError("sync crashed")

    client._sync_task = asyncio.create_task(failing_sync())
    await client.async_stop()
    assert client.nio is None


@pytest.mark.asyncio
async def test_require_nio_fails_when_not_started(tmp_path) -> None:
    client = _client(tmp_path)
    with pytest.raises(MatrixE2EEError) as err:
        client._require_nio()
    assert err.value.code == ERROR_SESSION_MISSING


@pytest.mark.asyncio
async def test_reauthenticate_login_exception_restores_password(tmp_path) -> None:
    client, nio = await _started(tmp_path)
    client._soft_logged_out = True
    previous = client._password

    async def login_raises(_password, device_name=""):
        raise RuntimeError("network down")

    nio.login = login_raises
    with pytest.raises(MatrixE2EEError) as err:
        await client.async_reauthenticate("replacement-password-value")
    assert err.value.code == ERROR_LOGIN_FAILED
    assert client._password == previous
    await client.async_stop()


@pytest.mark.asyncio
async def test_send_message_maps_error_response(tmp_path) -> None:
    client, nio = await _started(tmp_path)
    nio.rooms[ROOM] = SimpleNamespace(room_id=ROOM, encrypted=False)

    async def room_send_error(*_args, **_kwargs):
        return LoginError()

    nio.room_send = room_send_error
    with pytest.raises(MatrixE2EEError) as err:
        await client.async_send_message(ROOM, "hello")
    assert err.value.code == ERROR_SEND_FAILED
    await client.async_stop()


@pytest.mark.asyncio
async def test_handle_incoming_event_early_returns_and_thread_parent(tmp_path) -> None:
    events: list[tuple[str, dict]] = []
    client, _nio = await _started(tmp_path)
    client._soft_logged_out = True
    client.handle_incoming_event(
        SimpleNamespace(room_id=ROOM),
        SimpleNamespace(sender=PEER, body="!ping"),
    )

    client._soft_logged_out = False
    client._commands_enabled = True
    client.handle_incoming_event(
        SimpleNamespace(room_id=ROOM),
        SimpleNamespace(sender=None, body="!ping"),
    )
    client.handle_incoming_event(
        SimpleNamespace(room_id=ROOM),
        SimpleNamespace(sender=BOT, body="!ping"),
    )
    client.handle_incoming_event(
        SimpleNamespace(room_id=ROOM, encrypted=False),
        SimpleNamespace(sender=PEER, body=123, verified=True, decrypted=False),
    )

    client._fire_event = lambda event_type, data: events.append((event_type, data))
    client.handle_incoming_event(
        SimpleNamespace(room_id="!other:example.org", encrypted=False),
        SimpleNamespace(sender=PEER, body="!ping", verified=True, decrypted=False),
    )
    client.handle_incoming_event(
        SimpleNamespace(room_id=ROOM, encrypted=False),
        SimpleNamespace(
            sender=PEER,
            body="!echo hi",
            verified=True,
            decrypted=False,
            thread_parent="m.thread.root",
        ),
    )
    command_events = [data for event, data in events if event.endswith("command")]
    assert command_events[-1]["thread_parent"] == "m.thread.root"
    await client.async_stop()


@pytest.mark.asyncio
async def test_lookup_device_and_sas_snapshot_edge_paths(tmp_path) -> None:
    client, nio = await _started(tmp_path)
    nio.device_store[PEER] = {}
    assert client._lookup_device(nio, PEER, DEVICE) is None

    timed_out = FakeSas(TXN, PEER, DEVICE)
    timed_out.timed_out = True
    nio.key_verifications[TXN] = timed_out
    assert client._sas_is_timed_out(nio, TXN) is True

    client.nio = None
    assert client.sas_snapshot(TXN) is None
    assert client.latest_sas_snapshot() is None
    assert client.list_known_devices() == []

    client.nio = nio
    assert client.sas_snapshot("missing-txn") is None
    await client.async_stop()


def test_bootstrap_allowed_rejects_empty_sender(tmp_path) -> None:
    client = _client(tmp_path)
    assert client._bootstrap_allowed("") is False
    assert client._bootstrap_allowed(None) is False


@pytest.mark.asyncio
async def test_repair_dropped_start_handles_missing_and_failed_refeed(tmp_path) -> None:
    client, nio = await _started(tmp_path)
    event = SimpleNamespace(sender="", from_device=DEVICE, transaction_id=TXN)
    await client._repair_dropped_start(nio, event, TXN)

    event = SimpleNamespace(sender=PEER, from_device=DEVICE, transaction_id=TXN)
    nio.olm = SimpleNamespace(handle_key_verification=None)
    await client._repair_dropped_start(nio, event, TXN)

    def handle_raises(_event):
        raise RuntimeError("olm failed")

    nio.olm = SimpleNamespace(handle_key_verification=handle_raises)
    await client._repair_dropped_start(nio, event, TXN)
    await client.async_stop()


@pytest.mark.asyncio
async def test_handle_to_device_event_soft_logout_and_timeout(tmp_path) -> None:
    client, nio = await _started(tmp_path)
    client._soft_logged_out = True
    await client.handle_to_device_event(
        SimpleNamespace(type="m.key.verification.key", sender=PEER, transaction_id=TXN)
    )

    client._soft_logged_out = False
    client.nio = None
    await client.handle_to_device_event(
        SimpleNamespace(type="m.key.verification.key", sender=PEER, transaction_id=TXN)
    )

    client.nio = nio
    timed_out = FakeSas(TXN, PEER, DEVICE)
    timed_out.timed_out = True
    nio.key_verifications[TXN] = timed_out
    client._mark_sas_started(TXN)
    await client.handle_to_device_event(
        SimpleNamespace(type="m.key.verification.key", sender=PEER, transaction_id=TXN)
    )
    await client.async_stop()


def test_transaction_id_from_verifications_single_fallback() -> None:
    sas = FakeSas(TXN, PEER, DEVICE)
    assert (
        client_module._transaction_id_from_verifications({TXN: sas}, PEER, "OTHER")
        == TXN
    )


def test_to_device_message_builds_nio_payload() -> None:
    fake_nio = types.ModuleType("nio")
    fake_builders = types.ModuleType("nio.event_builders")

    def to_device_message(type_, recipient, recipient_device, content):
        return SimpleNamespace(
            type=type_,
            recipient=recipient,
            recipient_device=recipient_device,
            content=content,
        )

    fake_builders.ToDeviceMessage = to_device_message
    with patch.dict(
        sys.modules,
        {"nio": fake_nio, "nio.event_builders": fake_builders},
    ):
        message = client_module._to_device_message(
            VERIFICATION_READY,
            PEER,
            DEVICE,
            {"transaction_id": TXN, "methods": [SAS_METHOD_V1]},
        )
    assert message.type == VERIFICATION_READY
    assert message.recipient == PEER


def test_event_type_helpers_import_fallbacks(monkeypatch) -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "nio.events" and fromlist:
            raise ImportError("nio missing")
        if name == "nio.events.room_events":
            raise ImportError("nio missing")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert client_module._key_verification_event_type() is None
    assert client_module._to_device_event_type() is None
    assert client_module._room_message_type() is None


def test_verification_error_code_maps_unverified() -> None:
    class UnverifiedSendError(Exception):
        pass

    assert (
        client_module._verification_error_code(UnverifiedSendError("unverified device"))
        == ERROR_UNVERIFIED_DEVICE
    )


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_query_device_keys_skips_blank_user_ids(tmp_path) -> None:
    client, nio = await _started(tmp_path)
    queried: list[str] = []

    class QuerySet:
        def add(self, user_id):
            queried.append(user_id)

    nio.olm = SimpleNamespace(users_for_key_query=QuerySet())
    await client._query_device_keys("", PEER, "")
    assert queried == [PEER]
    await client.async_stop()


@pytest.mark.asyncio
async def test_async_stop_survives_completed_sync_task_exception(tmp_path) -> None:
    client, _nio = await _started(tmp_path)

    async def failing_sync():
        raise RuntimeError("sync crashed")

    task = asyncio.create_task(failing_sync())
    with pytest.raises(RuntimeError):
        await task
    client._sync_task = task
    await client.async_stop()
    assert client.nio is None


def test_transaction_id_from_verifications_returns_none_for_ambiguous() -> None:
    first = FakeSas("txn-one", PEER, DEVICE)
    second = FakeSas("txn-two", PEER, "OTHERDEV")
    assert (
        client_module._transaction_id_from_verifications(
            {"txn-one": first, "txn-two": second},
            PEER,
            "missing",
        )
        is None
    )


def test_event_type_helpers_return_types_when_nio_installed(monkeypatch) -> None:
    fake_events = types.ModuleType("nio.events")
    fake_events.KeyVerificationEvent = object
    fake_events.ToDeviceEvent = object
    fake_room_events = types.ModuleType("nio.events.room_events")
    fake_room_events.RoomMessageText = object

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "nio.events":
            return fake_events
        if name == "nio.events.room_events":
            return fake_room_events
        raise ImportError(name)

    import builtins

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert client_module._key_verification_event_type() is object
    assert client_module._to_device_event_type() is object
    assert client_module._room_message_type() is object


@pytest.mark.asyncio
async def test_send_message_rejects_disallowed_room(tmp_path) -> None:
    client, _nio = await _started(tmp_path)
    with pytest.raises(MatrixE2EEError) as err:
        await client.async_send_message("!denied:example.org", "hello")
    assert err.value.code == ERROR_ROOM_NOT_ALLOWED
    await client.async_stop()
