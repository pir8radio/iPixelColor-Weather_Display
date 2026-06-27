# iPixelColor Weather Display

A cross‑platform Python application that turns any iPixelColor LED sign into a live, auto‑updating weather dashboard with UV‑based brightness control, non‑blocking BLE communication, and robust reconnect logic for both Linux and Windows.

A great pool side led display!

<img width="1147" height="679" alt="image" src="https://github.com/user-attachments/assets/bc42b97d-1b3d-4704-a7df-f1ddc85306c6" />


## Features

• Live weather display (temperature, rain chance, UV index)  
• UV index and Temperature change color based on value.
• UV‑based automatic brightness control  
• Cross‑platform BLE auto‑reconnect  
• Non‑blocking time synchronization  
• Clock mode between weather pages  
• Auto‑install of missing Python modules  
• Designed for 24/7 unattended operation  

## Weather Display

The script pulls real‑time weather data from WeatherAPI.com and cycles through:

• Temperature (°F)  
• Chance of rain (%)  
• UV index  
• Clock mode  

Each page displays for a configurable duration.

## UV‑Based Brightness Control

Brightness automatically adjusts based on UV index:

UV 0–1 → 10% brightness  
UV 10 → 90% brightness  

Linear formula:

brightness = 10 + (uv * 8)

This keeps the sign bright in daylight and dim at night without schedules.

## BLE Auto‑Reconnect

The script includes a robust reconnect system:

• Works on Linux and Windows  
• Exponential backoff  
• Linux auto‑resets Bluetooth using rfkill  
• Windows waits for device reappearance  
• No crashes or hangs  

## Non‑Blocking Time Sync

Time is updated using a raw BLE packet with response disabled, meaning:

• No ACK required  
• No timeout  
• No blocking  
• No delay in the loop  

## Requirements

• Python 3.8+  
• iPixelColor LED sign  
• Bluetooth‑capable system  
• WeatherAPI.com API key  

## Configuration

On first run, the script creates:

pixelcolor_config.json

Example:

{
  "weather_api_key": "YOUR_API_KEY",
  "weather_lat": "41.8781",
  "weather_lon": "-87.6298",
  "poll_interval": 120,
  "text_color": "00aaff",
  "brightness": 80,
  "animation_type": 0,
  "animation_speed": 0,
  "ble_address": null,
  "weather_duration": 10,
  "clock_duration": 10
}

You may edit this file anytime.

## Running the Script

Linux / Raspberry Pi:

python3 weather_display.py

Windows:

python weather_display.py

On first run, the script will:

1. Ask for your WeatherAPI key  
2. Ask for latitude/longitude  
3. Scan for your LED sign  
4. Save configuration  

## BLE Device Scanning

If no BLE address is stored, the script automatically runs:

python -m pypixelcolor --scan

Select your sign from the list and the address is saved.

## How It Works

Every poll interval:

1. Fetch weather  
2. Adjust brightness based on UV  
3. Display temperature  
4. Display rain chance  
5. Display UV index  
6. Switch to clock mode  

BLE actions include:

• Connection check  
• Auto‑reconnect  
• Brightness restore  
• Non‑blocking time sync  

## License

MIT License

## Contributing

Pull requests are welcome.

## ❤️ Credits

Built by Pir8Radio
Powered by [PyPixelColor](https://github.com/lucagoc/pypixelcolor)
