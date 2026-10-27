"""The two camera frames of the print babysitter demo, drawn as plain line drawings.

    uv run --extra uvc python -m openhal.demo.frames

writes examples/print-babysitter/frames/first-layer.jpg and come-loose.jpg. Drawing the frames
needs OpenCV, which comes with the uvc extra. Running the demo needs no OpenCV, since the simulated
printer webcam only serves the files (openhal/demo/webcam.py). The frames are demo frames in the
house diagram style of docs/DESIGN.md, never photos, with 1.5 px lines in the secondary text color
on the page background. The first shows a corner of the first layer lifting off the bed. The second shows the
print knocked over and filament piling up under the nozzle.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Final

WIDTH: Final = 640
HEIGHT: Final = 480
SCALE: Final = 4
LINE: Final = 6
"""Stroke width at SCALE, so 1.5 px in the frame."""
BACKGROUND: Final = (253, 252, 252)
SURFACE: Final = (247, 245, 244)
INK: Final = (97, 86, 79)
QUALITY: Final = 90
NAMES: Final = ("first-layer", "come-loose")

Point = tuple[float, float]


def _cv2() -> Any:
    import cv2

    return cv2


def _canvas() -> Any:
    import numpy

    return numpy.full((HEIGHT * SCALE, WIDTH * SCALE, 3), BACKGROUND, dtype=numpy.uint8)


def _points(points: list[Point]) -> Any:
    import numpy

    return numpy.array([[round(x * SCALE), round(y * SCALE)] for x, y in points], dtype=numpy.int32)


def _line(image: Any, points: list[Point], *, closed: bool = False) -> None:
    cv2 = _cv2()
    cv2.polylines(image, [_points(points)], closed, INK, LINE, cv2.LINE_AA)


def _fill(image: Any, points: list[Point], color: tuple[int, int, int] = SURFACE) -> None:
    cv2 = _cv2()
    cv2.fillPoly(image, [_points(points)], color, cv2.LINE_AA)


def _shape(image: Any, points: list[Point], color: tuple[int, int, int] = SURFACE) -> None:
    _fill(image, points, color)
    _line(image, points, closed=True)


def _bed(image: Any) -> None:
    _shape(image, [(150, 250), (490, 250), (590, 420), (50, 420)])
    _shape(image, [(50, 420), (590, 420), (590, 432), (50, 432)])
    for x in (120, 520):
        _line(image, [(x, 432), (x, 470)])


def _toolhead(image: Any, nozzle: Point) -> None:
    x, y = nozzle
    _line(image, [(40, y - 92), (600, y - 92)])
    _line(image, [(40, y - 80), (600, y - 80)])
    _shape(image, [(x - 42, y - 104), (x + 42, y - 104), (x + 42, y - 46), (x - 42, y - 46)], BACKGROUND)
    _shape(image, [(x - 16, y - 46), (x + 16, y - 46), (x + 16, y - 16), (x - 16, y - 16)], BACKGROUND)
    _shape(image, [(x - 9, y - 16), (x + 9, y - 16), (x, y)], BACKGROUND)


def _first_layer(image: Any) -> None:
    back_left, back_right, front_left = (232, 332), (400, 332), (214, 372)
    bend, bend_low = (340, 372), (340, 377)
    corner, corner_low = (438, 324), (438, 331)
    _shape(image, [front_left, bend, bend_low, (214, 377)])
    _shape(image, [bend, corner, corner_low, bend_low])
    _shape(image, [back_left, back_right, corner, bend, front_left])
    _fill(image, [bend_low, corner_low, (428, 377)], BACKGROUND)
    _line(image, [bend_low, (428, 377), corner_low])
    _toolhead(image, (262, 326))


def _strand(center: Point, radius: float, turns: float, start: float) -> list[Point]:
    steps = max(8, int(turns * 24))
    points = []
    for step in range(steps + 1):
        angle = start + 2 * math.pi * turns * step / steps
        wobble = 1 + 0.18 * math.sin(3.1 * angle)
        points.append((center[0] + radius * wobble * math.cos(angle), center[1] + 0.45 * radius * math.sin(angle)))
    return points


def _come_loose(image: Any) -> None:
    _shape(image, [(372, 318), (452, 296), (500, 368), (420, 392)])
    _shape(image, [(420, 392), (500, 368), (500, 382), (420, 406)])
    _shape(image, [(372, 318), (420, 392), (420, 406), (372, 332)])
    _line(image, [(395, 307), (444, 380)])
    _line(image, [(412, 302), (461, 375)])
    _line(image, [(430, 298), (479, 371)])
    nozzle = (262, 250)
    _toolhead(image, nozzle)
    _line(image, [nozzle, (258, 268), (266, 286), (256, 304), (264, 322), (258, 338)])
    for radius, turns, start in ((34, 1.6, 0.4), (26, 1.3, 2.1), (40, 1.1, 4.0), (20, 1.8, 1.0)):
        _line(image, _strand((262, 348), radius, turns, start))


def draw(name: str) -> Any:
    """One frame as a BGR image of WIDTH by HEIGHT pixels."""
    if name not in NAMES:
        raise ValueError(f"No demo frame named {name}. The frames are {', '.join(NAMES)}.")
    image = _canvas()
    _bed(image)
    if name == "first-layer":
        _first_layer(image)
    else:
        _come_loose(image)
    cv2 = _cv2()
    return cv2.resize(image, (WIDTH, HEIGHT), interpolation=cv2.INTER_AREA)


def folder() -> Path:
    """examples/print-babysitter/frames/ in this checkout."""
    return Path(__file__).resolve().parents[2] / "examples" / "print-babysitter" / "frames"


def main() -> None:
    cv2 = _cv2()
    target = folder()
    target.mkdir(parents=True, exist_ok=True)
    for name in NAMES:
        path = target / f"{name}.jpg"
        cv2.imwrite(str(path), draw(name), [int(cv2.IMWRITE_JPEG_QUALITY), QUALITY])
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
