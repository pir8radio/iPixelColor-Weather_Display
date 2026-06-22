import sys
import time
import json
import os
import subprocess
import re
from datetime import datetime

# ---------------------------------------------------------
# AUTO-INSTALL ANY MISSING MODULES
# ---------------------------------------------------------
def ensure_module(name):
    try:
        return __import__(name)
    except ImportError:
        print(f'\n[WARN] Missing module "{name}". Installing...\n')
        from subprocess import check_call
        try:
            check_call([sys.executable, "-m", "pip", "install", "--user", name])
            print(f'\n[OK] Module "{name}" installed. Restarting...\n')
            sys.exit(1)
        except Exception as e:
            print(f'[ERR] Failed to install module "{name}": {e}')
            sys.exit(1)
            
requests = ensure_module("requests")
pypixelcolor = ensure_module("pypixelcolor")
from pypixelcolor.client import Client

# ---------------------------------------------------------
# CONFIGURATION FILE
# ---------------------------------------------------------
CONFIG_FILE = "pixelcolor_config.json"

DEFAULT_CONFIG = {
    "weather_api_key": "YOUR_API_KEY",
    "weather_lat": "41.6106",
    "weather_lon": "-87.0642",
    "poll_interval": 300,
    "text_color": "00aaff",
    "brightness": 80,
    "animation_type": 0,
    "animation_speed": 0,
    "ble_address": None,
    "led_sign_password": "",
    "weather_duration": 10,
    "clock_duration": 10
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        print("\n[SETUP] First-time setup — configure your Weather API.\n")

        api_key = input("Enter OpenWeatherMap API key: ").strip()
        lat = input("Enter latitude: ").strip()
        lon = input("Enter longitude: ").strip()
        led_sign_password = input("Enter LED sign password (optional): ").strip()

        new_cfg = DEFAULT_CONFIG.copy()
        new_cfg["weather_api_key"] = api_key
        new_cfg["weather_lat"] = lat
        new_cfg["weather_lon"] = lon
        new_cfg["led_sign_password"] = led_sign_password

        save_config(new_cfg)
        print("\n[OK] Configuration saved.\n")
        return new_cfg

    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
    except Exception:
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG

    updated = False
    for k, v in DEFAULT_CONFIG.items():
        if k not in data:
            data[k] = v
            updated = True

    if updated:
        save_config(data)

    return data

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=4)

config = load_config()

# ---------------------------------------------------------
# BLE SCANNING
# ---------------------------------------------------------
def run_cli_scan():
    print("\n[SCAN] Searching for iPixelColor LED signs...\n")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pypixelcolor", "--scan"],
            capture_output=True,
            text=True,
            check=True
        )
    except Exception as e:
        print(f"[ERR] Scanner failed: {e}")
        sys.exit(1)

    output = result.stdout + result.stderr
    print(output)

    devices = re.findall(r"-\s+(.+?)\s+\(([0-9A-F:]{17})\)", output)

    if not devices:
        print("[ERR] No LED signs found.")
        sys.exit(1)

    print("[DEV] Devices detected:\n")
    for i, (name, addr) in enumerate(devices):
        print(f"  [{i}] {name} — {addr}")

    print("\nSelect a device number:")
    while True:
        choice = input("> ").strip()
        if choice.isdigit() and int(choice) in range(len(devices)):
            name, addr = devices[int(choice)]
            print(f"\n[OK] Selected: {name} ({addr})\n")
            config["ble_address"] = addr
            save_config(config)
            return addr

        print("[ERR] Invalid choice. Try again.")

# ---------------------------------------------------------
# BLE CONNECT + AUTO-RECONNECT
# ---------------------------------------------------------
def connect_ble(address):
    backoff = 1
    while True:
        try:
            client = Client(address=address)
            client.connect()

            print("[BT] Connected")
            return client

        except Exception as e:
            print(f"[WARN] BLE connection failed: {e}")
            print(f"[WAIT] Retrying in {backoff} seconds...")
            subprocess.run(["sudo", "rfkill", "block", "bluetooth"], check=True)
            time.sleep(5)
            subprocess.run(["sudo", "rfkill", "unblock", "bluetooth"], check=True)
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)

