"""HaLink V3 – Config Flow

Feladata:
    - végigvezeti a felhasználót a szükséges lépéseken:
        1) host (hostname vagy IP)
        2) port
        3) device friendly name
    - előállítja a device_id-t normalize_key() segítségével
    - eltárolja a szükséges adatokat config_entry.data-ben
"""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_NAME
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .utils import normalize_key

class HaLinkConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for HaLink."""

    VERSION = 3

    def __init__(self) -> None:
        self._host: str | None = None
        self._port: int | None = None
        self._name: str | None = None

    # -----------------------------------------------------
    async def async_step_user(self, user_input=None):
        """Első lépés: host bekérése."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_HOST): str,
                    }
                ),
            )

        self._host = user_input[CONF_HOST]
        return await self.async_step_port()

    # -----------------------------------------------------
    async def async_step_port(self, user_input=None):
        """Második lépés: port bekérése."""
        if user_input is None:
            return self.async_show_form(
                step_id="port",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_PORT, default=5000): int,
                    }
                ),
            )

        self._port = user_input[CONF_PORT]
        return await self.async_step_name()

    # -----------------------------------------------------
    async def async_step_name(self, user_input=None):
        """Harmadik lépés: device friendly name."""
        if user_input is None:
            return self.async_show_form(
                step_id="name",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_NAME, default="HaLink Device"): str,
                    }
                ),
            )

        self._name = user_input[CONF_NAME]

        # ============================================
        #  DEVICE ID GENERATION (CRITICAL FOR V3)
        # ============================================
        device_id = normalize_key(f"{self._host}_{self._port}")

        # ============================================
        #  CREATE CONFIG ENTRY
        # ============================================
        return self.async_create_entry(
            title=self._name,
            data={
                CONF_HOST: self._host,
                CONF_PORT: self._port,
                CONF_NAME: self._name,
                "device_id": device_id,  # <-- PLATFORMOK EZT HASZNÁLJÁK
            },
        )
