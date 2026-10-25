"""The rpi-gpio driver. Raspberry Pi GPIO pins, plus a stop button helper for the hub."""

from __future__ import annotations

NAME = "rpi-gpio"
ENTRY = "openhal.drivers.rpi_gpio.driver:RpiGpioDriver"

from openhal.drivers.rpi_gpio.stop_button import StopButton, watch_stop_button  # noqa: E402 (stdlib only)

__all__ = ["ENTRY", "NAME", "StopButton", "watch_stop_button"]
