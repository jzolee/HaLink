# message_parser.py
"""
HaLink V3 Message Parser
------------------------
A bejövő raw JSON üzenetet osztályozza: CONFIG / STATE / EVENT.
A további feldolgozást a specializált parserek végzik.

Output formátum minden esetben:
{
    "type": "config" | "state" | "event",
    "data": <normalizált adatstruktúra>
}

Ha ismeretlen vagy hibás üzenet érkezik, "None"-t ad vissza.
"""

from __future__ import annotations
import json
from typing import Any, Dict, Optional

from .utils import expand_root_short_keys, log_invalid_format
from .config_parser import ConfigParser
from .state_parser import StateParser
from .event_parser import EventParser

class MessageParser:
    def __init__(self):
        self._config = ConfigParser()
        self._state = StateParser()
        self._event = EventParser()

    # ------------------------------------------------------------------
    def parse(self, raw: str) -> Optional[Dict[str, Any]]:
        """A raw TCP üzenet feldolgozása.
        Visszaad egy egységes normalizált struktúrát vagy None-t.
        """
        if not raw:
            return None

        # JSON próbálás
        try:
            data = json.loads(raw)
        except Exception:
            log_invalid_format("message_parser", "JSON decoding failed")
            return None

        if not isinstance(data, dict):
            log_invalid_format("message_parser", "root is not a dict")
            return None

        # Gyökér rövid kulcsok kiterjesztése
        data = expand_root_short_keys(data)

        # Esemény típusa
        if "config" in data:
            parsed = self._config.parse_config(data["config"])
            return {"type": "config", "data": parsed}

        if "state" in data:
            parsed = self._state.parse_state(data["state"])
            return {"type": "state", "data": parsed}

        if "event" in data:
            parsed = self._event.parse_event(data["event"])
            return {"type": "event", "data": parsed}

        # Ismeretlen üzenet
        log_invalid_format("message_parser", f"unknown root keys: {list(data.keys())}")
        return None
