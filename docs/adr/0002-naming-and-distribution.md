# 0002 Naming lives in one module, and the PyPI distribution is openhal-hub

## Context

The product is OpenHAL. The import name, CLI and daemon are `openhal`, `openhal` and `openhald`. Device files end in `.hal.yaml`. The PyPI name `openhal` is already used by an unrelated project (checked 2026-10-24).

## Options considered

1. Publish as `openhal` anyway. Impossible, the name is taken.
2. Rename the import package too. Breaks the brief's naming.
3. Keep every public name in one module and pick a free distribution name.

## Decision

- `openhal/_brand.py` holds the product name, package name, CLI name, daemon name, device file suffix, Arduino library name, default port and config directory. Every other module imports from it. Docs and the website read the same values at build time where possible.
- The distribution name is `openhal-hub`. Users run `uv tool install openhal-hub` or `pipx install openhal-hub` and get the `openhal` and `openhald` commands.
- The decision is listed in NEEDS_HUMAN.md for the owner to confirm before publishing.

## Consequences

A rename later is a change to `_brand.py`, `pyproject.toml` and the website config, plus a search for prose mentions in docs.
