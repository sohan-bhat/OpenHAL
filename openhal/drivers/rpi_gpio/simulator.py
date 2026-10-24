"""The rpi-gpio simulator is gpiozero's own mock pin factory, with helpers for tests.

`gpiozero.pins.mock.MockFactory` with `MockPWMPin` pins simulates every pin on the header,
including PWM state, and lets tests drive inputs (`drive_low`, `drive_high`) and read what an
output pin is set to (`state`). It ships with gpiozero, so nothing here talks to real pins.
"""

from __future__ import annotations

from typing import Any


def mock_factory() -> Any:
    """A fresh mock pin factory with PWM-capable pins."""
    from gpiozero.pins.mock import MockFactory, MockPWMPin  # type: ignore[import-untyped]

    return MockFactory(pin_class=MockPWMPin)


def pin_state(factory: Any, number: int) -> float:
    """What a mock pin outputs right now. 0 or 1 for digital pins, the duty cycle for PWM, or the
    pulse width as a fraction of the frame for servos."""
    return float(factory.pin(number).state)


def press(factory: Any, number: int) -> None:
    """Pull an input low, as a button to ground does when pressed."""
    factory.pin(number).drive_low()


def release(factory: Any, number: int) -> None:
    """Let an input go high again."""
    factory.pin(number).drive_high()
