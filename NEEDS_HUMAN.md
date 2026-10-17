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
