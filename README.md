## HaLink – Home Assistant Integration (V3 Protocol)

HaLink is a **TCP-based local control protocol** designed for microcontroller devices.
This Home Assistant custom integration implements the **full HaLink V3 specification**, providing:

* ultra-fast, offline, deterministic device control
* dynamic entities defined by firmware
* SET / STATE / EVENT communication
* automatic entity creation
* fully async TCP client
* built-in `alive` connectivity sensor
* selectable SET modes (light / object)
* configurable SET queue with TTL & delay
* compact short-key protocol support

The integration is ideal for **ESP32/STM32/Pico** devices or any microcontroller with a TCP stack and JSON encoding.

---

## ✨ Features

### ✔ Dynamic entity model

Entities are **not pre-defined** in the integration.
They are created by the device through a **CONFIG** message exactly matching the device’s capabilities.

Supported entity types:

* Sensor
* Number
* Switch
* Binary Sensor
* Select
* Button
* (plus an automatically created *Alive* sensor)

Each entity receives:

* device_class
* unit
* min/max/step
* icon
* attributes
* state_class
* entity_category
* custom metadata (merged)

---

### ✔ Fully asynchronous TCP engine

The integration includes an advanced async TCP client:

* auto-reconnect with exponential backoff
* OS-level TCP keepalive
* null-terminated frame decoder
* fallback ping (lightweight ":" messages)
* message dispatch via HA’s dispatcher bus

---

### ✔ Full HaLink V3 Protocol Support

Implements the complete specification (see `halink_v3_specification.txt`):


* CONFIG
* STATE
* SET (light/object)
* EVENT

Short-key expansions are handled automatically.

---

## 📦 Installation

### HACS (planned)

Coming soon.

### Manual installation

1. Copy the folder:
   `custom_components/halink/`
2. Restart Home Assistant
3. Add Integration → **HaLink Device**
4. Enter:

   * Host
   * Port
   * Friendly name

---

## 🧠 How It Works

### 1. Initial connection

When HA connects to the device:

* TCP client connects
* waits for `CONFIG`
* starts CONFIG-handshake timeout (5 seconds)
* launches SET-queue worker if `delay_ms` > 0

---

### 2. CONFIG message → entity creation

Firmware sends:

```json
{
  "config": {
    "version": 3,
    "sensor": {
      "Room Temperature": { "unit": "°C", "device_class": "temperature" }
    },
    "switch": {
      "Heater": {}
    }
  }
}
```

HA:

* parses CONFIG
* normalizes keys
* merges base/platform/entity attributes
* creates requested entities
* notifies all platforms using dispatcher signals
  (e.g. `halink_create_sensor`)

CONFIG parser:


Entity creation is performed in `device.py`:


---

### 3. STATE updates

STATE messages update the entities:

```json
{
  "state": {
    "room_temperature": 21.4,
    "heater": 1
  }
}
```

All entity updates go through dispatcher:
 → `_process_state()`

Each entity class applies only platform-specific logic:

* sensor → `_attr_native_value`
* switch → `_attr_is_on`
* number → `_attr_native_value`
* select → `current_option`

Platform example (sensor):


---

### 4. SET Commands (HA → device)

Two modes:

#### Light mode

```
override_enable=1\0
```

#### Object mode

```json
{ "set": { "override_temp": { "value": 22.5 } } }
```

Handled in:
 → `send_set()`

---

### 5. Events

Events do **not require CONFIG definition**.

Example:

```json
{ "event": "button1" }
```

Normalized and fired as HA events:

```
halink_event.<device_id>.button1
```

EVENT parser:


---

## 🛠 Firmware Developer Guide

Your device only needs to:

1. Open a TCP server
2. Accept connection
3. Send CONFIG once
4. Send STATE changes
5. Send EVENT messages when needed
6. Parse SET messages from the integration

### Minimal firmware sequence

```
Device boots →
Wait for TCP client (HA) →
On connect:
    Send CONFIG
    Start sending STATE periodically or when changed
On SET:
    Apply command
On EVENT:
    Send event immediately
```

### CONFIG is mandatory

If CONFIG is not received within 5 seconds, HA will auto-disconnect and reconnect.

---

## 📁 Project Structure

