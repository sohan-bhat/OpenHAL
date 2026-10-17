# Driver coverage

Status of every driver and bridge. The machine-readable version is `drivers/catalog.json`, and the website renders it as the supported devices page. This file starts as the plan (M0) and is updated as each driver lands.

Status values are planned, in progress, implemented (mock-tested, conformance passing), stub and verified (tested on real hardware by a human).

Device estimates are rough orders of magnitude with the reasoning given. They are not marketing numbers and the website shows them with their reasoning.

## Tier 1

| Driver | Library | Covers | Hazard default | Status | Estimate and reasoning |
|---|---|---|---|---|---|
| serial | pyserial | Any device with a line-based serial protocol, configured by its device file | medium | planned | Unbounded. Most hobby boards and many instruments speak line-based serial |
| firmata | pyfirmata2 or own implementation | Arduino-compatible boards running StandardFirmata | low | planned | Tens of board models (Arduino, Teensy, ESP boards with Firmata) |
| openhal-firmware | own (spec/FIRMWARE-PROTOCOL.md) | Boards running the OpenHAL Arduino library | from the sketch | planned | AVR and ESP32 boards |
| scpi | PyVISA, pyvisa-py | Bench instruments over USB-TMC, LAN (VXI-11, raw socket) and serial | medium | planned | Thousands of models. SCPI is the default command language for programmable test equipment since 1990 |
| moonraker | httpx, websockets | Klipper printers | medium | planned | Every Klipper install with Moonraker |
| octoprint | httpx | Printers run through OctoPrint | medium | planned | Every OctoPrint install |
| marlin | pyserial | Marlin firmware printers over USB serial | medium | planned | Most consumer FDM printers ship Marlin or a fork |
| homeassistant | httpx, websockets | User-selected Home Assistant entities | per entity | planned | Thousands of integrations in Home Assistant |
| esphome | aioesphomeapi | ESPHome devices over the native API | per entity | planned | Every ESPHome device |
| rpi-gpio | gpiozero | Raspberry Pi GPIO pins | low | planned | Every Raspberry Pi with a 40-pin header |
| rpi-camera | picamera2 | Raspberry Pi camera modules (read-only capture) | low | planned | Official camera modules |
| mqtt | paho-mqtt | Devices that publish and subscribe on MQTT topics | per mapping | planned | Unbounded |
| modbus | pymodbus | Modbus RTU and TCP devices (meters, PLCs, VFDs) | medium | planned | Thousands of industrial models |
| ble | bleak | BLE GATT devices | low | planned | Any BLE peripheral with standard or documented characteristics |
| midi | mido, python-rtmidi | MIDI controllers and instruments | low | planned | Every class-compliant MIDI device |
| hid | hidapi | USB HID devices (buttons, knobs, custom HID gadgets) | low | planned | Any HID device with a documented report format |
| uvc | OpenCV | USB webcams, read-only capture | low | planned | Every UVC webcam |
| http | httpx | Generic HTTP devices, endpoints in the device file or from an OpenAPI document | per endpoint | planned | Unbounded |

## Tier 2

| Driver | Library | Covers | Hazard default | Status |
|---|---|---|---|---|
| grbl | pyserial | GRBL CNC routers and laser cutters | high | planned |
| ros2 | roslibpy over rosbridge | ROS 2 topics, services and actions | high | planned |
| opcua | asyncua | OPC UA servers and lab devices (LADS) | medium | planned |
| sila2 | sila2 | SiLA 2 lab devices | medium | planned |
| indi | own client (INDI XML protocol) | Telescope mounts, cameras, focusers | medium | planned |
| alpaca | httpx (ASCOM Alpaca REST) | ASCOM Alpaca devices | medium | planned |
| onvif | onvif-zeep or own SOAP client | ONVIF cameras, read-only and PTZ with limits | low | planned |
| pylabrobot | pylabrobot | Liquid handlers and lab robots | high | planned |
| lerobot | lerobot | Hugging Face LeRobot arms | high | planned |

## Tier 3 (stubs with design notes)

Matter (through the Home Assistant bridge first), Zigbee and Z-Wave (through Home Assistant), CAN bus (python-can), I2C and SPI sensors on Raspberry Pi, UPnP, KNX, Bambu Lab printers (terms and local API status to be checked first).
