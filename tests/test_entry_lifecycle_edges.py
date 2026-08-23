"""Lifecycle validation and service-failure coverage."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

import custom_components.matrix_e2ee as matrix_e2ee
from custom_components.matrix_e2ee.client import MatrixE2EEError
from custom_components.matrix_e2ee.const import (
    ATTR_DEVICE_ID,
    ATTR_ED25519,
    ATTR_PASSWORD,
    ATTR_TRANSACTION_ID,
    ATTR_USER_ID,
    DOMAIN,
    ERROR_DEVICE_MISSING,
    EVENT_ERROR,
    SERVICE_CANCEL_VERIFICATION,
    SERVICE_CONFIRM_VERIFICATION,
    SERVICE_REAUTHENTICATE,
    SERVICE_START_VERIFICATION,
    SERVICE_VERIFY_DEVICE_BY_FINGERPRINT,
)


@pytest.fixture(autouse=True)
def _enable_custom_integrations(enable_custom_integrations) -> None:
    """Make HA discover the custom integration."""


def test_validate_homeserver_rejects_invalid_url() -> None:
    with pytest.raises(Exception, match="invalid homeserver URL"):
        matrix_e2ee._validate_homeserver("http://invalid.example")


async def test_verification_services_emit_events_and_surface_errors(
    hass: HomeAssistant,
) -> None:
    """Every verification service preserves its legacy event and raises to HA."""

    class FailedClient:
        _sync_task = None

        async def async_start_verification(self, *args) -> None:
            raise MatrixE2EEError(ERROR_DEVICE_MISSING, "missing")

        async def async_confirm_verification(self, *args) -> None:
            raise MatrixE2EEError(ERROR_DEVICE_MISSING, "missing")

        async def async_cancel_verification(self, *args) -> None:
            raise MatrixE2EEError(ERROR_DEVICE_MISSING, "missing")

        async def async_verify_device_by_fingerprint(self, *args) -> None:
            raise MatrixE2EEError(ERROR_DEVICE_MISSING, "missing")

        async def async_reauthenticate(self, *args) -> None:
            raise MatrixE2EEError(ERROR_DEVICE_MISSING, "missing")

    matrix_e2ee._register_services(hass, FailedClient())
    errors: list[dict] = []
    hass.bus.async_listen(EVENT_ERROR, lambda event: errors.append(event.data))

    calls = [
        (
            SERVICE_START_VERIFICATION,
            {ATTR_USER_ID: "@peer:example.org", ATTR_DEVICE_ID: "DEV"},
        ),
        (SERVICE_CONFIRM_VERIFICATION, {ATTR_TRANSACTION_ID: "txn"}),
        (SERVICE_CANCEL_VERIFICATION, {ATTR_TRANSACTION_ID: "txn"}),
        (
            SERVICE_VERIFY_DEVICE_BY_FINGERPRINT,
            {
                ATTR_USER_ID: "@peer:example.org",
                ATTR_DEVICE_ID: "DEV",
                ATTR_ED25519: "key",
            },
        ),
        (SERVICE_REAUTHENTICATE, {ATTR_PASSWORD: "password"}),
    ]
    for service, data in calls:
        with pytest.raises(ServiceValidationError, match=ERROR_DEVICE_MISSING):
            await hass.services.async_call(DOMAIN, service, data, blocking=True)

    assert errors == [{"code": ERROR_DEVICE_MISSING}] * len(calls)
    matrix_e2ee._unregister_services(hass)
