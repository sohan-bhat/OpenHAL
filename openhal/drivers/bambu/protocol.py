"""Bambu Lab LAN protocol pieces. Parameters, channel maps, report merging and SSDP parsing.

The field names come from the printers' `device/<serial>/report` messages as the community
documented them (OpenBambuAPI, mqtt.md). Nothing here opens a connection.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any, Final, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator

from openhal.drivers.base import Discovered
from openhal.drivers.http import values as v
from openhal.spec.units import parse_duration

USERNAME: Final = "bblp"
STATES: Final = ("idle", "prepare", "slicing", "running", "pause", "finish", "failed")
SPEEDS: Final = {"silent": 1, "standard": 2, "sport": 3, "ludicrous": 4}
PRINT_COMMANDS: Final = ("pause", "resume", "stop")
FIELDS: Final = {
    "nozzle_temp": ("nozzle_temper", "degC"),
    "nozzle_target": ("nozzle_target_temper", "degC"),
    "bed_temp": ("bed_temper", "degC"),
    "bed_target": ("bed_target_temper", "degC"),
    "chamber_temp": ("chamber_temper", "degC"),
    "progress": ("mc_percent", "percent"),
    "remaining": ("mc_remaining_time", "min"),
    "layer": ("layer_num", "dimensionless"),
    "total_layers": ("total_layer_num", "dimensionless"),
    "state": ("gcode_state", None),
    "job": ("subtask_name", None),
    "print_error": ("print_error", "dimensionless"),
    "speed_level": ("spd_lvl", None),
    "chamber_light": ("lights_report", None),
    "wifi_signal": ("wifi_signal", None),
}
CONTROLS: Final = ("speed_level", "chamber_light")
DISCOVERY_PORT = 2021
DISCOVERY_S = 3.0
NOTIFY_TYPE: Final = "urn:bambulab-com:device:3dprinter:1"


def _seconds(value: Any) -> Any:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return parse_duration(value)


Duration = Annotated[float, BeforeValidator(_seconds), Field(gt=0, le=60)]


class BambuParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1, max_length=253)
    serial: str = Field(pattern=r"^[A-Z0-9]{8,20}$")
    port: int = Field(default=8883, ge=1, le=65535)
    token_env: str = Field(default="BAMBU_ACCESS_CODE", pattern=r"^[A-Z_][A-Z0-9_]{0,63}$")
    cert_sha256: str | None = None
    ca_file: str | None = None
    timeout: Duration = 5.0
    reply_wait: Duration = 2.0
    safe_stop: Literal["stop", "pause"] = "stop"

    @field_validator("cert_sha256", mode="before")
    @classmethod
    def _fingerprint(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("cert_sha256 must be quoted in the device file, so YAML keeps it as text.")
        cleaned = value.replace(":", "").strip().lower()
        if len(cleaned) != 64 or any(char not in "0123456789abcdef" for char in cleaned):
            raise ValueError("cert_sha256 must be a SHA-256 fingerprint, 64 hex digits with or without colons.")
        return cleaned

    @model_validator(mode="after")
    def _trust(self) -> BambuParams:
        if self.cert_sha256 is None and self.ca_file is None:
            raise ValueError(
                "Give cert_sha256 (the printer certificate's fingerprint) or ca_file. Get the fingerprint with "
                "openssl s_client -connect <printer>:8883 </dev/null | openssl x509 -noout -fingerprint -sha256."
            )
        return self


class ReadMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str
    unit: str | None = None
    scale: float = 1.0

    @field_validator("field")
    @classmethod
    def _path(cls, value: str) -> str:
        v.parse_path(value)
        return value


class WriteMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    control: Literal["speed_level", "chamber_light"]


class ActionMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    command: Literal["pause", "resume", "stop"]


class PinMismatchError(Exception):
    """The printer's certificate is not the pinned one, so the access code was not sent."""


ClientFactory = Callable[[str], Any]


def default_client(client_id: str) -> Any:
    """A paho client for MQTT 3.1.1 with automatic reconnect off."""
    import paho.mqtt.client as mqtt
    from paho.mqtt.enums import CallbackAPIVersion, MQTTProtocolVersion

    return mqtt.Client(
        callback_api_version=CallbackAPIVersion.VERSION2,
        client_id=client_id,
        clean_session=True,
        protocol=MQTTProtocolVersion.MQTTv311,
        reconnect_on_failure=False,
    )


def merge(target: dict[str, Any], update: dict[str, Any]) -> None:
    """Merge a partial report into the state. Nested objects merge, lists and values replace."""
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            merge(target[key], value)
        else:
            target[key] = value


def parse_notify(text: str, sender: str) -> Discovered | None:
    """A printer from one SSDP NOTIFY datagram, or None if it isn't a Bambu Lab printer."""
    headers: dict[str, str] = {}
    for line in text.splitlines()[1:]:
        name, sep, value = line.partition(":")
        if sep:
            headers[name.strip().lower()] = value.strip()
    if headers.get("nt") != NOTIFY_TYPE or not headers.get("usn"):
        return None
    serial = headers["usn"]
    identifiers = {"serial": serial}
    for header, key in (
        ("devmodel.bambu.com", "model"),
        ("devname.bambu.com", "name"),
        ("devconnect.bambu.com", "mode"),
    ):
        if headers.get(header):
            identifiers[key] = headers[header]
    address = headers.get("location") or sender
    return Discovered("bambu", address, identifiers, f"Bambu Lab printer {identifiers.get('name', serial)}")


def propose(state: dict[str, Any], serial: str) -> dict[str, Any]:
    """Device file sections proposed from a status report. Writes and actions are suggested."""
    read: dict[str, Any] = {}
    for name, (path, unit) in FIELDS.items():
        if path not in state or name in CONTROLS:
            continue
        if name == "state":
            read[name] = {"type": "enum", "values": list(STATES)}
        elif unit is None:
            read[name] = {"type": "string"}
        else:
            read[name] = {"unit": unit}
    write: dict[str, Any] = {}
    if "spd_lvl" in state:
        write["speed_level"] = {"type": "enum", "values": list(SPEEDS), "suggested": True}
    if "lights_report" in state:
        write["chamber_light"] = {"type": "bool", "suggested": True}
    actions = {
        "pause": {"require": ["state == running"], "suggested": True},
        "resume": {"require": ["state == pause"], "suggested": True},
        "stop": {"confirm": "confirm", "suggested": True},
    }
    device: dict[str, Any] = {"name": f"Bambu Lab printer {serial}", "manufacturer": "Bambu Lab"}
    return {
        "device": device,
        "read": read,
        "write": write,
        "actions": actions,
        "notes": "Proposed from the printer's status report. Commands need LAN-only mode with Developer Mode on.",
    }
