# state_parser.py
"""HaLink V3 – STATE Parser

Feladat:
    - A CONFIG-től függetlenül feldolgozni a STATE üzenetet.
    - Támogatni a két fő formátumot:
        1) egyszerű érték: "room_temperature": 21.3
        2) objektum: "room_temperature": {"value": 21.3, "attributes": {...}, "ts": 1700}
    - Speciális "alive" kulcs kezelése:
        "alive": {"value": "online", "attributes": {...}}

Kimenet (normalizált struktúra):

{
  "alive": {
      "value": "online" | "offline" | None,
      "attributes": {...},
      "ts": <int|None>
  } | None,

  "entities": {
      "room_temperature": {
          "key": "room_temperature",
          "friendly_key": "Room temperature",  # opcionális, itt most az eredeti kulcs
          "value": 21.3,
          "attributes": { ... },
          "ts": 1700 | None,
      },
      ...
  }
}
"""

from __future__ import annotations
from typing import Any, Dict, Optional

from .utils import (
    normalize_key,
    normalize_friendly_name,
    merge_attributes,
    ensure_type,
    safe_get,
    log_invalid_format,
)


class StateParser:
    """V3 STATE parser.

    A parser szándékosan NEM ismeri a CONFIG-ot.
    Csak a bejövő STATE struktúrát normalizálja.
    """

    # ---------------------------------------------------------------
    def parse_state(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Normalizálja a STATE blokkot."""
        if not isinstance(raw, dict):
            log_invalid_format("state_parser", "STATE root is not dict")
            return {"alive": None, "entities": {}}

        result: Dict[str, Any] = {
            "alive": None,
            "entities": {},
        }

        for key, value in raw.items():
            norm_key = normalize_key(key)

            if norm_key == "alive":
                result["alive"] = self._parse_alive(value)
            else:
                ent = self._parse_entity_state(key, value)
                if ent is not None:
                    result["entities"][ent["key"]] = ent

        return result

    # ---------------------------------------------------------------
    def _parse_alive(self, raw: Any) -> Optional[Dict[str, Any]]:
        """Speciális alive entitás.

        Elvárt forma:
            "alive": {
                "value": "online" | "offline",
                "attributes": { ... },
                "ts": 1700 (opcionális)
            }

        A value technikailag redundáns, de megtartjuk.
        """
        if not isinstance(raw, dict):
            # ha csak egy stringet kapunk, azt is elfogadjuk
            return {
                "value": raw,
                "attributes": {},
                "ts": None,
            }

        val = raw.get("value")
        attrs = ensure_type(raw.get("attributes"), (dict,), default={}) or {}
        ts = raw.get("ts")
        if isinstance(ts, (int, float)):
            ts_val: Optional[int] = int(ts)
        else:
            ts_val = None

        return {
            "value": val,
            "attributes": attrs,
            "ts": ts_val,
        }

    # ---------------------------------------------------------------
    def _parse_entity_state(self, original_key: str, raw: Any) -> Optional[Dict[str, Any]]:
        """Egy generikus entitás state feldolgozása."""
        norm_key = normalize_key(original_key)
        if not norm_key:
            log_invalid_format("state_parser", f"empty normalized key for {original_key!r}")
            return None

        value: Any
        attrs: Dict[str, Any]
        ts_val: Optional[int]

        if isinstance(raw, dict):
            # két eset: value kulccsal vagy anélkül
            if "value" in raw:
                value = raw.get("value")
                attrs = ensure_type(raw.get("attributes"), (dict,), default={}) or {}
                ts = raw.get("ts")
                if isinstance(ts, (int, float)):
                    ts_val = int(ts)
                else:
                    ts_val = None
            else:
                # nincs value kulcs: tekintsük úgy, hogy itt csak attribútumok vannak
                value = None
                attrs = raw
                ts_val = None
        else:
            # primitív forma: közvetlenül az érték
            value = raw
            attrs = {}
            ts_val = None

        return {
            "key": norm_key,
            "friendly_key": normalize_friendly_name(original_key),
            "value": value,
            "attributes": attrs,
            "ts": ts_val,
        }
