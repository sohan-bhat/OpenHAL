"""Turning HTTP answers and connection failures into results or client exceptions."""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import ValidationError

from openhal.client.calls import Call
from openhal.client.errors import (
    BadRequest,
    HubError,
    HubNotRunning,
    NotFound,
    NotSupported,
    OpenHALError,
    Refused,
    Unauthorized,
)
from openhal.client.settings import TokenSource

START_HINT = "Start it with openhald (or run openhal doctor to see what is wrong)."
_ROUTE_MISSING = {"Not Found", "Method Not Allowed"}


def headers_for(source: TokenSource) -> dict[str, str]:
    headers = {"User-Agent": "openhal-client", "Accept": "application/json"}
    if source.token:
        headers["Authorization"] = f"Bearer {source.token}"
    return headers


def transport_error(url: str, exc: httpx.TransportError) -> OpenHALError:
    if isinstance(exc, httpx.ConnectError | httpx.ConnectTimeout):
        return HubNotRunning(f"The hub is not running at {url}. {START_HINT}")
    if isinstance(exc, httpx.TimeoutException):
        return HubError(f"The hub at {url} did not answer in time. It may be busy talking to a slow device.")
    return HubError(f"Could not talk to the hub at {url} ({type(exc).__name__}).")


def _detail(response: httpx.Response) -> Any:
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip() or response.reason_phrase
    if isinstance(payload, dict) and "detail" in payload:
        return payload["detail"]
    return payload


def _validation_text(detail: Any) -> str:
    if not isinstance(detail, list):
        return str(detail)
    parts = []
    for item in detail:
        if isinstance(item, dict):
            where = ".".join(str(part) for part in item.get("loc", []) if part != "body")
            parts.append(f"{where} {item.get('msg', 'is invalid')}".strip())
    return "The hub could not read the request. " + ". ".join(parts) + "." if parts else str(detail)


def error_for(call: Call[Any], response: httpx.Response, source: TokenSource) -> OpenHALError:
    code = response.status_code
    detail = _detail(response)
    text = detail if isinstance(detail, str) else str(detail)
    if code == 401:
        if source.token is None:
            message = (
                f"No token was sent ({source.describe()}). Run openhal init to create the human token, "
                "or set OPENHAL_TOKEN."
            )
        else:
            message = f"The hub did not accept the token from {source.describe()}. {text}"
        return Unauthorized(message, status_code=code, detail=detail)
    if code in (404, 405) and text in _ROUTE_MISSING:
        return NotSupported(
            f"This hub has no {call.method} {call.path.split('?')[0]}. It is older than this client. "
            "Update openhal-hub and restart openhald.",
            status_code=code,
            detail=detail,
        )
    if code == 404:
        return NotFound(text, status_code=code, detail=detail)
    if code in (403, 409):
        return Refused(text, status_code=code, detail=detail)
    if code in (400, 422):
        return BadRequest(_validation_text(detail), status_code=code, detail=detail)
    return HubError(f"The hub failed with HTTP {code}. {text}", status_code=code, detail=detail)


def finish[T](call: Call[T], response: httpx.Response, source: TokenSource) -> T:
    if response.is_success:
        try:
            payload = response.json()
        except ValueError as exc:
            raise HubError(f"The hub sent an answer that is not JSON for {call.path}.") from exc
        try:
            return call.parse(payload)
        except ValidationError as exc:
            raise HubError(
                f"The hub's answer to {call.method} {call.path} has a shape this client does not know. "
                "Update the client or the hub so their versions match."
            ) from exc
    raise error_for(call, response, source)
