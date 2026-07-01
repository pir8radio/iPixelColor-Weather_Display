# ---------------------------------------------------------
# https://github.com/pir8radio/iPixelColor-Weather_Display
# ---------------------------------------------------------

import sys
import time
import json
import os
import subprocess
import re
import platform
from datetime import datetime

# ---------------------------------------------------------
# AUTO-INSTALL ANY MISSING MODULES
# ---------------------------------------------------------
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

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------
CONFIG_FILE = "pixelcolor_config.json"

DEFAULT_CONFIG = {
    "weather_api_key": "YOUR_API_KEY",
    "weather_lat": "41.8781",
    "weather_lon": "-87.6298",
    "poll_interval": 120,
    "text_color": "00aaff",
    "brightness": 80,
    "animation_type": 1,
    "animation_speed": 0,
    "ble_address": None,
    "weather_duration": 5,
    "alert_duration": 10,
    "clock_duration": 5
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
# PLATFORM FLAGS
# ---------------------------------------------------------
IS_LINUX = platform.system().lower() == "linux"
IS_WINDOWS = platform.system().lower() == "windows"

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
# CROSS-PLATFORM BLE CONNECT + AUTO-RECONNECT
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

            if IS_LINUX:
                print("[BT] Linux detected — attempting Bluetooth reset")
                try:
                    subprocess.run(["sudo", "rfkill", "block", "bluetooth"], check=False)
                    time.sleep(2)
                    subprocess.run(["sudo", "rfkill", "unblock", "bluetooth"], check=False)
                except Exception:
                    pass

            if IS_WINDOWS:
                print("[BT] Windows detected — waiting for device to reappear")

            print(f"[WAIT] Retrying in {backoff} seconds...")
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
# SAFE BLE CALL WRAPPER
# ---------------------------------------------------------
def safe_ble_call(func, *args, **kwargs):
    global client
    try:
        client, reconnected = ensure_ble_connected(client, BLE_ADDRESS)
        if reconnected:
            try:
                client.set_brightness(config["brightness"])
            except Exception:
                pass
        return func(*args, **kwargs)

    except Exception as e:
        print(f"[BLE ERROR] {e}")
        print("[BLE] Forcing reconnect...")
        try:
            client = connect_ble(BLE_ADDRESS)
        except Exception as e2:
            print(f"[BLE] Reconnect failed: {e2}")
        return None

# ---------------------------------------------------------
# INITIAL CONNECT
# ---------------------------------------------------------
BLE_ADDRESS = config["ble_address"] or run_cli_scan()

print(f"[BLE] Connecting to {BLE_ADDRESS}...")
client = connect_ble(BLE_ADDRESS)

safe_ble_call(client.set_brightness, config["brightness"])
print(f"[INFO] Initial brightness set to {config['brightness']}")

# ---------------------------------------------------------
# UV-BASED BRIGHTNESS CONTROL
# ---------------------------------------------------------
def brightness_from_uv(uv):
    if uv < 1:
        return 10
    if uv > 10:
        uv = 10
    return max(10, min(int(10 + uv * 15), 99))

# ---------------------------------------------------------
# TIME SYNC
# ---------------------------------------------------------
def sync_time_to_sign():
    global client
    try:
        client.set_time()
    except Exception:
        pass
    print("[TIME] Time sync sent")

# ---------------------------------------------------------
# SAFE BLE WRAPPERS
# ---------------------------------------------------------
def safe_send_text(text, color, animation, speed):
    try:
        safe_ble_call(
            client.send_text,
            text,
            color=color,
            animation=animation,
            speed=speed,
            font="VCR_OSD_MONO"
        )
    except Exception as e:
        print(f"[WARN] send_text failed: {e}")

def safe_send_text_small(text, color, animation, speed):
    try:
       safe_ble_call(
           client.send_text,
           text,
           color=color,
           animation=animation,
           speed=speed,
           font="CUSONG"
       )
    except Exception as e:
        print(f"[WARN] send_text_small failed: {e}")

def safe_clock_mode():
    global client
    try:
        client.set_clock_mode(style=6, show_date=False, format_24=False)
    except Exception as e:
        print(f"[WARN] set_clock_mode failed: {e}")

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

# ---------------------------------------------------------
# WEATHER + FORECAST + ALERTS
# ---------------------------------------------------------
def get_weather_all():
    url = (
        "https://api.weatherapi.com/v1/forecast.json?"
        f"key={config['weather_api_key']}"
        f"&q={config['weather_lat']},{config['weather_lon']}"
        "&days=1&alerts=yes"
    )

    print("[INFO] Fetching weather + forecast + alerts...")
    r = requests.get(url, timeout=10)
    data = r.json()

    current = data["current"]
    forecast = data["forecast"]["forecastday"][0]["day"]
    alerts = data.get("alerts", {}).get("alert", [])

    temp_f = round(current["temp_f"])
    feels_like = round(current.get("feelslike_f", temp_f))
    uv = current.get("uv", 0)
    chance_of_rain = forecast.get("daily_chance_of_rain", 0)
    short_forecast = forecast["condition"]["text"]
    active_alert = alerts[0]["headline"] if alerts else None

    return temp_f, feels_like, uv, chance_of_rain, short_forecast, active_alert

# ---------------------------------------------------------
# MAIN LOOP (HOURLY TIME SYNC)
# ---------------------------------------------------------
last_weather_poll = 0
weather_cache = None

last_time_sync = 0
TIME_SYNC_INTERVAL = 3600  # 1 hour

while True:
    try:
        now = time.time()

        # WEATHER FETCH
        if now - last_weather_poll >= config["poll_interval"]:
            try:
                weather_cache = get_weather_all()
                print(f"[INTERNET] Weather updated: {weather_cache}")
            except Exception as e:
                print(f"[INTERNET] Weather fetch failed: {e}")
            last_weather_poll = now

        if weather_cache:
            temp, feels_like, uv, rain, short_forecast, active_alert = weather_cache

            # BRIGHTNESS
            new_brightness = brightness_from_uv(uv)
            safe_ble_call(client.set_brightness, new_brightness)
            print(f"[BRIGHT] Brightness set to {new_brightness}% based on UV {uv}")

            # TEMP PAGE
            print(f"[WX] TEMP: {temp}F")
            safe_send_text(
                f"{temp}F",
                color=temp_to_color(temp),
                animation=config["animation_type"],
                speed=config["animation_speed"]
            )
            time.sleep(config["weather_duration"])

            # SHORT FORECAST PAGE
            print(f"[WX] FORECAST: {short_forecast}")
            safe_send_text(
                short_forecast,
                color="ffffff",
                animation=config["animation_type"],
                speed=config["animation_speed"]
            )
            time.sleep(config["weather_duration"])

            # FEELS LIKE PAGE (small font)
            print(f"[WX] FEELS: {feels_like}F")
            safe_send_text_small(
                f"Feels: {feels_like}F",
                color=temp_to_color(feels_like),
                animation=config["animation_type"],
                speed=config["animation_speed"]
            )
            time.sleep(config["weather_duration"])

            # RAIN PAGE
            print(f"[WX] RAIN: {rain:.0f}%")
            safe_send_text(
                f"Rain: {rain:.0f}%",
                color=config["text_color"],
                animation=config["animation_type"],
                speed=config["animation_speed"]
            )
            time.sleep(config["weather_duration"])

            # UV PAGE
            print(f"[WX] UV: {uv}")
            safe_send_text(
                f"UV: {uv}",
                color=uv_to_color(uv),
                animation=config["animation_type"],
                speed=config["animation_speed"]
            )
            time.sleep(config["weather_duration"])

            # ALERT PAGE
            if active_alert:
                print(f"[WX] ALERT: {active_alert}")
                safe_send_text_small(
                    active_alert,
                    color="ff0000",
                    animation=config["animation_type"],
                    speed=config["animation_speed"]
                )
                time.sleep(config["alert_duration"])

        # CLOCK PAGE
        print("[TIME] Displaying clock...")

        # HOURLY TIME SYNC ONLY
        if now - last_time_sync >= TIME_SYNC_INTERVAL:
            sync_time_to_sign()
            last_time_sync = now

        safe_clock_mode()
        time.sleep(config["clock_duration"])

    except Exception as e:
        print(f"[FATAL LOOP ERROR] {e}")
        print("[RECOVERY] Restarting BLE connection...")
        try:
            client = connect_ble(BLE_ADDRESS)
        except Exception as e2:
            print(f"[RECOVERY] BLE reconnect failed: {e2}")
        time.sleep(1)
