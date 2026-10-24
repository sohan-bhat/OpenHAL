"""A fake mido backend with a simulated pad controller. No MIDI subsystem, no hardware.

The fake implements the parts of a `mido.Backend` the driver uses: `get_input_names`,
`get_output_names`, `open_input(name, callback=...)` and `open_output(name)`. Ports carry real
`mido.Message` objects in both directions, so message construction and parsing are the real thing.

The simulated controller has eight knobs on CC 1 to 8, pads on notes 36 to 43, and pad LEDs
driven by note on and note off messages it receives, like the Akai LPD8 and many others.

Fault injection. `unplug()` removes the ports and closes them, as when the USB cable is pulled,
and `plug_in()` brings them back.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import mido  # type: ignore[import-untyped]

PORT = "Sim Pads MIDI 1"


class FakeInput:
    def __init__(self, controller: SimulatedController, name: str, callback: Callable[[Any], None] | None) -> None:
        self.controller = controller
        self.name = name
        self.callback = callback
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeOutput:
    def __init__(self, controller: SimulatedController, name: str) -> None:
        self.controller = controller
        self.name = name
        self.closed = False

    def send(self, message: Any) -> None:
        if self.closed:
            raise ValueError("send() called on closed port")
        self.controller.receive(message)

    def close(self) -> None:
        self.closed = True


@dataclass
class SimulatedController:
    """A pad controller. `turn`, `press` and `release` act like a person using it."""

    name: str = PORT
    channel: int = 0
    plugged: bool = True
    received: list[Any] = field(default_factory=list)
    leds: dict[int, int] = field(default_factory=dict)
    inputs: list[FakeInput] = field(default_factory=list)
    outputs: list[FakeOutput] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _emit(self, message: Any) -> None:
        for port in list(self.inputs):
            if not port.closed and port.callback is not None:
                port.callback(message)

    def turn(self, cc: int, value: int, channel: int | None = None) -> None:
        self._emit(
            mido.Message(
                "control_change", channel=self.channel if channel is None else channel, control=cc, value=value
            )
        )

    def press(self, note: int, velocity: int = 100) -> None:
        self._emit(mido.Message("note_on", channel=self.channel, note=note, velocity=velocity))

    def release(self, note: int) -> None:
        self._emit(mido.Message("note_off", channel=self.channel, note=note, velocity=0))

    def bend(self, pitch: int) -> None:
        self._emit(mido.Message("pitchwheel", channel=self.channel, pitch=pitch))

    def receive(self, message: Any) -> None:
        with self._lock:
            self.received.append(message)
            if message.type == "note_on":
                self.leds[message.note] = message.velocity
            elif message.type == "note_off":
                self.leds[message.note] = 0

    def unplug(self) -> None:
        self.plugged = False
        ports: list[FakeInput | FakeOutput] = [*self.inputs, *self.outputs]
        for port in ports:
            port.close()

    def plug_in(self) -> None:
        self.plugged = True


class FakeMidiBackend:
    """Stands in for `mido.Backend`. Lists and opens the simulated controller's ports."""

    def __init__(self, *controllers: SimulatedController) -> None:
        self.controllers = list(controllers)

    def _controller(self, name: str | None) -> SimulatedController:
        for controller in self.controllers:
            if controller.plugged and (name is None or name == controller.name):
                return controller
        raise OSError(f"unknown port {name!r}")

    def get_input_names(self) -> list[str]:
        return [controller.name for controller in self.controllers if controller.plugged]

    def get_output_names(self) -> list[str]:
        return [controller.name for controller in self.controllers if controller.plugged]

    def open_input(self, name: str | None = None, callback: Callable[[Any], None] | None = None, **_: Any) -> FakeInput:
        controller = self._controller(name)
        port = FakeInput(controller, controller.name, callback)
        controller.inputs.append(port)
        return port

    def open_output(self, name: str | None = None, **_: Any) -> FakeOutput:
        controller = self._controller(name)
        port = FakeOutput(controller, controller.name)
        controller.outputs.append(port)
        return port
