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