```
halink/
  ├── __init__.py              # HA integration setup
  ├── config_flow.py           # User setup UI
  ├── device.py                # Device manager (CONFIG/STATE/EVENT, SET engine)  :contentReference[oaicite:7]{index=7}
  ├── client.py                # Async TCP client                                 :contentReference[oaicite:8]{index=8}
  ├── message_parser.py        # Root parser (config/state/event)                 :contentReference[oaicite:9]{index=9}
  ├── config_parser.py         # CONFIG normalization                             :contentReference[oaicite:10]{index=10}
  ├── state_parser.py          # STATE normalization                              :contentReference[oaicite:11]{index=11}
  ├── event_parser.py          # EVENT normalization                              :contentReference[oaicite:12]{index=12}
  ├── base_entity.py           # Common entity logic                              :contentReference[oaicite:13]{index=13}
  ├── sensor.py, number.py,
  │   switch.py, binary_sensor.py,
  │   select.py, button.py     # Platform implementations                         (files cited above)
  ├── utils.py                 # Short-key expansion, ID generation               :contentReference[oaicite:14]{index=14}
  ├── short_keys.py            # Short-key mapping tables                         :contentReference[oaicite:15]{index=15}
  └── halink_v3_specification.txt  # Full protocol spec                           :contentReference[oaicite:16]{index=16}
```

---

## 📚 HaLink V3 Specification

A full protocol description is included:
**halink_v3_specification.txt**


---

## 🤝 Contributing

Pull requests, suggestions, and discussions are welcome!

---

## 📜 License

MIT License.

---

# 🔥 **Firmware Examples for HaLink V3**

---

# ✅ **1. ESP32 – Arduino (C++) – Full Working Example**

### ✔ TCP client

### ✔ CONFIG V3

### ✔ STATE sending

### ✔ EVENT sending

### ✔ SET receiving (light mode)

### ✔ Null-terminated protocol

```cpp
#include <WiFi.h>
#include <WiFiClient.h>
#include <ArduinoJson.h>

WiFiClient client;

const char* ssid = "WIFI";
const char* pass = "PASS";
const char* host = "homeassistant.local"; 
const int   port = 5001;                  // Same as HA integration

unsigned long lastStateSent = 0;

void sendJson(const JsonDocument& doc) {
    String out;
    serializeJson(doc, out);
    out += '\0';      // <-- HaLink V3 protocol requirement
    client.print(out);
}

void sendConfig() {
    StaticJsonDocument<1024> doc;

    auto cfg = doc["config"].to<JsonObject>();
    cfg["version"] = 3;
    cfg["set_mode"] = "light";    // or "object"
    cfg["delay_ms"] = 0;

    // device metadata
    auto dev = cfg["device"].to<JsonObject>();
    dev["manufacturer"] = "ESP32";
    dev["model"] = "BoilerController";
    dev["sw_version"] = "1.0";

    // entities
    auto sensors = cfg["sensor"].to<JsonObject>();
    sensors["Room Temperature"]["unit"] = "°C";
    sensors["Outer Temperature"]["unit"] = "°C";

    auto switches = cfg["switch"].to<JsonObject>();
    switches["Heater"] = JsonObject();

    sendJson(doc);
}

void sendState() {
    StaticJsonDocument<512> doc;

    auto st = doc["state"].to<JsonObject>();
    st["room_temperature"] = 21.7;
    st["outer_temperature"] = 4.2;
    st["heater"] = 1;

    sendJson(doc);
}

void sendEvent(const char* key) {
    StaticJsonDocument<256> doc;
    doc["event"] = key;
    sendJson(doc);
}

void processSet(const String& raw) {
    // light mode: key=value
    if (!raw.contains("=")) return;

    int eq = raw.indexOf('=');
    String key = raw.substring(0, eq);
    String val = raw.substring(eq + 1);

    Serial.printf("[SET] %s = %s\n", key.c_str(), val.c_str());

    if (key == "heater") {
        int v = val.toInt();
        digitalWrite(5, v);
    }
}

void setup() {
    Serial.begin(115200);
    pinMode(5, OUTPUT);

    WiFi.begin(ssid, pass);
    while (WiFi.status() != WL_CONNECTED) delay(200);

    while (!client.connect(host, port)) {
        Serial.println("Retry connect...");
        delay(1000);
    }

    sendConfig();
}

String rx;

void loop() {
    // process incoming SET commands
    while (client.available()) {
        char c = client.read();
        if (c == '\0') {
            processSet(rx);
            rx = "";
        } else {
            rx += c;
        }
    }

    // send state every 5 sec
    if (millis() - lastStateSent > 5000) {
        sendState();
        lastStateSent = millis();
    }

    // example event after 10 sec
    if (millis() > 10000)
        sendEvent("button1");
}
```

