"""WS-Discovery for ONVIF cameras. One Probe for NetworkVideoTransmitter devices, then the ProbeMatches.

A Probe is a SOAP 1.2 message sent over UDP to 239.255.255.250:3702 (OASIS WS-Discovery 1.1,
ONVIF Core Specification section 7.3). It only asks devices to say where their device service is,
so it changes nothing. Each ProbeMatch carries XAddrs (the device service URLs) and Scopes such as
`onvif://www.onvif.org/name/Garage` and `onvif://www.onvif.org/hardware/C6CN`.
"""

from __future__ import annotations

import asyncio
import contextlib
import socket
import uuid
from typing import Final
from urllib.parse import unquote, urlsplit

from openhal.drivers.base import Discovered
from openhal.drivers.onvif import soap

GROUP = "239.255.255.250"
PORT = 3702
LISTEN_S = 2.0
WSD: Final = "http://schemas.xmlsoap.org/ws/2005/04/discovery"
WSA: Final = "http://schemas.xmlsoap.org/ws/2004/08/addressing"
TYPES: Final = "http://www.onvif.org/ver10/network/wsdl"


def probe(message_id: str | None = None) -> bytes:
    """A WS-Discovery Probe for ONVIF NetworkVideoTransmitter devices."""
    ident = message_id or f"uuid:{uuid.uuid4()}"
    return (
        f'<?xml version="1.0" encoding="utf-8"?><s:Envelope xmlns:s="{soap.SOAP}" xmlns:a="{WSA}" '
        f'xmlns:d="{WSD}" xmlns:dn="{TYPES}"><s:Header>'
        f"<a:Action>{WSD}/Probe</a:Action><a:MessageID>{ident}</a:MessageID>"
        "<a:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</a:To></s:Header>"
        "<s:Body><d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe></s:Body></s:Envelope>"
    ).encode()


def parse_matches(raw: bytes) -> list[Discovered]:
    """Cameras from one ProbeMatches message. Anything else gives an empty list."""
    try:
        body = soap.parse(raw)
    except (ValueError, soap.SoapFaultError):
        return []
    found: list[Discovered] = []
    for match in soap.find_all(body, "ProbeMatch"):
        xaddrs = (soap.text(match, "XAddrs") or "").split()
        if not xaddrs:
            continue
        scopes = (soap.text(match, "Scopes") or "").split()
        identifiers = {"xaddr": xaddrs[0]}
        for scope in scopes:
            for key in ("name", "hardware", "location"):
                prefix = f"onvif://www.onvif.org/{key}/"
                if scope.startswith(prefix):
                    identifiers[key] = unquote(scope[len(prefix) :])
        host = urlsplit(xaddrs[0]).hostname or xaddrs[0]
        found.append(Discovered("onvif", host, identifiers, f"ONVIF camera {identifiers.get('name', host)}"))
    return found


async def search() -> list[Discovered]:
    """Send one Probe and collect the answers for LISTEN_S seconds."""
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    found: dict[str, Discovered] = {}
    try:
        sock.setblocking(False)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.bind(("", 0))
        await loop.sock_sendto(sock, probe(), (GROUP, PORT))
        deadline = loop.time() + LISTEN_S
        while (left := deadline - loop.time()) > 0:
            try:
                data, _ = await asyncio.wait_for(loop.sock_recvfrom(sock, 65535), left)
            except (TimeoutError, OSError):
                break
            for camera in parse_matches(data):
                found.setdefault(camera.identifiers["xaddr"], camera)
    except OSError:
        return list(found.values())
    finally:
        with contextlib.suppress(OSError):
            sock.close()
    return list(found.values())
