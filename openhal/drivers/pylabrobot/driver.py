"""Liquid handlers through PyLabRobot. Every motion is an action.

Protocol (PyLabRobot 0.2 LiquidHandler API, docs.pylabrobot.org). Deck layouts and addresses
are in `deck.py`, and the recording chatterbox backend in `simulator.py`.

- One device file is one liquid handler and its deck. The deck comes from a PyLabRobot deck
  JSON file or from a layout of resource factories in the file.
- connect() builds the deck and the LiquidHandler and checks every address the file names, but
  doesn't initialize the robot unless `setup_on_connect: true`, because PyLabRobot's setup()
  homes the channels. The `initialize` action does it under the kernel instead.
- Actions are pick_up_tips, drop_tips, return_tips, discard_tips, aspirate, dispense and
  transfer. Tip spots and wells are addressed as `tips:A1` or `plate:A1:H1`. PyLabRobot checks
  tips and tracked volumes before anything moves, and those refusals fail the action.
- An operation that takes longer than `action_wait` answers `started` and finishes in the
  background. The next action waits for it.
- Reads come from PyLabRobot's own state, whether it is initialized, which channels hold tips
  and the tracked volume in a well. Tracked volumes are a model of what was pipetted, not a
  measurement.

Safe state. Native. Running operations are cancelled. The instrument finishes the firmware
command it is executing and then stops. Nothing is moved to make it safe, since any move on a
liquid handler can spill.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
from typing import Any, ClassVar, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from openhal.drivers.base import Driver, DriverError, DriverInfo, Health, Reading
from openhal.drivers.pylabrobot import deck as decks
from openhal.drivers.pylabrobot.deck import Placement
from openhal.drivers.serial import mapping
from openhal.spec.models import DeviceFile
from openhal.spec.units import Quantity, UnitError, convert, parse_quantity, parse_unit

BACKENDS: Final = {
    "chatterbox": ("openhal.drivers.pylabrobot.simulator", "RecordingBackend"),
    "star": ("pylabrobot.liquid_handling.backends", "STARBackend"),
    "evo": ("pylabrobot.liquid_handling.backends", "EVOBackend"),
    "opentrons": ("pylabrobot.liquid_handling.backends", "OpentronsOT2Backend"),
}
DEFAULT_DECK: Final = {"chatterbox": "starlet", "star": "star", "evo": "evo150", "opentrons": "ot2"}
OPS: Final[dict[str, set[str]]] = {
    "initialize": set(),
    "pick_up_tips": {"tips"},
    "drop_tips": {"tips"},
    "return_tips": set(),
    "discard_tips": set(),
    "aspirate": {"well", "volume"},
    "dispense": {"well", "volume"},
    "transfer": {"source", "target", "volume"},
}
CANCEL_WAIT_S = 2.0


class PyLabRobotParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: Literal["chatterbox", "star", "evo", "opentrons"]
    deck: Literal["starlet", "star", "ot2", "evo150"] | None = None
    deck_file: str | None = Field(default=None, max_length=500)
    layout: list[Placement] = Field(default=[], max_length=64)
    num_channels: int = Field(default=8, ge=1, le=16)
    host: str | None = Field(default=None, max_length=253)
    port: int = Field(default=31950, ge=1, le=65535)
    serial_number: str | None = Field(default=None, max_length=64)
    setup_on_connect: bool = False
    track_volumes: bool = True
    volumes: dict[str, str] = Field(default={}, max_length=96, description="Starting volumes, address to quantity.")
    action_wait: float = 8.0

    @field_validator("action_wait", mode="before")
    @classmethod
    def _duration(cls, value: Any) -> float:
        return mapping.duration(value)

    @model_validator(mode="after")
    def _shape(self) -> PyLabRobotParams:
        if not 0.1 <= self.action_wait <= 9:
            raise ValueError("action_wait must be between 100 ms and 9 s.")
        if self.deck_file and self.layout:
            raise ValueError("give deck_file or layout, not both.")
        if self.backend == "opentrons" and not self.host:
            raise ValueError("the opentrons backend needs host, the robot's address.")
        for address, quantity in self.volumes.items():
            try:
                decks.parse(address)
                convert(parse_quantity(quantity), "uL")
            except (DriverError, UnitError) as exc:
                raise ValueError(f"volumes {address}: {exc}") from None
        names = [item.name for item in self.layout]
        if len(set(names)) != len(names):
            raise ValueError("layout names must be unique.")
        return self


class ReadMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["initialized", "tips_mounted", "channels"] | None = None
    channel: int | None = Field(default=None, ge=0, le=15)
    container: str | None = None

    @model_validator(mode="after")
    def _one(self) -> ReadMap:
        if sum(item is not None for item in (self.status, self.channel, self.container)) != 1:
            raise ValueError("give exactly one of status, channel or container.")
        return self


class ActionMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    op: Literal[
        "initialize", "pick_up_tips", "drop_tips", "return_tips", "discard_tips", "aspirate", "dispense", "transfer"
    ]


def _validate(model: type[BaseModel], raw: dict[str, Any] | None, default: dict[str, Any] | None, where: str) -> Any:
    data = raw if raw is not None else default
    if data is None:
        raise DriverError(
            f"{where} is not a PyLabRobot channel or action the driver knows. "
            "Add a map, see docs/drivers/pylabrobot.md."
        )
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'map'}: {e['msg']}" for e in exc.errors())
        raise DriverError(f"{where}.map is not valid for the PyLabRobot driver ({problems}).") from exc


class PyLabRobotDriver(Driver):
    """Liquid handling robots through PyLabRobot."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="pylabrobot",
        protocols=("PyLabRobot LiquidHandler API",),
        hazard_default="high",
        summary="Liquid handlers through PyLabRobot. Tips, aspirate, dispense and transfer as confirmed actions.",
        safe_state_support="native",
        conformance="full",
    )
    params_model: ClassVar[type[Any] | None] = PyLabRobotParams

    def __init__(self, device: DeviceFile, *, backend: Any = None) -> None:
        super().__init__(device)
        self.settings = PyLabRobotParams.model_validate(device.connect.params)
        self._injected = backend
        self.backend: Any = None
        self.handler: Any = None
        self.deck: Any = None
        self.reads: dict[str, ReadMap] = {}
        self.actions: dict[str, ActionMap] = {}
        self._lock = asyncio.Lock()
        self._running: set[asyncio.Task[Any]] = set()
        self._lost: str | None = None
        self.uncertain: str | None = None
        """Why the tip and volume model may be wrong, after an operation failed while it ran."""
        if device.write:
            raise DriverError("The PyLabRobot driver has no write channels. Every motion is an action.")
        for name, spec in device.read.items():
            default = {"status": name} if name in ("initialized", "tips_mounted", "channels") else None
            read_map = _validate(ReadMap, spec.map, default, f"read.{name}")
            wanted = "bool" if read_map.status == "initialized" or read_map.channel is not None else "number"
            if spec.type != wanted:
                raise DriverError(f"read.{name}: this reading is a {wanted}.")
            if read_map.container is not None:
                decks.parse(read_map.container)
                self._volume_unit(spec.unit, f"read.{name}")
            self.reads[name] = read_map
        for name, action in device.actions.items():
            action_map = _validate(ActionMap, action.map, {"op": name} if name in OPS else None, f"actions.{name}")
            wanted_args = OPS[action_map.op]
            if set(action.args) != wanted_args:
                raise DriverError(
                    f"actions.{name}: {action_map.op} takes the arguments {sorted(wanted_args) or 'none'}."
                )
            for arg, arg_spec in action.args.items():
                if arg == "volume":
                    if arg_spec.type != "number":
                        raise DriverError(f"actions.{name}.args.volume must be a number.")
                    self._volume_unit(arg_spec.unit, f"actions.{name}.args.volume")
                elif arg_spec.type not in ("string", "enum"):
                    raise DriverError(
                        f"actions.{name}.args.{arg} is a deck address such as plate:A1, so make it a string or enum."
                    )
                else:
                    for value in arg_spec.values:
                        decks.parse(value)
            self.actions[name] = action_map

    @staticmethod
    def _volume_unit(unit: str | None, where: str) -> None:
        try:
            convert(Quantity(1.0, parse_unit(unit or "")), "uL")
        except UnitError:
            raise DriverError(f"{where} needs a volume unit such as uL, not {unit!r}.") from None

    def _make_backend(self) -> Any:
        if self._injected is not None:
            return self._injected
        module_name, class_name = BACKENDS[self.settings.backend]
        try:
            backend_class = getattr(importlib.import_module(module_name), class_name)
        except ImportError as exc:
            raise DriverError(
                f"The {self.settings.backend} backend needs PyLabRobot's extras ({exc.name}). Install them."
            ) from exc
        if self.settings.backend == "chatterbox":
            return backend_class(num_channels=self.settings.num_channels)
        if self.settings.backend == "opentrons":
            return backend_class(host=self.settings.host, port=self.settings.port)
        if self.settings.backend == "star":
            return backend_class(serial_number=self.settings.serial_number)
        return backend_class()

    async def identify(self) -> dict[str, str]:
        identity: dict[str, str] = {"backend": str(self.settings.backend)}
        if self.handler is not None:
            identity["channels"] = str(self.backend.num_channels)
            identity["deck"] = type(self.deck).__name__
            identity["resources"] = ", ".join(sorted(child.name for child in self.deck.children))
        return identity

    async def connect(self) -> None:
        import pylabrobot.resources as resources  # type: ignore[import-untyped]
        from pylabrobot.liquid_handling import LiquidHandler  # type: ignore[import-untyped]

        await self.close()
        if self.settings.track_volumes:
            resources.set_volume_tracking(True)
            resources.set_tip_tracking(True)
        kind = self.settings.deck or DEFAULT_DECK[self.settings.backend]
        self.deck = await asyncio.to_thread(decks.build, kind, self.settings.layout, self.settings.deck_file)
        for name, read_map in self.reads.items():
            if read_map.container is not None:
                decks.items(self.deck, read_map.container, "wells")
            if (
                read_map.channel is not None
                and read_map.channel >= self.settings.num_channels
                and self.settings.backend == "chatterbox"
            ):
                raise DriverError(
                    f"read.{name}: channel {read_map.channel} doesn't exist on {self.settings.num_channels} channels."
                )
        for spec in self.device.actions.values():
            for arg, arg_spec in spec.args.items():
                for value in arg_spec.values:
                    decks.items(self.deck, value, "tips" if arg == "tips" else "wells")
        self.backend = self._make_backend()
        self.handler = LiquidHandler(backend=self.backend, deck=self.deck)
        for address, quantity in self.settings.volumes.items():
            microliters = convert(parse_quantity(quantity), "uL")
            for well in decks.items(self.deck, address, "wells"):
                well.tracker.set_volume(microliters)
        self._lost = None
        if self.settings.setup_on_connect:
            await self._guard(self.handler.setup(), "setup")

    async def _guard(self, operation: Any, what: str) -> Any:
        """Await one PyLabRobot operation and turn its failures into DriverError."""
        import pylabrobot.liquid_handling.errors as handling_errors  # type: ignore[import-untyped]
        import pylabrobot.resources.errors as resource_errors  # type: ignore[import-untyped]

        checks = (
            resource_errors.TooLittleLiquidError,
            resource_errors.TooLittleVolumeError,
            resource_errors.HasTipError,
            resource_errors.NoTipError,
            resource_errors.CrossContaminationError,
            handling_errors.NoChannelError,
            handling_errors.ChannelsDoNotFitError,
            ValueError,
        )
        try:
            result = await operation
        except asyncio.CancelledError:
            self.uncertain = f"{what} was cancelled while it ran"
            raise
        except checks as exc:
            raise DriverError(f"PyLabRobot refused {what} ({type(exc).__name__}, {exc}).") from exc
        except (OSError, ConnectionError, TimeoutError) as exc:
            self._lost = f"{what} failed ({exc})"
            self.uncertain = f"{what} failed while it ran"
            raise DriverError(
                f"The liquid handler stopped answering during {what} ({exc}). Check it, then reconnect."
            ) from exc
        except Exception as exc:
            self.uncertain = f"{what} failed while it ran"
            raise DriverError(f"PyLabRobot reported a failure during {what} ({type(exc).__name__}, {exc}).") from exc
        self.uncertain = None if what == "setup" else self.uncertain
        return result

    def _handler(self) -> Any:
        if self.handler is None:
            raise DriverError(f"{self.device.device_id} is not connected. Connect it first.")
        return self.handler

    async def read(self, channel: str) -> Reading:
        handler = self._handler()
        read_map = self.reads.get(channel)
        if read_map is None:
            raise DriverError(f"{self.device.device_id} has no channel {channel!r}.")
        unit = self.device.channel_unit(channel)
        if read_map.status == "initialized":
            return Reading(channel, bool(handler.setup_finished), None)
        if read_map.status == "channels":
            return Reading(channel, float(self.backend.num_channels), unit)
        unsure = self.uncertain is not None
        if read_map.channel is not None:
            if read_map.channel not in handler.head:
                raise DriverError(f"{channel}: the head has no channel {read_map.channel}.")
            return Reading(channel, bool(handler.head[read_map.channel].has_tip), None, suspect=unsure)
        if read_map.status == "tips_mounted":
            mounted = float(sum(1 for tracker in handler.head.values() if tracker.has_tip))
            return Reading(channel, mounted, unit, suspect=unsure)
        assert read_map.container is not None
        well = decks.items(self.deck, read_map.container, "wells")[0]
        volume = float(well.tracker.get_used_volume())
        return Reading(channel, convert(Quantity(volume, parse_unit("uL")), unit or "uL"), unit, suspect=unsure)

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        raise DriverError("The PyLabRobot driver has no write channels. Every motion is an action.")

    def _microliters(self, name: str, value: Any) -> float:
        unit = self.device.actions[name].args["volume"].unit or "uL"
        return convert(Quantity(float(value), parse_unit(unit)), "uL")

    async def _operation(self, name: str, op: str, args: dict[str, Any]) -> dict[str, Any]:
        handler = self._handler()
        async with self._lock:
            if op == "initialize":
                if handler.setup_finished:
                    await self._guard(handler.stop(), "stop before setup")
                await self._guard(handler.setup(), "setup")
                return {"op": op}
            if not handler.setup_finished:
                raise DriverError("The liquid handler isn't initialized. Run the initialize action first.")
            if op in ("pick_up_tips", "drop_tips"):
                spots = decks.items(self.deck, str(args["tips"]), "tips")
                await self._guard(getattr(handler, op)(spots), op)
                return {"op": op, "spots": len(spots)}
            if op in ("return_tips", "discard_tips"):
                await self._guard(getattr(handler, op)(), op)
                return {"op": op}
            volume = self._microliters(name, args["volume"])
            if op in ("aspirate", "dispense"):
                wells = decks.items(self.deck, str(args["well"]), "wells")
                await self._guard(getattr(handler, op)(wells, vols=[volume] * len(wells)), op)
                return {"op": op, "wells": len(wells), "volume_ul": volume}
            source = decks.items(self.deck, str(args["source"]), "wells")
            target = decks.items(self.deck, str(args["target"]), "wells")
            if len(source) != len(target):
                raise DriverError(
                    f"transfer needs as many source wells as target wells, not {len(source)} and {len(target)}."
                )
            await self._guard(handler.aspirate(source, vols=[volume] * len(source)), "aspirate")
            await self._guard(handler.dispense(target, vols=[volume] * len(target)), "dispense")
            return {"op": op, "wells": len(source), "volume_ul": volume}

    async def _action(self, name: str, args: dict[str, Any]) -> Any:
        action = self.actions.get(name)
        if action is None:
            raise DriverError(f"{self.device.device_id} has no action {name!r}.")
        task = asyncio.create_task(self._operation(name, action.op, args))
        self._running.add(task)
        task.add_done_callback(self._finished)
        try:
            result = await asyncio.wait_for(asyncio.shield(task), self.settings.action_wait)
        except TimeoutError:
            return {"op": action.op, "status": "started"}
        return {**result, "status": "done"}

    def _finished(self, task: asyncio.Task[Any]) -> None:
        self._running.discard(task)
        if not task.cancelled():
            task.exception()

    async def _safe_state(self) -> None:
        running = list(self._running)
        for task in running:
            task.cancel()
        for task in running:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await asyncio.wait_for(task, CANCEL_WAIT_S)

    async def describe(self) -> dict[str, Any] | None:
        if self.deck is None:
            return None
        return _proposal(self.deck, self.settings.num_channels)

    async def health(self) -> Health:
        if self.handler is None:
            return Health(connected=False, detail="not connected")
        if getattr(self.backend, "lost", False):
            return Health(connected=False, detail="the instrument doesn't answer")
        if self._lost:
            return Health(connected=False, detail=self._lost)
        state = "initialized" if self.handler.setup_finished else "not initialized"
        busy = f", {len(self._running)} operations running" if self._running else ""
        return Health(connected=True, detail=f"{self.settings.backend} liquid handler, {state}{busy}")

    async def close(self) -> None:
        for task in list(self._running):
            task.cancel()
        handler, self.handler = self.handler, None
        if handler is not None and handler.setup_finished:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(handler.stop(), 5.0)


