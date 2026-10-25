"""An ASCOM Alpaca server simulator on an httpx mock transport, and a discovery responder.

It follows the Alpaca Device and Management API reference (ascom-standards.org/api). The devices
are in `sim_devices.py`, each device number 0. GET parameter names are matched without case,
PUT form names must match the reference exactly. Errors use the ASCOM numbers in HTTP 200
replies, and malformed requests get HTTP 400.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import json
from typing import Any
from urllib.parse import parse_qsl

from openhal.drivers.alpaca.sim_devices import (
    BadRequest,
    Camera,
    Dome,
    Focuser,
    SimDevice,
    SimError,
    Switch,
    Telescope,
)

__all__ = ["AlpacaSim", "BadRequest", "DiscoveryResponder", "SimError"]


class AlpacaSim:
    """One simulated Alpaca server with five devices. Fault hooks are attributes."""

    def __init__(self, *, port: int = 11111) -> None:
        self.port = port
        self.time_scale = 1.0
        self.latency_s = 0.0
        self.fail_next = 0
        self.down = False
        self.malformed_next = 0
        self.server_error_next = 0
        self.requests: list[tuple[str, str, dict[str, str]]] = []
        self._transactions = itertools.count(1)
        self.telescope = Telescope(self)
        self.focuser = Focuser(self)
        self.camera = Camera(self)
        self.switch = Switch(self)
        self.dome = Dome(self)
        self.devices: dict[tuple[str, int], SimDevice] = {
            (device.kind, 0): device for device in (self.telescope, self.focuser, self.camera, self.switch, self.dome)
        }

    def http_transport(self) -> Any:
        import httpx

        return httpx.MockTransport(self._handle)

    def puts(self, member: str) -> list[dict[str, str]]:
        """The form fields of every PUT to a member, for assertions."""
        return [params for method, path, params in self.requests if method == "PUT" and path.endswith("/" + member)]

    async def _handle(self, request: Any) -> Any:
        import httpx

        if self.latency_s:
            await asyncio.sleep(self.latency_s)
        if self.down or self.fail_next > 0:
            self.fail_next = max(0, self.fail_next - 1)
            raise httpx.ConnectError("connection refused", request=request)
        if request.method == "GET":
            params = {key.lower(): value for key, value in request.url.params.items()}
        else:
            params = dict(parse_qsl(request.content.decode("ascii"), keep_blank_values=True))
        self.requests.append((request.method, request.url.path, params))
        if self.malformed_next > 0:
            self.malformed_next -= 1
            return httpx.Response(200, text="<html>not json</html>")
        if self.server_error_next > 0:
            self.server_error_next -= 1
            return httpx.Response(500, text="internal error")
        client_tx = params.get("clienttransactionid") or params.get("ClientTransactionID") or "0"
        try:
            value = self._route(request.method, request.url.path, params)
        except BadRequest as exc:
            return httpx.Response(400, text=str(exc))
        except LookupError as exc:
            return httpx.Response(404, text=str(exc))
        except SimError as exc:
            return self._reply(None, client_tx, exc.number, str(exc))
        return self._reply(value, client_tx, 0, "")

    def _reply(self, value: Any, client_tx: str, number: int, message: str) -> Any:
        import httpx

        body: dict[str, Any] = {
            "ClientTransactionID": int(client_tx) if client_tx.isdigit() else 0,
            "ServerTransactionID": next(self._transactions),
            "ErrorNumber": number,
            "ErrorMessage": message,
        }
        if value is not None or number == 0:
            body["Value"] = value
        return httpx.Response(200, content=json.dumps(body).encode(), headers={"Content-Type": "application/json"})

    def _route(self, method: str, path: str, params: dict[str, str]) -> Any:
        parts = [part for part in path.lower().split("/") if part]
        if parts[:2] == ["management", "apiversions"]:
            return [1]
        if parts[:3] == ["management", "v1", "description"]:
            return {
                "ServerName": "OpenHAL Alpaca simulator",
                "Manufacturer": "OpenHAL",
                "ManufacturerVersion": "1.0",
                "Location": "Test bench",
            }
        if parts[:3] == ["management", "v1", "configureddevices"]:
            return [
                {
                    "DeviceName": device.name,
                    "DeviceType": kind.capitalize(),
                    "DeviceNumber": number,
                    "UniqueID": f"sim-{kind}-{number}",
                }
                for (kind, number), device in self.devices.items()
            ]
        if len(parts) != 5 or parts[:2] != ["api", "v1"] or not parts[3].isdigit():
            raise LookupError(path)
        device = self.devices.get((parts[2], int(parts[3])))
        if device is None:
            raise LookupError(path)
        if method == "GET":
            return device.get(parts[4], params)
        if "ClientID" not in params or "ClientTransactionID" not in params:
            raise BadRequest("PUT needs ClientID and ClientTransactionID with the exact case")
        return device.put(parts[4], params)


class DiscoveryResponder(asyncio.DatagramProtocol):
    """Answers `alpacadiscovery1` with `{"AlpacaPort": port}`, like an Alpaca server on UDP 32227."""

    def __init__(self, alpaca_port: int) -> None:
        self.alpaca_port = alpaca_port
        self.transport: asyncio.DatagramTransport | None = None
        self.queries = 0

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        assert isinstance(transport, asyncio.DatagramTransport)
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]) -> None:
        if data.strip() == b"alpacadiscovery1" and self.transport is not None:
            self.queries += 1
            self.transport.sendto(json.dumps({"AlpacaPort": self.alpaca_port}).encode(), addr)

    @classmethod
    async def start(cls, alpaca_port: int) -> tuple[DiscoveryResponder, int]:
        loop = asyncio.get_running_loop()
        transport, protocol = await loop.create_datagram_endpoint(lambda: cls(alpaca_port), local_addr=("127.0.0.1", 0))
        return protocol, transport.get_extra_info("sockname")[1]

    def close(self) -> None:
        if self.transport is not None:
            with contextlib.suppress(Exception):
                self.transport.close()
