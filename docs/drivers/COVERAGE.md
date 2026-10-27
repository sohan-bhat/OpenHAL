# Driver coverage

Status of every driver and bridge. The machine-readable version is `drivers/catalog.json`, and the website renders the catalog as the supported devices page. This page started as the plan in M0. The status column follows the catalog, and a test keeps the column and the catalog in step.

Status values are planned, tested on simulator (the driver passes the conformance suite against its simulator) and verified on hardware (a hardware test report exists).

Device estimates are rough orders of magnitude with the reasoning given. The estimates are not marketing numbers, and the website shows each estimate with its reasoning.

## Tier 1

| Driver | Library | Covers | Hazard default | Status | Estimate and reasoning |
|---|---|---|---|---|---|
| serial | pyserial | Any device with a line-based serial protocol, configured by its device file | medium | tested on simulator | Unbounded. Most hobby boards and many instruments speak line-based serial |
| firmata | own Firmata client on pyserial | Arduino-compatible boards running StandardFirmata | low | tested on simulator | Tens of board models (Arduino, Teensy, ESP boards with Firmata) |
| openhal-firmware | own (spec/FIRMWARE-PROTOCOL.md) | Boards running the OpenHAL Arduino library | from the sketch | tested on simulator | AVR and ESP32 boards |
| scpi | PyVISA, pyvisa-py | Bench instruments over USB-TMC, LAN (VXI-11, raw socket) and serial | medium | tested on simulator | Thousands of models. SCPI is the default command language for programmable test equipment since 1990 |
| moonraker | httpx, websockets | Klipper printers | medium | tested on simulator | Every Klipper install with Moonraker |
| octoprint | httpx | Printers run through OctoPrint | medium | tested on simulator | Every OctoPrint install |
| marlin | pyserial | Marlin firmware printers over USB serial | medium | tested on simulator | Most consumer FDM printers ship Marlin or a fork |
| homeassistant | httpx, websockets | User-selected Home Assistant entities | per entity | tested on simulator | Thousands of integrations in Home Assistant |
| esphome | aioesphomeapi | ESPHome devices over the native API | per entity | tested on simulator | Every ESPHome device |
| rpi-gpio | gpiozero | Raspberry Pi GPIO pins | low | tested on simulator | Every Raspberry Pi with a 40-pin header |
| rpi-camera | picamera2 | Raspberry Pi camera modules (read-only capture) | low | tested on simulator | Official camera modules |
| mqtt | paho-mqtt | Devices that publish and subscribe on MQTT topics | per mapping | tested on simulator | Unbounded |
| modbus | pymodbus | Modbus RTU and TCP devices (meters, PLCs, VFDs) | medium | tested on simulator | Thousands of industrial models |
| ble | bleak | BLE GATT devices | low | tested on simulator | Any BLE peripheral with standard or documented characteristics |
| midi | mido, python-rtmidi | MIDI controllers and instruments | low | tested on simulator | Every class-compliant MIDI device |
| hid | hidapi | USB HID devices (buttons, knobs, custom HID gadgets) | low | tested on simulator | Any HID device with a documented report format |
| uvc | OpenCV | USB webcams, read-only capture | low | tested on simulator | Every UVC webcam |
| http | httpx | Generic HTTP devices, endpoints in the device file or from an OpenAPI document | per endpoint | tested on simulator | Unbounded |

## Tier 2

| Driver | Library | Covers | Hazard default | Status |
|---|---|---|---|---|
| grbl | pyserial | GRBL CNC routers and laser cutters | high | tested on simulator |
| ros2 | own rosbridge client on websockets | ROS 2 topics, services and actions | high | tested on simulator |
| opcua | asyncua | OPC UA servers and lab devices (LADS) | medium | tested on simulator |
| sila2 | sila2 | SiLA 2 lab devices | medium | tested on simulator |
| indi | own client (INDI XML protocol) | Telescope mounts, cameras, focusers | medium | tested on simulator |
| alpaca | httpx (ASCOM Alpaca REST) | ASCOM Alpaca devices | medium | tested on simulator |
| onvif | own SOAP client on httpx and defusedxml | ONVIF cameras, read-only and PTZ with limits | low | tested on simulator |
| pylabrobot | pylabrobot | Liquid handlers and lab robots | high | tested on simulator |
| lerobot | lerobot | Hugging Face LeRobot arms | high | tested on simulator |

## Tier 3

| Driver | Covers | Hazard default | Status |
|---|---|---|---|
| bambu | Bambu Lab X1 series, Bambu Lab P1 series, Bambu Lab A1 and A1 mini | medium | tested on simulator |
| can | motor controllers (VESC, ODrive, CubeMars), battery management systems, CAN sensor and IO nodes | medium | tested on simulator |
| knx | KNX switch and dimmer actuators, KNX blind actuators, KNX room thermostats | low | tested on simulator |
| matter | Matter lights and plugs, Matter sensors, Matter thermostats and fans | low | tested on simulator |
| pi-i2c-spi | I2C temperature and humidity sensors, SPI and I2C ADCs, SPI and I2C DACs | low | tested on simulator |
| upnp | UPnP AV media renderers and speakers, smart TVs with DLNA rendering, internet gateways (IGD) | low | tested on simulator |
| zigbee-zwave | Zigbee lights, plugs and sensors, Z-Wave switches, dimmers and plugs, Z-Wave multisensors | low | tested on simulator |
