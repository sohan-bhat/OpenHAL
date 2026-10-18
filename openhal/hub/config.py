"""Hub configuration, read from `config.yaml` in the config directory.

Every setting has a safe default, so a missing file is fine. LAN access is off unless turned on.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

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