def ensure_ble_connected(client, address):
    try:
        client.get_device_info()
        return client, False
    except Exception:
        print("[WARN] BLE connection lost — reconnecting...")
        new_client = connect_ble(address)
        return new_client, True

# ---------------------------------------------------------
# GET BLE ADDRESS (SCAN IF FIRST RUN)
# ---------------------------------------------------------
BLE_ADDRESS = config["ble_address"]

if not BLE_ADDRESS:
    BLE_ADDRESS = run_cli_scan()

print(f"[BLE] Using device: {BLE_ADDRESS}")

# ---------------------------------------------------------
# INITIALIZE CLIENT
# ---------------------------------------------------------
client = connect_ble(BLE_ADDRESS)
client.set_brightness(config["brightness"])
print(f"[BRI] Brightness set to {config['brightness']}")

# ---------------------------------------------------------
# TIME SYNC
# ---------------------------------------------------------
def sync_time_to_sign(client):
    try:
        client.set_time()
        print("[TIME] Time sync sent")
    except Exception:
        print("[WARN] Time sync failed")

# ---------------------------------------------------------
# TEMP → COLOR LOGIC
# ---------------------------------------------------------
def temp_to_color(temp_f):
    if temp_f <= 31:
        return "ffffff"   # white
    elif temp_f <= 55:
        return "00aaff"   # blue
    elif temp_f <= 78:
        return "ff8800"   # orange
    else:
        return "ff0000"   # red

# ---------------------------------------------------------
# UV → COLOR LOGIC
# ---------------------------------------------------------
def uv_to_color(uv):
    if uv <= 2:
        return "00ff00"   # green
    elif uv <= 5:
        return "ffff00"   # yellow
    elif uv <= 7:
        return "ff8800"   # orange
    elif uv <= 10:
        return "ff0000"   # red
    else:
        return "cc00ff"   # purple

# ---------------------------------------------------------
# WEATHER FETCHING
# ---------------------------------------------------------
def get_weather():
    url = (
        "https://api.openweathermap.org/data/2.5/onecall?"
        f"lat={config['weather_lat']}&lon={config['weather_lon']}"
        f"&appid={config['weather_api_key']}&units=imperial"
    )

    try:
        r = requests.get(url, timeout=10)
        data = r.json()

        temp = round(data["current"]["temp"])
        rain = data["hourly"][0].get("pop", 0) * 100
        uv = data["current"].get("uvi", 0)

        return temp, rain, uv

    except Exception as e:
        print(f"[ERR] Weather API error: {e}")
        return None

# ---------------------------------------------------------
# MAIN LOOP — ROTATE WEATHER + CLOCK
# ---------------------------------------------------------
last_weather_poll = 0
weather_cache = None

while True:
    try:
        client, reconnected = ensure_ble_connected(client, BLE_ADDRESS)

        # Sync time every 10 minutes
        if int(time.time()) % 600 < 2:
            sync_time_to_sign(client)

        # Poll weather only every poll_interval
        now = time.time()
        if now - last_weather_poll >= config["poll_interval"]:
            weather_cache = get_weather()
            last_weather_poll = now

        # WEATHER DISPLAY
        if weather_cache:
            temp, rain, uv = weather_cache
            degree = "°"

            temp_color = temp_to_color(temp)
            uv_color = uv_to_color(uv)

            multi_color_text = (
                f"{temp}{degree}F|{temp_color}, "
                f"Rain:{rain:.0f}%|{config['text_color']}, "
                f"UV:{uv}|{uv_color}"
            )

            print(f"[WX] Displaying weather: {multi_color_text}")

            client.send_text(
                multi_color_text,
                animation=config["animation_type"],
                speed=config["animation_speed"]
            )

        time.sleep(config["weather_duration"])

        # CLOCK DISPLAY
        print("[TIME] Displaying clock")
        sync_time_to_sign(client)
        client.set_clock_mode(style=6, show_date=False, format_24=False)

        time.sleep(config["clock_duration"])

    except Exception as e:
        print(f"[ERR] Error: {e}")
        time.sleep(5)
