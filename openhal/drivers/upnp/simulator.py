"""A fake UPnP media renderer behind async-upnp-client's requester interface, for tests and the conformance case.

`FakeRenderer` is an `UpnpRequester`. It answers HTTP requests the way a device does, with a
device description, two service descriptions (SCPD) and SOAP responses or SOAP faults, written
from UPnP Device Architecture 2.0 and the RenderingControl:1 and AVTransport:1 service templates.

- RenderingControl. GetVolume and SetVolume (Volume, ui2, 0 to 100), GetMute and SetMute.
- AVTransport. Play, Pause, Stop, Seek and GetTransportInfo with the TransportState values.

Faults. `unplugged` raises a connection error for every request, `drop_next` for that many requests,
`latency_s` slows answers,
`fault_next` answers the next action with that UPnP error code, and `garbage` returns a body that
isn't XML.
"""

from __future__ import annotations

import asyncio
from typing import Any
from xml.sax.saxutils import escape

import defusedxml.ElementTree as SafeET
from async_upnp_client.client import UpnpRequester
from async_upnp_client.const import HttpRequest, HttpResponse
from async_upnp_client.exceptions import UpnpConnectionError

BASE = "http://192.168.1.30:1400"
LOCATION = f"{BASE}/xml/device_description.xml"
RENDERING = "urn:schemas-upnp-org:service:RenderingControl:1"
TRANSPORT = "urn:schemas-upnp-org:service:AVTransport:1"
STATES = ("STOPPED", "PLAYING", "PAUSED_PLAYBACK", "TRANSITIONING", "NO_MEDIA_PRESENT")

DESCRIPTION = f"""<?xml version="1.0" encoding="utf-8"?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
  <specVersion><major>1</major><minor>0</minor></specVersion>
  <device>
    <deviceType>urn:schemas-upnp-org:device:MediaRenderer:1</deviceType>
    <friendlyName>Simulated speaker</friendlyName>
    <manufacturer>OpenHAL simulator</manufacturer>
    <modelName>MR-1</modelName>
    <UDN>uuid:5f9ec1b3-ed59-49d6-a2b1-0a1b2c3d4e5f</UDN>
    <serviceList>
      <service>
        <serviceType>{RENDERING}</serviceType>
        <serviceId>urn:upnp-org:serviceId:RenderingControl</serviceId>
        <SCPDURL>/xml/RenderingControl1.xml</SCPDURL>
        <controlURL>/MediaRenderer/RenderingControl/Control</controlURL>
        <eventSubURL>/MediaRenderer/RenderingControl/Event</eventSubURL>
      </service>
      <service>
        <serviceType>{TRANSPORT}</serviceType>
        <serviceId>urn:upnp-org:serviceId:AVTransport</serviceId>
        <SCPDURL>/xml/AVTransport1.xml</SCPDURL>
        <controlURL>/MediaRenderer/AVTransport/Control</controlURL>
        <eventSubURL>/MediaRenderer/AVTransport/Event</eventSubURL>
      </service>
    </serviceList>
  </device>
</root>"""


def _argument(name: str, direction: str, variable: str) -> str:
    return (
        f"<argument><name>{name}</name><direction>{direction}</direction>"
        f"<relatedStateVariable>{variable}</relatedStateVariable></argument>"
    )


def _action(name: str, *arguments: str) -> str:
    return f"<action><name>{name}</name><argumentList>{''.join(arguments)}</argumentList></action>"


def _variable(
    name: str, data_type: str, *, allowed: tuple[str, ...] = (), value_range: tuple[int, int] | None = None
) -> str:
    extra = ""
    if allowed:
        extra = (
            "<allowedValueList>"
            + "".join(f"<allowedValue>{value}</allowedValue>" for value in allowed)
            + "</allowedValueList>"
        )
    if value_range is not None:
        low, high = value_range
        extra = (
            f"<allowedValueRange><minimum>{low}</minimum><maximum>{high}</maximum><step>1</step></allowedValueRange>"
        )
    return f'<stateVariable sendEvents="no"><name>{name}</name><dataType>{data_type}</dataType>{extra}</stateVariable>'


def _scpd(actions: list[str], variables: list[str]) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?><scpd xmlns="urn:schemas-upnp-org:service-1-0">'
        "<specVersion><major>1</major><minor>0</minor></specVersion>"
        f"<actionList>{''.join(actions)}</actionList><serviceStateTable>{''.join(variables)}</serviceStateTable></scpd>"
    )


INSTANCE = _argument("InstanceID", "in", "A_ARG_TYPE_InstanceID")
CHANNEL = _argument("Channel", "in", "A_ARG_TYPE_Channel")
RENDERING_SCPD = _scpd(
    [
        _action("GetVolume", INSTANCE, CHANNEL, _argument("CurrentVolume", "out", "Volume")),
        _action("SetVolume", INSTANCE, CHANNEL, _argument("DesiredVolume", "in", "Volume")),
        _action("GetMute", INSTANCE, CHANNEL, _argument("CurrentMute", "out", "Mute")),
        _action("SetMute", INSTANCE, CHANNEL, _argument("DesiredMute", "in", "Mute")),
    ],
    [
        _variable("Volume", "ui2", value_range=(0, 100)),
        _variable("Mute", "boolean"),
        _variable("A_ARG_TYPE_Channel", "string", allowed=("Master",)),
        _variable("A_ARG_TYPE_InstanceID", "ui4"),
    ],
)
TRANSPORT_SCPD = _scpd(
    [
        _action("Play", INSTANCE, _argument("Speed", "in", "TransportPlaySpeed")),
        _action("Pause", INSTANCE),
        _action("Stop", INSTANCE),
        _action(
            "Seek",
            INSTANCE,
            _argument("Unit", "in", "A_ARG_TYPE_SeekMode"),
            _argument("Target", "in", "A_ARG_TYPE_SeekTarget"),
        ),
        _action(
            "GetTransportInfo",
            INSTANCE,
            _argument("CurrentTransportState", "out", "TransportState"),
            _argument("CurrentTransportStatus", "out", "TransportStatus"),
            _argument("CurrentSpeed", "out", "TransportPlaySpeed"),
        ),
    ],
    [
        _variable("TransportState", "string", allowed=STATES),
        _variable("TransportStatus", "string", allowed=("OK", "ERROR_OCCURRED")),
        _variable("TransportPlaySpeed", "string", allowed=("1",)),
        _variable("A_ARG_TYPE_SeekMode", "string", allowed=("TRACK_NR", "REL_TIME")),
        _variable("A_ARG_TYPE_SeekTarget", "string"),
        _variable("A_ARG_TYPE_InstanceID", "ui4"),
    ],
)
ENVELOPE = (
    '<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
    's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>{body}</s:Body></s:Envelope>'
)


