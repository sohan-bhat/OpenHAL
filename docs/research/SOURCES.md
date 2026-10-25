# Sources

Every external fact used in the design, with the date it was checked.

## Model Hardware Standard (checked 2026-10-24)

- Anthropic announcement, "Previewing the Model Hardware Standard". https://www.anthropic.com/news/model-hardware-standard-research-preview
  - Drivers expose read and write primitives and make each device discoverable in a standard format.
  - Users add natural-language tags to the driver, directly or through an agent interview. The driver generates a reference file covering what can be measured, what can be adjusted and which limits are enforced.
  - Agents reach devices through MCP, a command line interface, or code files.
  - Works only with devices that have a programmable interface.
  - Research preview for a first group of labs and manufacturers. Open source planned after the preview with no date.
- Official site. https://modelhardwarestandard.com/ ("MHS is starting as a limited research preview", apply for access, no spec, repo, SDK or license listed.)
- CNBC, 2026-08-27. https://www.cnbc.com/2026/08/27/anthropic-pushes-into-physical-world-with-new-standard-to-help-ai-agents-operate-machines.html
- The Decoder. https://the-decoder.com/anthropic-wants-to-do-for-physical-hardware-what-its-model-context-protocol-did-for-software/ (partner claims not independently verified, driver burden unanswered)
- Kingy AI analysis, 2026-09-19. https://kingy.ai/blog/anthropic-model-hardware-standard-mhs/ (no public spec, schema, SDK, license, conformance suite or security guidance)
- DataNorth explainer. https://datanorth.ai/blog/model-hardware-standard-mhs-what-it-is-how-it-works-and-why-it-matters (step by step flow, limits enforced by the driver, unclear whether anything is auto-detected)
- AlphaSignal. https://alphasignal.ai/news/anthropic-s-model-hardware-standard-lets-claude-control-lab-robots-overnight (partner list, Carnegie Mellon 8 hour integration, hobbyist hardware planned later)
- explainx. https://explainx.ai/blog/anthropic-model-hardware-standard-mhs-research-preview-august-2026
- Packet Nebula. https://packetnebula.com/articles/model-hardware-standard-mhs-research-preview/ ("no spec, no repo, no reference driver")
- ANI. https://www.aninews.in/news/business/anthropic-announces-new-model-hardware-standard-for-ai-agents-plans-open-source-release-with-safety-guidance20260828112959/
- Third-party notes, no official repo as of 2026-08-28. https://github.com/ImChong/Robotics_Notebooks/blob/main/sources/sites/anthropic-model-hardware-standard.md

## Open projects in the same space (checked 2026-10-24)

- OpenMHP. https://pypi.org/project/openmhp/ and https://github.com/kushalsinha/openmhp (Apache-2.0, v0.9.0, 2026-09-16, simulator tested)
- Device Context Protocol. https://arxiv.org/abs/2605.26159 and https://trendshift.io/repositories/40309 (MIT)
- Octopus Protocol. https://arxiv.org/abs/2605.09055
- HACP IETF draft. https://datatracker.ietf.org/doc/draft-sunyi-hacp-protocol/
- LAP (Lab Agent Protocol). https://arxiv.org/abs/2606.03755
- EMQ Device Agent. https://www.emqx.com/en/blog/turning-every-iot-device-into-an-ai-agent
- arduino-mcp-server. https://github.com/hardware-mcp/arduino-mcp-server
- BufrAI arduino-mcp. https://github.com/BufrAI/arduino-mcp
- mcp-serial. https://glama.ai/mcp/servers/HumbertoBernal/mcp-serial
- serial-mcp. https://github.com/bmdragos/serial-mcp
- esp32-mcp. https://github.com/StefanYasin/esp32-mcp
- ROS MCP Server. https://discourse.openrobotics.org/t/ros-mcp-server-release/50024
- Kiln (AGPL-3.0, studied for scope only, no code used). https://pypi.org/project/kiln3d/
- OctoEverywhere MCP. https://blog.octoeverywhere.com/mcp-server-for-3d-printing/
- labmcp-scpi. https://socket.dev/pypi/package/labmcp-scpi
- LabMCP. https://pypi.org/project/labmcp/
- plr-mcp. https://glama.ai/mcp/servers/mcvs54hua1
- Home Assistant MCP guide. https://dev.to/raspberry_tips/connect-home-assistant-to-ai-set-up-an-mcp-server-for-claude-chatgpt-gemini-3io5
- SiLA 2 and OPC UA LADS comparison. https://www.zeiss.com/digital-innovation/insights/a/r-and-d-lab-automation-interoperability-standards-ai.html

