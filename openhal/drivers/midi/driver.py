"""MIDI driver. Controllers and instruments over MIDI 1.0, through mido and python-rtmidi.

Protocol. MIDI 1.0 channel voice messages (MIDI 1.0 Detailed Specification 4.2.1). The driver
reads Control Change (CC), Note On and Note Off, Program Change and Pitch Bend from an input
port, and sends the same messages to an output port, for pad LEDs, motorised faders and synth
parameters. Channels in the device file are numbered 1 to 16, as on the device, and sent as 0
to 15 on the wire.

Behavior worth knowing.

- MIDI is push only and has no way to ask a controller for the position of a knob. A read
  returns the newest value received since connecting, timestamped when it arrived, or None
  (unknown) until the control is moved.
- Write channels report the last value the driver sent, or None before the first write,
  because controllers don't report LED or parameter state.
- Values in `percent` map 0 to 100 onto 0 to 127 (pitch bend onto -8192 to 8191), rounded to the
  nearest step. Values in `dimensionless` are the raw MIDI numbers.
- Note On with velocity 0 counts as Note Off, as the specification says.
- Health checks that the ports are still listed by the MIDI system, which catches unplugged
  USB devices.
- MIDI has no emergency behavior. The device file's safe state is sent like any other message.
"""

from __future__ import annotations

import asyncio
import re
import threading
import time
from typing import Annotated, Any, ClassVar, Final, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, model_validator

from openhal.drivers.base import Discovered, Driver, DriverError, DriverInfo, Health, Reading
from openhal.spec.models import DeviceFile
from openhal.spec.units import parse_duration

Kind = Literal["cc", "note", "program", "pitchwheel"]
_RANGE: Final = {"cc": (0, 127), "note": (0, 127), "program": (0, 127), "pitchwheel": (-8192, 8191)}
_UNITS: Final = frozenset({"dimensionless", "percent", "%"})


def _seconds(value: Any) -> Any:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return parse_duration(value)


Duration = Annotated[float, BeforeValidator(_seconds), Field(gt=0, le=60)]
Channel = Annotated[int, Field(ge=1, le=16)]
Data = Annotated[int, Field(ge=0, le=127)]


class MidiParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = "auto"
    input: str | None = None
    output: str | None = None
    channel: Channel = 1
    backend: str | None = Field(default=None, pattern=r"^[a-z_][a-z0-9_.]*$")
    timeout: Duration = 2.0


class MidiMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cc: Data | None = None
    note: Data | None = None
    program: bool = False
    pitchwheel: bool = False
    channel: Channel | None = None
    velocity: Annotated[int, Field(ge=1, le=127)] = 127
    on: Data = 127
    off: Data = 0

    @model_validator(mode="after")
    def _one(self) -> MidiMap:
        chosen = [self.cc is not None, self.note is not None, self.program, self.pitchwheel]
        if sum(chosen) != 1:
            raise ValueError("Give exactly one of cc, note, program: true or pitchwheel: true.")
        return self

    @property
    def kind(self) -> Kind:
        if self.cc is not None:
            return "cc"
        if self.note is not None:
            return "note"
        return "program" if self.program else "pitchwheel"


def _default_backend(name: str | None) -> Any:
    import mido  # type: ignore[import-untyped]

    return mido.Backend(name) if name else mido.Backend()