class FakeRenderer(UpnpRequester):
    """A media renderer that answers what async-upnp-client sends. Every request is kept in `requests`."""

    def __init__(self) -> None:
        self.volume = 25
        self.mute = False
        self.state = "STOPPED"
        self.track = 1
        self.unplugged = False
        self.drop_next = 0
        self.latency_s = 0.0
        self.fault_next: int | None = None
        self.garbage = False
        self.requests: list[HttpRequest] = []
        self.calls: list[tuple[str, dict[str, str]]] = []

    async def async_http_request(self, http_request: HttpRequest) -> HttpResponse:
        self.requests.append(http_request)
        if self.latency_s:
            await asyncio.sleep(self.latency_s)
        if self.drop_next:
            self.drop_next -= 1
            raise UpnpConnectionError("Connection reset by peer")
        if self.unplugged:
            raise UpnpConnectionError("Cannot connect to host 192.168.1.30:1400")
        path = http_request.url.removeprefix(BASE)
        if http_request.method == "GET":
            documents = {
                "/xml/device_description.xml": DESCRIPTION,
                "/xml/RenderingControl1.xml": RENDERING_SCPD,
                "/xml/AVTransport1.xml": TRANSPORT_SCPD,
            }
            if path in documents:
                return HttpResponse(200, {"Content-Type": 'text/xml; charset="utf-8"'}, documents[path])
            return HttpResponse(404, {}, "Not Found")
        if http_request.method == "POST" and path.endswith("/Control"):
            return self._soap(path, http_request)
        return HttpResponse(405, {}, "Method Not Allowed")

    def _soap(self, path: str, http_request: HttpRequest) -> HttpResponse:
        if self.garbage:
            return HttpResponse(200, {}, "<<not xml")
        envelope = SafeET.fromstring(http_request.body or "")
        body = next(iter(envelope.find("{http://schemas.xmlsoap.org/soap/envelope/}Body") or []), None)
        if body is None:
            return self._fault(401, "Invalid Action")
        name = body.tag.rsplit("}", 1)[-1]
        args = {child.tag.rsplit("}", 1)[-1]: child.text or "" for child in body}
        self.calls.append((name, args))
        if self.fault_next is not None:
            code, self.fault_next = self.fault_next, None
            return self._fault(code, "Action Failed" if code == 501 else "Invalid Args")
        service = RENDERING if "RenderingControl" in path else TRANSPORT
        try:
            result = self._run(name, args)
        except KeyError:
            return self._fault(401, "Invalid Action")
        except ValueError:
            return self._fault(402, "Invalid Args")
        values = "".join(f"<{key}>{escape(str(value))}</{key}>" for key, value in result.items())
        reply = f'<u:{name}Response xmlns:u="{service}">{values}</u:{name}Response>'
        return HttpResponse(200, {"Content-Type": 'text/xml; charset="utf-8"'}, ENVELOPE.format(body=reply))

    def _run(self, name: str, args: dict[str, str]) -> dict[str, Any]:
        if args.get("InstanceID", "0") != "0":
            raise ValueError(args["InstanceID"])
        if name == "GetVolume":
            return {"CurrentVolume": self.volume}
        if name == "SetVolume":
            volume = int(args["DesiredVolume"])
            if not 0 <= volume <= 100:
                raise ValueError(volume)
            self.volume = volume
            return {}
        if name == "GetMute":
            return {"CurrentMute": 1 if self.mute else 0}
        if name == "SetMute":
            self.mute = args["DesiredMute"] in ("1", "true")
            return {}
        if name == "Play":
            self.state = "PLAYING"
            return {}
        if name == "Pause":
            self.state = "PAUSED_PLAYBACK" if self.state == "PLAYING" else self.state
            return {}
        if name == "Stop":
            self.state = "STOPPED"
            return {}
        if name == "Seek":
            if args.get("Unit") != "TRACK_NR" or not args.get("Target", "").isdigit():
                raise ValueError(args)
            self.track = int(args["Target"])
            return {}
        if name == "GetTransportInfo":
            return {"CurrentTransportState": self.state, "CurrentTransportStatus": "OK", "CurrentSpeed": "1"}
        raise KeyError(name)

    def _fault(self, code: int, description: str) -> HttpResponse:
        fault = (
            "<s:Fault><faultcode>s:Client</faultcode><faultstring>UPnPError</faultstring><detail>"
            f'<UPnPError xmlns="urn:schemas-upnp-org:control-1-0"><errorCode>{code}</errorCode>'
            f"<errorDescription>{description}</errorDescription></UPnPError></detail></s:Fault>"
        )
        return HttpResponse(500, {"Content-Type": 'text/xml; charset="utf-8"'}, ENVELOPE.format(body=fault))
