# device.py
"""
HaLink V3 - Device Manager

Feladat:
  ✓ kapcsolatkezelés (connect / disconnect)
  ✓ üzenetek fogadása → MessageParser
  ✓ CONFIG feldolgozása → entitások létrehozása
  ✓ STATE feldolgozása → entitások állapotfrissítése
  ✓ EVENT feldolgozása → HA event bus publikálás
  ✓ SET parancsok küldése (light / object mode, delay_ms queue-val)

A V3 architektúra szerint minden nyers üzenet először a MessageParser-hez kerül:
{
   "type": "config" | "state" | "event",
   "data": {... normalizált ...}
}
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .message_parser import MessageParser
from .const import (
    DOMAIN,
    SIGNAL_CONFIG_UPDATE,
    SIGNAL_DATA_RECEIVED,
    SIGNAL_CONNECTION_STATE,
    SIGNAL_ALIVE_STATE,
    RESERVED_ENTITY_KEYS,
)
from .logger import DedupLogger

log = DedupLogger(name="halink.device")


class HaLinkDevice:
    """Eszközpéldány a teljes V3 protokollhoz."""

    # parancsok maximális élettartama a queue-ban (másodperc)
    CMD_TTL_SEC = 600.0  # 10 perc

    # CONFIG handshake timeout (másodperc)
    CONFIG_TIMEOUT_SEC = 5.0

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        host: str,
        port: int,
        client,
        entry_name: str | None = None,
        entry_id: str | None = None,
    ) -> None:
        self.hass = hass
        self.host = host
        self.port = port
        self.client = client  # TcpClient objektum

        # device_id: config_flow által számolt normalize_key(host_port)
        self.device_id: str = device_id

        # A név, amit az integráció telepítésekor adtál
        self.entry_name: str = entry_name or self.device_id

        # Config entry azonosító (globálisan egyedi)
        self.entry_id: str = entry_id or self.device_id

        # Egységes meta adatok – entity_id / unique_id generáláshoz
        self.meta: Dict[str, Any] = {
            "domain": DOMAIN,
            "entry_id": self.entry_id,
            "name": self.entry_name,
            "host": self.host,
            "port": self.port,
            "device_id": self.device_id,
        }

        # konfigurációs állapot (config_parser kimenete)
        self.config: Dict[str, Any] = {}

        # alive állapot (STATE parser kimenete)
        self.alive_state: Optional[Dict[str, Any]] = None

        # SET queue engine
        self._delay_ms: int = 0
        # Bounded queue to avoid unbounded memory growth if producer floods SETs.
        # Choose a reasonable default maxsize (adjustable if you want).
        self._set_queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._set_task: Optional[asyncio.Task] = None

        # Track which entity keys we've already created to avoid duplicate creation
        # on repeated CONFIG messages.
        self._entities_created: set[str] = set()

        self.parser = MessageParser()
        self.connected = False

        # CONFIG-handshake állapot
        self._config_received: bool = False
        self._config_timeout_task: Optional[asyncio.Task] = None

    # ==================================================================
    # KAPCSOLATKEZELÉS
    # ==================================================================
    async def handle_connected(self) -> None:
        """Kapcsolat létrejött."""
        self.connected = True
        self._config_received = False  # új handshake indul
        log.info(f"HaLink device connected: {self.host}:{self.port}")

        # CONFIG-handshake timeout indítása
        self._start_config_timeout()

        # SET queue worker indítása, ha kell
        self._restart_set_worker_if_needed()

        # notify HA
        async_dispatcher_send(
            self.hass,
            SIGNAL_CONNECTION_STATE.format(self.device_id),
            True,
        )

    async def handle_disconnected(self) -> None:
        """Kapcsolat megszakadt."""
        self.connected = False
        log.info(f"HaLink device disconnected: {self.host}:{self.port}")

        # CONFIG-timeout leállítása
        self._cancel_config_timeout()

        # worker leállítása, queue megőrzése (TTL miatt később lejár)
        if self._set_task:
            self._set_task.cancel()
            self._set_task = None

        async_dispatcher_send(
            self.hass,
            SIGNAL_CONNECTION_STATE.format(self.device_id),
            False,
        )

    async def async_shutdown(self) -> None:
        """Integráció leállításakor hívjuk."""
        # CONFIG-timeout leállítása
        self._cancel_config_timeout()
        # worker leállítása
        if self._set_task:
            self._set_task.cancel()
            self._set_task = None

        # queue kiürítése
        while not self._set_queue.empty():
            try:
                self._set_queue.get_nowait()
            except Exception:  # noqa: BLE001
                break

        # reset created entity tracking (cleanup)
        try:
            self._entities_created.clear()
        except Exception:
            pass

        # TCP kliens leállítása
        try:
            await self.client.stop()
        except Exception as err:  # noqa: BLE001
            log.warning(f"Error while stopping client for {self.host}:{self.port}: {err}")

    # ==================================================================
    # RAW ÜZENET FOGADÁS
    # ==================================================================
    async def handle_raw_message(self, raw: str) -> None:
        """TCP raw üzenet beérkezett – MessageParser végzi a felismerést."""
        try:
            parsed = self.parser.parse(raw)
        except Exception as e:  # noqa: BLE001
            log.error(f"Message parsing error from {self.host}:{self.port}: {e}")
            return

        if not parsed:
            return

        msg_type = parsed["type"]
        data = parsed["data"]

        if msg_type == "config":
            await self._process_config(data)
        elif msg_type == "state":
            await self._process_state(data)
        elif msg_type == "event":
            await self._process_event(data)

    # ==================================================================
    # CONFIG feldolgozás
    # ==================================================================
    async def _process_config(self, data: Dict[str, Any]) -> None:
        # Handshake: megjött a CONFIG
        self._config_received = True
        self._cancel_config_timeout()

        log.info(
            f"Received CONFIG V{data.get('version')}: "
            f"{len(data.get('entities', {}))} entities"
        )
        self.config = data or {}

        # SET engine config
        self._delay_ms = int(self.config.get("delay_ms", 0))
        self._restart_set_worker_if_needed()

        # entitások létrehozása
        await self._create_entities_from_config(self.config)

        # jelzés minden platformnak – device_id-vel formázva!
        async_dispatcher_send(
            self.hass,
            SIGNAL_CONFIG_UPDATE.format(self.device_id),
        )

    async def _create_entities_from_config(self, cfg: Dict[str, Any]) -> None:
        """Entitások létrehozása CONFIG alapján – platformok jelzése."""
        entities = cfg.get("entities", {})
        if not isinstance(entities, dict):
            return

        for key, ent in entities.items():
            # 🛡️ Foglalt kulcs védelem
            if key in RESERVED_ENTITY_KEYS:
                log.warning(
                    f"Ignoring reserved entity key '{key}' from {self.host}:{self.port}. "
                    f"Reserved for system use."
                )
                continue

            # Avoid recreating same entity multiple times across CONFIG messages.
            if key in self._entities_created:
                # entity already created — skip creation.
                continue

            platform = ent.get("platform")
            if not platform:
                continue

            # A platform modulok ezt figyelik:
            #   f"{DOMAIN}_create_{platform}"
            async_dispatcher_send(
                self.hass,
                f"{DOMAIN}_create_{platform}",
                self.device_id,
                ent,
            )

            # Mark as created so repeated CONFIG won't recreate entity instances.
            try:
                self._entities_created.add(key)
            except Exception:
                pass


    # ==================================================================
    # STATE feldolgozás
    # ==================================================================
    async def _process_state(self, data: Dict[str, Any]) -> None:
        # Alive frissítése
        if data.get("alive") is not None:
            self.alive_state = data["alive"]
            async_dispatcher_send(
                self.hass,
                SIGNAL_ALIVE_STATE.format(self.device_id),
                self.alive_state,
            )

        # Entity frissítések
        for key, st in data.get("entities", {}).items():
            async_dispatcher_send(
                self.hass,
                SIGNAL_DATA_RECEIVED.format(self.device_id),
                key,
                st,
            )

    # ==================================================================
    # EVENT feldolgozás → HA Event Bus
    # ==================================================================
    async def _process_event(self, data: Dict[str, Any]) -> None:
        events = data.get("events", [])
        if not events:
            return

        for ev in events:
            ev_key = ev.get("key")
            if not ev_key:
                continue

            event_type = f"halink_event.{self.device_id}.{ev_key}"
            payload: Dict[str, Any] = {}

            if ev.get("value") is not None:
                payload["value"] = ev["value"]

            if ev.get("attributes"):
                payload.update(ev["attributes"])

            if ev.get("ts") is not None:
                payload["ts"] = ev["ts"]

            self.hass.bus.async_fire(event_type, payload)

    # ==================================================================
    # SET parancsok küldése – light / object mód
    # ==================================================================
    async def send_set(self, key: str, value: Any) -> None:
        """SET parancs küldése az aktuális set_mode szerint."""
        cfg = self.config or {}
        mode = cfg.get("set_mode", "light")

        if mode == "light":
            await self._send_set_light(key, value)
        else:
            await self._send_set_object(key, value)

    async def _send_set_light(self, key: str, value: Any) -> None:
        # Végleges light frame: key=value\0
        msg = f"{key}={value}\0"
        await self._enqueue_or_send(msg)

    async def _send_set_object(self, key: str, value: Any) -> None:
        # JSON body V3 szerint
        body = {"set": {key: {"value": value}}}
        await self._enqueue_or_send(body)

    async def _enqueue_or_send(self, msg: Any) -> None:
        """Ha delay_ms > 0 → queue, különben azonnali küldés."""
        if self._delay_ms > 0:
            loop = asyncio.get_running_loop()
            ts = loop.time()
            try:
                # Try to put without waiting if queue is full -> drop oldest item
                self._set_queue.put_nowait((ts, msg))
            except Exception:
                # Queue full: drop one oldest and try again (drop-oldest policy).
                try:
                    _ = self._set_queue.get_nowait()
                except Exception:
                    # if unable to remove, fallback to blocking put (rare)
                    await self._set_queue.put((ts, msg))
                else:
                    try:
                        self._set_queue.put_nowait((ts, msg))
                    except Exception:
                        # finally, fallback to blocking put
                        await self._set_queue.put((ts, msg))
        else:
            await self._send_raw(msg)

    async def _send_raw(self, msg: Any) -> None:
        """Közvetlen küldés a kliensen keresztül."""
        try:
            await self.client.send_message(msg)
        except Exception as err:  # noqa: BLE001
            log.warning(f"Error sending message to {self.host}:{self.port}: {err}")

    # ==================================================================
    # SET queue worker – delay_ms + TTL
    # ==================================================================
    def _restart_set_worker_if_needed(self) -> None:
        """delay_ms alapján indítja / állítja a worker taskot."""
        if self._delay_ms > 0 and self.connected:
            # worker szükséges
            if self._set_task is None or self._set_task.done():
                self._set_task = self.hass.async_create_task(self._set_worker())
                log.debug(
                    f"SET worker started for {self.device_id} "
                    f"(delay_ms={self._delay_ms})"
                )
        else:
            # worker nem kell
            if self._set_task:
                self._set_task.cancel()
                # do not leak task reference; the cancelled task will finish soon
                self._set_task = None
                log.debug(f"SET worker stopped for {self.device_id}")
            # queue ürítése (a régieket inkább eldobjuk)
            while not self._set_queue.empty():
                try:
                    self._set_queue.get_nowait()
                except Exception:  # noqa: BLE001
                    break

    async def _set_worker(self) -> None:
        """Háttértask: SET parancsok küldése delay_ms és TTL figyelembevételével."""
        loop = asyncio.get_running_loop()
        delay_sec = self._delay_ms / 1000.0 if self._delay_ms > 0 else 0.0

        try:
            while True:
                ts, msg = await self._set_queue.get()
                now = loop.time()

                # TTL ellenőrzés
                if now - ts > self.CMD_TTL_SEC:
                    log.debug("Dropping stale SET command (older than TTL)")
                    continue

                # ha időközben megszakadt a kapcsolat, eldobhatjuk
                if not self.connected:
                    log.debug("Dropping SET command because device is disconnected")
                    continue

                await self._send_raw(msg)

                if delay_sec > 0:
                    await asyncio.sleep(delay_sec)
        except asyncio.CancelledError:
            # normál leállás
            log.debug(f"SET worker cancelled for {self.device_id}")
            return

    # ==================================================================
    # CONFIG-handshake timeout – ha nincs CONFIG, reconnect
    # ==================================================================
    def _cancel_config_timeout(self) -> None:
        """Leállítja a folyamatban lévő CONFIG-timeoutot (ha van)."""
        task = self._config_timeout_task
        if task and not task.done():
            task.cancel()
        self._config_timeout_task = None

    def _start_config_timeout(self) -> None:
        """Indít egy timeoutot, ami CONFIG-et vár a kapcsolódás után."""
        # Előző timeout leállítása, ha lenne
        self._cancel_config_timeout()

        loop = asyncio.get_running_loop()

        async def _wait_for_config() -> None:
            try:
                await asyncio.sleep(self.CONFIG_TIMEOUT_SEC)

                # Ha még mindig nincs CONFIG, miközben kapcsolódva vagyunk, reconnect
                if not self._config_received and self.connected:
                    log.warning(
                        f"No CONFIG received within {self.CONFIG_TIMEOUT_SEC}s "
                        f"from {self.host}:{self.port}; forcing reconnect."
                    )
                    try:
                        # ha közben már nincs writer / folyamatban van a stop, ne erőltessük
                        await self.client.disconnect()
                    except Exception as err:  # noqa: BLE001
                        log.warning(
                            f"Error while forcing reconnect for "
                            f"{self.host}:{self.port}: {err}"
                        )
            except asyncio.CancelledError:
                # normál leállítás
                return

        # HA saját task-kal indítjuk
        self._config_timeout_task = self.hass.async_create_task(_wait_for_config())


