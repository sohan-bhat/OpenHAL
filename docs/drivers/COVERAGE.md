# Driver coverage

The status of every driver and bridge. `docs/drivers/catalog.json` is the machine-readable source behind the website's supported devices page, and a test keeps the status column in step with the catalog.

A driver is planned, tested on simulator once the driver passes the conformance suite against its simulator, or verified on hardware once a hardware test report exists. Device estimates are rough orders of magnitude, each with its reasoning.

## Tier 1

| Driver | Library | Covers | Hazard default | Status | Estimate |
|---|---|---|---|---|---|
| serial | pyserial | Line-based serial devices, set up by the device file | medium | tested on simulator | Unbounded. Most hobby boards and many instruments use line-based serial |
| firmata | own Firmata client on pyserial | Arduino-compatible boards running StandardFirmata | low | tested on simulator | Tens of Arduino, Teensy and ESP board models |
| openhal-firmware | own, spec/FIRMWARE-PROTOCOL.md | Boards running the OpenHAL Arduino library | from the sketch | tested on simulator | AVR and ESP32 boards |
| scpi | PyVISA, pyvisa-py | Bench instruments over USB-TMC, LAN with VXI-11 or raw socket, and serial | medium | tested on simulator | Thousands of models. SCPI has been the command language of programmable test equipment since 1990 |
| moonraker | httpx, websockets | Klipper printers | medium | tested on simulator | Every Klipper install with Moonraker |
| octoprint | httpx | Printers run through OctoPrint | medium | tested on simulator | Every OctoPrint install |
| marlin | pyserial | Marlin firmware printers over USB serial | medium | tested on simulator | Most consumer FDM printers ship Marlin or a fork |
| homeassistant | httpx, websockets | User-selected Home Assistant entities | per entity | tested on simulator | Thousands of integrations in Home Assistant |
| esphome | aioesphomeapi | ESPHome devices over the native API | per entity | tested on simulator | Every ESPHome device |
| rpi-gpio | gpiozero | Raspberry Pi GPIO pins | low | tested on simulator | Every Raspberry Pi with a 40-pin header |
| rpi-camera | picamera2 | Raspberry Pi camera modules, read-only capture | low | tested on simulator | Official camera modules |
| mqtt | paho-mqtt | Devices that publish and subscribe on MQTT topics | per mapping | tested on simulator | Unbounded |
| modbus | pymodbus | Modbus RTU and TCP meters, PLCs and VFDs | medium | tested on simulator | Thousands of industrial models |
| ble | bleak | BLE GATT devices | low | tested on simulator | Any BLE peripheral with standard or documented characteristics |
| midi | mido, python-rtmidi | MIDI controllers and instruments | low | tested on simulator | Every class-compliant MIDI device |
| hid | hidapi | USB HID buttons, knobs and custom gadgets | low | tested on simulator | Any HID device with a documented report format |
| uvc | OpenCV | USB webcams, read-only capture | low | tested on simulator | Every UVC webcam |
| http | httpx | HTTP devices, with endpoints from the device file or an OpenAPI document | per endpoint | tested on simulator | Unbounded |

## Tier 2

| Driver | Library | Covers | Hazard default | Status |
|---|---|---|---|---|
| grbl | pyserial | GRBL CNC routers and laser cutters | high | tested on simulator |
| ros2 | own rosbridge client on websockets | ROS 2 topics, services and actions | high | tested on simulator |
| opcua | asyncua | OPC UA servers and LADS lab devices | medium | tested on simulator |
| sila2 | sila2 | SiLA 2 lab devices | medium | tested on simulator |
| indi | own INDI XML client | Telescope mounts, cameras, focusers | medium | tested on simulator |
| alpaca | httpx, ASCOM Alpaca REST | ASCOM Alpaca devices | medium | tested on simulator |
| onvif | own SOAP client on httpx and defusedxml | ONVIF cameras, read-only and PTZ with limits | low | tested on simulator |
| pylabrobot | pylabrobot | Liquid handlers and lab robots | high | tested on simulator |
| micromanager | pymmcore-plus | Research microscopes, their cameras, stages, turrets, wheels, shutters and light sources | medium | tested on simulator |
| seabreeze | python-seabreeze | Ocean Insight and Ocean Optics spectrometers | low | tested on simulator |
| lerobot | lerobot | Hugging Face LeRobot arms | high | tested on simulator |

## Tier 3

| Driver | Covers | Hazard default | Status |
|---|---|---|---|
| bambu | Bambu Lab X1, P1, A1 and A1 mini | medium | tested on simulator |
| can | VESC, ODrive and CubeMars motor controllers, battery management systems, CAN sensor and IO nodes | medium | tested on simulator |
| knx | KNX switch, dimmer and blind actuators and room thermostats | low | tested on simulator |
| matter | Matter lights, plugs, sensors, thermostats and fans | low | tested on simulator |
| pi-i2c-spi | I2C temperature and humidity sensors, SPI and I2C ADCs and DACs | low | tested on simulator |
| upnp | UPnP media renderers and speakers, DLNA smart TVs, internet gateways | low | tested on simulator |
| zigbee-zwave | Zigbee lights, plugs and sensors, Z-Wave switches, dimmers, plugs and multisensors | low | tested on simulator |
