"""Config flow per l'integrazione GHL ProfiLux."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ProfiLuxAuthError, ProfiLuxClient, ProfiLuxConnectionError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_DISCLAIMER_SCHEMA = vol.Schema(
    {
        vol.Required("accept_risks", default=False): bool,
    }
)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME, default="admin"): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


async def _async_test_connection(
    hass: HomeAssistant, host: str, username: str, password: str
) -> str | None:
    """Testa la connessione e restituisce il codice di errore o None se ok.

    Restituisce anche il seriale del controller (per unique_id) via side-effect
    nei dati: usa ProfiLuxClient direttamente e legge il seriale.
    """
    client = ProfiLuxClient(hass, host, username, password, async_get_clientsession(hass))
    try:
        await client.async_connect()
    except ProfiLuxAuthError:
        return "invalid_auth"
    except ProfiLuxConnectionError:
        return "cannot_connect"
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Errore inatteso durante il test di connessione")
        return "unknown"
    finally:
        await client.async_disconnect()
    return None


async def _async_get_serial(
    hass: HomeAssistant, host: str, username: str, password: str
) -> str | None:
    """Legge il seriale del controller per usarlo come unique_id."""
    from .api import ProfiLuxError
    from .const import CODE_SERIALNUMBER
    client = ProfiLuxClient(hass, host, username, password, async_get_clientsession(hass))
    try:
        await client.async_connect()
        serial = await client.async_get_data(CODE_SERIALNUMBER)
        return str(serial) if serial else None
    except ProfiLuxError:
        return None
    finally:
        await client.async_disconnect()


class ProfiLuxConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow: indirizzo IP, username e password del ProfiLux."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: disclaimer — l'utente deve accettare esplicitamente i rischi."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get("accept_risks"):
                errors["base"] = "disclaimer_required"
            else:
                return await self.async_step_connect()
        return self.async_show_form(
            step_id="user",
            data_schema=STEP_DISCLAIMER_SCHEMA,
            errors=errors,
        )

    async def async_step_connect(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: connessione e verifica credenziali."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD]

            error = await _async_test_connection(self.hass, host, username, password)
            if error:
                errors["base"] = error
            else:
                # Usa il seriale come unique_id per evitare doppi
                serial = await _async_get_serial(self.hass, host, username, password)
                unique_id = serial or host
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                return self.async_create_entry(
                    title=f"ProfiLux ({host})",
                    data={
                        CONF_HOST: host,
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                    },
                )

        return self.async_show_form(
            step_id="connect",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
            description_placeholders={
                "ws_note": (
                    "Il WebSocket deve essere abilitato sul ProfiLux "
                    "(GHL Control Center → Impostazioni → Interfacce web)"
                )
            },
        )
