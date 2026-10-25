"""A simulated ONVIF PTZ camera behind an `httpx.MockTransport`, for tests and the conformance case.

`OnvifCameraSim` answers the SOAP 1.2 calls the driver makes on the device, media and PTZ
services, written from the ONVIF Core, Media and PTZ service specifications. Every call except
GetSystemDateAndTime needs a WS-Security UsernameToken whose digest matches the password and whose
Created time is within five minutes of the camera's clock, which can run ahead with `clock_skew`.

The camera has two profiles. `profile_1` (MainStream, H.264 1920x1080) has a PTZ configuration,
and `profile_2` (SubStream) has none. PTZ positions are in the generic spaces and stay inside
them. ContinuousMove integrates the velocity until its timeout or a Stop. Presets 1 (Door) and
2 (Driveway) and a home position exist.

Faults. `offline` refuses connections, `drop_next` drops that many requests, `latency_s` slows
answers, `fault_next` answers the next call with a SOAP fault, and `garbage` returns a body that isn't XML.
"""

from __future__ import annotations

import asyncio
import base64
import datetime as dt
import time
from xml.etree.ElementTree import Element

import defusedxml.ElementTree as SafeET
import httpx

from openhal.drivers.onvif import soap

HOST = "camera.local"
PASSWORD = "simulated-password"  # noqa: S105
USERNAME = "admin"
PRESETS = {"1": ("Door", (-0.5, 0.1, 0.0)), "2": ("Driveway", (0.6, -0.2, 0.3))}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class OnvifCameraSim:
    """Pass `sim.transport()` to the driver. Every SOAP call is kept in `calls` as (operation, body)."""

    def __init__(self, *, username: str = USERNAME, password: str = PASSWORD) -> None:
        self.username = username
        self.password = password
        self.pan, self.tilt, self.zoom = 0.0, 0.0, 0.0
        self.velocity: tuple[float, float, float] | None = None
        self.moving_until = 0.0
        self.moved_at = 0.0
        self.clock_skew = dt.timedelta(0)
        self.offline = False
        self.drop_next = 0
        self.latency_s = 0.0
        self.fault_next: str | None = None
        self.garbage = False
        self.calls: list[tuple[str, Element]] = []

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def now(self) -> dt.datetime:
        return dt.datetime.now(dt.UTC) + self.clock_skew

    def operations(self) -> list[str]:
        return [name for name, _ in self.calls]

    async def handle(self, request: httpx.Request) -> httpx.Response:
        if self.latency_s:
            await asyncio.sleep(self.latency_s)
        if self.drop_next:
            self.drop_next -= 1
            raise httpx.ConnectError("[Errno 54] Connection reset by peer", request=request)
        if self.offline:
            raise httpx.ConnectError("[Errno 64] Host is down", request=request)
        if request.method != "POST":
            return httpx.Response(405)
        if self.garbage:
            return httpx.Response(200, text="<<not xml")
        try:
            root = SafeET.fromstring(request.content)
        except Exception:  # noqa: BLE001
            return self._fault("Sender", "ter:WellFormed", "The request is not well formed", 400)
        body = next(child for child in root if soap.local(child.tag) == "Body")
        operation = soap.local(next(iter(body)).tag)
        self.calls.append((operation, body))
        if operation != "GetSystemDateAndTime" and not self._authorized(root):
            return self._fault("Sender", "ter:NotAuthorized", "Sender not Authorized", 400)
        if self.fault_next is not None:
            reason, self.fault_next = self.fault_next, None
            return self._fault("Receiver", "ter:Action", reason, 500)
        handler = getattr(self, f"_{operation}", None)
        if handler is None:
            return self._fault("Receiver", "ter:ActionNotSupported", f"{operation} is not supported", 500)
        if request.url.path.endswith("ptz_service") and soap.text(body, "ProfileToken") != "profile_1":
            return self._fault("Sender", "ter:NoPTZProfile", "The profile has no PTZ configuration", 400)
        try:
            reply = handler(body, f"{request.url.scheme}://{request.url.host}")
        except KeyError:
            return self._fault("Sender", "ter:NoToken", "The preset token does not exist", 400)
        return httpx.Response(200, headers={"Content-Type": "application/soap+xml"}, text=soap.envelope(reply))

    def _authorized(self, root: Element) -> bool:
        header = next((child for child in root if soap.local(child.tag) == "Header"), None)
        token = soap.find(header, "UsernameToken")
        if token is None or soap.text(token, "Username") != self.username:
            return False
        try:
            nonce = base64.b64decode(soap.text(token, "Nonce") or "")
            created_text = soap.text(token, "Created") or ""
            created = dt.datetime.strptime(created_text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.UTC)
        except ValueError:
            return False
        if abs(created - self.now()) > dt.timedelta(minutes=5):
            return False
        return soap.text(token, "Password") == soap.digest(nonce, created_text, self.password)

    def _fault(self, code: str, subcode: str, reason: str, status: int) -> httpx.Response:
        fault = (
            f"<s:Fault><s:Code><s:Value>s:{code}</s:Value><s:Subcode><s:Value>{subcode}</s:Value></s:Subcode></s:Code>"
            f'<s:Reason><s:Text xml:lang="en">{reason}</s:Text></s:Reason></s:Fault>'
        )
        body = soap.envelope(fault).replace(
            "<s:Envelope ", '<s:Envelope xmlns:ter="http://www.onvif.org/ver10/error" ', 1
        )
        return httpx.Response(status, headers={"Content-Type": "application/soap+xml"}, text=body)

    def _GetSystemDateAndTime(self, body: Element, base: str) -> str:  # noqa: N802
        now = self.now()
        return (
            "<tds:GetSystemDateAndTimeResponse><tds:SystemDateAndTime><tt:DateTimeType>NTP</tt:DateTimeType>"
            "<tt:DaylightSavings>false</tt:DaylightSavings><tt:UTCDateTime>"
            f"<tt:Time><tt:Hour>{now.hour}</tt:Hour><tt:Minute>{now.minute}</tt:Minute><tt:Second>{now.second}</tt:Second></tt:Time>"
            f"<tt:Date><tt:Year>{now.year}</tt:Year><tt:Month>{now.month}</tt:Month><tt:Day>{now.day}</tt:Day></tt:Date>"
            "</tt:UTCDateTime></tds:SystemDateAndTime></tds:GetSystemDateAndTimeResponse>"
        )

    def _GetDeviceInformation(self, body: Element, base: str) -> str:  # noqa: N802
        return (
            "<tds:GetDeviceInformationResponse><tds:Manufacturer>OpenHAL simulator</tds:Manufacturer>"
            "<tds:Model>PTZ-1</tds:Model><tds:FirmwareVersion>2.4.1</tds:FirmwareVersion>"
            "<tds:SerialNumber>SIM0001</tds:SerialNumber><tds:HardwareId>PTZ1-A</tds:HardwareId>"
            "</tds:GetDeviceInformationResponse>"
        )

    def _GetCapabilities(self, body: Element, base: str) -> str:  # noqa: N802
        return (
            "<tds:GetCapabilitiesResponse><tds:Capabilities>"
            f"<tt:Device><tt:XAddr>{base}/onvif/device_service</tt:XAddr></tt:Device>"
            f"<tt:Media><tt:XAddr>{base}/onvif/media_service</tt:XAddr></tt:Media>"
            f"<tt:PTZ><tt:XAddr>{base}/onvif/ptz_service</tt:XAddr></tt:PTZ>"
            "</tds:Capabilities></tds:GetCapabilitiesResponse>"
        )

    def _GetProfiles(self, body: Element, base: str) -> str:  # noqa: N802
        def profile(token: str, name: str, width: int, height: int, ptz: bool) -> str:
            config = (
                '<tt:PTZConfiguration token="ptz_config"><tt:Name>PTZ</tt:Name></tt:PTZConfiguration>' if ptz else ""
            )
            return (
                f'<trt:Profiles token="{token}" fixed="true"><tt:Name>{name}</tt:Name>'
                f"<tt:VideoEncoderConfiguration><tt:Encoding>H264</tt:Encoding><tt:Resolution><tt:Width>{width}</tt:Width>"
                f"<tt:Height>{height}</tt:Height></tt:Resolution></tt:VideoEncoderConfiguration>{config}</trt:Profiles>"
            )

        return (
            "<trt:GetProfilesResponse>"
            + profile("profile_1", "MainStream", 1920, 1080, True)
            + profile("profile_2", "SubStream", 640, 360, False)
            + "</trt:GetProfilesResponse>"
        )

    def _GetStreamUri(self, body: Element, base: str) -> str:  # noqa: N802
        token = soap.text(body, "ProfileToken")
        return (
            f"<trt:GetStreamUriResponse><trt:MediaUri><tt:Uri>rtsp://{HOST}:554/stream/{token}</tt:Uri>"
            "<tt:InvalidAfterConnect>false</tt:InvalidAfterConnect><tt:Timeout>PT0S</tt:Timeout></trt:MediaUri>"
            "</trt:GetStreamUriResponse>"
        )

    def _GetSnapshotUri(self, body: Element, base: str) -> str:  # noqa: N802
        token = soap.text(body, "ProfileToken")
        uri = f"<trt:MediaUri><tt:Uri>{base}/snapshot/{token}.jpg</tt:Uri></trt:MediaUri>"
        return f"<trt:GetSnapshotUriResponse>{uri}</trt:GetSnapshotUriResponse>"

    def _settle(self) -> None:
        if self.velocity is None:
            return
        end = min(time.monotonic(), self.moving_until)
        elapsed = max(0.0, end - self.moved_at)
        pan_speed, tilt_speed, zoom_speed = self.velocity
        self.pan = _clamp(self.pan + pan_speed * elapsed * 0.5, -1, 1)
        self.tilt = _clamp(self.tilt + tilt_speed * elapsed * 0.5, -1, 1)
        self.zoom = _clamp(self.zoom + zoom_speed * elapsed * 0.5, 0, 1)
        self.moved_at = end
        if time.monotonic() >= self.moving_until:
            self.velocity = None

    def _GetStatus(self, body: Element, base: str) -> str:  # noqa: N802
        self._settle()
        state = "MOVING" if self.velocity is not None else "IDLE"
        return (
            "<tptz:GetStatusResponse><tptz:PTZStatus><tt:Position>"
            f'<tt:PanTilt x="{self.pan:.4f}" y="{self.tilt:.4f}" '
            'space="http://www.onvif.org/ver10/tptz/PanTiltSpaces/PositionGenericSpace"/>'
            f'<tt:Zoom x="{self.zoom:.4f}" space="http://www.onvif.org/ver10/tptz/ZoomSpaces/PositionGenericSpace"/>'
            f"</tt:Position><tt:MoveStatus><tt:PanTilt>{state}</tt:PanTilt><tt:Zoom>{state}</tt:Zoom></tt:MoveStatus>"
            f"<tt:UtcTime>{self.now().strftime('%Y-%m-%dT%H:%M:%SZ')}</tt:UtcTime></tptz:PTZStatus></tptz:GetStatusResponse>"
        )

    def _axes(self, element: Element | None) -> tuple[float | None, float | None, float | None]:
        pan_tilt = soap.find(element, "PanTilt")
        return (
            soap.attribute(pan_tilt, "x"),
            soap.attribute(pan_tilt, "y"),
            soap.attribute(soap.find(element, "Zoom"), "x"),
        )

    def _AbsoluteMove(self, body: Element, base: str) -> str:  # noqa: N802
        self._settle()
        self.velocity = None
        pan, tilt, zoom = self._axes(soap.find(body, "Position"))
        self.pan = _clamp(pan, -1, 1) if pan is not None else self.pan
        self.tilt = _clamp(tilt, -1, 1) if tilt is not None else self.tilt
        self.zoom = _clamp(zoom, 0, 1) if zoom is not None else self.zoom
        return "<tptz:AbsoluteMoveResponse/>"

    def _RelativeMove(self, body: Element, base: str) -> str:  # noqa: N802
        self._settle()
        pan, tilt, zoom = self._axes(soap.find(body, "Translation"))
        self.pan = _clamp(self.pan + (pan or 0.0), -1, 1)
        self.tilt = _clamp(self.tilt + (tilt or 0.0), -1, 1)
        self.zoom = _clamp(self.zoom + (zoom or 0.0), 0, 1)
        return "<tptz:RelativeMoveResponse/>"

    def _ContinuousMove(self, body: Element, base: str) -> str:  # noqa: N802
        self._settle()
        pan, tilt, zoom = self._axes(soap.find(body, "Velocity"))
        timeout = (soap.text(body, "Timeout") or "PT1S").removeprefix("PT").removesuffix("S")
        self.velocity = (pan or 0.0, tilt or 0.0, zoom or 0.0)
        self.moved_at = time.monotonic()
        self.moving_until = self.moved_at + float(timeout)
        return "<tptz:ContinuousMoveResponse/>"

    def _Stop(self, body: Element, base: str) -> str:  # noqa: N802
        self._settle()
        self.velocity = None
        return "<tptz:StopResponse/>"

    def _GotoPreset(self, body: Element, base: str) -> str:  # noqa: N802
        token = soap.text(body, "PresetToken") or ""
        if token not in PRESETS:
            raise KeyError(token)
        self.velocity = None
        self.pan, self.tilt, self.zoom = PRESETS[token][1]
        return "<tptz:GotoPresetResponse/>"

    def _GotoHomePosition(self, body: Element, base: str) -> str:  # noqa: N802
        self.velocity = None
        self.pan = self.tilt = self.zoom = 0.0
        return "<tptz:GotoHomePositionResponse/>"

    def _GetPresets(self, body: Element, base: str) -> str:  # noqa: N802
        presets = "".join(
            f'<tptz:Preset token="{token}"><tt:Name>{name}</tt:Name></tptz:Preset>'
            for token, (name, _) in PRESETS.items()
        )
        return f"<tptz:GetPresetsResponse>{presets}</tptz:GetPresetsResponse>"
