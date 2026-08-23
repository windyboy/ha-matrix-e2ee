"""Configuration and reauth error-path tests."""

from __future__ import annotations

import pytest
from homeassistant.config_entries import (
    SOURCE_IMPORT,
    SOURCE_REAUTH,
    SOURCE_RECONFIGURE,
)
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.matrix_e2ee import config_flow
from custom_components.matrix_e2ee.client import MatrixE2EEError
from custom_components.matrix_e2ee.const import (
    CONF_HOMESERVER,
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
    ERROR_LOGIN_FAILED,
)
from tests.fakes import FakeNio

HS = "https://matrix.example.org"
USERNAME = "@ha-bot:example.org"


@pytest.fixture
def hass_config_dir(tmp_path) -> str:
    return str(tmp_path)


@pytest.fixture(autouse=True)
def _enable_custom_integrations(enable_custom_integrations) -> None:
    """Make HA discover the custom integration."""


@pytest.fixture(autouse=True)
def _inject_fake_nio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config_flow, "_NIO_CLIENT_FACTORY", FakeNio)


def _entry(hass: HomeAssistant, homeserver: str = HS) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=USERNAME,
        data={CONF_HOMESERVER: homeserver, CONF_USERNAME: USERNAME},
    )
    entry.add_to_hass(hass)
    return entry


def test_error_helpers_fall_back_for_unknown_codes() -> None:
    assert config_flow._base_error("unknown") == "cannot_connect"
    assert config_flow._homeserver_error("unknown") == "homeserver_invalid"


async def test_import_aborts_for_missing_invalid_or_existing_configuration(
    hass: HomeAssistant,
) -> None:
    missing = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_IMPORT}, data=None
    )
    assert (missing["type"], missing["reason"]) == ("abort", "unknown")

    invalid = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data={
            CONF_HOMESERVER: "http://invalid.example",
            CONF_USERNAME: USERNAME,
            CONF_PASSWORD: "pw",
        },
    )
    assert (invalid["type"], invalid["reason"]) == ("abort", "unknown")

    _entry(hass)
    existing = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data={CONF_HOMESERVER: HS, CONF_USERNAME: USERNAME, CONF_PASSWORD: "pw"},
    )
    assert existing["type"] == "abort"


async def test_reconfigure_rejects_invalid_homeserver(hass: HomeAssistant) -> None:
    entry = _entry(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOMESERVER: "http://invalid.example"}
    )
    assert result["type"] == "form"
    assert result["errors"] == {"base": "homeserver_http_not_allowed"}


async def test_reconfigure_new_device_surfaces_login_error(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failed_login(homeserver, user, **kwargs):
        nio = FakeNio(homeserver, user, **kwargs)
        nio.login_should_fail = True
        return nio

    monkeypatch.setattr(config_flow, "_NIO_CLIENT_FACTORY", failed_login)
    entry = _entry(hass, "https://old.example.org")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOMESERVER: "https://new.example.org"}
    )
    assert result["step_id"] == "reconfigure_new_device"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "wrong"}
    )
    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_reauth_surfaces_client_error(hass: HomeAssistant) -> None:
    class FailedReauthClient:
        async def async_reauthenticate(self, password: str) -> None:
            raise MatrixE2EEError(ERROR_LOGIN_FAILED, "invalid credentials")

    entry = _entry(hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = FailedReauthClient()
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "wrong"}
    )
    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_options_flow_verification_abort_paths(hass: HomeAssistant) -> None:
    """Canceled, missing, and incomplete SAS snapshots abort with the reason shown."""
    entry = _entry(hass)
    flow = config_flow.MatrixE2EEOptionsFlow()
    flow.hass = hass
    flow._config_entry = entry
    flow.handler = entry.entry_id

    result = await flow.async_step_compare()
    assert result["reason"] == "verification_timeout"

    flow._txn = "txn"
    result = await flow.async_step_compare()
    assert result["reason"] == "verification_failed"

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = type(
        "Client", (), {"sas_snapshot": lambda self, transaction_id: {"canceled": False}}
    )()
    result = await flow.async_step_compare()
    assert result["reason"] == "verification_timeout"

    flow._txn = None
    result = await flow.async_step_match()
    assert result["reason"] == "verification_failed"

    flow._txn = "txn"

    class Client:
        def sas_snapshot(self, transaction_id: str):
            return {"canceled": True, "verified": False}

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = Client()
    result = await flow.async_step_compare()
    assert result["reason"] == "verification_canceled"

    result = await flow.async_step_match()
    assert result["reason"] == "verification_canceled"

    result = await flow.async_step_finish()
    assert result["reason"] == "verification_canceled"

    hass.data[DOMAIN][entry.entry_id].sas_snapshot = lambda transaction_id: {
        "canceled": False,
        "verified": False,
    }
    result = await flow.async_step_finish()
    assert result["reason"] == "verification_timeout"


async def test_user_and_import_abort_when_an_entry_already_exists(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Flow-level entry checks reject a second configured bot."""
    entry = _entry(hass)

    async def successful_login(user_input) -> None:
        return None

    user_flow = config_flow.MatrixE2EEConfigFlow()
    user_flow.hass = hass
    monkeypatch.setattr(user_flow, "_ensure_login", successful_login)
    monkeypatch.setattr(user_flow, "_async_current_entries", lambda: [entry])
    result = await user_flow.async_step_user(
        {CONF_HOMESERVER: HS, CONF_USERNAME: USERNAME, CONF_PASSWORD: "pw"}
    )
    assert result["reason"] == "already_configured"

    import_flow = config_flow.MatrixE2EEConfigFlow()
    import_flow.hass = hass
    monkeypatch.setattr(import_flow, "_ensure_login", successful_login)
    monkeypatch.setattr(import_flow, "_async_current_entries", lambda: [entry])
    result = await import_flow.async_step_import(
        {CONF_HOMESERVER: HS, CONF_USERNAME: USERNAME, CONF_PASSWORD: "pw"}
    )
    assert result["reason"] == "already_configured"
