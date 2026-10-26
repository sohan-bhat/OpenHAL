"""The Arduino plant waterer (examples/plant-waterer/), the example `openhal demo --full` runs.

It is the lowest hazard example, so it also runs the driver writer tutorial, the first hardware
test and the sample `openhal init` installs. The simulated board runs `SPEED` times faster than
real time, so a 20 s watering takes half a second.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from openhal.demo.scenario import example

DEVICE: Final = "plant-waterer"
FILE_NAME: Final = "plant-waterer.hal.yaml"
FOLDER: Final = "plant-waterer"
SPEED: Final = 40.0


def example_file() -> Path:
    """The mock device file, examples/plant-waterer/mock/plant-waterer.hal.yaml."""
    return example(FOLDER, "mock", FILE_NAME)


def sketch(name: str) -> Path:
    """A file next to the sketch, such as plant-waterer.ino."""
    return example(FOLDER, name)
