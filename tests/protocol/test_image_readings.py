"""Image readings travel as `{ mimeType, bytes, width, height, data }`, are capped in size and never logged."""

from __future__ import annotations

import base64
import json
import struct
import zlib

import httpx
import pytest

from openhal import images
from openhal.hub.hub import Hub
from openhal.protocol.log import NOT_KEPT
from openhal.spec import loads
from tests.protocol.conftest import Connect

CAM = """
device: Bed camera
id: cam
connect: { mock: cam }
read:
  frame: { type: image }
hazard: low
confirmed: { by: owner, at: 2026-10-24 }
"""
FRAME = {"device": "cam", "channel": "frame"}


def png(width: int, height: int) -> bytes:
    """A small gray PNG, written by hand so the test needs no imaging library."""

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    rows = b"".join(b"\x00" + b"\x80" * width for _ in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


def jpeg(width: int, height: int) -> bytes:
    cv2 = pytest.importorskip("cv2")
    numpy = pytest.importorskip("numpy")
    ok, buffer = cv2.imencode(".jpg", numpy.full((height, width, 3), 200, dtype=numpy.uint8))
    assert ok
    return bytes(buffer)


@pytest.fixture
async def camera(hub: Hub) -> dict[str, bytes]:
    await hub.add_and_start(loads(CAM))
    values: dict[str, bytes] = hub.kernel.devices["cam"].driver.values  # type: ignore[attr-defined]
    values["frame"] = png(64, 48)
    return values


def test_formats_and_sizes_come_from_the_header() -> None:
    small = png(64, 48)
    assert images.describe(small) == {"mimeType": "image/png", "bytes": len(small), "width": 64, "height": 48}
    photo = jpeg(320, 240)
    assert images.describe(photo) == {"mimeType": "image/jpeg", "bytes": len(photo), "width": 320, "height": 240}
    assert images.describe(b"not an image") == {
        "mimeType": "application/octet-stream",
        "bytes": 12,
        "width": None,
        "height": None,
    }
    assert base64.b64decode(images.value(photo)["data"]) == photo


def test_the_size_cap_names_the_limit_and_the_settings_to_lower() -> None:
    assert images.too_large(b"\xff\xd8\xff" + b"\x00" * 100, "cam.frame") is None
    reason = images.too_large(b"\xff\xd8\xff" + b"\x00" * (images.MAX_BYTES + 1), "cam.frame")
    assert reason is not None
    assert "cam.frame" in reason
    assert "2 MB limit" in reason
    assert "width, height or jpeg_quality" in reason


async def test_hal_read_sends_the_image_and_the_logs_keep_only_its_shape(
    transport: Connect, base_url: str, tokens: dict[str, str], hub: Hub, camera: dict[str, bytes]
) -> None:
    async with transport(tokens["reader"]) as rpc:
        await rpc.initialize()
        reading = await rpc.call("hal/read", FRAME)
    frame = camera["frame"]
    assert reading["value"] == {
        "mimeType": "image/png",
        "bytes": len(frame),
        "width": 64,
        "height": 48,
        "data": base64.b64encode(frame).decode("ascii"),
    }
    logged = hub.kernel.audit.entries(device="cam", event="read")[0]
    assert logged.status == "done"
    assert logged.body["details"]["value"] == {"mimeType": "image/png", "bytes": len(frame), "width": 64, "height": 48}
    assert base64.b64encode(frame).decode("ascii") not in json.dumps(logged.body)
    assert hub.kernel.audit.verify() == (True, None)
    async with httpx.AsyncClient(base_url=base_url, headers={"Authorization": f"Bearer {tokens['human']}"}) as http:
        messages = (await http.get("/v1/rpc/log")).json()
    results = [entry["message"].get("result") for entry in messages if entry["direction"] == "out"]
    sent = [result for result in results if isinstance(result, dict) and result.get("channel") == "frame"]
    assert sent[-1]["value"] == {**images.describe(frame), "data": NOT_KEPT}
    assert base64.b64encode(frame).decode("ascii") not in json.dumps(messages)


async def test_a_frame_over_the_cap_is_refused_with_its_reason(
    transport: Connect, tokens: dict[str, str], hub: Hub, camera: dict[str, bytes]
) -> None:
    camera["frame"] = b"\xff\xd8\xff" + b"\x00" * images.MAX_BYTES
    async with transport(tokens["reader"]) as rpc:
        await rpc.initialize()
        error = await rpc.error("hal/read", FRAME)
    assert (error["code"], error["data"]["name"]) == (-32020, "DRIVER_ERROR")
    assert "2 MB limit" in error["data"]["kernelMessage"]
    assert "jpeg_quality" in error["data"]["kernelMessage"]
    logged = hub.kernel.audit.entries(device="cam", event="read")[0]
    assert (logged.status, logged.code) == ("failed", "driver_error")
    assert logged.body["details"]["value"]["bytes"] == images.MAX_BYTES + 3
    assert "data" not in logged.body["details"]["value"]


async def test_rest_read_sends_the_same_shape(
    base_url: str, tokens: dict[str, str], hub: Hub, camera: dict[str, bytes]
) -> None:
    async with httpx.AsyncClient(base_url=base_url, headers={"Authorization": f"Bearer {tokens['reader']}"}) as http:
        body = (await http.post("/v1/read", json=FRAME)).json()
        view = (await http.get("/v1/devices/cam")).json()
    frame = camera["frame"]
    assert body["ok"] is True
    assert body["value"] == images.value(frame)
    assert body["bytes"] == len(frame)
    assert view["read"]["frame"]["value"] == images.describe(frame), "device views never carry the pixels"


def test_the_cli_shows_an_image_as_one_line() -> None:
    from openhal.cli._common import show
    from openhal.client import Image

    small = png(8, 6)
    assert show(Image.model_validate(images.value(small))) == f"image/png, 8 x 6, {len(small)} bytes"
