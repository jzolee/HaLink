# number.py
"""
HaLink V3 – Number platform
===========================
Ez a modul a HaLink number entitások platform-implementációja.
Az új V3 architektúrára épül:
    - entitásdefiníció: config_parser → ent_cfg
    - közös bázismodul: HaLinkBaseEntity
    - per-entity state: device.py → dispatcher(key, state)
    - platform-specifikus update: _apply_state()

A base_entity elvégzi:
    - attribútumok összevonása
    - _attr mezők alkalmazása
    - extra attribútumok tárolása
    - elérhetőség kezelését
"""

from __future__ import annotations
from typing import Any, Dict

from homeassistant.components.number import NumberEntity

from .base_entity import HaLinkBaseEntity
from .utils import async_setup_platform_common
from .logger import DedupLogger

_LOG = DedupLogger(name="halink.number")

# =====================================================================
# PLATFORM HANDLER
# =====================================================================
async def async_setup_entry(hass, config_entry, async_add_entities):
    await async_setup_platform_common(
        hass, config_entry, async_add_entities, "number", HaLinkNumberEntity
    )

# =====================================================================
# NUMBER ENTITY
# =====================================================================
class HaLinkNumberEntity(HaLinkBaseEntity, NumberEntity):
    """HaLink V3 number entitás."""

    def __init__(self, hass, device, ent_cfg: Dict[str, Any]):
        super().__init__(hass, device, ent_cfg)

        # Platform-specifikus CONFIG mezők
        self._apply_number_config(ent_cfg)

    # ------------------------------------------------------------------
    def _apply_number_config(self, cfg: Dict[str, Any]):
        """Config V3 platform-specifikus number mezők alkalmazása."""
        if "min" in cfg:
            self._attr_native_min_value = cfg["min"]
        if "max" in cfg:
            self._attr_native_max_value = cfg["max"]
        if "step" in cfg:
            self._attr_native_step = cfg["step"]
        if "mode" in cfg:
            self._attr_mode = cfg["mode"]

    # ------------------------------------------------------------------
    def _apply_state(self, state: Dict[str, Any]) -> None:
        """STATE frissítés – numerikus értéket vár.
        A base_entity már kezelte az attribútumokat.
        """
        raw = state.get("value")

        try:
            if raw is None:
                self._attr_native_value = None
            else:
                self._attr_native_value = float(raw)
        except Exception:
            _LOG.warning(f"Invalid number value for {self.entity_id}: {raw}")
            return

        _LOG.debug(
            f"Number state update: {self.entity_id} value={self._attr_native_value}"
        )

    # ------------------------------------------------------------------
    async def async_set_native_value(self, value: float) -> None:
        """SET parancs küldése – V3 szabvány szerint."""
        try:
            fval = float(value)
        except Exception:
            _LOG.error(f"Invalid SET value for {self.entity_id}: {value}")
            return

        await self.async_send_set(fval)
        _LOG.debug(f"SET sent for {self.entity_id}: {fval}")
