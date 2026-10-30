"""The onvif driver's conformance case, against the simulated PTZ camera."""

from __future__ import annotations

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.onvif.driver import OnvifDriver
from openhal.drivers.onvif.simulator import HOST, PASSWORD, USERNAME, OnvifCameraSim
from openhal.spec import loads
from openhal.spec.models import DeviceFile

TOKEN_ENV = "OPENHAL_CONFORMANCE_ONVIF_PASSWORD"  # noqa: S105

CAMERA = """
read:
  manufacturer: { type: string }
  model: { type: string }
  stream_uri: { type: string }
  snapshot_uri: { type: string }
  moving: { type: bool }
write:
  pan: { unit: degree, min: -90, max: 90, map: { field: pan, scale: 170 } }
  tilt: { unit: dimensionless, min: -0.5, max: 0.5 }
  zoom: { unit: dimensionless, min: 0, max: 1 }
actions:
  move:
    args:
      pan: { unit: dimensionless, min: -0.5, max: 0.5 }
      tilt: { unit: dimensionless, min: -0.5, max: 0.5 }
      duration: { unit: s, min: 0.1, max: 2 }
  goto_preset: { args: { preset: { type: enum, values: ["1", "2"] } } }
  home: {}
  stop: {}
hazard: low
confirmed: { by: conformance, at: 2026-10-24 }
"""


def environ(name: str) -> str | None:
    """The environment the driver reads, with the simulator's password."""
    return PASSWORD if name == TOKEN_ENV else None


def device_file(*, channels: str = CAMERA, extra: str = "", timeout: str = "1 s") -> DeviceFile:
    connect = f"{{ onvif: {HOST}, username: {USERNAME}, token_env: {TOKEN_ENV}, timeout: {timeout}{extra} }}"
    return loads(f"device: Conformance camera\nid: conformance-onvif\nconnect: {connect}\n{channels}")


def case() -> ConformanceCase:
    camera = OnvifCameraSim()

    def make(file: DeviceFile) -> Driver:
        return OnvifDriver(file, transport=camera.transport(), environ=environ)

    async def broken(driver: Driver) -> None:
        camera.drop_next = 1

    async def slow(driver: Driver) -> None:
        camera.latency_s = 3.0

    async def cleanup() -> None:
        camera.latency_s = 0.0

    return ConformanceCase(
        name="onvif", file=device_file(), make=make, break_connection=broken, make_slow=slow, cleanup=cleanup
    )
