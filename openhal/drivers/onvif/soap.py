"""A small SOAP 1.2 client for the ONVIF calls the driver uses, with WS-Security UsernameToken digests.

ONVIF services are SOAP 1.2 over HTTP (ONVIF Core Specification, section 5). Requests are
authenticated with a WS-Security UsernameToken whose password is a digest,
Base64(SHA-1(nonce + created + password)) (OASIS Web Services Security UsernameToken Profile 1.0).
Cameras reject a `Created` time far from their own clock, so the client keeps the offset from
GetSystemDateAndTime, which needs no authentication.

Replies are parsed with defusedxml, which refuses DTDs and entity expansion, because camera
replies are untrusted input. Elements are matched by local name, as ONVIF namespaces vary
between firmware versions.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import os
from typing import Any, Final
from xml.etree.ElementTree import Element
from xml.sax.saxutils import escape

import defusedxml.ElementTree as SafeET

SOAP: Final = "http://www.w3.org/2003/05/soap-envelope"
WSSE: Final = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
WSU: Final = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
DIGEST: Final = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest"
BASE64: Final = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary"
DEVICE: Final = "http://www.onvif.org/ver10/device/wsdl"
MEDIA: Final = "http://www.onvif.org/ver10/media/wsdl"
PTZ: Final = "http://www.onvif.org/ver20/ptz/wsdl"
SCHEMA: Final = "http://www.onvif.org/ver10/schema"


class SoapFaultError(Exception):
    """The camera answered with a SOAP fault."""

    def __init__(self, code: str, subcode: str, reason: str) -> None:
        super().__init__(f"{subcode or code}: {reason}".strip(": "))
        self.code = code
        self.subcode = subcode
        self.reason = reason

    @property
    def not_authorized(self) -> bool:
        return "NotAuthorized" in self.subcode or "FailedAuthentication" in self.subcode


def local(tag: str) -> str:
    """An element's name without its namespace."""
    return tag.rsplit("}", 1)[-1]


def find(element: Element | None, *path: str) -> Element | None:
    """The first descendant chain matching local names, such as find(body, "MediaUri", "Uri")."""
    current = element
    for name in path:
        if current is None:
            return None
        current = next((child for child in current.iter() if child is not current and local(child.tag) == name), None)
    return current


def text(element: Element | None, *path: str) -> str | None:
    found = find(element, *path)
    return found.text.strip() if found is not None and found.text is not None else None


def find_all(element: Element | None, name: str) -> list[Element]:
    if element is None:
        return []
    return [child for child in element.iter() if child is not element and local(child.tag) == name]


def digest(nonce: bytes, created: str, password: str) -> str:
    """The UsernameToken PasswordDigest."""
    return base64.b64encode(hashlib.sha1(nonce + created.encode() + password.encode()).digest()).decode()  # noqa: S324


def security_header(username: str, password: str, now: dt.datetime, nonce: bytes | None = None) -> str:
    """A wsse:Security header with a digest UsernameToken for one request."""
    nonce = nonce if nonce is not None else os.urandom(16)
    created = now.astimezone(dt.UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        f'<Security s:mustUnderstand="1" xmlns="{WSSE}"><UsernameToken>'
        f"<Username>{escape(username)}</Username>"
        f'<Password Type="{DIGEST}">{digest(nonce, created, password)}</Password>'
        f'<Nonce EncodingType="{BASE64}">{base64.b64encode(nonce).decode()}</Nonce>'
        f'<Created xmlns="{WSU}">{created}</Created>'
        "</UsernameToken></Security>"
    )


def envelope(body: str, header: str = "") -> str:
    """A SOAP 1.2 envelope around one request body."""
    head = f"<s:Header>{header}</s:Header>" if header else ""
    return (
        f'<?xml version="1.0" encoding="utf-8"?><s:Envelope xmlns:s="{SOAP}" '
        f'xmlns:tds="{DEVICE}" xmlns:trt="{MEDIA}" xmlns:tptz="{PTZ}" xmlns:tt="{SCHEMA}">'
        f"{head}<s:Body>{body}</s:Body></s:Envelope>"
    )


def parse(raw: bytes | str) -> Element:
    """The SOAP Body of a reply. Raises SoapFaultError for faults and ValueError for anything that isn't SOAP."""
    try:
        root = SafeET.fromstring(raw)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"the reply is not XML ({type(exc).__name__})") from None
    if local(root.tag) != "Envelope":
        raise ValueError("the reply is not a SOAP envelope")
    body = next((child for child in root if local(child.tag) == "Body"), None)
    if body is None:
        raise ValueError("the reply has no SOAP body")
    fault = find(body, "Fault")
    if fault is not None:
        code = text(fault, "Code", "Value") or ""
        subcode = text(fault, "Subcode", "Value") or ""
        reason = text(fault, "Reason", "Text") or text(fault, "faultstring") or ""
        raise SoapFaultError(code, subcode, reason)
    return body


def device_time(body: Element) -> dt.datetime | None:
    """The camera's UTC clock from a GetSystemDateAndTime reply."""
    utc = find(body, "UTCDateTime")
    if utc is None:
        return None
    try:
        year, month, day = (int(text(utc, "Date", name) or "") for name in ("Year", "Month", "Day"))
        hour, minute, second = (int(text(utc, "Time", name) or "") for name in ("Hour", "Minute", "Second"))
        return dt.datetime(year, month, day, hour, minute, second, tzinfo=dt.UTC)
    except ValueError:
        return None


def vector(pan: float | None, tilt: float | None, zoom: float | None) -> str:
    """A PTZVector, with PanTilt when pan or tilt is given and Zoom when zoom is."""
    parts = ""
    if pan is not None or tilt is not None:
        parts += f'<tt:PanTilt x="{0.0 if pan is None else pan:g}" y="{0.0 if tilt is None else tilt:g}"/>'
    if zoom is not None:
        parts += f'<tt:Zoom x="{zoom:g}"/>'
    return parts


def attribute(element: Element | None, name: str) -> float | None:
    if element is None or element.get(name) is None:
        return None
    try:
        return float(element.get(name, ""))
    except ValueError:
        return None


def call(service: str, name: str, inner: str = "") -> str:
    """One request body element, such as <tptz:Stop>...</tptz:Stop>."""
    prefix = {DEVICE: "tds", MEDIA: "trt", PTZ: "tptz"}[service]
    return f"<{prefix}:{name}>{inner}</{prefix}:{name}>"


def element(name: str, value: Any) -> str:
    return f"<{name}>{escape(str(value))}</{name}>"