def _proposal(deck: Any, channels: int) -> dict[str, Any]:
    import pylabrobot.resources as resources

    each = {"confirm": "confirm-each-time", "suggested": True}
    racks = sorted(child.name for child in deck.children if isinstance(child, resources.TipRack))
    plates = [child for child in deck.children if isinstance(child, resources.Plate)]
    actions: dict[str, Any] = {"initialize": dict(each)}
    pattern = r"^({names}):[A-P]([1-9]|[1-3][0-9]|4[0-8])(:[A-P]([1-9]|[1-3][0-9]|4[0-8]))?$"
    if racks:
        tips = {"type": "string", "max_length": 80, "pattern": pattern.format(names="|".join(racks))}
        actions["pick_up_tips"] = {"args": {"tips": tips}, **each}
        actions["drop_tips"] = {"args": {"tips": tips}, **each}
        actions["return_tips"] = dict(each)
        actions["discard_tips"] = dict(each)
    read: dict[str, Any] = {
        "initialized": {"type": "bool"},
        "tips_mounted": {"unit": "dimensionless", "range": [0, channels]},
    }
    if plates:
        names = "|".join(sorted(plate.name for plate in plates))
        top = min(float(well.max_volume) for plate in plates for well in plate.children)
        well = {"type": "string", "max_length": 80, "pattern": pattern.format(names=names)}
        volume = {"unit": "uL", "min": 0, "max": round(top, 3)}
        actions["aspirate"] = {"args": {"well": well, "volume": volume}, **each}
        actions["dispense"] = {"args": {"well": well, "volume": volume}, **each}
        actions["transfer"] = {"args": {"source": well, "target": well, "volume": volume}, **each}
        first = plates[0]
        read[f"{first.name}_a1_volume"] = {"unit": "uL", "map": {"container": f"{first.name}:A1"}}
    return {
        "device": {"name": f"{type(deck).__name__} liquid handler"},
        "read": read,
        "actions": actions,
        "notes": "Proposed from the deck. Volume limits come from the smallest well. "
        "Lower them to your tips and protocol.",
    }
