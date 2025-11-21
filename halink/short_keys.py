# short_keys.py
"""Short key mapping táblák a HaLink ultra-compact üzenetekhez (V2/V3).

Itt *csak* a rövid→hosszú kulcs mapping van.
A tényleges bővítést a utils.py végzi (expand_* függvények).
"""

from __future__ import annotations

from typing import Dict

# ---------------------------------------------------------------------------
# ROOT SZINT – üzenet gyökere
# ---------------------------------------------------------------------------
# TCP → JSON után a gyökér kulcsok rövidítése:
#  c  -> config
#  s  -> state
#  e  -> event

ROOT_KEYS: Dict[str, str] = {
    "c": "config",
    "s": "state",
    "e": "event",
}

# ---------------------------------------------------------------------------
# ÁLTALÁNOS / CONFIG SZINTŰ KULCSOK
# ---------------------------------------------------------------------------
# Ezek a config["..."] alatt fordulnak elő.
# (A teljes értelmezés a config_parser.py-ben lesz.)

CONFIG_KEYS: Dict[str, str] = {
    # Protokoll verzió
    "v": "version",

    # Eszköz metaadat
    "d": "device",

    # Base konfiguráció
    "b": "base",

    # Platformok: sensor / number / switch / binary_sensor / button
    "s": "sensor",
    "n": "number",
    "sw": "switch",
    "bs": "binary_sensor",
    "bn": "button",

    # Alive / diagnostics blokk (V3-ban: "alive")
    "al": "alive",

    # Események
    "ev": "events",

    # Beállítások a SET protokollhoz
    "sm": "set_mode",    # pl. "light" / "object"
    "ts": "ts_enable",   # timestamp engedélyezés
    "dm": "delay_ms",    # SET üzenetek közötti minimális delay

    # V2 kompatibilitás (nem kötelező, de elfogadhatjuk)
    "bset": "batch_set",
    "lm": "light_mode",
}

# GENERAL_KEYS: tágabb halmaz, amit több szinten is használhatunk,
# pl. ha a parser egyszerre szeretné a globális rövidítéseket bővíteni.
GENERAL_KEYS: Dict[str, str] = {
    **CONFIG_KEYS,
    # ide később felvehetünk közös rövid kulcsokat, ha szükséges
}

# ---------------------------------------------------------------------------
# DEVICE SZINTŰ RÖVIDÍTÉSEK – config["device"] alatt
# ---------------------------------------------------------------------------

DEVICE_KEYS: Dict[str, str] = {
    "m": "manufacturer",
    "mod": "model",
    "sw": "sw_version",
    "hw": "hw_version",
    "n": "name",
}

# ---------------------------------------------------------------------------
# PLATFORM SZINTŰ RÖVIDÍTÉSEK – config["sensor"], ["number"], stb.
# ---------------------------------------------------------------------------
# Ezek platformonként eltérhetnek, ezért külön dict-be tesszük őket.

PLATFORM_KEYS: Dict[str, Dict[str, str]] = {
    "sensor": {
        "dc": "device_class",
        "u": "unit_of_measurement",
        "ic": "icon",
        "ec": "entity_category",
        "sc": "state_class",
        "attr": "attributes",
    },
    "number": {
        "dc": "device_class",
        "u": "unit_of_measurement",
        "ic": "icon",
        "ec": "entity_category",
        "sc": "state_class",
        "attr": "attributes",
        "mn": "min",
        "mx": "max",
        "st": "step",
        "m": "mode",
    },
    "switch": {
        "ic": "icon",
        "ec": "entity_category",
        "attr": "attributes",
    },
    "binary_sensor": {
        "dc": "device_class",
        "ic": "icon",
        "ec": "entity_category",
        "attr": "attributes",
    },
    "select": {
        "dc": "device_class",
        "ic": "icon", 
        "ec": "entity_category",
        "attr": "attributes",
        "opt": "options",
        "def": "default",
    },
    "button": {
        "dc": "device_class",
        "ic": "icon", 
        "ec": "entity_category",
        "attr": "attributes",
        "pv": "press_value",
    },
}

# ---------------------------------------------------------------------------
# ENTITÁS SZINTŰ RÖVIDÍTÉSEK – egy konkrét entitás definícióján belül
# ---------------------------------------------------------------------------
# Ezek átfedik a PLATFORM_KEYS-et, de itt platformfüggetlenül is megadhatók.
# A parser döntheti el, mit használ.

ENTITY_KEYS: Dict[str, Dict[str, str]] = {
    "*": {  # közös, minden platformra
        "dc": "device_class",
        "u": "unit_of_measurement",
        "ic": "icon",
        "ec": "entity_category",
        "sc": "state_class",
        "attr": "attributes",
        "as": "assumed_state",
        "opt": "options",
        "pv": "press_value",
    },
    # ha kell platform-specifikus szintű override, ide tehetjük:
    "number": {
        "mn": "min",
        "mx": "max",
        "st": "step",
        "m": "mode",
    },
}

# ---------------------------------------------------------------------------
# NUMBER SPECIFIKUS RÖVIDÍTÉSEK – ha külön kell (legacy kompatibilitás)
# ---------------------------------------------------------------------------

NUMBER_KEYS: Dict[str, str] = {
    "mn": "min",
    "mx": "max",
    "st": "step",
    "m": "mode",
}
