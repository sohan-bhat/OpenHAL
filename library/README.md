# Device library

Starter device files for real products. The hub offers a library file when discovery finds a device the file matches.
Every file is unverified and loads read-only until a person checks and confirms the file's limits.
[How the library works](../docs/guide/library.md).

```
openhal library list
openhal library show rigol-dp832
openhal library add rigol-dp832
```

## Arduino and ESP32 boards running the OpenHAL firmware

| Name | Device | Hazard | Controls |
|---|---|---|---|
| [`openhal-desk-fan`](openhal_firmware/openhal-desk-fan.hal.yaml) | Desk fan | low | 1 control |
| [`openhal-led-strip`](openhal_firmware/openhal-led-strip.hal.yaml) | LED strip | low | 1 control |
| [`openhal-plant-waterer`](openhal_firmware/openhal-plant-waterer.hal.yaml) | Arduino plant waterer | low | 2 actions |
| [`openhal-servo-arm`](openhal_firmware/openhal-servo-arm.hal.yaml) | Servo arm | medium | 1 control |
| [`openhal-soil-pump`](openhal_firmware/openhal-soil-pump.hal.yaml) | Soil pump | low | 1 control |

## SCPI instruments

| Name | Device | Hazard | Controls |
|---|---|---|---|
| [`keysight-34461a`](scpi/keysight-34461a.hal.yaml) | Keysight 34461A multimeter | low | reads only |
| [`rigol-dp832`](scpi/rigol-dp832.hal.yaml) | Rigol DP832 power supply | medium | 3 controls, 3 actions |
| [`rigol-ds1054z`](scpi/rigol-ds1054z.hal.yaml) | Rigol DS1054Z oscilloscope | low | 3 actions |
| [`siglent-sdm3045x`](scpi/siglent-sdm3045x.hal.yaml) | Siglent SDM3045X multimeter | low | reads only |
| [`siglent-spd3303x`](scpi/siglent-spd3303x.hal.yaml) | Siglent SPD3303X power supply | medium | 2 controls, 4 actions |

## Marlin printers over USB

| Name | Device | Hazard | Controls |
|---|---|---|---|
| [`prusa-mini`](marlin/prusa-mini.hal.yaml) | Original Prusa MINI+ | high | 3 controls, 1 action |
| [`prusa-mk3s`](marlin/prusa-mk3s.hal.yaml) | Original Prusa i3 MK3S+ | high | 3 controls, 4 actions |
| [`prusa-mk4`](marlin/prusa-mk4.hal.yaml) | Original Prusa MK4 | high | 3 controls, 1 action |

## Klipper printers through Moonraker

| Name | Device | Hazard | Controls |
|---|---|---|---|
| [`ratrig-v-core-4`](moonraker/ratrig-v-core-4.hal.yaml) | Rat Rig V-Core 4 | high | 3 controls, 4 actions |
| [`sovol-sv08`](moonraker/sovol-sv08.hal.yaml) | Sovol SV08 | high | 3 controls, 4 actions |

## Raspberry Pi GPIO boards

| Name | Device | Hazard | Controls |
|---|---|---|---|
| [`pimoroni-fan-shim`](rpi_gpio/pimoroni-fan-shim.hal.yaml) | Pimoroni Fan SHIM | low | 1 control |
| [`waveshare-rpi-relay-board`](rpi_gpio/waveshare-rpi-relay-board.hal.yaml) | Waveshare RPi Relay Board | high | 3 controls |

## Raspberry Pi cameras

| Name | Device | Hazard | Controls |
|---|---|---|---|
| [`raspberry-pi-camera-module-3`](rpi_camera/raspberry-pi-camera-module-3.hal.yaml) | Raspberry Pi Camera Module 3 | low | reads only |
| [`raspberry-pi-hq-camera`](rpi_camera/raspberry-pi-hq-camera.hal.yaml) | Raspberry Pi High Quality Camera | low | reads only |

## ESPHome devices

| Name | Device | Hazard | Controls |
|---|---|---|---|
| [`apollo-air-1`](esphome/apollo-air-1.hal.yaml) | Apollo AIR-1 air quality sensor | low | 2 controls |
| [`apollo-msr-2`](esphome/apollo-msr-2.hal.yaml) | Apollo MSR-2 multisensor | low | 2 controls |
| [`athom-smart-plug-v2`](esphome/athom-smart-plug-v2.hal.yaml) | Athom Smart Plug V2 | high | 1 control |

## MQTT sensors

| Name | Device | Hazard | Controls |
|---|---|---|---|
| [`shelly-ht-gen3`](mqtt/shelly-ht-gen3.hal.yaml) | Shelly H&T Gen3 | low | reads only |

## Home Assistant plugs and lights

| Name | Device | Hazard | Controls |
|---|---|---|---|
| [`shelly-dimmer-gen3`](homeassistant/shelly-dimmer-gen3.hal.yaml) | Shelly Dimmer Gen3 | high | 2 controls |
| [`shelly-plus-plug-s`](homeassistant/shelly-plus-plug-s.hal.yaml) | Shelly Plus Plug S | high | 1 control |

## Modbus energy meters

| Name | Device | Hazard | Controls |
|---|---|---|---|
| [`eastron-sdm120`](modbus/eastron-sdm120.hal.yaml) | Eastron SDM120 energy meter | low | reads only |
| [`eastron-sdm630`](modbus/eastron-sdm630.hal.yaml) | Eastron SDM630 energy meter | low | reads only |

## MIDI controllers

| Name | Device | Hazard | Controls |
|---|---|---|---|
| [`akai-lpd8`](midi/akai-lpd8.hal.yaml) | Akai LPD8 pad controller | low | reads only |
| [`korg-nanokontrol2`](midi/korg-nanokontrol2.hal.yaml) | Korg nanoKONTROL2 controller | low | 3 controls |

## Bluetooth LE sensors

| Name | Device | Hazard | Controls |
|---|---|---|---|
| [`polar-h10`](ble/polar-h10.hal.yaml) | Polar H10 heart rate sensor | low | reads only |
| [`xiaomi-lywsd03mmc`](ble/xiaomi-lywsd03mmc.hal.yaml) | Xiaomi Mi Temperature and Humidity Monitor 2 | low | reads only |
| [`xiaomi-lywsd03mmc-pvvx`](ble/xiaomi-lywsd03mmc-pvvx.hal.yaml) | Xiaomi LYWSD03MMC with pvvx firmware | low | reads only |

## Telescope mounts through ASCOM Alpaca

| Name | Device | Hazard | Controls |
|---|---|---|---|
| [`sky-watcher-eq6-r-pro`](alpaca/sky-watcher-eq6-r-pro.hal.yaml) | Sky-Watcher EQ6-R Pro mount | medium | 1 control, 4 actions |

This list is generated from the files by `uv run python -m openhal.cli.library_cmd`. 33 files.