class MidiDriver(Driver):
    """MIDI controllers and instruments. Each channel maps to one CC, note, program or pitch bend."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="midi",
        protocols=("MIDI 1.0",),
        hazard_default="low",
        summary="MIDI controllers and instruments, read knobs and pads, set LEDs and parameters.",
    )
    params_model: ClassVar[type[Any] | None] = MidiParams

    def __init__(self, device: DeviceFile, *, backend: Any = None) -> None:
        super().__init__(device)
        self.settings = MidiParams.model_validate(device.connect.params)
        self._backend = backend
        self._input: Any = None
        self._output: Any = None
        self._names: tuple[str | None, str | None] = (None, None)
        self._lock = threading.Lock()
        self._latest: dict[tuple[str, int, int], tuple[int, float]] = {}
        self._written: dict[str, float | bool | str] = {}
        self.maps: dict[str, MidiMap] = {}
        for name, spec in device.read.items():
            self.maps[name] = self._check(name, spec.type, spec.unit, spec.map)
        for name, wspec in device.write.items():
            self.maps[name] = self._check(name, wspec.type, wspec.unit, wspec.map)
        if device.actions:
            raise DriverError("The midi driver has no actions. Model each message as a write channel.")

    def _check(self, name: str, kind: str, unit: str | None, raw: dict[str, Any] | None) -> MidiMap:
        if raw is None:
            raise DriverError(f"{name} needs a map, for example map: {{ cc: 1 }} or map: {{ note: 36 }}.")
        try:
            mmap = MidiMap.model_validate(raw)
        except ValidationError as exc:
            problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'map'}: {e['msg']}" for e in exc.errors())
            raise DriverError(f"{name} has an invalid midi map. {problems}") from None
        if kind not in ("number", "bool"):
            raise DriverError(f"{name} is a {kind} channel. MIDI values are numbers or bools.")
        if kind == "number" and unit not in _UNITS:
            raise DriverError(f"{name} uses {unit}. MIDI channels use dimensionless (raw values) or percent.")
        if kind == "bool" and mmap.kind in ("program", "pitchwheel"):
            raise DriverError(f"{name} is a bool channel, which works with cc or note maps only.")
        return mmap

    @property
    def backend(self) -> Any:
        if self._backend is None:
            self._backend = _default_backend(self.settings.backend)
        return self._backend

    def _channel(self, mmap: MidiMap) -> int:
        return (mmap.channel or self.settings.channel) - 1

    def _key(self, mmap: MidiMap) -> tuple[str, int, int]:
        number = mmap.cc if mmap.cc is not None else mmap.note if mmap.note is not None else 0
        return mmap.kind, self._channel(mmap), number

    @classmethod
    async def discover(cls, *, backend: Any = None) -> list[Discovered]:
        """List the MIDI ports the system knows. Listing never opens a port."""
        midi = backend or _default_backend(None)
        inputs = set(await asyncio.to_thread(midi.get_input_names))
        outputs = set(await asyncio.to_thread(midi.get_output_names))
        found = []
        for name in sorted(inputs | outputs):
            direction = (
                "input and output" if name in inputs and name in outputs else "input" if name in inputs else "output"
            )
            found.append(
                Discovered(
                    driver="midi", address=name, identifiers={"usb_class": "midi"}, label=f"{name} ({direction})"
                )
            )
        return found

    def _pick(self, names: list[str], explicit: str | None, what: str) -> str:
        if explicit is not None:
            if explicit not in names:
                raise DriverError(f"No MIDI {what} port named {explicit!r}. Ports: {', '.join(names) or 'none'}.")
            return explicit
        wanted = self.settings.name
        if wanted == "auto":
            if len(names) != 1:
                raise DriverError(
                    f"name is auto but there are {len(names)} MIDI {what} ports ({', '.join(names) or 'none'}). "
                    "Set name to part of the port name."
                )
            return names[0]
        matches = [port for port in names if wanted.lower() in port.lower()]
        if len(matches) != 1:
            raise DriverError(
                f"{len(matches)} MIDI {what} ports match {wanted!r} ({', '.join(names) or 'none'} exist). "
                "Use a longer part of the port name, or set input and output."
            )
        return matches[0]

    def _needs(self) -> tuple[bool, bool]:
        return bool(self.device.read), bool(self.device.write)

    async def connect(self) -> None:
        await self.close()
        needs_input, needs_output = self._needs()
        midi = self.backend
        input_name = output_name = None
        try:
            if needs_input:
                input_name = self._pick(await asyncio.to_thread(midi.get_input_names), self.settings.input, "input")
                self._input = await asyncio.to_thread(midi.open_input, input_name, callback=self._on_message)
            if needs_output:
                output_name = self._pick(await asyncio.to_thread(midi.get_output_names), self.settings.output, "output")
                self._output = await asyncio.to_thread(midi.open_output, output_name)
        except (OSError, ValueError) as exc:
            await self.close()
            raise DriverError(f"Could not open the MIDI port ({exc}). Check the device is plugged in.") from None
        except DriverError:
            await self.close()
            raise
        self._names = (input_name, output_name)
        with self._lock:
            self._latest.clear()

    async def close(self) -> None:
        for port in (self._input, self._output):
            if port is not None:
                await asyncio.to_thread(port.close)
        self._input = self._output = None

    async def health(self) -> Health:
        input_name, output_name = self._names
        needs_input, needs_output = self._needs()
        if (needs_input and self._input is None) or (needs_output and self._output is None):
            return Health(connected=False, detail="MIDI ports are not open")
        try:
            inputs = await asyncio.to_thread(self.backend.get_input_names) if needs_input else []
            outputs = await asyncio.to_thread(self.backend.get_output_names) if needs_output else []
        except (OSError, ValueError) as exc:
            return Health(connected=False, detail=f"MIDI system error ({exc})")
        if needs_input and input_name not in inputs:
            return Health(connected=False, detail=f"MIDI input {input_name} is gone")
        if needs_output and output_name not in outputs:
            return Health(connected=False, detail=f"MIDI output {output_name} is gone")
        return Health(connected=True, detail=" / ".join(filter(None, self._names)))

    async def identify(self) -> dict[str, str]:
        identity = {"name": self.settings.name, "channel": str(self.settings.channel)}
        input_name, output_name = self._names
        if input_name:
            identity["input"] = input_name
        if output_name:
            identity["output"] = output_name
        return identity

    def _on_message(self, message: Any) -> None:
        kind = message.type
        channel = getattr(message, "channel", None)
        if channel is None:
            return
        now = time.time()
        with self._lock:
            if kind == "control_change":
                self._latest[("cc", channel, message.control)] = (message.value, now)
            elif kind == "note_on":
                self._latest[("note", channel, message.note)] = (message.velocity, now)
            elif kind == "note_off":
                self._latest[("note", channel, message.note)] = (0, now)
            elif kind == "program_change":
                self._latest[("program", channel, 0)] = (message.program, now)
            elif kind == "pitchwheel":
                self._latest[("pitchwheel", channel, 0)] = (message.pitch, now)

    def _to_channel(self, raw: int, mmap: MidiMap, kind: str, unit: str | None) -> float | bool:
        if kind == "bool":
            return raw > 0 if mmap.kind == "note" else raw >= 64
        if unit in ("percent", "%"):
            low, high = _RANGE[mmap.kind]
            return raw * 100.0 / high if mmap.kind != "pitchwheel" else raw * 100.0 / (8191 if raw >= 0 else -low)
        return float(raw)

    def _to_raw(self, value: float, mmap: MidiMap, unit: str | None) -> int:
        low, high = _RANGE[mmap.kind]
        if unit in ("percent", "%"):
            scaled = value * high / 100.0 if mmap.kind != "pitchwheel" or value >= 0 else value * -low / 100.0
        else:
            scaled = value
        raw = round(scaled)
        if not low <= raw <= high:
            raise DriverError(
                f"{value:g} {unit} is outside what a MIDI {mmap.kind} message can carry ({low} to {high})."
            )
        return raw

    async def read(self, channel: str) -> Reading:
        mmap = self.maps.get(channel)
        if mmap is None:
            raise DriverError(f"This midi device has no channel {channel!r}.")
        unit = self.device.channel_unit(channel)
        if channel in self.device.write:
            if self._output is None:
                raise DriverError("The MIDI output port is not open.")
            return Reading(channel, self._written.get(channel), unit=unit)
        if self._input is None:
            raise DriverError("The MIDI input port is not open.")
        with self._lock:
            latest = self._latest.get(self._key(mmap))
        if latest is None:
            return Reading(channel, None, unit=unit)
        raw, at = latest
        value = self._to_channel(raw, mmap, self.device.read[channel].type, unit)
        spec = self.device.read[channel]
        suspect = bool(
            spec.range is not None and isinstance(value, float) and not spec.range[0] <= value <= spec.range[1]
        )
        return Reading(channel, value, unit=unit, at=at, suspect=suspect)

    def _message(self, mmap: MidiMap, value: float | bool | str, unit: str | None) -> tuple[Any, float | bool]:
        import mido

        channel = self._channel(mmap)
        if isinstance(value, bool):
            if mmap.kind == "note":
                if value:
                    return mido.Message("note_on", channel=channel, note=mmap.note, velocity=mmap.velocity), True
                return mido.Message("note_off", channel=channel, note=mmap.note, velocity=0), False
            return mido.Message(
                "control_change", channel=channel, control=mmap.cc, value=mmap.on if value else mmap.off
            ), value
        if isinstance(value, str):
            raise DriverError("MIDI channels take numbers or bools.")
        raw = self._to_raw(float(value), mmap, unit)
        sent = self._to_channel(raw, mmap, "number", unit)
        if mmap.kind == "cc":
            return mido.Message("control_change", channel=channel, control=mmap.cc, value=raw), sent
        if mmap.kind == "note":
            return mido.Message("note_on", channel=channel, note=mmap.note, velocity=raw), sent
        if mmap.kind == "program":
            return mido.Message("program_change", channel=channel, program=raw), sent
        return mido.Message("pitchwheel", channel=channel, pitch=raw), sent

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        mmap = self.maps.get(channel)
        if mmap is None or channel not in self.device.write:
            raise DriverError(f"This midi device has no write channel {channel!r}.")
        if self._output is None:
            raise DriverError("The MIDI output port is not open.")
        unit = self.device.channel_unit(channel)
        message, sent = self._message(mmap, value, unit)
        try:
            await asyncio.wait_for(asyncio.to_thread(self._output.send, message), self.settings.timeout)
        except (OSError, ValueError) as exc:
            raise DriverError(f"Sending {message} failed ({exc}). Check the device is still plugged in.") from None
        self._written[channel] = sent
        return Reading(channel, sent, unit=unit)

    async def describe(self, listen_s: float = 3.0) -> dict[str, Any] | None:
        """Propose read channels for every control that sent something. Move each control while it listens."""
        if self._input is None:
            return None
        await asyncio.sleep(listen_s)
        with self._lock:
            seen = sorted(self._latest)
        reads: dict[str, Any] = {}
        for kind, channel, number in seen[:64]:
            suffix = f"_ch{channel + 1}" if channel + 1 != self.settings.channel else ""
            entry: dict[str, Any] = {"unit": "dimensionless", "stream": True}
            if kind == "cc":
                entry["range"] = [0, 127]
                entry["map"] = {"cc": number}
                name = f"cc_{number}"
            elif kind == "note":
                entry["range"] = [0, 127]
                entry["map"] = {"note": number}
                name = f"note_{number}"
            else:
                entry["map"] = {kind: True}
                name = kind
            if suffix:
                entry["map"]["channel"] = channel + 1
            reads[re.sub(r"[^a-z0-9_]", "_", name + suffix)] = entry
        result: dict[str, Any] = {
            "match": {"usb_class": "midi"},
            "notes": (
                f"Proposed from {len(seen)} controls that sent messages while the driver listened. "
                "Rename them after what they are on the device. Outputs such as pad LEDs can't be seen by "
                "listening, so add write channels from the device's MIDI implementation chart."
            ),
        }
        if reads:
            result["read"] = reads
        return result
