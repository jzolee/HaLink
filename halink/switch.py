# switch.py
"""
HaLink V3 – Switch platform
===========================
Ez a modul a HaLink switch entitások platform-implementációja.
Az új V3 architektúrához igazítva:
    - entitásdefiníció: config_parser → ent_cfg (per-entity)
    - state frissítés: device.py → dispatcher(key, state)
    - platform logika: _apply_state + async_turn_on/off

A base_entity kezeli:
    - attributum merge
    - kapcsolatelérhetőség
    - HA state publish

A switch platform csak:
    - value → _attr_is_on beállítást
    - SET küldést (async_turn_on/off)
"""

from __future__ import annotations
from typing import Any, Dict

from homeassistant.components.switch import SwitchEntity
from .base_entity import HaLinkBaseEntity
from .utils import async_setup_platform_common
from .logger import DedupLogger

_LOG = DedupLogger(name="halink.switch")


# =====================================================================
# PLATFORM HANDLER
# =====================================================================
async def async_setup_entry(hass, config_entry, async_add_entities):
    await async_setup_platform_common(
        hass, config_entry, async_add_entities, "switch", HaLinkSwitchEntity
    )

# =====================================================================
# SWITCH ENTITY
# =====================================================================
class HaLinkSwitchEntity(HaLinkBaseEntity, SwitchEntity):
    """HaLink V3 switch entitás."""

    _attr_is_on = False

    # --------------------------------------------------------------
    def _apply_state(self, state: Dict[str, Any]) -> None:
        """Kapcsoló állapotának frissítése.
        A base_entity már frissítette az attribútumokat.
        """
        raw = state.get("value")
        is_on = bool(raw) if raw is not None else False

        self._attr_is_on = is_on
        _LOG.debug(f"Switch state update: {self.entity_id} is_on={is_on}")

    # --------------------------------------------------------------
    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.async_send_set(1)
        _LOG.debug(f"SET ON sent for {self.entity_id}")

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.async_send_set(0)
        _LOG.debug(f"SET OFF sent for {self.entity_id}")
