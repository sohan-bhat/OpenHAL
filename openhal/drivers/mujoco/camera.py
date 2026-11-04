"""Camera snapshots for the mujoco driver, rendered offscreen and sent as PNG (ADR 0021, Cameras).

A camera the MJCF model names becomes an image channel, read the way the uvc and rpi_camera
drivers read theirs, so an agent sees the frame through the same read tool. Rendering uses
`mujoco.Renderer`, which needs OpenGL. A machine with a display has it. A machine without one
sets MUJOCO_GL to egl or osmesa before the hub starts. A GL context belongs to the thread that
made it, so every render runs on one thread the camera owns, and the frame is read from one
whole physics step.
"""

from __future__ import annotations

import asyncio
import contextlib
import struct
import zlib
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

import mujoco
import numpy

from openhal.drivers.base import DriverError
from openhal.drivers.mujoco.simulator import World

RendererFactory = Callable[[Any, int, int], Any]
GL_HINT = (
    "Rendering needs OpenGL. On a machine without a display, set MUJOCO_GL to egl or osmesa before the hub starts."
)
SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class Shot:
    """One image channel, a camera of the model at a size in pixels."""

    camera: int
    name: str
    width: int
    height: int


def default_renderer(model: Any, height: int, width: int) -> Any:
    return mujoco.Renderer(model, height=height, width=width)


class Cameras:
    """Renders the model's cameras on a thread of its own, one renderer for each frame size."""

    def __init__(self, factory: RendererFactory = default_renderer) -> None:
        self._factory = factory
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="openhal-mujoco-camera")
        self._renderers: dict[tuple[int, int], Any] = {}

    async def snapshot(self, world: World, shot: Shot) -> bytes:
        """The camera's view of the world now, as PNG bytes."""
        return await asyncio.get_running_loop().run_in_executor(self._pool, self._render, world, shot)

    def _render(self, world: World, shot: Shot) -> bytes:
        size = (shot.width, shot.height)
        renderer = self._renderers.get(size)
        if renderer is None:
            try:
                renderer = self._factory(world.model, shot.height, shot.width)
            except Exception as exc:
                raise DriverError(f"Camera {shot.name} can't render ({type(exc).__name__}: {exc}). {GL_HINT}") from exc
            self._renderers[size] = renderer
        world.peek(lambda _model, data: renderer.update_scene(data, camera=shot.camera))
        return png(renderer.render())

    def _release(self) -> None:
        for renderer in self._renderers.values():
            with contextlib.suppress(Exception):
                renderer.close()
        self._renderers.clear()

    async def close(self) -> None:
        with contextlib.suppress(Exception):
            await asyncio.get_running_loop().run_in_executor(self._pool, self._release)
        self._pool.shutdown(wait=False)


def png(pixels: Any) -> bytes:
    """An RGB image as a PNG file, compressed with the standard library's zlib."""
    image = numpy.ascontiguousarray(pixels[:, :, :3], dtype=numpy.uint8)
    height, width = image.shape[:2]
    rows = numpy.zeros((height, width * 3 + 1), dtype=numpy.uint8)
    rows[:, 1:] = image.reshape(height, width * 3)
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        SIGNATURE + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(rows.tobytes(), 6)) + _chunk(b"IEND", b"")
    )


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
