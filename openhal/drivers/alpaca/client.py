"""A small ASCOM Alpaca REST client on httpx.

Written from the ASCOM Alpaca API reference (ascom-standards.org/api, "Alpaca Device API" and
"Alpaca Management API") and the Alpaca API documentation PDF.

- Device members live at `/api/v1/{device_type}/{device_number}/{member}`, lower case.
- Properties are read with GET and query parameters. Methods and property setters use PUT
  with form encoded parameters. Every request carries `ClientID` and `ClientTransactionID`.
- Replies are JSON with `Value`, `ErrorNumber`, `ErrorMessage`, `ClientTransactionID` and
  `ServerTransactionID`. An ASCOM error comes back as HTTP 200 with a non-zero ErrorNumber.
  HTTP 400 means the request itself was malformed, HTTP 500 a server fault.
- The management API at `/management/apiversions` and `/management/v1/...` describes the
  server and its configured devices. It works without connecting any device.
"""

from __future__ import annotations

import asyncio
import itertools
import secrets
from typing import Any, Final

from openhal.drivers.base import DriverError

NOT_IMPLEMENTED: Final = 0x400
INVALID_VALUE: Final = 0x401
VALUE_NOT_SET: Final = 0x402
NOT_CONNECTED: Final = 0x407
INVALID_WHILE_PARKED: Final = 0x408
INVALID_WHILE_SLAVED: Final = 0x409
INVALID_OPERATION: Final = 0x40B
ACTION_NOT_IMPLEMENTED: Final = 0x40C
OPERATION_CANCELLED: Final = 0x40E

ERROR_NAMES: Final[dict[int, str]] = {
    NOT_IMPLEMENTED: "not implemented by this device",
    INVALID_VALUE: "invalid value",
    VALUE_NOT_SET: "value not set yet",
    NOT_CONNECTED: "the device is not connected",
    INVALID_WHILE_PARKED: "not allowed while parked",
    INVALID_WHILE_SLAVED: "not allowed while slaved",
    INVALID_OPERATION: "not allowed in the current state",
    ACTION_NOT_IMPLEMENTED: "action not implemented",
    OPERATION_CANCELLED: "operation cancelled",
}


class AlpacaError(DriverError):
    """The device returned a non-zero ASCOM ErrorNumber."""

    def __init__(self, message: str, number: int) -> None:
        super().__init__(message)
        self.number = number


def error_name(number: int) -> str:
    if number in ERROR_NAMES:
        return ERROR_NAMES[number]
    if 0x500 <= number <= 0xFFF:
        return "a driver specific error"
    return "an unknown error"


class AlpacaClient:
    """One Alpaca server. Safe to share between devices on that server."""

    def __init__(self, base_url: str, *, timeout: float, transport: Any = None) -> None:
        import httpx

        self.base_url = base_url
        self.timeout = timeout
        self.client_id = secrets.randbelow(2**31 - 2) + 1
        self._ids = itertools.count(1)
        self._http = httpx.AsyncClient(base_url=base_url, timeout=timeout, transport=transport)

    def _ident(self) -> dict[str, str]:
        return {"ClientID": str(self.client_id), "ClientTransactionID": str(next(self._ids))}

    async def _request(self, method: str, path: str, params: dict[str, str] | None = None) -> Any:
        import httpx

        fields = {**self._ident(), **(params or {})}
        try:
            request = self._http.get(path, params=fields) if method == "GET" else self._http.put(path, data=fields)
            response = await asyncio.wait_for(request, self.timeout)
        except (httpx.TimeoutException, TimeoutError):
            raise TimeoutError(
                f"The Alpaca server sent no reply to {method} {path} within {self.timeout:g} s."
            ) from None
        except httpx.HTTPError as exc:
            raise DriverError(
                f"Could not reach the Alpaca server at {self.base_url} ({exc}). Check that it is running and reachable."
            ) from exc
        if response.status_code == 400:
            raise DriverError(
                f"The Alpaca server returned HTTP 400 for {method} {path} ({response.text.strip()[:200]})."
            )
        if response.status_code == 404:
            raise DriverError(f"The Alpaca server has no {path}. Check the device type and number.")
        if response.status_code >= 400:
            raise DriverError(f"The Alpaca server failed {method} {path} with HTTP {response.status_code}.")
        try:
            body = response.json()
        except ValueError:
            raise DriverError(f"The Alpaca server sent a reply to {path} that is not JSON.") from None
        if not isinstance(body, dict):
            raise DriverError(f"The Alpaca server sent a reply to {path} that is not a JSON object.")
        number = body.get("ErrorNumber", 0)
        if not isinstance(number, int) or isinstance(number, bool):
            raise DriverError(f"The Alpaca reply to {path} has an ErrorNumber that is not a number.")
        if number != 0:
            message = str(body.get("ErrorMessage", ""))[:300]
            raise AlpacaError(
                f"The device returned ASCOM error 0x{number:X} for {path.rsplit('/', 1)[-1]} "
                f"({error_name(number)}{', ' + message if message else ''}).",
                number,
            )
        return body

    async def get(self, path: str, params: dict[str, str] | None = None) -> Any:
        body = await self._request("GET", path, params)
        if "Value" not in body:
            raise DriverError(f"The Alpaca reply to {path} has no Value.")
        return body["Value"]

    async def put(self, path: str, params: dict[str, str] | None = None) -> Any:
        body = await self._request("PUT", path, params)
        return body.get("Value")

    async def close(self) -> None:
        await self._http.aclose()


def form(value: Any) -> str:
    """Alpaca form and query values. Booleans are True and False, numbers use repr precision."""
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        return repr(value)
    return str(value)
