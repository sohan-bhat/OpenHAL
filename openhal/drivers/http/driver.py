"""HTTP driver. Generic HTTP devices whose endpoints are described in the device file.

Protocol. Plain HTTP/1.1 requests through httpx (RFC 9110). Each read channel names a request
(method, path, query and an optional body) and how to find the value in the response, either a
JSON path into a JSON body or the whole body as text. Each write channel names a request and a
body or query template, and actions do the same with their arguments.

Quirks worth knowing.

- Many small devices reply slowly or drop connections under load, so every request has a hard
  deadline (`timeout`) enforced by the driver itself, not only by httpx.
- Some devices change state with GET requests (Shelly Gen1 `/relay/0?turn=on`). The driver
  allows GET for write channels because the device file sets it, and never sends a write on its
  own. Reads, identify, health and describe only ever send the requests the file names, plus a
  GET of `health` or `/`.
- Secrets never go in the device file. `token_env` names an environment variable whose value is
  sent in the `Authorization` header (or `auth_header`).
- There is no protocol-level safe state. The device file's safe state is applied through
  ordinary writes.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from collections.abc import Callable
from typing import Annotated, Any, ClassVar, Final, Literal
from urllib.parse import quote, urlsplit

import httpx
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, field_validator

from openhal.drivers.base import Discovered, Driver, DriverError, DriverInfo, Health, Reading
from openhal.drivers.http import values as v
from openhal.spec.models import DeviceFile, ReadChannel
from openhal.spec.units import parse_duration

_SECRET_HEADER: Final = re.compile(r"auth|cookie|token|secret|key|pass", re.IGNORECASE)
_MAX_DESCRIBED: Final = 64


def _seconds(value: Any) -> Any:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return parse_duration(value)


Duration = Annotated[float, BeforeValidator(_seconds), Field(gt=0, le=120)]
Scalar = str | int | float | bool


class HttpParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str
    timeout: Duration = 5.0
    headers: dict[str, str] = {}
    token_env: str | None = Field(default=None, pattern=r"^[A-Z_][A-Z0-9_]*$")
    auth_header: str = "Authorization"
    auth_scheme: str = "Bearer"
    verify_tls: bool = True
    health: str | None = None
    identify: str | None = None
    openapi: str | None = None
    max_response_bytes: int = Field(default=1_048_576, ge=1024, le=64 * 1_048_576)

    @field_validator("base_url")
    @classmethod
    def _url(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise ValueError("base_url must be an http:// or https:// URL, for example http://192.168.1.40")
        if parts.username or parts.password:
            raise ValueError("base_url must not carry credentials. Use token_env with an environment variable name.")
        return value.rstrip("/")

    @field_validator("headers")
    @classmethod
    def _no_secret_headers(cls, value: dict[str, str]) -> dict[str, str]:
        for name in value:
            if _SECRET_HEADER.search(name):
                raise ValueError(f"Header {name} looks like a credential. Put secrets in token_env, never the file.")
        return value

    @field_validator("health", "identify", "openapi")
    @classmethod
    def _path(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith("/"):
            raise ValueError("Paths start with /, for example /api/status.")
        return value


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    path: str
    query: dict[str, Scalar] = {}
    body: Any = None

    @field_validator("path")
    @classmethod
    def _path(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("path starts with /, for example /api/status.")
        return value


class ReadMap(_Request):
    method: Literal["GET", "POST"] = "GET"
    json_path: str | None = Field(default=None, alias="json")
    format: Literal["json", "text"] | None = None
    on: Scalar | list[Scalar] | None = None
    off: Scalar | list[Scalar] | None = None
    scale: float = 1.0
    offset: float = 0.0

    @field_validator("json_path")
    @classmethod
    def _json_path(cls, value: str | None) -> str | None:
        if value is not None:
            v.parse_path(value)
        return value

    @field_validator("scale")
    @classmethod
    def _scale(cls, value: float) -> float:
        if value == 0:
            raise ValueError("scale can't be zero.")
        return value


class WriteMap(_Request):
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "POST"
    on: Scalar | None = None
    off: Scalar | None = None
    scale: float = 1.0
    offset: float = 0.0
    state: ReadMap | None = None

    @field_validator("scale")
    @classmethod
    def _scale(cls, value: float) -> float:
        if value == 0:
            raise ValueError("scale can't be zero.")
        return value


class ActionMap(_Request):
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "POST"
    json_path: str | None = Field(default=None, alias="json")


def _map_error(where: str, exc: ValidationError) -> DriverError:
    problems = "; ".join(
        f"{'.'.join(str(part) for part in error['loc']) or where}: {error['msg']}" for error in exc.errors()
    )
    return DriverError(f"{where} has an invalid http map. {problems}")


class HttpDriver(Driver):
    """Generic HTTP device. Requests come from the device file, never from the driver itself."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="http",
        protocols=("HTTP/1.1 JSON and text APIs",),
        hazard_default="medium",
        summary="Generic HTTP devices, endpoints in the device file or proposed from an OpenAPI document.",
    )
    params_model: ClassVar[type[Any] | None] = HttpParams

    def __init__(
        self,
        device: DeviceFile,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        environ: Callable[[str], str | None] = os.environ.get,
    ) -> None:
        super().__init__(device)
        self.settings = HttpParams.model_validate(device.connect.params)
        self._transport = transport
        self._environ = environ
        self._client: httpx.AsyncClient | None = None
        self._last_ok: float | None = None
        self._written: dict[str, float | bool | str] = {}
        self.reads: dict[str, ReadMap] = {}
        self.writes: dict[str, WriteMap] = {}
        self.actions: dict[str, ActionMap] = {}
        for name, spec in device.read.items():
            self.reads[name] = self._parse(ReadMap, name, spec.map)
        for name, wspec in device.write.items():
            parsed = self._parse(WriteMap, name, wspec.map)
            unknown = v.placeholders([parsed.path, parsed.query, parsed.body]) - {"value"}
            if unknown:
                raise DriverError(f"write.{name} uses {sorted(unknown)} in its template. Only {{value}} is supported.")
            self.writes[name] = parsed
        for name, action in device.actions.items():
            amap = self._parse(ActionMap, name, action.map)
            unknown = v.placeholders([amap.path, amap.query, amap.body]) - set(action.args)
            if unknown:
                raise DriverError(f"actions.{name} uses {sorted(unknown)} in its template, which are not its args.")
            self.actions[name] = amap

    @staticmethod
    def _parse[M: BaseModel](model: type[M], name: str, raw: dict[str, Any] | None) -> M:
        if raw is None:
            raise DriverError(f"{name} needs a map with at least a path, for example map: {{ path: /api/status }}.")
        try:
            return model.model_validate(raw)
        except ValidationError as exc:
            raise _map_error(name, exc) from None

    @classmethod
    async def discover(cls) -> list[Discovered]:
        return []

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json, text/plain;q=0.9, */*;q=0.5", **self.settings.headers}
        if self.settings.token_env:
            secret = self._environ(self.settings.token_env)
            if not secret:
                raise DriverError(
                    f"The environment variable {self.settings.token_env} is not set. "
                    "Set it to the device's token before starting the hub."
                )
            scheme = self.settings.auth_scheme.strip()
            headers[self.settings.auth_header] = f"{scheme} {secret}" if scheme else secret
        return headers

    def _new_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.settings.base_url,
            headers=self._headers(),
            timeout=self.settings.timeout,
            verify=self.settings.verify_tls,
            transport=self._transport,
            follow_redirects=False,
        )

    async def connect(self) -> None:
        await self.close()
        client = self._new_client()
        try:
            await self._send(client, "GET", self.settings.health or "/", accept_any_status=True)
        except BaseException:
            await client.aclose()
            raise
        self._client = client

    async def close(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()

    async def health(self) -> Health:
        if self._client is None:
            return Health(connected=False, detail="not connected")
        started = time.monotonic()
        try:
            await self._send(self._client, "GET", self.settings.health or "/", accept_any_status=True)
        except (DriverError, TimeoutError) as exc:
            return Health(connected=False, detail=str(exc))
        return Health(connected=True, detail=self.settings.base_url, latency_ms=(time.monotonic() - started) * 1000)

    async def identify(self) -> dict[str, str]:
        identity = {"base_url": self.settings.base_url}
        if self.settings.identify is None:
            return identity
        client = self._client or self._new_client()
        try:
            response = await self._send(client, "GET", self.settings.identify)
            document = self._json(response, "identify")
        finally:
            if client is not self._client:
                await client.aclose()
        if isinstance(document, dict):
            for key, item in document.items():
                if isinstance(item, str | int | float | bool) and len(identity) < 32:
                    identity[str(key)[:64]] = v.show(item)[:200]
        return identity

    async def _send(
        self,
        client: httpx.AsyncClient,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: Any = None,
        accept_any_status: bool = False,
    ) -> httpx.Response:
        url = f"{self.settings.base_url}{path}"
        content = None if body is None else json.dumps(body, separators=(",", ":")).encode()
        headers = {"Content-Type": "application/json"} if content is not None else None
        try:
            response = await asyncio.wait_for(
                client.request(method, path, params=query or None, content=content, headers=headers),
                self.settings.timeout,
            )
        except (TimeoutError, httpx.TimeoutException):
            raise TimeoutError(
                f"{method} {url} got no reply within {self.settings.timeout:g} s. "
                "Check the device is powered and on the network, or raise timeout."
            ) from None
        except httpx.HTTPError as exc:
            raise DriverError(
                f"{method} {url} failed ({type(exc).__name__}: {exc}). Check base_url and that the device is reachable."
            ) from None
        self._last_ok = time.monotonic()
        if len(response.content) > self.settings.max_response_bytes:
            raise DriverError(f"{method} {url} returned {len(response.content)} bytes, more than max_response_bytes.")
        if not accept_any_status and response.status_code >= 400:
            excerpt = response.text[:200].strip()
            raise DriverError(
                f"{method} {url} returned {response.status_code} {response.reason_phrase}. "
                f"{excerpt!r}. Check the path and method in the channel map."
            )
        return response

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise DriverError(f"The http device at {self.settings.base_url} is not connected.")
        return self._client

    @staticmethod
    def _json(response: httpx.Response, where: str) -> Any:
        try:
            return response.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise DriverError(
                f"{where} needs JSON from {response.request.url.path} but got "
                f"{response.text[:80]!r}. Check the path, or set format: text in the map."
            ) from None

    async def read(self, channel: str) -> Reading:
        if channel in self.reads:
            spec = self.device.read[channel]
            value = await self._read_map(channel, self.reads[channel], spec.type, spec.values)
            return self._reading(channel, value, spec)
        if channel in self.writes:
            wspec = self.device.write[channel]
            state = self.writes[channel].state
            if state is None:
                return Reading(channel, self._written.get(channel), unit=wspec.unit)
            value = await self._read_map(channel, state, wspec.type, wspec.values)
            return Reading(channel, value, unit=wspec.unit)
        raise DriverError(f"This http device has no channel {channel!r}.")

    async def _read_map(self, channel: str, rmap: ReadMap, kind: str, allowed: list[str]) -> Any:
        client = self._require_client()
        response = await self._send(client, rmap.method, rmap.path, query=rmap.query, body=rmap.body)
        where = f"{rmap.method} {rmap.path} for {channel}"
        if kind == "image":
            return response.content
        fmt = rmap.format or ("json" if rmap.json_path else "text")
        raw: Any
        if fmt == "json":
            raw = self._json(response, where)
            if rmap.json_path:
                raw = v.extract(raw, v.parse_path(rmap.json_path), where)
        else:
            raw = response.text.strip()
        if kind == "number":
            return v.to_number(raw, where) * rmap.scale + rmap.offset
        if kind == "bool":
            return v.to_bool(raw, v.words(rmap.on, v.DEFAULT_ON), v.words(rmap.off, v.DEFAULT_OFF), where)
        text = v.to_text(raw)
        if kind == "enum" and text not in allowed:
            raise DriverError(f"{where} reported {text[:60]!r}, which is not one of {', '.join(allowed)}.")
        return text

    def _reading(self, channel: str, value: Any, spec: ReadChannel) -> Reading:
        suspect = False
        if spec.range is not None and isinstance(value, float):
            suspect = not spec.range[0] <= value <= spec.range[1]
        return Reading(channel, value, unit=spec.unit, suspect=suspect)

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        wmap = self.writes.get(channel)
        if wmap is None:
            raise DriverError(f"This http device has no write channel {channel!r}.")
        client = self._require_client()
        payload: Any = value
        if isinstance(value, bool):
            chosen = wmap.on if value else wmap.off
            payload = value if chosen is None else chosen
        elif isinstance(value, int | float):
            payload = v.device_number(value, wmap.scale, wmap.offset)
        values = {"value": payload}
        path = v.render_text(wmap.path, values, quote=lambda text: quote(text, safe=""))
        query = {key: v.show(item) for key, item in v.render(wmap.query, values).items()}
        body = v.render(wmap.body, values) if wmap.body is not None else None
        await self._send(client, wmap.method, path, query=query, body=body)
        self._written[channel] = value
        return Reading(channel, value, unit=self.device.channel_unit(channel))

    async def _action(self, name: str, args: dict[str, Any]) -> Any:
        amap = self.actions.get(name)
        if amap is None:
            raise DriverError(f"This http device has no action {name!r}.")
        client = self._require_client()
        path = v.render_text(amap.path, args, quote=lambda text: quote(text, safe=""))
        query = {key: v.show(item) for key, item in v.render(amap.query, args).items()}
        body = v.render(amap.body, args) if amap.body is not None else None
        response = await self._send(client, amap.method, path, query=query, body=body)
        if amap.json_path is None:
            return {"status": response.status_code}
        document = self._json(response, f"action {name}")
        return v.extract(document, v.parse_path(amap.json_path), f"action {name}")

    async def describe(self) -> dict[str, Any] | None:
        if self.settings.openapi is None:
            return None
        client = self._client or self._new_client()
        try:
            response = await self._send(client, "GET", self.settings.openapi)
            document = self._json(response, "describe")
        finally:
            if client is not self._client:
                await client.aclose()
        from openhal.drivers.http.openapi import describe_openapi

        return describe_openapi(document, limit=_MAX_DESCRIBED)
