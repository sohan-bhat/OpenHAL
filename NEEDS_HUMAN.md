# Needs a human

Items that only the owner can do, in the order they should be done. Each has exact steps.

## 1. Decide the PyPI distribution name

The PyPI name `openhal` belongs to an unrelated project (HAL, Harmful Action Limiter, v0.1.0, March 2026). The import name and CLI stay `openhal`. The distribution is built as `openhal-hub` until you decide (ADR 0002). The name lives in one place, `openhal/_brand.py` plus `pyproject.toml`.

Options if you want a different public name, all checked free on PyPI and npm as of 2026-10-24 unless noted.
1. `openhal-hub` (current default)
2. `openhal-core`
3. `openhald` (the daemon name, free on PyPI)
4. Ask the owner of `openhal` on PyPI whether they would transfer it (https://pypi.org/project/openhal/, repository https://github.com/otherland/hal)
5. Rename the whole project. Five alternatives that searched clean on 2026-10-24, said as words where possible.
   - OpenHAIL (Open Hardware Agent Interface Layer, "open hail")
   - OpenHARI (Open Hardware Agent Runtime Interface, "open harry")
   - OpenAHI (Open Agent Hardware Interface)
   - OpenMDI (Open Model Device Interface)
   - OpenDLI (Open Device Layer Interface, not yet searched)

## 2. Domain

openhal.com and openhal.org are registered by someone else. openhal.io looked unregistered on 2026-10-24. openhal.dev could not be checked. Check and buy at a registrar of your choice, then tell the website where it lives (website/astro.config.mjs, `site`).

## 3. Legal review of the bambu driver

The bambu driver controls Bambu Lab printers over LAN MQTT in Developer Mode, a mode Bambu Lab documents but doesn't support. Bambu Lab's Terms of Use restrict using its technology to develop software associated with its products without consent (section 3.1, read secondhand), and in April 2026 it sent a cease-and-desist letter over an OrcaSlicer fork that presented itself as Bambu Studio to reach Bambu Cloud. The driver never contacts the cloud, never impersonates Bambu software and never gets around authorization. Details and sources are in docs/drivers/bambu.md.

1. Read the current Terms of Use at https://bambulab.com/en-us/policies/terms, sections 3.1 and 3.4.
2. Decide whether to ship the driver, ship it marked experimental, or ask Bambu Lab (devpartner@bambulab.com) first.
3. Until then the catalog lists it as implemented and untested on hardware. Remove openhal/drivers/bambu/ if the answer is no.
