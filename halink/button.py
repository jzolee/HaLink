# button.py
"""
HaLink V3 – Button platform
===========================
Button entitások a HaLink V3-hoz.

Használati esetek:
- egyszeri műveletek (press, trigger, reset, calibrate)
- nem állapottartó entitások
- parancsküldés egyetlen értékkel vagy üres payload-dal
"""

from __future__ import annotations
from typing import Any, Dict

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity import EntityCategory

from .base_entity import HaLinkBaseEntity
from .utils import async_setup_platform_common
from .logger import DedupLogger

_LOG = DedupLogger(name="halink.button")

# =====================================================================
# PLATFORM HANDLER
# =====================================================================
async def async_setup_entry(hass, config_entry, async_add_entities):
    await async_setup_platform_common(
        hass, config_entry, async_add_entities, "button", HaLinkButtonEntity
    )

# =====================================================================
# BUTTON ENTITY
# =====================================================================
class HaLinkButtonEntity(HaLinkBaseEntity, ButtonEntity):
    """HaLink V3 button entitás."""

    def __init__(self, hass, device, ent_cfg: Dict[str, Any]):
        super().__init__(hass, device, ent_cfg)

        # Button-specifikus CONFIG mezők
        self._apply_button_config(ent_cfg)

    # ------------------------------------------------------------------
    def _apply_button_config(self, cfg: Dict[str, Any]):
        """Config V3 platform-specifikus button mezők alkalmazása."""
        
        # Press value - opcionális, mire nyomódjon meg a gomb
        self._press_value = cfg.get("press_value", 1)
        
        # Entity category - gyakran "config" lesz
        if cfg.get("entity_category") == "config":
            self._attr_entity_category = EntityCategory.CONFIG
        elif cfg.get("entity_category") == "diagnostic":
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

        # Device class - opcionális
        if "device_class" in cfg:
            self._attr_device_class = cfg["device_class"]

    # ------------------------------------------------------------------
    def _apply_state(self, state: Dict[str, Any]) -> None:
        """Button állapot frissítése.
        
        Button-ok általában nem kapnak állapotfrissítést, 
        de ha érkezik, logolhatjuk.
        """
        value = state.get("value")
        if value is not None:
            _LOG.debug(f"Button state update (usually unused): {self.entity_id} value={value}")

    # ------------------------------------------------------------------
    async def async_press(self) -> None:
        """Button megnyomása - SET parancs küldése."""
        await self.async_send_set(self._press_value)
        _LOG.debug(f"BUTTON pressed: {self.entity_id} value={self._press_value}")

    # ------------------------------------------------------------------
    @property
    def icon(self) -> str | None:
        """Alapértelmezett ikon button-okhoz, ha nincs megadva."""
        if hasattr(self, '_attr_icon') and self._attr_icon:
            return self._attr_icon
        
        # Device class alapú alapértelmezett ikonok
        device_class = getattr(self, '_attr_device_class', None)
        icon_map = {
            'restart': 'mdi:restart',
            'update': 'mdi:package-up',
            'identify': 'mdi:account-eye',
            None: 'mdi:button-pointer',  # alapértelmezett
        }
        return icon_map.get(device_class, 'mdi:button-pointer')


""" example

{
  "config": {
    "version": 3,
    "device": {
      "name": "Smart Controller"
    },
    "button": {
      "Restart Device": {
        "device_class": "restart",
        "entity_category": "config",
        "press_value": "restart",
        "icon": "mdi:restart"
      },
      "Calibrate Sensors": {
        "press_value": "calibrate",
        "entity_category": "config",
        "icon": "mdi:tape-measure"
      },
      "Identify Device": {
        "device_class": "identify", 
        "press_value": 1,
        "icon": "mdi:account-eye"
      },
      "Factory Reset": {
        "press_value": "factory_reset",
        "entity_category": "config",
        "icon": "mdi:alert-octagon"
      }
    }
  }
}


"""