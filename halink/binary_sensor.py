# binary_sensor.py
"""
HaLink V3 – Binary Sensor platform
=================================
- Normál binary_sensor entitások (CONFIG-ból jönnek)
- Speciális "Alive" binary sensor, ami mindig létrejön

Alive logika:
    - on  : ha van TCP kapcsolat ÉS a CONFIG lefutott (entities létrejöttek)
    - off : egyébként
    - device_class: connectivity
    - attribútumok: state.alive.attributes (uptime, rssi, stb. ha van)
"""

from __future__ import annotations

from typing import Any, Dict

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .base_entity import HaLinkBaseEntity
from .const import (
    DOMAIN,
    SIGNAL_CONNECTION_STATE,
    SIGNAL_ALIVE_STATE,
    SIGNAL_CONFIG_UPDATE,
)
from .logger import DedupLogger

_LOG = DedupLogger(name="halink.binary_sensor")

# =====================================================================
# PLATFORM HANDLER
# =====================================================================
async def async_setup_entry(hass, config_entry, async_add_entities):
    """A device.py dispatcher ezt hívja új binary_sensor entity létrehozására.

    Ezen felül itt hozzuk létre az "alive" binary sensort is, ami mindig létezik.
    """

    device_id = config_entry.data.get("device_id")
    device = hass.data[DOMAIN][device_id]

    # 1) Alive binary sensor – mindig létrejön
    alive_cfg = {
        "key": "alive",
        "platform": "binary_sensor",
        "friendly_name": "Alive",
        "device_class": "connectivity",
    }
    alive_entity = HaLinkAliveBinarySensorEntity(hass, device, alive_cfg)
    async_add_entities([alive_entity])
    _LOG.debug(f"Created alive binary_sensor entity: {alive_entity.entity_id}")

    # 2) Normál binary_sensor entitások, amelyeket a CONFIG hoz létre
    async def _create(device_id_from_signal, ent_cfg):
        if device_id_from_signal != device_id:
            return

        ent = HaLinkBinarySensorEntity(hass, device, ent_cfg)
        async_add_entities([ent])
        _LOG.debug(f"Created binary_sensor entity: {ent.entity_id}")

    async_dispatcher_connect(
        hass,
        f"{DOMAIN}_create_binary_sensor",
        _create,
    )

# =====================================================================
# NORMÁL BINARY SENSOR ENTITY (CONFIG-ból)
# =====================================================================
class HaLinkBinarySensorEntity(HaLinkBaseEntity, BinarySensorEntity):
    """HaLink V3 binary sensor entitás (CONFIG-ból)."""

    _attr_is_on = False

    def _apply_state(self, state: Dict[str, Any]) -> None:
        """Állapot frissítése STATE alapján."""
        raw = state.get("value")
        is_on = bool(raw) if raw is not None else False
        self._attr_is_on = is_on
        _LOG.debug(f"Binary sensor state update: {self.entity_id} is_on={is_on}")


# =====================================================================
# ALIVE BINARY SENSOR ENTITY (speciális)
# =====================================================================
class HaLinkAliveBinarySensorEntity(HaLinkBaseEntity, BinarySensorEntity):
    """Speciális Alive binary sensor.

    - A CONFIG-ben nincs definiálva, mindig automatikusan létrejön.
    - Állapot: connection AND config_ready
    - Attribútumok: STATE.alive.attributes merge-elve extra attribútumokba.
    """

    _attr_is_on = False

    def __init__(self, hass, device, ent_cfg: Dict[str, Any]) -> None:
        super().__init__(hass, device, ent_cfg)

        self._connected: bool = False
        self._config_ready: bool = False
        self._alive_attrs: Dict[str, Any] = {}

        # A base_entity-ben lévő dispatcher kapcsolatok mellé
        # extra jelzéseket is figyelünk:
        self._unsub_alive = None
        self._unsub_conn2 = None
        self._unsub_cfg2 = None

    async def async_added_to_hass(self) -> None:
        # alap dispatcher kapcsolatok (connection + data + config)
        await super().async_added_to_hass()

        did = self._device.device_id

        # Külön alive STATE jelzés
        self._unsub_alive = async_dispatcher_connect(
            self.hass,
            SIGNAL_ALIVE_STATE.format(did),
            self._async_handle_alive_state,
        )

        # Külön connection jelzés (saját flaghez)
        self._unsub_conn2 = async_dispatcher_connect(
            self.hass,
            SIGNAL_CONNECTION_STATE.format(did),
            self._async_handle_connection_state_alive,
        )

        # Külön config jelzés (config_ready flag)
        self._unsub_cfg2 = async_dispatcher_connect(
            self.hass,
            SIGNAL_CONFIG_UPDATE.format(did),
            self._async_handle_config_update_alive,
        )

    async def async_will_remove_from_hass(self) -> None:
        await super().async_will_remove_from_hass()

        for unsub in (self._unsub_alive, self._unsub_conn2, self._unsub_cfg2):
            if unsub:
                try:
                    unsub()
                except Exception:  # noqa: BLE001
                    pass

        self._unsub_alive = self._unsub_conn2 = self._unsub_cfg2 = None

    # ------------------------------------------------------------------
    @callback
    def _async_handle_alive_state(self, alive: Dict[str, Any]) -> None:
        """Alive STATE frissítés – csak attribútumokat veszünk át."""
        attrs = alive.get("attributes") or {}
        if isinstance(attrs, dict):
            self._alive_attrs = attrs
            # merge az extra attribútumokkal
            self._extra_attrs.update(attrs)

        _LOG.debug(f"Alive attributes updated for {self.entity_id}: {self._alive_attrs}")
        self._recompute_state()

    @callback
    def _async_handle_connection_state_alive(self, connected: bool) -> None:
        """Kapcsolat állapot a Alive entitás belső flagjeihez."""
        self._connected = bool(connected)
        self._recompute_state()

    @callback
    def _async_handle_config_update_alive(self) -> None:
        """Első CONFIG után config_ready = True."""
        self._config_ready = True
        self._recompute_state()

    # ------------------------------------------------------------------
    def _recompute_state(self) -> None:
        """Alive logika: connection AND config_ready."""
        new_state = bool(self._connected and self._config_ready)
        if new_state != self._attr_is_on:
            self._attr_is_on = new_state
            _LOG.debug(
                f"Alive state recomputed for {self.entity_id}: "
                f"connected={self._connected}, "
                f"config_ready={self._config_ready}, "
                f"is_on={self._attr_is_on}"
            )
        self.async_write_ha_state()

    # ------------------------------------------------------------------
    def _apply_state(self, state: Dict[str, Any]) -> None:
        """Alive entitás nem használja a normál STATE-et."""
        # A base_entity ugyan hívhatná, de itt nincs teendő.
        return
