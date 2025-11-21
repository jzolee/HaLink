# select.py
"""
HaLink V3 – Select platform
===========================
Select entitások a HaLink V3-hoz.

Használati esetek:
- mód választás (auto/manual/boost)
- előre definiált értékek listája
- enum-szerű beállítások
"""

from __future__ import annotations
from typing import Any, Dict, List

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity import EntityCategory

from .base_entity import HaLinkBaseEntity
from .utils import async_setup_platform_common
from .logger import DedupLogger

_LOG = DedupLogger(name="halink.select")


# =====================================================================
# PLATFORM HANDLER
# =====================================================================
async def async_setup_entry(hass, config_entry, async_add_entities):
    await async_setup_platform_common(
        hass, config_entry, async_add_entities, "select", HaLinkSelectEntity
    )

# =====================================================================
# SELECT ENTITY
# =====================================================================
class HaLinkSelectEntity(HaLinkBaseEntity, SelectEntity):
    """HaLink V3 select entitás."""

    _attr_current_option: str | None = None
    _attr_options: List[str] = []

    def __init__(self, hass, device, ent_cfg: Dict[str, Any]):
        super().__init__(hass, device, ent_cfg)

        # Select-specifikus CONFIG mezők
        self._apply_select_config(ent_cfg)

    # ------------------------------------------------------------------
    def _apply_select_config(self, cfg: Dict[str, Any]):
        """Config V3 platform-specifikus select mezők alkalmazása."""
        # Opciók listája (kötelező)
        options = cfg.get("options", [])
        if isinstance(options, list):
            self._attr_options = [str(opt) for opt in options]
        else:
            _LOG.warning(f"Invalid options for select {self.entity_id}: {options}")
            self._attr_options = []

        # Alapértelmezett érték
        if "default" in cfg:
            default = str(cfg["default"])
            if default in self._attr_options:
                self._attr_current_option = default

        # Entity category
        if cfg.get("entity_category") == "config":
            self._attr_entity_category = EntityCategory.CONFIG
        elif cfg.get("entity_category") == "diagnostic":
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    # ------------------------------------------------------------------
    def _apply_state(self, state: Dict[str, Any]) -> None:
        """STATE frissítés – támogatja a dinamikus opciók frissítését."""
        raw = state.get("value")
        
        # Opciók frissítése (ha a STATE-ben érkezik)
        new_options = state.get("options")
        if isinstance(new_options, list) and new_options:
            self._attr_options = [str(opt) for opt in new_options]
            _LOG.debug(f"Options updated for {self.entity_id}: {self._attr_options}")

        # Current option frissítése
        if raw is not None:
            option = str(raw)
            if option in self._attr_options:
                self._attr_current_option = option

    # ------------------------------------------------------------------
    async def async_select_option(self, option: str) -> None:
        """SELECT parancs küldése - V3 szabvány szerint."""
        if option not in self._attr_options:
            _LOG.error(
                f"Invalid SELECT option for {self.entity_id}: {option} "
                f"(available: {self._attr_options})"
            )
            return

        await self.async_send_set(option)
        _LOG.debug(f"SELECT sent for {self.entity_id}: {option}")

    # ------------------------------------------------------------------
    @property
    def current_option(self) -> str | None:
        """Visszaadja a jelenleg kiválasztott opciót."""
        return self._attr_current_option

    @property
    def options(self) -> List[str]:
        """Visszaadja az elérhető opciók listáját."""
        return self._attr_options


"""
Példa CONFIG a Select platformhoz
{
  "config": {
    "version": 3,
    "device": {
      "name": "Climate Controller"
    },
    "select": {
      "Operating Mode": {
        "options": ["auto", "heat", "cool", "fan_only", "off"],
        "default": "auto",
        "device_class": "climate__fan_mode",
        "entity_category": "config",
        "icon": "mdi:thermostat"
      },
      "Fan Speed": {
        "options": ["low", "medium", "high", "auto"],
        "default": "auto", 
        "icon": "mdi:fan"
      },
      "Scene Selection": {
        "options": ["normal", "cinema", "gaming", "night"],
        "entity_category": "config"
      }
    }
  }
}

Példa STATE üzenet Select-hez

{
  "state": {
    "operating_mode": "heat",
    "fan_speed": "medium"
  }
}

vagy részletes formában:

{
  "state": {
    "operating_mode": {
      "value": "heat",
      "attributes": {
        "last_change": 1700000000
      }
    }
  }
}

Példa SET parancs Select-hez
Light mode:
operating_mode=heat

Object mode:
{
  "set": {
    "operating_mode": {
      "value": "heat"
    }
  }
}

CONFIG példa dinamikus opciókkal:
{
  "select": {
    "Source Input": {
      "options": ["hdmi1", "hdmi2", "usb", "bluetooth"],
      "attributes": {
        "_attr_icon": "mdi:input-hdmi"
      }
    }
  }
}

"""
