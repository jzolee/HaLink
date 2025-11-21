import asyncio
import json
import socket
from typing import Optional, Callable, Any

from .const import (
    DEFAULT_RECONNECT_INTERVAL,
    DEFAULT_MAX_RECONNECT_INTERVAL,
)
from .logger import DedupLogger

_LOG = DedupLogger(name=__name__)

class TcpClient:
    """Fully async TCP kliens HaLink V3-hoz.

    Feladat:
    - TCP kapcsolat kezelése (connect / reconnect / disconnect)
    - OS-level keepalive, fallback ping
    - null-terminált frame olvasása ("\0" a frame vége)
    - nyers szöveges üzenet továbbítása a device felé (on_raw_message)
    - JSON / text SET frame küldése a device-tól érkezett kérések alapján

    FONTOS:
    - A kliens NEM értelmezi a JSON-t, csak továbbadja a teljes raw stringet.
      A V3 MessageParser a HaLinkDevice-ben fut.
    """

    def __init__(
        self,
        hass,
        host: str,
        port: int,
        on_raw_message: Optional[Callable[[str], Any]] = None,
        on_disconnect: Optional[Callable[[], Any]] = None,
        on_connect: Optional[Callable[[], Any]] = None,
    ) -> None:
        self.hass = hass
        self.host = host
        self.port = port

        # Callback-ek (sync vagy async is lehet)
        self.on_raw_message = on_raw_message
        self.on_disconnect = on_disconnect
        self.on_connect = on_connect

        self.connected: bool = False
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None

        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task] = None

        # reconnect backoff state
        self._reconnect_delay = DEFAULT_RECONNECT_INTERVAL

        self._os_keepalive_enabled = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def start(self) -> None:
        """Indítja a kliens fő loopját (ha még nem fut)."""
        if self._task and not self._task.done():
            return

        self._stop_event.clear()
        if hasattr(self.hass, "async_create_task"):
            self._task = self.hass.async_create_task(self._run_loop())
        else:
            self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Leállítja a klienst és bezárja a kapcsolatot."""
        self._stop_event.set()

        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=3.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        await self.disconnect()
        _LOG.reset()

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            if not self.connected:
                await self._try_connect()

            if self.connected:
                await self._read_loop()

            if not self._stop_event.is_set():
                _LOG.warning(
                    f"Disconnected from {self.host}:{self.port}, "
                    f"retrying in {self._reconnect_delay:.1f}s."
                )
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(
                    self._reconnect_delay * 2, DEFAULT_MAX_RECONNECT_INTERVAL
                )

    # ------------------------------------------------------------------
    # Connect
    # ------------------------------------------------------------------
    async def _try_connect(self) -> None:
        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=5.0,
            )

            self.connected = True
            self._reconnect_delay = DEFAULT_RECONNECT_INTERVAL

            self._enable_os_keepalive()

            _LOG.info(f"Connected to {self.host}:{self.port}")
            _LOG.reset()

            await self._safe_callback(self.on_connect)

        except asyncio.TimeoutError:
            self.connected = False
            _LOG.warning(f"Connect timeout to {self.host}:{self.port}")

        except Exception as e:  # noqa: BLE001
            self.connected = False
            if not self._stop_event.is_set():
                _LOG.error(f"Connection failed to {self.host}:{self.port}: {e}")

    # ------------------------------------------------------------------
    # OS keepalive
    # ------------------------------------------------------------------
    def _enable_os_keepalive(self) -> None:
        try:
            if not self.writer:
                return

            sock = self.writer.get_extra_info("socket")
            if not sock:
                return

            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

            if hasattr(socket, "TCP_KEEPIDLE"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 15)
            if hasattr(socket, "TCP_KEEPINTVL"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 5)
            if hasattr(socket, "TCP_KEEPCNT"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 2)

            self._os_keepalive_enabled = True
            _LOG.debug(f"OS-level TCP keepalive enabled for {self.host}:{self.port}")
        except Exception as e:  # noqa: BLE001
            self._os_keepalive_enabled = False
            _LOG.debug(f"OS keepalive unavailable: {e}")

    # ------------------------------------------------------------------
    # Read loop
    # ------------------------------------------------------------------
    async def _read_loop(self) -> None:
        ping_interval = 15.0

        while not self._stop_event.is_set() and self.connected:
            try:
                if self._os_keepalive_enabled:
                    data = await self.reader.readuntil(b"\0")  # type: ignore[union-attr]
                else:
                    data = await asyncio.wait_for(  # type: ignore[union-attr]
                        self.reader.readuntil(b"\0"),
                        timeout=ping_interval,
                    )

                if not data:
                    _LOG.warning(f"Server closed connection ({self.host}:{self.port})")
                    break

                message = data[:-1].decode("utf-8", errors="ignore").strip()
                if not message or message == ":":
                    # keepalive jel, ignoráljuk
                    continue

                _LOG.debug(
                    f"Received raw message from {self.host}:{self.port}: {message!r}"
                )
                await self._safe_callback(self.on_raw_message, message)

            except asyncio.TimeoutError:
                # fallback keepalive
                try:
                    if self.writer:
                        self.writer.write(b":")
                        await self.writer.drain()
                except Exception:  # noqa: BLE001
                    _LOG.warning(f"Keepalive failed ({self.host}:{self.port})")
                    break

            except asyncio.IncompleteReadError:
                _LOG.warning(f"Incomplete read ({self.host}:{self.port})")
                break

            except Exception as e:  # noqa: BLE001
                _LOG.error(f"Read error {self.host}:{self.port}: {e}")
                break

        await self.disconnect()

    # ------------------------------------------------------------------
    # Disconnect
    # ------------------------------------------------------------------
    async def disconnect(self) -> None:
        if self.connected:
            self.connected = False
            await self._safe_callback(self.on_disconnect)

        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass

        self.reader = None
        self.writer = None

    # ------------------------------------------------------------------
    # Send helpers
    # ------------------------------------------------------------------
    async def send_message(self, message: Any) -> None:
        """Általános küldő.

        - dict → JSON + null terminátor
        - str  → text frame (ha nincs, automatikusan kap "\\0"-t)
        """
        if not self.connected or not self.writer:
            _LOG.warning(
                f"Cannot send message to {self.host}:{self.port}: not connected"
            )
            return

        try:
            if isinstance(message, dict):
                payload = json.dumps(message)
                data = payload.encode("utf-8") + b"\0"
            elif isinstance(message, str):
                text = message
                if not text.endswith("\0"):
                    text += "\0"
                data = text.encode("utf-8")
            else:
                _LOG.error(
                    f"Unsupported message type for send_message: {type(message)!r}"
                )
                return

            self.writer.write(data)
            await self.writer.drain()
            _LOG.debug(f"Sent message to {self.host}:{self.port}: {message!r}")
        except Exception as e:  # noqa: BLE001
            _LOG.error(f"Error sending message: {e}")
            await self.disconnect()

    async def send_text_frame(self, text: str) -> None:
        """Kényelmi wrapper szöveges (light mode) frame küldéséhez."""
        await self.send_message(text)

    # ------------------------------------------------------------------
    # Internal: callback futtatás (sync / async támogatás)
    # ------------------------------------------------------------------
    async def _safe_callback(
        self, cb: Optional[Callable[..., Any]], *args: Any
    ) -> None:
        if not cb:
            return
        try:
            result = cb(*args)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:  # noqa: BLE001
            _LOG.error(f"Callback error in TcpClient: {e}")

    # ------------------------------------------------------------------
    # HA-lifecycle aware start helper
    # ------------------------------------------------------------------
    def schedule_start(self) -> None:
        """Ütemezett indítás Home Assistant életciklus szerint.

        - Ha HA már fut: azonnal indítja a kliens fő loopját.
        - Ha még nem fut: vár az EVENT_HOMEASSISTANT_STARTED eseményre, és akkor indul.
        """
        from homeassistant.const import EVENT_HOMEASSISTANT_STARTED

        # HA már fut → azonnali start
        if getattr(self.hass, "is_running", False):
            if hasattr(self.hass, "async_create_task"):
                self.hass.async_create_task(self.start())
            else:
                asyncio.create_task(self.start())
            return

        # HA még nem fut → egyszeri callback induláskor
        async def _start_later(_event) -> None:
            try:
                if hasattr(self.hass, "async_create_task"):
                    self.hass.async_create_task(self.start())
                else:
                    asyncio.create_task(self.start())
            except Exception as e:  # noqa: BLE001
                _LOG.error(f"Error scheduling TcpClient start after HA start: {e}")

        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _start_later)
