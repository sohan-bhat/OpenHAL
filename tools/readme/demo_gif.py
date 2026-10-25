"""Draw the README demo GIF from docs/assets/demo-run.json, in light and dark variants.

    uv run python tools/readme/record_demo.py
    uv run --with fonttools --with brotli --with pillow python tools/readme/demo_gif.py

Ten seconds, looping. An agent asks for 150 %, the limit line shows it blocked at 100 % with the
kernel's own message, the agent asks for 60 %, it is granted, and the simulated room cools. Every
number and message comes from the recorded run. Only the fill sweep moves, as a readout update.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "docs" / "assets"
FONTS = ROOT / "design" / "fonts"
W, H, SCALE = 880, 304, 2
LEFT, RIGHT = 40, 40
FPS = 10

THEMES = {
    "light": {
        "bg": "#ffffff",
        "text": "#1F2328",
        "text2": "#59636E",
        "panel": "#F6F8FA",
        "border": "#D0D7DE",
        "red": "#B3261E",
        "green": "#276B43",
        "blue": "#2D5B8C",
        "track": "#D0D7DE",
    },
    "dark": {
        "bg": "#0d1117",
        "text": "#E6EDF3",
        "text2": "#9198A1",
        "panel": "#161B22",
        "border": "#30363D",
        "red": "#EE6B62",
        "green": "#5CB884",
        "blue": "#79A9DA",
        "track": "#3D444D",
    },
}
CAUTION, ON_CAUTION = "#F2B705", "#15181B"
FACES = {
    "label": "sofia-sans-condensed-latin-wght-normal.woff2",
    "text": "atkinson-hyperlegible-next-latin-wght-normal.woff2",
    "mono": "martian-mono-latin-wght-normal.woff2",
}
_cache: dict[tuple[str, int, int], ImageFont.FreeTypeFont] = {}
_tmp = Path(tempfile.mkdtemp())


def font(face: str, size: int, weight: int = 400) -> ImageFont.FreeTypeFont:
    key = (face, size, weight)
    if key not in _cache:
        target = _tmp / f"{face}-{weight}.ttf"
        if not target.exists():
            static = instancer.instantiateVariableFont(TTFont(FONTS / FACES[face]), {"wght": weight})
            static.flavor = None
            static.save(target)
        _cache[key] = ImageFont.truetype(str(target), size * SCALE)
    return _cache[key]


class Frame:
    def __init__(self, theme: dict[str, str]) -> None:
        self.t = theme
        self.image = Image.new("RGB", (W * SCALE, H * SCALE), theme["bg"])
        self.draw = ImageDraw.Draw(self.image)

    def s(self, *values: float) -> list[float]:
        return [value * SCALE for value in values]

    def rect(
        self, x: float, y: float, w: float, h: float, fill: str, outline: str | None = None, width: int = 1
    ) -> None:
        self.draw.rounded_rectangle(
            self.s(x, y, x + w, y + h), radius=3 * SCALE, fill=fill, outline=outline, width=width * SCALE
        )

    def text(
        self,
        value: str,
        x: float,
        y: float,
        face: str,
        size: int,
        fill: str,
        weight: int = 400,
        anchor: str = "ls",
        tracking: float = 0.0,
    ) -> float:
        loaded = font(face, size, weight)
        if not tracking:
            self.draw.text(self.s(x, y), value, font=loaded, fill=fill, anchor=anchor)
            return loaded.getlength(value) / SCALE
        cursor = x
        for char in value:
            self.draw.text(self.s(cursor, y), char, font=loaded, fill=fill, anchor=anchor)
            cursor += loaded.getlength(char) / SCALE + tracking * size
        return cursor - x

    def legend(self, value: str, x: float, y: float, fill: str | None = None) -> None:
        self.text(value.upper(), x, y, "label", 12, fill or self.t["text2"], 700, tracking=0.08)

    def line(self, x0: float, y0: float, x1: float, y1: float, fill: str, width: float = 2) -> None:
        self.draw.line(self.s(x0, y0, x1, y1), fill=fill, width=round(width * SCALE))

    def circle(self, cx: float, cy: float, r: float, fill: str | None, outline: str | None = None) -> None:
        self.draw.ellipse(self.s(cx - r, cy - r, cx + r, cy + r), fill=fill, outline=outline, width=2 * SCALE)

    def final(self) -> Image.Image:
        # Crop the side margins so the content lines up with the README's text column.
        cropped = self.image.crop((LEFT * SCALE, 0, (W - RIGHT) * SCALE, H * SCALE))
        return cropped.resize((W - LEFT - RIGHT, H), Image.LANCZOS)


TRACK_X, TRACK_W, TRACK_Y = 40, 560, 150


def gx(percent: float) -> float:
    return TRACK_X + percent * TRACK_W / 160


def draw(theme: dict[str, str], run: dict, state: dict) -> Image.Image:
    f = Frame(theme)
    t = theme
    dev = run["device_file"]
    f.legend("Demo fan", 40, 30, t["text"])
    f.text(f"{dev['id']}.hal.yaml   max {dev['max']:g} %   rate {dev['rate']} %/s", 128, 30, "mono", 12, t["text2"])

    # The agent's request
    f.rect(40, 48, 560, 40, t["panel"], t["border"])
    f.legend("Agent", 56, 73)
    request = state.get("request")
    if request:
        f.text(f"claude   write fan_speed = {request}", 112, 73, "mono", 13, t["text"])
    else:
        f.text("waiting for a request", 112, 73, "text", 14, t["text2"])

    # The gauge, with every mark labeled
    current = state["fill"]
    f.rect(TRACK_X, TRACK_Y - 5, TRACK_W, 10, t["track"])
    f.rect(TRACK_X, TRACK_Y - 5, gx(current) - TRACK_X, 10, t["blue"])
    f.line(gx(current), TRACK_Y - 12, gx(current), TRACK_Y + 12, t["blue"], 2)
    f.text(f"current {current:g} %", TRACK_X, TRACK_Y - 20, "mono", 12, t["blue"])
    limit = gx(dev["max"])
    f.line(limit, TRACK_Y - 40, limit, TRACK_Y + 16, t["red"], 3)
    flag = f.text("MAX 100 %", limit + 9, TRACK_Y - 25, "label", 13, ON_CAUTION, 700, tracking=0.08)
    f.rect(limit + 1.5, TRACK_Y - 40, flag + 15, 20, CAUTION)
    f.text("MAX 100 %", limit + 9, TRACK_Y - 25, "label", 13, ON_CAUTION, 700, tracking=0.08)
    if state.get("requested") == 150:
        x = gx(150)
        f.circle(x, TRACK_Y, 10, t["bg"], t["red"])
        f.line(x - 4, TRACK_Y - 4, x + 4, TRACK_Y + 4, t["red"])
        f.line(x + 4, TRACK_Y - 4, x - 4, TRACK_Y + 4, t["red"])
        f.text("requested 150 %", TRACK_X + TRACK_W, TRACK_Y + 32, "mono", 12, t["red"], anchor="rs")
    if state.get("requested") == 60:
        x = gx(60)
        f.text("requested 60 %", x, TRACK_Y + 32, "mono", 12, t["green"], anchor="ms")

    # Status plate, word and shape and color
    status = state.get("status")
    if status:
        request_data = run["requests"][0 if status == "blocked" else 1]
        color = t["red"] if status == "blocked" else t["green"]
        f.rect(40, 212, 560, 52, t["panel"], color, 2)
        cx, cy = 66, 238
        if status == "blocked":
            f.circle(cx, cy, 10, None, color)
            f.line(cx - 4, cy - 4, cx + 4, cy + 4, color)
            f.line(cx + 4, cy - 4, cx - 4, cy + 4, color)
            word = f"BLOCKED   {request_data['code']}"
        else:
            f.circle(cx, cy, 10, color)
            f.draw.line(f.s(cx - 4.5, cy, cx - 1, cy + 3.5, cx + 5, cy - 3.5), fill=t["panel"], width=2 * SCALE)
            word = "GRANTED"
        f.text(word, 88, 233, "label", 14, color, 700, tracking=0.08)
        f.text(request_data["message"], 88, 253, "mono", 11, t["text"])

    # Readouts
    f.rect(640, 48, 200, 216, t["panel"], t["border"])
    f.legend("Fan speed", 656, 76)
    value = f.text(f"{state['fan']:g}", 656, 116, "mono", 30, t["text"], 600)
    f.text("%", 656 + value + 6, 116, "label", 14, t["text2"], 700)
    f.legend("Temperature", 656, 160)
    value = f.text(f"{state['temp']:.1f}", 656, 200, "mono", 30, t["text"], 600)
    f.text("degC", 656 + value + 6, 200, "label", 14, t["text2"], 700)
    if state.get("cooling"):
        f.text("falling", 656, 230, "text", 13, t["text2"])
    f.text(
        "Simulated fan. Every decision and reading is recorded from a real OpenHAL hub run.",
        40,
        290,
        "text",
        13,
        t["text2"],
    )
    return f.final()


def timeline(run: dict) -> list[tuple[dict, int]]:
    """(state, milliseconds) pairs adding up to 10 s."""
    before, after = run["before"], run["after"]
    base = {"fill": before["fan_speed"], "fan": before["fan_speed"], "temp": before["temperature"]}
    steps: list[tuple[dict, int]] = [(dict(base), 1000)]
    steps.append(({**base, "request": "150 %", "requested": 150, "status": "blocked"}, 3000))
    steps.append(({**base, "request": "60 %", "requested": 60}, 800))
    sweep = 4
    for i in range(1, sweep + 1):
        fill = before["fan_speed"] + (60 - before["fan_speed"]) * i / sweep
        steps.append(({**base, "fill": fill, "request": "60 %", "requested": 60, "status": "granted"}, 50))
    granted = {"fill": 60, "fan": after[0]["fan_speed"], "request": "60 %", "status": "granted"}
    remaining = 10_000 - sum(ms for _, ms in steps)
    each = remaining // len(after)
    for sample in after:
        steps.append(({**granted, "temp": sample["temperature"], "cooling": True}, each))
    steps[-1] = (steps[-1][0], steps[-1][1] + 10_000 - sum(ms for _, ms in steps))
    return steps


def main() -> None:
    run = json.loads((ASSETS / "demo-run.json").read_text())
    for name, theme in THEMES.items():
        frames, durations = [], []
        for state, ms in timeline(run):
            frames.append(draw(theme, run, state).convert("P", palette=Image.ADAPTIVE, colors=192))
            durations.append(ms)
        target = ASSETS / f"demo-{name}.gif"
        frames[0].save(target, save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True)
        print(
            f"{target.name}  {target.stat().st_size / 1024:.0f} KB  {sum(durations) / 1000:g} s  {len(frames)} frames"
        )


if __name__ == "__main__":
    main()
