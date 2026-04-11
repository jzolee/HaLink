# const.py
DOMAIN = "halink"

CONF_HOST = "host"
CONF_PORT = "port"

# Entry-specifikus dispatcher csatornák
SIGNAL_CONFIG_UPDATE = f"{DOMAIN}_config_update_{{}}"
SIGNAL_DATA_RECEIVED = f"{DOMAIN}_data_received_{{}}"
SIGNAL_CONNECTION_STATE = f"{DOMAIN}_connection_state_{{}}"
SIGNAL_ALIVE_STATE = f"{DOMAIN}_alive_state_{{}}"

DEFAULT_PORT = 5000
DEFAULT_RECONNECT_INTERVAL = 5.0
DEFAULT_MAX_RECONNECT_INTERVAL = 60.0

# HaLink message types
MESSAGE_CONFIG = "config"
MESSAGE_STATE = "state"
MESSAGE_SET = "set"

RESERVED_ENTITY_KEYS = {"alive"}
