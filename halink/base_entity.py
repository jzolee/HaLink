# base_entity.py
"""HaLink V3 – közös bázis entitás.

Feladat:
    - közös init az összes HaLink entitásnak
    - CONFIG-ból kapott entitás-konfig feldolgozása
    - _attr_* mezők beállítása (device_class, unit_of_measurement, stb.)
    - extra attribútumok kezelése
    - per-entity STATE frissítés fogadása dispatcher-en keresztül
    - kapcsolat állapot kezelése (online / offline)
    - SET parancs küldésének közös felülete
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import (
    DOMAIN,
    SIGNAL_CONNECTION_STATE,
    SIGNAL_DATA_RECEIVED,
    SIGNAL_CONFIG_UPDATE,
)
from .utils import generate_unique_id, generate_entity_id
from .logger import DedupLogger

_LOG = DedupLogger(name="halink.base_entity")

# CONFIG -> Entity attribútumok mapje
RUNTIME_ATTR_MAP: Dict[str, str] = {
    "name": "_attr_name",
    "icon": "_attr_icon",
    "device_class": "_attr_device_class",
    "state_class": "_attr_state_class",
    "unit_of_measurement": "_attr_native_unit_of_measurement",
    "unit": "_attr_native_unit_of_measurement",
    "entity_category": "_attr_entity_category",
    "assumed_state": "_attr_assumed_state",
}


class HaLinkBaseEntity(Entity):
    """Közös ős minden HaLink entitásnak."""

    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, device, ent_cfg: Dict[str, Any]) -> None:
        """ent_cfg: a config_parser által normalizált entitás-definíció."""
        self.hass = hass
        self._device = device  # HaLinkDevice példány
        self._ent_cfg = ent_cfg
        self._attr_entity_registry_visible_default = False

        self._entity_key: str = ent_cfg.get("key")
        self._platform: str = ent_cfg.get("platform", "sensor")
        self._friendly_name: str = ent_cfg.get("friendly_name", self._entity_key)

        self._attr_unique_id = generate_unique_id(
            device.meta,
            self._entity_key
        )

        self.entity_id = generate_entity_id(
            self._device.meta,
            self._entity_key,
            self._platform,
        )

        # megjelenített név
        self._attr_name = self._friendly_name

        # extra attribútumok tárolása
        self._extra_attrs: Dict[str, Any] = {}

        # kapcsolat állapot (device szint)
        self._available: bool = True

        # dispatcher leiratkozók
        self._unsub_conn = None
        self._unsub_state = None
        self._unsub_cfg = None

        # CONFIG attribútumok alkalmazása
        self._apply_config_attributes(ent_cfg)

    # ------------------------------------------------------------------
    @property
    def entity_key(self) -> str:
        """A normalizált kulcs, amit STATE / SET / EVENT használ."""
        return self._entity_key

    @property
    def device(self):
        """A háttérben levő HaLinkDevice objektum."""
        return self._device

    # ------------------------------------------------------------------
    @property
    def available(self) -> bool:
        """Kapcsolat állapota."""
        return self._available

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Extra attribútumok."""
        return dict(self._extra_attrs)

    @property
    def device_info(self) -> Optional[Dict[str, Any]]:
        """HA device-regiszter adatok (CONFIG device szekcióból)."""
        cfg = self._device.config or {}
        dev = cfg.get("device", {})

        # Ha nincs device config, használjuk az alapértelmezettet
        if not dev:
            return {
                "identifiers": {(DOMAIN, self._device.device_id)},
                "name": self._device.entry_name,
                "manufacturer": "HaLink Device",
                "model": "Generic",
            }
        
        # Egyébként a config-ból
        return {
            "identifiers": {(DOMAIN, self._device.device_id)},
            "name": dev.get("name") or self._device.entry_name,
            "manufacturer": dev.get("manufacturer"),
            "model": dev.get("model"),
            "sw_version": dev.get("sw_version"),
        }

    # ------------------------------------------------------------------
    async def async_added_to_hass(self) -> None:
        """Dispatcher kapcsolatok létrehozása."""
        did = self._device.device_id

        # kapcsolat állapot
        self._unsub_conn = async_dispatcher_connect(
            self.hass,
            SIGNAL_CONNECTION_STATE.format(did),
            self._async_handle_connection_state,
        )

        # per-entity STATE frissítés
        self._unsub_state = async_dispatcher_connect(
            self.hass,
            SIGNAL_DATA_RECEIVED.format(did),
            self._async_handle_state_update,
        )

        # CONFIG frissítés (ha később új config jönne)
        self._unsub_cfg = async_dispatcher_connect(
            self.hass,
            SIGNAL_CONFIG_UPDATE.format(did),
            self._async_handle_config_update,
        )

    async def async_will_remove_from_hass(self) -> None:
        """Dispatcher kapcsolatok lekapcsolása."""
        for unsub in (self._unsub_conn, self._unsub_state, self._unsub_cfg):
            if unsub:
                try:
                    unsub()
                except Exception:  # noqa: BLE001
                    pass

        self._unsub_conn = self._unsub_state = self._unsub_cfg = None

    # ------------------------------------------------------------------
    @callback
    def _async_handle_connection_state(self, connected: bool) -> None:
        """Kapcsolat állapotváltozás kezelése."""
        self._available = bool(connected)
        self.async_write_ha_state()

    @callback
    def _async_handle_state_update(self, key: str, state: Dict[str, Any]) -> None:
        """Per-entity STATE frissítés (device dispatcher hívja)."""
        if key != self._entity_key:
            return

        # attribútumok merge
        attrs = state.get("attributes") or {}
        if isinstance(attrs, dict):
            self._extra_attrs.update(attrs)

        # platform-specifikus state alkalmazása
        self._apply_state(state)

        self.async_write_ha_state()

    @callback
    def _async_handle_config_update(self) -> None:
        """CONFIG frissítés – új attribútumok alkalmazása."""
        cfg = self._device.config or {}
        entities = cfg.get("entities", {}) or {}
        ent = entities.get(self._entity_key)
        if not isinstance(ent, dict):
            return

        self._apply_config_attributes(ent)
        self.async_write_ha_state()

    # ------------------------------------------------------------------
    def _apply_config_attributes(self, cfg: Dict[str, Any]) -> None:
        """CONFIG -> Entity runtime attribútumok és extra attribútumok."""
        for key, value in cfg.items():
            if key in ("key", "platform", "friendly_name"):
                continue

            if key in RUNTIME_ATTR_MAP:
                attr_name = RUNTIME_ATTR_MAP[key]
                setattr(self, attr_name, value)
            else:
                # extra attribútumnak tekintjük
                self._extra_attrs[key] = value

    # ------------------------------------------------------------------
    def _apply_state(self, state: Dict[str, Any]) -> None:
        """Platform-specifikus state frissítés hook.

        Ezt az alosztályok implementálják (sensor, number, switch, stb.).
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    async def async_send_set(self, value: Any) -> None:
        """SET parancs küldése a device felé (entity_key alapján)."""
        await self._device.send_set(self._entity_key, value)