## Name check for OpenHAL (checked 2026-10-24)

- PyPI `openhal` is taken by "HAL, Harmful Action Limiter, lean command guard for AI coding agents" v0.1.0, 2026-03-13. https://pypi.org/project/openhal/
- PyPI `openhald` is free. npm `openhal` is free.
- GitHub has no notable repository named exactly OpenHAL (closest are OpenHalo, OpenHalcon, OpenHaldex).
- Arduino Library Manager index has no `OpenHAL` library (10,265 libraries checked).
- openhal.com and openhal.org are registered (Gandi). openhal.io returned "Domain not found". openhal.dev could not be checked from this machine.

## Protocol and library references

Added as drivers are built. See docs/DEPENDENCIES.md for every dependency, version and license.

## Device library identifiers (checked 2026-10-25)

Where each identifier and default in library/ comes from. Identifiers in backticks are exactly what the files match.

- Linux USB id database, version 2026.06.26. http://www.linux-usb.org/usb.ids (Korg `0944:0117` nanoKONTROL2, Rigol `1ab1:04ce` DS1000Z series, Prusa vendor `2c99`. It lists `09e8:0076` as the LPK25, not the LPD8.)
- libsigrok udev rules. https://github.com/sigrokproject/libsigrok/blob/master/contrib/60-libsigrok.rules (Rigol DP800 series `1ab1:0e11`, Rigol 1000Z series `1ab1:04ce`, Siglent `f4ec:ee38` for the SDS1104X-E and SDM3055)
- Siglent SDM3065X resource string `USB0::0xF4EC::0xEE38::...::INSTR`, the SDM3000 family id. https://www.mikrocontroller.net/topic/544731
- Siglent SPD programming tips, resource string `USB0::0x0483::0x7540::SPD3X...::INSTR` and newline termination only. https://siglentna.com/operating-tip/spd-programming-tips/
- Siglent SPD3303X Quick Start, `*IDN?` reply `Siglent Technologies,SPD3303X,...`. https://siglentna.com/wp-content/uploads/dlm_uploads/2022/11/SPD3303X_QuickStart_E02A.pdf
- Keysight 34461A resource string `USB0::0x2A8D::0x1301::MY53216054::0::INSTR` from a real `list_resources()` run. https://www.denshi.club/pc/python/iotpythonstep34-4-dmm-34461a.html
- ds1054z library documentation, vendor `RIGOL TECHNOLOGIES` and product `DS1054Z` from `*IDN?`. https://ds1054z.readthedocs.io/en/latest/api/ds1054z.html
- Rigol DP800 and DS1000Z programming guides for `MEAS`, `OUTP`, `APPL`, `:TRIG:STAT?` and `:MEAS:ITEM?`, as in docs/drivers/scpi.md.
- Prusa i3 MK3 `2c99:0002`, product string "Original Prusa i3 MK3". https://github.com/dorssel/usbipd-win/issues/319
- Prusa MINI `2c99:000c`. https://github.com/prusa3d/Prusa-Firmware-Buddy/issues/2542
- Prusa MK4 `2c99:000d`. https://forum.repetier.com/discussion/11481/prusa-mk4-in-repetier-server-einbinden
- Sovol SV08 factory host name `SPI-XI` on firmware 2.4.6. https://github.com/eric-s-raymond/sovol-SV08-from-scratch/blob/master/unix-setup.adoc
- RatOS host name `RatOS` before setup, renamed during setup. https://os.ratrig.com/docs/installation and https://docs.ratrig.com/v-core-4-1/commissioning-guide-hub/idex/configuration
- Moonraker zeroconf service `_moonraker._tcp`. https://github.com/Arksine/moonraker/blob/master/moonraker/components/zeroconf.py
- ESPHome mDNS TXT records, including `project_name`. https://github.com/esphome/esphome/blob/dev/esphome/components/mdns/mdns_component.cpp
- Apollo MSR-2 project `ApolloAutomation.MSR-2` and entity names. https://github.com/ApolloAutomation/MSR-2/tree/main/Integrations/ESPHome
- Apollo AIR-1 project `ApolloAutomation.AIR-1` and entity names. https://github.com/ApolloAutomation/AIR-1/tree/main/Integrations/ESPHome
- Athom Smart Plug V2 project `China Athom Technology.Athom Plug V2`, entity names and restore mode. https://github.com/athom-tech/athom-configs/blob/main/athom-smart-plug-v2.yaml
- Shelly Gen2 mDNS service `_shelly._tcp`. https://shelly-api-docs.shelly.cloud/gen2/General/mDNS/
- Shelly MQTT status topics `<device id>/status/<component>:<id>`, off until `status_ntf` is set. https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/Mqtt/
- Shelly H&T Gen3 topic `shellyhtg3-<mac>/status/temperature:0` with `tC`, and its sparse reports on battery. https://github.com/home-assistant/core/issues/181421 and https://taphome.com/en/compatibility/shelly-ht-gen3-mqtt/
- Home Assistant Shelly entity naming from the device id when no device name is set. https://www.home-assistant.io/integrations/shelly/
- Shelly Plus Plug S and Dimmer Gen3 model names and ids. https://kb.shelly.cloud/knowledge-base/shelly-plus-plug-s and https://kb.shelly.cloud/knowledge-base/shelly-dimmer-gen3
- Eastron SDM register offsets (voltage `0x00`, current `0x06`, power `0x34`, power factor `0x3E`, frequency `0x46`, import `0x48`, total `0x156`), from Eastron's SDM630 protocol. https://github.com/volkszaehler/mbmd/blob/master/meters/rs485/sdm.go
- Eastron SDM630 factory address 1 and 9600 baud. https://docs.evcc.io/en/meters/eastron-sdm630-modbus and https://taphome.com/en/compatibility/eastron-sdm630/
- Akai LPD8 `09e8:0075` from `lsusb` output. https://bbs.archlinux.org/viewtopic.php?id=253043 and https://sourceforge.net/p/alsa/mailman/alsa-user/thread/50B7DA50.2050306@dynamix-tontechnik.ch/
- Korg nanoKONTROL2 sliders on CC 0 to 7 and knobs on CC 16 to 23. https://support.spectrasonics.net/manual/Omnisphere3HW/3/en/topic/setting-up-the-nanokontrol-2
- Xiaomi LYWSD03MMC characteristic `ebe0ccc1-7a0a-4b0c-8a1a-6ff2997da3a6` and its byte layout. https://github.com/keks51/lywsd03mmc-client and https://www.b4x.com/android/forum/threads/rmilywsd03mmc-xiaomi-mi-temperature-humidity-monitor-2.131806/
- pvvx ATC_MiThermometer names such as `ATC_F02AED` and the Environmental Sensing characteristics. https://github.com/pvvx/ATC_MiThermometer
- Bluetooth Heart Rate service `180d` and measurement `2a37`, and Battery Level `2a19`. https://www.bluetooth.com/specifications/assigned-numbers/
- Waveshare RPi Relay Board relays on BCM 26, 20 and 21, active low. https://www.waveshare.com/wiki/RPi_Relay_Board
- Pimoroni Fan SHIM fan on BCM 18 and button on BCM 17. https://pinout.xyz/pinout/fan_shim
- Raspberry Pi Camera Module 3 (IMX708) and High Quality Camera (IMX477). https://www.raspberrypi.com/documentation/accessories/camera.html
- ASCOM Remote, an Alpaca server for ASCOM drivers such as GS Server. https://github.com/ASCOMInitiative/ASCOMRemote and https://ascom-standards.org/Downloads/ScopeDrivers.htm
- Polar H10 names start with `Polar H10 ` followed by the sensor id. This comes from scans people have posted, not from a Polar document, so check it with openhal discover. https://github.com/polarofficial/polar-ble-sdk
- Akai LPD8 program 1 sends CC 1 to 8 from the knobs and notes 36 to 43 from the pads, as in openhal/drivers/midi/examples/lpd8-pads.hal.yaml.
