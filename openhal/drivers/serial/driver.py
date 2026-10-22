"""Generic line-based serial driver.

Protocol. Many boards and instruments speak plain text over a serial port. The host sends one
command line and the device answers with one line. Nothing about the commands is built in.
Each channel's `map` in the device file gives the query, the reply pattern and the command
template, so the same driver covers any device with a documented line protocol.

    read:
      temperature: { unit: degC, map: { query: "TEMP?", parse: "T=(?P<value>[-0-9.]+)" } }
      level: { unit: percent, stream: true, map: { listen: "^L=(?P<value>[0-9.]+)$" } }
    write:
      fan_speed:
        unit: percent
        min: 0
        max: 100
        map:
          command: "FAN {value:.0f}"
          scale: 0.392157
          expect: "^OK$"
          error: "^ERR"
          get: "FAN?"
          parse: "FAN=(\\d+)"
    actions:
      beep: { args: { count: { unit: dimensionless, min: 1, max: 5 } }, map: { command: "BEEP {count:.0f}" } }

Quirks.

- Lines that match a `listen` pattern are unsolicited values and never count as a reply.
  Every other line is the reply to the command in flight. Late replies are dropped before the
  next command is sent, so a slow device can't shift answers onto the wrong channel.
- Values are refused if they contain control characters, so a string channel can't append a
  second command with an embedded newline.
- Many Arduino boards reset when the port opens. Set `settle` (for example `2 s`) to wait for
  the boot banner before the first command. Anything received during that time is discarded.
- Without `map.get`, reading a write channel returns the last value this driver sent and fails
  before the first write. The driver never invents a value.
- The serial protocol has no emergency behavior of its own. The safe state comes from the
  device file.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from openhal.drivers.base import Discovered, Driver, DriverError, DriverInfo, Health, Reading
from openhal.drivers.serial import mapping
from openhal.drivers.serial.link import (
    Opener,
    SerialLink,
    list_serial_ports,
    port_identifiers,
    pyserial_opener,
    resolve_port,
)
from openhal.spec.models import DeviceFile

NEWLINES: dict[str, str] = {"lf": "\n", "crlf": "\r\n", "cr": "\r", "\n": "\n", "\r\n": "\r\n", "\r": "\r"}
MAX_LINE = 4096


class SerialParams(BaseModel):
    """`connect` parameters for the serial driver."""

    model_config = ConfigDict(extra="forbid")

    port: str = Field(min_length=1, max_length=300, description="Device path, pyserial URL or auto.")
    baud: int = Field(default=9600, ge=50, le=4_000_000)
    newline: Literal["lf", "crlf", "cr", "\n", "\r\n", "\r"] = "lf"
    encoding: Literal["ascii", "utf-8", "latin-1"] = "ascii"
    timeout: float = Field(default=1.0, description="How long to wait for a reply.")
    settle: float = Field(default=0.0, description="Wait after opening, for boards that reset on open.")
    identify: str | None = Field(default=None, max_length=100, description="A read-only query, such as ID?")
    board: str | None = Field(default=None, max_length=80)
    rtscts: bool = False
    dsrdtr: bool = False

    @field_validator("timeout", "settle", mode="before")
    @classmethod
    def _duration(cls, value: Any) -> float:
        return mapping.duration(value)

    @field_validator("timeout")
    @classmethod
    def _timeout_range(cls, value: float) -> float:
        if not 0.05 <= value <= 30:
            raise ValueError("timeout must be between 50 ms and 30 s.")
        return value

    @field_validator("settle")
    @classmethod
    def _settle_range(cls, value: float) -> float:
        if not 0 <= value <= 10:
            raise ValueError("settle must be between 0 s and 10 s.")
        return value

    @field_validator("identify")
    @classmethod
    def _identify(cls, value: str | None) -> str | None:
        if value is not None:
            mapping.plain_text(value, "identify")
        return value


class ReadMap(mapping.ValueMap):
    query: str | None = Field(default=None, max_length=mapping.MAX_TEMPLATE)
    listen: str | None = Field(default=None, description="Regex for lines the device sends on its own.")

    @field_validator("listen")
    @classmethod
    def _listen(cls, value: str | None) -> str | None:
        return mapping.check_regex(value)

    @model_validator(mode="after")
    def _one_source(self) -> ReadMap:
        if (self.query is None) == (self.listen is None):
            raise ValueError("give exactly one of query or listen.")
        if self.listen is not None and self.parse is None:
            return self.model_copy(update={"parse": self.listen})
        return self


class WriteMap(mapping.ValueMap):
    command: str = Field(max_length=mapping.MAX_TEMPLATE)
    get: str | None = Field(default=None, max_length=mapping.MAX_TEMPLATE)
    expect: str | None = None
    error: str | None = None

    @field_validator("expect", "error")
    @classmethod
    def _patterns(cls, value: str | None) -> str | None:
        return mapping.check_regex(value)


class ActionMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    command: str = Field(max_length=mapping.MAX_TEMPLATE)
    expect: str | None = None
    error: str | None = None
    on: str = "1"
    off: str = "0"

    @field_validator("expect", "error")
    @classmethod
    def _patterns(cls, value: str | None) -> str | None:
        return mapping.check_regex(value)


def _parse_map(model: type[BaseModel], raw: dict[str, Any] | None, where: str) -> Any:
    if raw is None:
        raise DriverError(f"{where} needs a map for the serial driver, for example map: {{ query: 'TEMP?' }}.")
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'map'}: {e['msg']}" for e in exc.errors())
        raise DriverError(f"{where}.map is not valid for the serial driver ({problems}).") from exc


class SerialDriver(Driver):
    """Line-based text protocols over a serial port, configured entirely by the device file."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="serial",
        protocols=("line-based text over serial (USB CDC, UART, RFC 2217, raw TCP)",),
        hazard_default="medium",
        summary="Any device with a line-based text protocol, configured by its device file.",
    )
    params_model: ClassVar[type[Any] | None] = SerialParams

    def __init__(self, device: DeviceFile, *, opener: Opener | None = None) -> None:
        super().__init__(device)
        self.settings = SerialParams.model_validate(device.connect.params)
        self._opener = opener
        self.newline = NEWLINES[self.settings.newline]
        self.link: SerialLink | None = None
        self._reads: dict[str, ReadMap] = {}
        self._writes: dict[str, WriteMap] = {}
        self._actions: dict[str, ActionMap] = {}
        self._streamed: dict[str, Reading] = {}
        self._written: dict[str, Reading] = {}
        self._replies: asyncio.Queue[str | None] = asyncio.Queue()
        self._pump_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._check_maps()

    def _check_maps(self) -> None:
        for name, spec in self.device.read.items():
            if spec.type == "image":
                raise DriverError(f"read.{name}: the serial driver can't read images.")
            read_map = _parse_map(ReadMap, spec.map, f"read.{name}")
            if read_map.query is not None:
                mapping.check_template(read_map.query, set(), f"read.{name}.map.query")
                mapping.plain_text(read_map.query, f"read.{name}.map.query")
            self._reads[name] = read_map
        for name, write_spec in self.device.write.items():
            write_map = _parse_map(WriteMap, write_spec.map, f"write.{name}")
            mapping.check_template(write_map.command, {"value"}, f"write.{name}.map.command")
            mapping.render(write_map.command, {"value": mapping.sample(write_spec)}, f"write.{name}.map.command")
            if write_map.get is not None:
                mapping.check_template(write_map.get, set(), f"write.{name}.map.get")
                mapping.plain_text(write_map.get, f"write.{name}.map.get")
            self._writes[name] = write_map
        for name, action in self.device.actions.items():
            action_map = _parse_map(ActionMap, action.map, f"actions.{name}")
            mapping.check_template(action_map.command, set(action.args), f"actions.{name}.map.command")
            samples = {arg: mapping.sample(spec) for arg, spec in action.args.items()}
            mapping.render(action_map.command, samples, f"actions.{name}.map.command")
            self._actions[name] = action_map

    # ------------------------------------------------------------------ discovery

    @classmethod
    async def discover(cls) -> list[Discovered]:
        ports = await asyncio.to_thread(list_serial_ports)
        return [
            Discovered(
                driver="serial",
                address=str(info.device),
                identifiers=port_identifiers(info),
                label=getattr(info, "description", None) or str(info.device),
            )
            for info in ports
        ]

    async def identify(self) -> dict[str, str]:
        identity = {"port": self.settings.port}
        if self.settings.board:
            identity["board"] = self.settings.board
        if self.settings.identify and self.link is not None and self.link.connected:
            identity["reply"] = await self._exchange(self.settings.identify)
        return identity

    # ------------------------------------------------------------------ connection

    async def connect(self) -> None:
        await self.close()
        opener = self._opener
        if opener is None:
            port = await asyncio.to_thread(
                resolve_port,
                self.settings.port,
                self.device.match.usb,
                self.device.match.serial_number,
                driver="serial",
            )
            opener = pyserial_opener(port, self.settings.baud, rtscts=self.settings.rtscts, dsrdtr=self.settings.dsrdtr)
        self.link = SerialLink(opener, name=self.settings.port)
        await self.link.open()
        if self.settings.settle:
            await asyncio.sleep(self.settings.settle)
        self.link.take_buffered()
        self._replies = asyncio.Queue()
        self._pump_task = asyncio.create_task(self._pump(self.link))

    async def _pump(self, link: SerialLink) -> None:
        terminator = b"\r" if self.newline == "\r" else b"\n"
        try:
            while True:
                try:
                    raw = await link.read_line(3600, terminator)
                except TimeoutError:
                    continue
                text = raw[:MAX_LINE].decode(self.settings.encoding, errors="replace").strip("\r\n")
                if not self._route_stream(text):
                    self._replies.put_nowait(text)
        except DriverError:
            self._replies.put_nowait(None)

    def _route_stream(self, text: str) -> bool:
        import re

        routed = False
        for name, read_map in self._reads.items():
            if read_map.listen is None or re.search(read_map.listen, text) is None:
                continue
            routed = True
            try:
                value = mapping.decode(name, text, self.device.read[name], read_map, f"read.{name}")
            except DriverError:
                continue
            self._streamed[name] = Reading(name, value, self.device.channel_unit(name))
        return routed

    def _require_link(self) -> SerialLink:
        if self.link is None or not self.link.connected or self._pump_task is None or self._pump_task.done():
            raise DriverError(f"{self.device.device_id} is not connected on {self.settings.port}. Reconnect it.")
        return self.link

    async def _send(self, line: str) -> None:
        link = self._require_link()
        while not self._replies.empty():
            if self._replies.get_nowait() is None:
                raise DriverError(f"{self.settings.port} disconnected. Check the cable, then reconnect.")
        await link.write((line + self.newline).encode(self.settings.encoding))

    async def _reply(self, line: str) -> str:
        try:
            reply = await asyncio.wait_for(self._replies.get(), self.settings.timeout)
        except TimeoutError:
            raise TimeoutError(
                f"No reply to {line!r} on {self.settings.port} within {self.settings.timeout:g} s. "
                "Check the baud rate, the newline setting and the command."
            ) from None
        if reply is None:
            raise DriverError(f"{self.settings.port} disconnected while waiting for a reply to {line!r}.")
        return reply

    async def _exchange(self, line: str) -> str:
        async with self._lock:
            await self._send(line)
            return await self._reply(line)

    # ------------------------------------------------------------------ channels

    async def read(self, channel: str) -> Reading:
        unit = self.device.channel_unit(channel)
        if channel in self._reads:
            read_map = self._reads[channel]
            if read_map.listen is not None:
                self._require_link()
                streamed = self._streamed.get(channel)
                if streamed is None:
                    raise DriverError(f"No {channel} line has arrived from the device yet. Try again shortly.")
                return streamed
            assert read_map.query is not None
            reply = await self._exchange(read_map.query)
            value = mapping.decode(channel, reply, self.device.read[channel], read_map, f"read.{channel}")
            return Reading(channel, value, unit)
        if channel in self._writes:
            write_map = self._writes[channel]
            if write_map.get is None:
                self._require_link()
                last = self._written.get(channel)
                if last is None:
                    raise DriverError(
                        f"{channel} has no map.get query, so it can only report a value after the first write."
                    )
                return last
            reply = await self._exchange(write_map.get)
            value = mapping.decode(channel, reply, self.device.write[channel], write_map, f"write.{channel}")
            return Reading(channel, value, unit)
        raise DriverError(f"{self.device.device_id} has no channel {channel!r}.")

    def _check_reply(self, reply: str, expect: str | None, error: str | None, sent: str) -> None:
        import re

        if error is not None and re.search(error, reply):
            raise DriverError(f"The device refused {sent!r} and replied {reply!r}.")
        if expect is not None and re.search(expect, reply) is None:
            raise DriverError(f"The device replied {reply!r} to {sent!r}, expected {expect!r}.")

    async def _command(self, line: str, expect: str | None, error: str | None) -> str | None:
        async with self._lock:
            await self._send(line)
            if expect is None and error is None:
                return None
            reply = await self._reply(line)
        self._check_reply(reply, expect, error, line)
        return reply

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        write_map = self._writes.get(channel)
        if write_map is None:
            raise DriverError(f"{self.device.device_id} has no write channel {channel!r}.")
        spec = self.device.write[channel]
        raw = mapping.encode(value, spec, write_map, f"write.{channel}")
        line = mapping.render(write_map.command, {"value": raw}, f"write.{channel}")
        await self._command(line, write_map.expect, write_map.error)
        reading = Reading(channel, value, self.device.channel_unit(channel))
        self._written[channel] = reading
        return reading

    async def _action(self, name: str, args: dict[str, Any]) -> Any:
        action_map = self._actions.get(name)
        if action_map is None:
            raise DriverError(f"{self.device.device_id} has no action {name!r}.")
        values: dict[str, Any] = {}
        for arg, value in args.items():
            if isinstance(value, bool):
                values[arg] = action_map.on if value else action_map.off
            else:
                values[arg] = value
        line = mapping.render(action_map.command, values, f"actions.{name}")
        reply = await self._command(line, action_map.expect, action_map.error)
        return {"sent": line, "reply": reply}

    async def health(self) -> Health:
        try:
            self._require_link()
        except DriverError as exc:
            return Health(connected=False, detail=str(exc))
        return Health(connected=True, detail=self.settings.port)

    async def close(self) -> None:
        task, link = self._pump_task, self.link
        self._pump_task = None
        self.link = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if link is not None:
            await link.close()

    def stream_age(self, channel: str) -> float | None:
        """Seconds since the last streamed value for a listen channel, for diagnostics."""
        reading = self._streamed.get(channel)
        return None if reading is None else time.time() - reading.at
