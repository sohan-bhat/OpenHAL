"""The upnp driver's conformance case, against the fake media renderer."""

from __future__ import annotations

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.upnp.driver import UpnpDriver
from openhal.drivers.upnp.simulator import LOCATION, FakeRenderer
from openhal.spec import loads
from openhal.spec.models import DeviceFile

SPEAKER = """
read:
  transport_state:
    type: enum
    values: [STOPPED, PLAYING, PAUSED_PLAYBACK, TRANSITIONING, NO_MEDIA_PRESENT]
    map: { service: AVTransport, action: GetTransportInfo, args: { InstanceID: 0 }, output: CurrentTransportState }
write:
  volume:
    unit: percent
    min: 0
    max: 60
    map:
      service: RenderingControl
      action: SetVolume
      args: { InstanceID: 0, Channel: Master, DesiredVolume: "{value}" }
      state:
        service: RenderingControl
        action: GetVolume
        args: { InstanceID: 0, Channel: Master }
        output: CurrentVolume
  mute:
    type: bool
    map:
      service: RenderingControl
      action: SetMute
      args: { InstanceID: 0, Channel: Master, DesiredMute: "{value}" }
      state:
        service: RenderingControl
        action: GetMute
        args: { InstanceID: 0, Channel: Master }
        output: CurrentMute
actions:
  play: { map: { service: AVTransport, action: Play, args: { InstanceID: 0, Speed: "1" } } }
  stop: { map: { service: AVTransport, action: Stop, args: { InstanceID: 0 } } }
safe_state:
  - { action: stop }
  - { volume: 0 }
hazard: low
confirmed: { by: conformance, at: 2026-10-24 }
"""


def device_file(*, channels: str = SPEAKER, timeout: str = "1 s") -> DeviceFile:
    connect = f"{{ upnp: {LOCATION}, timeout: {timeout} }}"
    return loads(f"device: Conformance speaker\nid: conformance-upnp\nconnect: {connect}\n{channels}")


def case() -> ConformanceCase:
    renderer = FakeRenderer()

    def make(file: DeviceFile) -> Driver:
        return UpnpDriver(file, requester=renderer)

    async def broken(driver: Driver) -> None:
        renderer.drop_next = 1

    async def slow(driver: Driver) -> None:
        renderer.latency_s = 3.0

    async def cleanup() -> None:
        renderer.latency_s = 0.0

    return ConformanceCase(
        name="upnp", file=device_file(), make=make, break_connection=broken, make_slow=slow, cleanup=cleanup
    )
