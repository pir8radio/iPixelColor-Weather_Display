import sys
import time
import json
import os
import subprocess
import re
from datetime import datetime

def ensure_module(name):
    try:
        return __import__(name)
    except ImportError:
        print(f"[WARN] Missing module {name}, installing...")
        from subprocess import check_call
        check_call([sys.executable, "-m", "pip", "install", "--user", name])
        print(f"[INFO] Installed {name}, restart script.")
        sys.exit(1)

requests = ensure_module("requests")
pypixelcolor = ensure_module("pypixelcolor")
from pypixelcolor.client import Client

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
    "weather_duration": 10,
    "clock_duration": 10
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        print("[SETUP] First-time setup...")

        api_key = input("Enter WeatherAPI key: ").strip()
        lat = input("Enter latitude: ").strip()
        lon = input("Enter longitude: ").strip()
        led_sign_password = input("Enter LED sign password (optional): ").strip()

        new_cfg = DEFAULT_CONFIG.copy()
        new_cfg["weather_api_key"] = api_key
        new_cfg["weather_lat"] = lat
        new_cfg["weather_lon"] = lon
        new_cfg["led_sign_password"] = led_sign_password

        save_config(new_cfg)
        print("[INFO] Config saved.")
        return new_cfg

    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=4)

config = load_config()

# ---------------------------------------------------------
# BLE SCAN
# ---------------------------------------------------------
def run_cli_scan():
    print("[SCAN] Searching for LED signs...")
    result = subprocess.run(
        [sys.executable, "-m", "pypixelcolor", "--scan"],
        capture_output=True,
        text=True
    )
    output = result.stdout + result.stderr
    print(output)

    devices = re.findall(r"-\s+(.+?)\s+\(([0-9A-F:]{17})\)", output)
    if not devices:
        print("[ERR] No devices found.")
        sys.exit(1)

    for i, (name, addr) in enumerate(devices):
        print(f"[{i}] {name} — {addr}")

    choice = int(input("Select device: "))
    addr = devices[choice][1]
    config["ble_address"] = addr
    save_config(config)
    return addr

# ---------------------------------------------------------
# BLE CONNECT + AUTO-RECONNECT (from Plex script)
# ---------------------------------------------------------
def connect_ble(address):
    backoff = 1
    while True:
        try:
            client = Client(address=address)
            client.connect()
            print("[BT] BLE connected")
            return client

        except Exception as e:
            print(f"[WARN] BLE connection failed: {e}")
            print(f"[WAIT] Retrying in {backoff} seconds...")

            subprocess.run(["sudo", "rfkill", "block", "bluetooth"], check=True)
            print("[BT] Restarting Bluetooth")
            time.sleep(5)
            subprocess.run(["sudo", "rfkill", "unblock", "bluetooth"], check=True)
            print("[BT] Bluetooth re-enabled")

            time.sleep(backoff)
            backoff = min(backoff * 2, 60)

def ensure_ble_connected(client, address):
    try:
        client.get_device_info()
        return client, False
    except Exception:
        print("[RECON] BLE connection lost — reconnecting...")
        new_client = connect_ble(address)
        return new_client, True

# ---------------------------------------------------------
# GET BLE ADDRESS
# ---------------------------------------------------------
BLE_ADDRESS = config["ble_address"] or run_cli_scan()

print(f"[BLE] Connecting to {BLE_ADDRESS}...")
client = connect_ble(BLE_ADDRESS)

client.set_brightness(config["brightness"])
print(f"[INFO] Brightness set to {config['brightness']}")

# ---------------------------------------------------------
# TIME SYNC
# ---------------------------------------------------------
def sync_time_to_sign():
    try:
        client.set_time()
        print("[TIME] Time synced.")
    except:
        print("[WARN] Time sync failed.")

# ---------------------------------------------------------
# WEATHER HELPERS
# ---------------------------------------------------------
def temp_to_color(temp_f):
    if temp_f <= 31: return "ffffff"
    if temp_f <= 55: return "00aaff"
    if temp_f <= 78: return "ff8800"
    return "ff0000"

def uv_to_color(uv):
    if uv <= 2: return "00ff00"
    if uv <= 5: return "ffff00"
    if uv <= 7: return "ff8800"
    if uv <= 10: return "ff0000"
    return "cc00ff"

def get_weather():
    url = (
        "https://api.weatherapi.com/v1/current.json?"
        f"key={config['weather_api_key']}"
        f"&q={config['weather_lat']},{config['weather_lon']}"
        "&aqi=no"
    )
    print("[INFO] Fetching weather...")
    r = requests.get(url, timeout=10)
    data = r.json()
    current = data["current"]
    return round(current["temp_f"]), current.get("chance_of_rain", 0), current.get("uv", 0)

# ---------------------------------------------------------
# MAIN LOOP
# ---------------------------------------------------------
last_weather_poll = 0
weather_cache = None
last_page = None  # track what was last shown

while True:
    # Auto-reconnect check
    client, reconnected = ensure_ble_connected(client, BLE_ADDRESS)

    if reconnected:
        print("[RECON] Restoring brightness + last page")
        client.set_brightness(config["brightness"])

        if last_page == "TEMP":
            client.send_text(f"{temp} F", color=temp_to_color(temp),
                             animation=config["animation_type"],
                             speed=config["animation_speed"])

        elif last_page == "RAIN":
            client.send_text(f"Rain: {rain:.0f}%",
                             color=config["text_color"],
                             animation=config["animation_type"],
                             speed=config["animation_speed"])

        elif last_page == "UV":
            client.send_text(f"UV: {uv}",
                             color=uv_to_color(uv),
                             animation=config["animation_type"],
                             speed=config["animation_speed"])

        elif last_page == "CLOCK":
            sync_time_to_sign()
            client.set_clock_mode(style=6, show_date=False, format_24=False)

    now = time.time()

    # Poll weather
    if now - last_weather_poll >= config["poll_interval"]:
        try:
            weather_cache = get_weather()
            print(f"[WX] Weather updated: {weather_cache}")
        except Exception as e:
            print(f"[ERR] Weather fetch failed: {e}")
        last_weather_poll = now

    if weather_cache:
        temp, rain, uv = weather_cache

        # TEMP PAGE
        print(f"[WX] TEMP: {temp} F (color {temp_to_color(temp)})")
        client.send_text(
            f"{temp} F",
            color=temp_to_color(temp),
            animation=config["animation_type"],
            speed=config["animation_speed"]
        )
        last_page = "TEMP"
        time.sleep(config["weather_duration"])

        # RAIN PAGE
        print(f"[WX] RAIN: Rain: {rain:.0f}%")
        client.send_text(
            f"Rain: {rain:.0f}%",
            color=config["text_color"],
            animation=config["animation_type"],
            speed=config["animation_speed"]
        )
        last_page = "RAIN"
        time.sleep(config["weather_duration"])

        # UV PAGE
        print(f"[WX] UV: {uv}")
        client.send_text(
            f"UV: {uv}",
            color=uv_to_color(uv),
            animation=config["animation_type"],
            speed=config["animation_speed"]
        )
        last_page = "UV"
        time.sleep(config["weather_duration"])

    # CLOCK PAGE
    print("[TIME] Displaying clock...")
    sync_time_to_sign()
    client.set_clock_mode(style=6, show_date=False, format_24=False)
    last_page = "CLOCK"
    time.sleep(config["clock_duration"])
