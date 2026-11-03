"""Hub configuration, read from `config.yaml` in the config directory.

Every setting has a safe default, so a missing file is fine. LAN access is off unless turned on.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Final

import yaml
from pydantic import BaseModel, ConfigDict, Field

from openhal._brand import DEFAULT_HOST, DEFAULT_PORT, config_dir


class ApiSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = DEFAULT_HOST
    port: int = Field(default=DEFAULT_PORT, ge=1024, le=65535)
    allow_lan: bool = False


class ConfirmSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    require_tty: bool = True
    ttl_s: float = Field(default=300.0, ge=10, le=3600)


class RoutineSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_enable_low_hazard: bool = False
    max_runtime_s: float = Field(default=3600.0, ge=1)
    min_interval_s: float = Field(default=1.0, ge=0.1)


class RunSettings(BaseModel):
    """Caps on runs of steps, waits and samples. A person changes them with openhal runs caps."""

    model_config = ConfigDict(extra="forbid")

    max_steps: int = Field(default=200, ge=1, le=10_000)
    max_seconds: float = Field(default=600.0, ge=1, le=86_400)
    per_agent: int = Field(default=2, ge=1, le=20)


class GpioStopSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pin: int | None = None
    pull_up: bool = True


class HubConfig(BaseModel):
    """Everything the hub reads at start. Paths are resolved against `home`."""

    model_config = ConfigDict(extra="forbid")

    home: Path = Field(default_factory=config_dir)
    api: ApiSettings = ApiSettings()
    confirm: ConfirmSettings = ConfirmSettings()
    routines: RoutineSettings = RoutineSettings()
    runs: RunSettings = RunSettings()
    stop_button: GpioStopSettings = GpioStopSettings()
    poll_floor_s: float = Field(default=0.2, ge=0.05)
    watchdog_tick_s: float = Field(default=0.5, ge=0.05)

    @property
    def devices_dir(self) -> Path:
        return self.home / "devices"

    @property
    def routines_dir(self) -> Path:
        return self.home / "routines"

    @property
    def db_path(self) -> Path:
        return self.home / "hub.db"

    @property
    def locks_dir(self) -> Path:
        return self.home / "locks"

    @property
    def human_token_path(self) -> Path:
        return self.home / "human.token"

    @property
    def approval_key_path(self) -> Path:
        return self.home / "approval.key"

    def ensure_dirs(self) -> None:
        for path in (self.home, self.devices_dir, self.routines_dir, self.locks_dir):
            path.mkdir(parents=True, exist_ok=True)
        self.home.chmod(0o700)


_OUTSIDE: Final = re.compile(r"^\S")
"""A line that starts at column 0 ends a section, a comment as much as the next key."""


def save_section(home: Path, name: str, values: dict[str, Any]) -> Path:
    """Write one top-level section of config.yaml and keep every other line, comments included.

    The section's old lines, up to the next line at column 0, are replaced, or the section is added
    at the end. The result must still load, so a bad value never reaches the file, and the new file
    replaces the old one in one step, so a crash never leaves half a file.
    """
    path = home / "config.yaml"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    block = yaml.safe_dump({name: values}, sort_keys=False).splitlines()
    start = next((index for index, line in enumerate(lines) if re.match(rf"^{re.escape(name)}\s*:", line)), None)
    if start is None:
        kept = [*lines, *block]
    else:
        end = next((index for index in range(start + 1, len(lines)) if _OUTSIDE.match(lines[index])), len(lines))
        kept = [*lines[:start], *block, *lines[end:]]
    text = "\n".join(kept) + "\n"
    data = yaml.safe_load(text) or {}
    HubConfig.model_validate({**data, "home": home})
    staged = path.with_name(f".{path.name}.{os.getpid()}.new")
    staged.write_text(text, encoding="utf-8")
    staged.chmod(0o600)
    os.replace(staged, path)
    return path


def load_config(home: Path | None = None) -> HubConfig:
    """Read config.yaml from the config directory, or return defaults."""
    base = home or config_dir()
    path = base / "config.yaml"
    data: dict[str, Any] = {}
    if path.exists():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"{path} must be a mapping.")
        data = loaded
    data.setdefault("home", base)
    return HubConfig.model_validate(data)