---

# ✅ **2. ESP32 – Arduino (C++) – Object SET Mode Example**

```cpp
void processSetObject(const String& json) {
    StaticJsonDocument<256> doc;
    if (deserializeJson(doc, json)) return;

    if (!doc.containsKey("set")) return;

    JsonObject set = doc["set"].as<JsonObject>();
    for (auto kv : set) {
        const char* key = kv.key().c_str();
        float value = kv.value()["value"].as<float>();

        Serial.printf("[SET OBJECT] %s = %f\n", key, value);

        if (strcmp(key, "override_temperature") == 0) {
            // apply override
        }
    }
}
```

Light/Object mód között a HA integráció automatikusan vált a CONFIG alapján.

---

# ✅ **3. ESP32 – ESP-IDF (C) Minimal TCP Implementation**

```c
static void send_raw(const char* s) {
    send(sock, s, strlen(s), 0);
    send(sock, "\0", 1, 0);
}

static void send_config() {
    const char* cfg =
        "{"
        "\"config\":{"
            "\"version\":3,"
            "\"set_mode\":\"light\","
            "\"sensor\":{\"Temperature\":{\"u\":\"C\"}},"
            "\"switch\":{\"Pump\":{}}"
        "}"
        "}";

    send_raw(cfg);
}

static void send_state() {
    const char* st =
        "{"
        "\"state\":{"
            "\"temperature\":22.1,"
            "\"pump\":1"
        "}"
        "}";

    send_raw(st);
}

void tcp_task(void *arg) {
    sock = socket(AF_INET, SOCK_STREAM, 0);
    connect(sock, ...);

    send_config();

    while (1) {
        send_state();
        vTaskDelay(5000 / portTICK_PERIOD_MS);
    }
}
```

---

# ✅ **4. MicroPython (ESP32, Raspberry Pi Pico W)**

```python
import socket
import ujson
import time

HOST = "homeassistant.local"
PORT = 5001

s = socket.socket()
s.connect((HOST, PORT))

def send(obj):
    raw = ujson.dumps(obj) + '\0'
    s.send(raw.encode())

def send_config():
    cfg = {
        "config": {
            "version": 3,
            "set_mode": "light",
            "sensor": {
                "Room Temperature": {"unit": "C"}
            },
            "switch": {
                "Heater": {}
            }
        }
    }
    send(cfg)

def send_state():
    st = {
        "state": {
            "room_temperature": 21.6,
            "heater": 1
        }
    }
    send(st)

send_config()

buf = ""

while True:
    # receive SET command
    if s.recv(1) as c:
        if c == b'\0':
            print("SET:", buf)
            buf = ""
        else:
            buf += c.decode()

    send_state()
    time.sleep(5)
```

---

# ✅ **5. STM32 HAL (C) – Lightweight Example**

TCP komponensek mcu-tól függnek (LWIP + netconn API).
Csak a HaLink adatlogika:

```c
void halink_send_config(struct netconn* conn) {
    const char* cfg =
        "{\"config\":{"
            "\"version\":3,"
            "\"sensor\":{\"Flow Temp\":{\"u\":\"C\"}},"
            "\"binary_sensor\":{\"Gas Valve\":{}}"
        "}}";

    netconn_write(conn, cfg, strlen(cfg), NETCONN_COPY);
    netconn_write(conn, "\0", 1, NETCONN_COPY);
}

void halink_send_state(struct netconn* conn, float temp, int valve) {
    char buf[128];
    sprintf(buf,
        "{\"state\":{\"flow_temp\":%.2f,\"gas_valve\":%d}}\0",
        temp, valve);

    netconn_write(conn, buf, strlen(buf), NETCONN_COPY);
}
```

---

# ✅ **6. Minimal MCU-agnostic Example (Pseudo-Code)**

Ez a lehető legkisebb implementáció, bármi portolható rá:

```
on_tcp_connect():
    send("{"config":{...}}\0")

loop:
    if tcp_has_frame():
        frame = read_until('\0')
        if frame startswith("{"):
            parse_json_set(frame)
        else if frame like "key=value":
            parse_light_set(frame)

    if time_to_send_state():
        send_state_json + '\0'
```

