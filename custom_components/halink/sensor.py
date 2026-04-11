# sensor.py
"""
HaLink V3 – Sensor platform
===========================
Ez a modul a HaLink szenzor entitások platform-implementációja.

Feladata:
    - a HaLinkBaseEntity-re épülő sensor entitások létrehozása
    - per-entity STATE frissítések fogadása
    - a _apply_state(state_dict) metódus override-ja
        → a szenzor értékét (_attr_native_value) frissíti
"""

from __future__ import annotations
from typing import Any, Dict

from homeassistant.components.sensor import SensorEntity
from .base_entity import HaLinkBaseEntity
from .utils import async_setup_platform_common
from .logger import DedupLogger

_LOG = DedupLogger(name="halink.sensor")


# =====================================================================
# PLATFORM HANDLER – a DEVICE modul ezt hívja, amikor config érkezik
# =====================================================================
async def async_setup_entry(hass, config_entry, async_add_entities):
    await async_setup_platform_common(
        hass, config_entry, async_add_entities, "sensor", HaLinkSensorEntity
    )

# =====================================================================
# SENSOR ENTITY
# =====================================================================
class HaLinkSensorEntity(HaLinkBaseEntity, SensorEntity):
    """HaLink V3 szenzor entitás."""

    _attr_native_value = None

    # ------------------------------------------------------------------
    def _apply_state(self, state: Dict[str, Any]) -> None:
        """STATE frissítés – csak a value-t állítjuk.
        A base_entity kezeli az attribútumokat és a HA state írást.
        """
        value = state.get("value")
        self._attr_native_value = value

        _LOG.debug(
            f"Sensor state update: {self.entity_id} value={value}"
        )
