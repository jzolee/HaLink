# utils.py

import re
import unicodedata
from typing import Any, Dict, Tuple

from homeassistant.helpers.dispatcher import async_dispatcher_connect

async def async_setup_platform_common(hass, config_entry, async_add_entities, platform: str, entity_cls):
    """Közös platform setup HaLink entitásokhoz."""
    from .const import DOMAIN

    device_id = config_entry.data.get("device_id")

    async def _create(device_id_from_signal, ent_cfg):
        if device_id_from_signal != device_id:
            return
        device = hass.data[DOMAIN][device_id]
        ent = entity_cls(hass, device, ent_cfg)
        async_add_entities([ent])

    async_dispatcher_connect(
        hass,
        f"{DOMAIN}_create_{platform}",
        _create,
    )

# -----------------------------
# 1. NORMALIZATION
# -----------------------------

def normalize_key(key: str) -> str:
    """Normalize any string into a safe entity/config key.
    Steps:
    - lowercase
    - trim spaces
    - remove accents
    - spaces -> underscore
    - remove non-alphanumeric/underscore
    - collapse multiple underscores
    """
    if not isinstance(key, str):
        return ""

    k = key.strip().lower()
    # remove accents
    k = unicodedata.normalize("NFKD", k)
    k = "".join(c for c in k if not unicodedata.combining(c))
    # replace spaces with underscore
    k = re.sub(r"\s+", "_", k)
    # keep only letters, digits, underscore
    k = re.sub(r"[^a-z0-9_]+", "", k)
    # collapse multiple underscores
    k = re.sub(r"_+", "_", k)
    return k

def normalize_friendly_name(name: str) -> str:
    if not isinstance(name, str):
        return ""
    return name.strip()

def generate_entity_id(meta: Dict[str, Any], key: str, platform: str) -> str:
    """Entity ID generálása egységes meta adatokból.

    meta tartalmazhatja:
      - "name" vagy "device_name": integráció telepítésekor megadott név
      - "entry_id": config entry azonosító
      - "domain": integráció domain (pl. "halink")
      - "host", "port", "device_id": technikai azonosítók
    """
    key = normalize_key(key)
    # Elsődlegesen a felhasználó által adott névből képezzük az ID-t
    base = (
        meta.get("name")
        or meta.get("device_name")
        or meta.get("host")
        or meta.get("device_id")
        or ""
    )
    base = normalize_key(str(base)) if base else "halink"
    return f"{platform}.{base}_{key}"

def generate_unique_id(meta: Dict[str, Any], key: str) -> str:
    """Globálisan egyedi ID generálása.

    Elsődleges forrás: config entry ID + entity key.
    Ha az entry_id nem áll rendelkezésre, domain+host+port alapú fallbacket használunk.
    """
    key = normalize_key(key)
    #entry_id = (
    #    normalize_key(str(meta.get("entry_id", "")))
    #    if meta.get("entry_id")
    #    else ""
    #)
    #if entry_id:
    #    return f"{entry_id}_{key}"

    # fallback: domain + host + port
    domain = normalize_key(str(meta.get("domain", "halink")))
    host = normalize_key(str(meta.get("host", ""))) if meta.get("host") else ""
    port = str(meta.get("port", "")).strip()
    base_parts = [p for p in (domain, host, port) if p]
    base = "_".join(base_parts) if base_parts else "halink"
    return f"{base}_{key}"

# -----------------------------
# 2. SHORT KEY EXPANSION
# -----------------------------

def expand_short_keys(obj: Dict[str, Any], mapping: Dict[str, str]) -> Dict[str, Any]:
    if not isinstance(obj, dict):
        return obj
    out = {}
    for k, v in obj.items():
        full = mapping.get(k, k)  # replace if exists
        out[full] = v
    return out

# These helpers will be filled by parsers using short_keys.py mappings

def expand_root_short_keys(obj: Dict[str, Any]) -> Dict[str, Any]:
    from .short_keys import ROOT_KEYS
    return expand_short_keys(obj, ROOT_KEYS)

def expand_platform_short_keys(obj: Dict[str, Any], platform: str) -> Dict[str, Any]:
    from .short_keys import PLATFORM_KEYS
    mapping = PLATFORM_KEYS.get(platform, {})
    return expand_short_keys(obj, mapping)

def expand_entity_short_keys(obj: Dict[str, Any], platform: str) -> Dict[str, Any]:
    """
    Entitás-szintű rövid kulcsok kibontása.

    - ENTITY_KEYS["*"] : közös kulcsok (dc, u, ic, ec, sc, attr, as, opt, ...)
    - ENTITY_KEYS[platform] : platform-specifikus (pl. number: mn/mx/st/m)
    """
    from .short_keys import ENTITY_KEYS

    mapping: Dict[str, str] = {}

    # Közös, minden platformra érvényes rövid kulcsok
    common = ENTITY_KEYS.get("*", {})
    if isinstance(common, dict):
        mapping.update(common)

    # Platform-specifikus rövid kulcsok
    platform_map = ENTITY_KEYS.get(platform, {})
    if isinstance(platform_map, dict):
        mapping.update(platform_map)

    return expand_short_keys(obj, mapping)


def expand_general_short_keys(obj: Dict[str, Any]) -> Dict[str, Any]:
    from .short_keys import GENERAL_KEYS
    return expand_short_keys(obj, GENERAL_KEYS)

# -----------------------------
# 3. DICT MERGE & ATTRIBUTES
# -----------------------------

def deep_merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(a)
    for k, v in b.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result

def merge_attributes(*dicts: Dict[str, Any]) -> Dict[str, Any]:
    merged = {}
    for d in dicts:
        if isinstance(d, dict):
            merged.update(d)
    return merged

# -----------------------------
# 4. TYPE CHECKS & RAW SET PARSER
# -----------------------------

def ensure_type(value: Any, expected: Tuple[type, ...], default=None):
    if isinstance(value, expected):
        return value
    return default

def safe_get(obj: Dict[str, Any], key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default

def is_primitive(value: Any) -> bool:
    return isinstance(value, (int, float, str, bool)) or value is None


def parse_raw_set_light_mode(text: str) -> Tuple[str, str]:
    """Parse `key=value\0` format.
    Returns (key, value_str)
    """
    if text.endswith("\0"):
        text = text[:-1]
    if "=" not in text:
        return "", ""
    key, val = text.split("=", 1)
    return normalize_key(key), val

# -----------------------------
# 5. LOG HELPERS
# -----------------------------
from .logger import DedupLogger
log = DedupLogger(name="halink.utils")

def log_unknown_key(ctx: str, key: str):
    log.debug(f"Unknown key in {ctx}: {key}")

def log_invalid_format(ctx: str, msg: str):
    log.debug(f"Invalid format in {ctx}: {msg}")

def log_missing_required(ctx: str, key: str):
    log.debug(f"Missing required field `{key}` in {ctx}")

def log_entity_not_found(entity: str):
    log.debug(f"Entity not found: {entity}")
