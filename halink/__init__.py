# __init__.py – HaLink V3-kompatibilis, teljes újraírt verzió
"""
HaLink V3 – fő integrációs modul
--------------------------------
Ez a verzió tiszta V3 architektúrát követ:
- Minden eszköz: HaLinkDevice instance
- device_id = config_flow által számolt normalize_key(host_port)
- TcpClient → csak raw TCP, minden üzenet továbbmegy a device.handle_raw_message()-be
- MessageParser + ConfigParser + StateParser + EventParser működik
- Platformok automatikusan létrejönnek és dispatcherre kapcsolódnak
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from homeassistant.const import CONF_NAME
from .device import HaLinkDevice
from .client import TcpClient

# -----------------------------------------------------------------------------
# GLOBAL: hass.data STRUCTURE (V3)
# hass.data[DOMAIN][device_id] = HaLinkDevice
# -----------------------------------------------------------------------------

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HaLink from a config entry (V3)."""

    hass.data.setdefault(DOMAIN, {})

    host: str = entry.data["host"]
    port: int = entry.data["port"]
    device_id: str = entry.data["device_id"]

    entry_name: str = entry.data.get(CONF_NAME, entry.title)

    # 1) Létrehozzuk a TcpClient-et (nyers TCP)
    client = TcpClient(
        hass=hass,
        host=host,
        port=port,
        on_raw_message=None,  # majd lentebb kötjük rá a device-ra
        on_disconnect=None,
        on_connect=None,
    )

    # 2) Létrehozzuk a HaLinkDevice-et
    device = HaLinkDevice(
        hass=hass,
        device_id=device_id,
        host=host,
        port=port,
        client=client,
        entry_name=entry_name,
        entry_id=entry.entry_id,
    )

    # Drótozás: TcpClient → HaLinkDevice
    client.on_raw_message = device.handle_raw_message
    client.on_connect = lambda: device.handle_connected()
    client.on_disconnect = lambda: device.handle_disconnected()

    # Tárolás – közvetlenül a device-példányt tároljuk
    hass.data[DOMAIN][device_id] = device

    # Kliens indításának ütemezése a TcpClient saját metódusával
    client.schedule_start()

    # Platformok betöltése (Home Assistant standard)
    await hass.config_entries.async_forward_entry_setups(
        entry,
        [
            "sensor",
            "number",
            "switch",
            "binary_sensor",
            "select",
            "button",
        ],
    )

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    device_id = entry.data["device_id"]

    device = hass.data.get(DOMAIN, {}).pop(device_id, None)
    if device is not None:
        # device maga leállítja a klienst és a worker-t
        await device.async_shutdown()

    # Platformok lekapcsolása
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry,
        [
            "sensor",
            "number",
            "switch",
            "binary_sensor",
            "select",
            "button",
        ],
    )
    return unload_ok
