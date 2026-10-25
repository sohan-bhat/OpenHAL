"""A physical stop button on a Raspberry Pi GPIO input, for the hub's stop command.

The hub wires this to `Kernel.stop_all`. This module only watches the pin and calls back. It
never decides anything and never changes an output.

    from openhal.drivers.rpi_gpio import watch_stop_button

    button = watch_stop_button(27, lambda: hub.stop("stop button"), loop=asyncio.get_running_loop())
    ...
    button.close()

Wiring. A normally open push button between the GPIO pin and ground, with the Pi's internal
pull-up (the default). A latching mushroom-head e-stop with a normally closed contact is better
for real machines. Use `pull_up=False` and `active_state` to match the wiring, and keep the
hardware e-stop that cuts power. This button only asks the hub to stop.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from typing import Any


class StopButton:
    """A running watch. `close()` releases the pin."""

    def __init__(self, button: Any) -> None:
        self._button = button

    @property
    def pressed(self) -> bool:
        return bool(self._button.is_pressed)

    def close(self) -> None:
        self._button.close()


def watch_stop_button(
    pin: int,
    on_press: Callable[[], Any],
    *,
    pull_up: bool | None = True,
    active_state: bool | None = None,
    bounce_s: float | None = 0.05,
    loop: asyncio.AbstractEventLoop | None = None,
    pin_factory: Any = None,
) -> StopButton:
    """Call `on_press` each time the button on BCM `pin` is pressed.

    gpiozero calls back on its own thread. Pass the hub's event loop as `loop` and `on_press` runs
    on that loop instead. A coroutine function is scheduled as a task. Without `loop`, `on_press`
    runs on gpiozero's thread and must be thread safe.
    """
    if not 0 <= pin <= 27:
        raise ValueError(f"GPIO {pin} is not on the 40-pin header. Use a BCM number from 0 to 27.")
    from gpiozero import Button  # type: ignore[import-untyped]

    def pressed() -> None:
        if loop is None:
            on_press()
            return
        if inspect.iscoroutinefunction(on_press):
            asyncio.run_coroutine_threadsafe(on_press(), loop)
        else:
            loop.call_soon_threadsafe(on_press)

    button = Button(pin, pull_up=pull_up, active_state=active_state, bounce_time=bounce_s, pin_factory=pin_factory)
    button.when_pressed = pressed
    return StopButton(button)
