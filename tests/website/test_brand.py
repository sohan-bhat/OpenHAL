"""The website's names must match openhal/_brand.py, and the site URL must live in one place."""

from __future__ import annotations

import re
from pathlib import Path

from openhal import _brand

ROOT = Path(__file__).resolve().parents[2]
BRAND_TS = ROOT / "website" / "src" / "config" / "brand.ts"
ASTRO_CONFIG = ROOT / "website" / "astro.config.mjs"


def website_constants() -> dict[str, str]:
    text = BRAND_TS.read_text(encoding="utf-8")
    found: dict[str, str] = {}
    for name, value in re.findall(r'^export const ([A-Z_]+) = (".*?"|\d+);$', text, re.M):
        found[name] = value.strip('"')
    return found


def test_every_python_brand_name_is_mirrored() -> None:
    site = website_constants()
    for name in dir(_brand):
        if not name.isupper() or name in ("DEFAULT_CONFIG_DIR",):
            continue
        assert name in site, f"website/src/config/brand.ts is missing {name}"
        assert site[name] == str(getattr(_brand, name)), f"{name} differs between _brand.py and brand.ts"


def test_config_dir_matches() -> None:
    assert website_constants()["DEFAULT_CONFIG_DIR"] == "~/" + _brand.DEFAULT_CONFIG_DIR.name


def test_site_url_is_one_constant() -> None:
    config = ASTRO_CONFIG.read_text(encoding="utf-8")
    assert len(re.findall(r'^const SITE_URL = process\.env\.OPENHAL_SITE \?\? "https://[^"]+";$', config, re.M)) == 1
    source = ROOT / "website" / "src"
    for path in source.rglob("*"):
        if path.is_file() and path.suffix in (".ts", ".astro", ".svelte", ".mjs", ".md"):
            assert "openhal.dev" not in path.read_text(encoding="utf-8"), f"{path} hard-codes the domain"
