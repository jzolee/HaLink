# config_parser.py
"""
HaLink V3 – CONFIG Parser
=========================
Ez a modul a V3 CONFIG üzenetek feldolgozásáért felelős.
A parser feladata:
    - root & config short key-ek kibontása
    - base / platform / entity short key-ek kibontása
    - entitás platformok normalizálása
    - entitások összeállítása (base + platform + entity override)
    - set_mode, ts_enable, delay_ms kezelése
    - alive blokk kezelése (diagnostics → alive)
    - egységes normalizált output készítése
"""

from __future__ import annotations
from typing import Dict, Any

from .utils import (
    normalize_key,
    normalize_friendly_name,
    expand_short_keys,
    expand_general_short_keys,
    expand_platform_short_keys,
    expand_entity_short_keys,
    deep_merge,
    merge_attributes,
    log_invalid_format,
)
from .short_keys import CONFIG_KEYS, DEVICE_KEYS, PLATFORM_KEYS, ENTITY_KEYS


class ConfigParser:
    def parse_config(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """CONFIG fő feldolgozása, normalizált Python struktúrára.
        OUTPUT (példa):
        {
           "version": 3,
           "device": {...},
           "alive": {...},
           "events": {...},
           "set_mode": "light",
           "ts_enable": false,
           "delay_ms": 0,
           "base": { ... },
           "entities": {
                "room_temperature": { "platform": "sensor", ...},
                ...
            }
        }
        """
        if not isinstance(raw, dict):
            log_invalid_format("config_parser", "CONFIG root is not dict")
            return {}

        # ----------------------------------------------------
        # CONFIG rövid kulcsok kibontása (root szint)
        #   b  -> base
        #   s  -> sensor
        #   n  -> number
        #   sw -> switch
        #   bs -> binary_sensor
        #   al -> alive
        #   ev -> events
        # stb.
        # ----------------------------------------------------
        raw = expand_short_keys(raw, CONFIG_KEYS)

        out: Dict[str, Any] = {}

        # -------------------------------
        # Kötelező: version
        # -------------------------------
        version = raw.get("version")
        if not isinstance(version, int):
            log_invalid_format("config_parser", "invalid or missing version")
            version = None
        out["version"] = version

        # -------------------------------
        # Opcionális: device blokk
        # -------------------------------
        device_block = raw.get("device", {})
        if isinstance(device_block, dict):
            device_block = expand_short_keys(device_block, DEVICE_KEYS)
        out["device"] = device_block or {}

        # -------------------------------
        # Alive blokk
        # -------------------------------
        alive_block = raw.get("alive", {})
        if isinstance(alive_block, dict):
            out["alive"] = alive_block
        else:
            out["alive"] = {}

        # -------------------------------
        # Events blokk
        # -------------------------------
        events_block = raw.get("events", {})
        if isinstance(events_block, dict):
            out["events"] = events_block
        else:
            out["events"] = {}

        # -------------------------------
        # SET módok (light / object)
        # -------------------------------
        out["set_mode"] = raw.get("set_mode", "light")
        out["ts_enable"] = bool(raw.get("ts_enable", False))
        out["delay_ms"] = int(raw.get("delay_ms", 0))

        # -------------------------------
        # BASE blokk feldolgozása
        #
        #  Várt forma (V3, short key-kkel is mehet):
        #    "base": {
        #        "*": { ... },
        #        "s": { ... },        # sensor
        #        "n": { ... },        # number
        #        "sw": { ... },       # switch
        #        "bs": { ... },       # binary_sensor
        #        "select": { ... }    # (ha kell)
        #    }
        #
        #  Itt kétféle kulcsváltás kell:
        #   1) platform rövid kulcsai (s/n/sw/bs) → sensor/number/...
        #   2) a platformon belüli rövid kulcsok (dc/u/ic/...) → long form
        # -------------------------------
        base_block_raw = raw.get("base", {})
        if isinstance(base_block_raw, dict):
            # 1) platform short key-ek kibontása (s → sensor, n → number, stb.)
            #    FIGYELEM: itt is CONFIG_KEYS-t használjuk, mert abban vannak
            #    definiálva a platform rövidítések.
            base_block = expand_short_keys(base_block_raw, CONFIG_KEYS)

            base_final: Dict[str, Dict[str, Any]] = {}
            for key, val in base_block.items():
                if not isinstance(val, dict):
                    continue

                if key == "*":
                    # minden platformra érvényes default
                    base_final["*"] = expand_general_short_keys(val)
                else:
                    # adott platformra érvényes
                    pkey = normalize_key(key)

                    # Ha ismert platform (sensor/number/switch/binary_sensor/select),
                    # akkor a platform-specifikus short kulcsokat is bontsuk ki:
                    if pkey in PLATFORM_KEYS:
                        mapped = expand_platform_short_keys(val, pkey)
                        base_final[pkey] = mapped
                    else:
                        # ismeretlen kulcs: nyersen visszük tovább
                        base_final[pkey] = val
        else:
            base_final = {}

        out["base"] = base_final

        # -------------------------------
        # Entitások összegyűjtése
        # -------------------------------
        all_entities: Dict[str, Dict[str, Any]] = {}

        # platformok: sensor, number, switch, binary_sensor, select
        for platform in ("sensor", "number", "switch", "binary_sensor", "select"):
            block = raw.get(platform, {})
            if not isinstance(block, dict):
                continue

            # platform-szintű short keys itt már nincsenek,
            # csak entitásszintű rövid kulcsokat bontunk ki.
            for friendly_name, entity_def in block.items():
                if not isinstance(entity_def, dict):
                    entity_def = {}

                # entitás-szintű rövid kulcsok:
                #  - közös (ENTITY_KEYS["*"])
                #  - platform-specifikus (ENTITY_KEYS[platform])
                entity_def = expand_entity_short_keys(entity_def, platform)

                # normalizált key (STATE / SET ezt használja)
                normalized_key = normalize_key(friendly_name)

                # entitás base összeállítása:
                # 1) base[*]
                b_global = base_final.get("*", {})
                # 2) base[platform]
                b_platform = base_final.get(platform, {})
                # 3) entity-def override
                final = deep_merge(b_global, b_platform)
                final = deep_merge(final, entity_def)

                # platform + friendly name + key
                final["platform"] = platform
                final["friendly_name"] = normalize_friendly_name(friendly_name)
                final["key"] = normalized_key

                # attributes háromszintű merge
                attrs = merge_attributes(
                    b_global.get("attributes"),
                    b_platform.get("attributes"),
                    entity_def.get("attributes"),
                )
                if attrs:
                    final["attributes"] = attrs

                all_entities[normalized_key] = final

        out["entities"] = all_entities
        return out
