# event_parser.py
"""
HaLink V3 – EVENT Parser

Támogatott formák:
1)  "event": "button1"

2)  "event": {
        "button1": "triple_click"
    }

3)  "event": {
        "rfid_reader": {
            "uid": "AA-11-22-33",
            "rssi": -44,
            "ts": 1700
        }
    }

Visszatérési érték (normalizált):

{
    "events": [
        {
            "key": "button1",
            "friendly_key": "button1",
            "value": "triple_click" | None,
            "attributes": { ... },
            "ts": <timestamp or None>
        },
        ...
    ]
}

Megjegyzés:
– Az EVENT parser nem ismeri a CONFIG-ot.
– Minden esemény dinamikusan, előzetes deklaráció nélkül működik.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional

from .utils import (
    normalize_key,
    normalize_friendly_name,
    ensure_type,
    log_invalid_format,
)


class EventParser:

    # -----------------------------------------------------------
    def parse_event(self, raw: Any) -> Dict[str, List[Dict[str, Any]]]:
        """
        Normalizálja az EVENT blokkot.
        OUTPUT:
        {
            "events": [ {event1}, {event2}, ... ]
        }
        """
        result = {"events": []}

        # -----------------------------------------------
        # 1) Egyszerű string:
        #    "event": "button1"
        # -----------------------------------------------
        if isinstance(raw, str):
            ev = self._parse_simple_string_event(raw)
            if ev:
                result["events"].append(ev)
            return result

        # -----------------------------------------------
        # 2) Objektum: { key: value }
        # -----------------------------------------------
        if isinstance(raw, dict):
            for key, val in raw.items():
                ev = self._parse_key_value_event(key, val)
                if ev:
                    result["events"].append(ev)
            return result

        # -----------------------------------------------
        # Invalid format
        # -----------------------------------------------
        log_invalid_format("event_parser", "event root must be string or dict")
        return result

    # -----------------------------------------------------------
    def _parse_simple_string_event(self, key: str) -> Optional[Dict[str, Any]]:
        """Egyszerű EVENT: 'button1'."""
        norm = normalize_key(key)
        if not norm:
            log_invalid_format("event_parser", f"invalid event key: {key!r}")
            return None

        return {
            "key": norm,
            "friendly_key": normalize_friendly_name(key),
            "value": None,
            "attributes": {},
            "ts": None,
        }

    # -----------------------------------------------------------
    def _parse_key_value_event(self, key: str, val: Any) -> Optional[Dict[str, Any]]:
        """Kulcs → érték vagy objektum események feldolgozása."""
        norm = normalize_key(key)
        if not norm:
            log_invalid_format("event_parser", f"invalid event key: {key!r}")
            return None

        # -----------------------------------------------
        # a) "button": "double_click"
        # -----------------------------------------------
        if isinstance(val, str):
            return {
                "key": norm,
                "friendly_key": normalize_friendly_name(key),
                "value": val,
                "attributes": {},
                "ts": None,
            }

        # -----------------------------------------------
        # b) "rfid": { "uid": "...", "ts": 1700 }
        # -----------------------------------------------
        if isinstance(val, dict):
            ts_raw = val.get("ts")
            if isinstance(ts_raw, (int, float)):
                ts_val = int(ts_raw)
            else:
                ts_val = None

            attrs = dict(val)
            attrs.pop("ts", None)

            return {
                "key": norm,
                "friendly_key": normalize_friendly_name(key),
                "value": None,
                "attributes": attrs,
                "ts": ts_val,
            }

        # -----------------------------------------------
        # c) ismeretlen formátum
        # -----------------------------------------------
        log_invalid_format("event_parser", f"invalid event value for key {key!r}: {val!r}")
        return None
