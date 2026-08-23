"""Client reauthentication failure-path tests."""

from __future__ import annotations

import pytest

from custom_components.matrix_e2ee.client import MatrixE2EEClient, MatrixE2EEError
from custom_components.matrix_e2ee.const import (
    ERROR_DEVICE_MISMATCH,
    ERROR_LOGIN_FAILED,
    ERROR_PASSWORD_REQUIRED,
    ERROR_REFRESH_TOKEN_UNSUPPORTED,
    ERROR_SESSION_MISSING,
)
from tests.fakes import FakeNio


async def _started_client(tmp_path):
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
        verification_peer_users=[],
        command_prefix="!",
        fire_event=lambda event_type, data: None,
        nio_client_factory=factory,
    )
    await client.async_start()
    client._soft_logged_out = True
    return client, created["nio"]


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("missing_password", ERROR_PASSWORD_REQUIRED),
        ("missing_session", ERROR_SESSION_MISSING),
        ("failed_login", ERROR_LOGIN_FAILED),
        ("refresh_token", ERROR_REFRESH_TOKEN_UNSUPPORTED),
        ("device_mismatch", ERROR_DEVICE_MISMATCH),
        ("missing_token", ERROR_LOGIN_FAILED),
    ],
)
async def test_reauthenticate_rejects_invalid_or_unsafe_responses(
    tmp_path, case: str, expected: str
) -> None:
    """Reauth keeps the original session whenever the replacement is unsafe."""
    client, nio = await _started_client(tmp_path)

    if case == "missing_password":
        password = ""
    elif case == "missing_session":
        client.session = None
        password = "new-password"
    else:
        password = "new-password"
        if case == "failed_login":
            nio.login_should_fail = True
        elif case == "refresh_token":
            nio.login_refresh_token = True
        elif case == "device_mismatch":
            nio.login_device_id = "OTHER_DEVICE"
        elif case == "missing_token":
            async def no_token_login(password, device_name=""):
                nio.user_id = client.session.user_id
                nio.device_id = client.session.device_id
                nio.access_token = ""
                return object()

            nio.login = no_token_login

    with pytest.raises(MatrixE2EEError) as err:
        await client.async_reauthenticate(password)
    assert err.value.code == expected
    await client.async_stop()
