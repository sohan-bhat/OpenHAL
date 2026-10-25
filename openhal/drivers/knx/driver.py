"""KNX building automation through xknx, over KNXnet/IP tunneling (UDP or TCP) or routing.

Protocol. KNX devices talk in group telegrams. A group address such as `1/2/3` carries one value,
encoded by its datapoint type (DPT), such as 1.001 for on and off, 5.001 for percent or 9.001 for
a temperature. A KNXnet/IP interface or router puts the hub on the bus (KNX Standard 03.08,
KNXnet/IP), and xknx speaks that protocol.

How channels map to KNX.

- Every channel names a `group_address` and a `dpt`. Reads come from the newest
  GroupValueWrite or GroupValueResponse seen on the bus. When nothing has been seen since
  connecting, a read sends one GroupValueRead and waits `timeout` for the answer. An address
  whose read flag is off never answers, and reads as no value until a telegram arrives.
- A channel under `write` sends a GroupValueWrite. KNX actuators usually report their state on a
  separate status address, which `state_address` names. The driver reads that address, or the
  command address itself, and falls back to the last value it sent when neither answers.
- Values are converted from the DPT's unit to the channel unit, and rounded to the DPT's
  resolution. The reading a command returns shows the value as encoded.

Behavior worth knowing.

- Commands wait for the interface's data link confirmation (L_Data.con), which proves the
  telegram reached the bus, not that an actuator acted. Read the status address for that.
- xknx's own reconnect is off. A lost tunnel makes the device unavailable until the hub
  reconnects it, so nothing is replayed late.
- KNX has no emergency command of its own, so the device file's safe state is sent like any
  other telegram. KNX actuators have their own bus-voltage-failure behavior, which is the real
  fallback.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import time
from typing import Annotated, Any, ClassVar, Final, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, field_validator
from xknx import XKNX
from xknx.core.connection_state import XknxConnectionState
from xknx.dpt.dpt import DPTBase, DPTEnum, DPTNumeric
from xknx.dpt.dpt_16 import DPTString
from xknx.dpt.payload import DPTArray, DPTBinary
from xknx.exceptions import CommunicationError, ConversionError, XKNXException
from xknx.io import ConnectionConfig, ConnectionType
from xknx.telegram import GroupAddress, Telegram
from xknx.telegram.address import InternalGroupAddress
from xknx.telegram.apci import GroupValueRead, GroupValueResponse, GroupValueWrite

from openhal.drivers.base import Discovered, Driver, DriverError, DriverInfo, Health, Reading
from openhal.drivers.serial import mapping
from openhal.spec.models import DeviceFile, ReadChannel, WriteChannel
from openhal.spec.units import Quantity, UnitError, convert, parse_duration, parse_unit

GROUP: Final = re.compile(r"^\d{1,2}/\d{1,2}/\d{1,3}$|^\d{1,2}/\d{1,4}$|^\d{1,5}$")
CONNECTIONS: Final = {
    "tunneling": ConnectionType.TUNNELING,
    "tunneling_tcp": ConnectionType.TUNNELING_TCP,
    "routing": ConnectionType.ROUTING,
}


def _seconds(value: Any) -> Any:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return parse_duration(value)


Duration = Annotated[float, BeforeValidator(_seconds), Field(gt=0, le=60)]


def _group(value: str) -> str:
    text = str(value).strip()
    if not GROUP.match(text):
        raise ValueError(f"{value!r} is not a group address such as 1/2/3.")
    try:
        GroupAddress(text)
    except XKNXException as exc:
        raise ValueError(f"{value!r} is not a valid group address ({exc}).") from None
    return text


class KnxParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gateway: str = Field(min_length=1, max_length=253)
    port: int = Field(default=3671, ge=1, le=65535)
    connection: Literal["tunneling", "tunneling_tcp", "routing"] = "tunneling"
    local_ip: str | None = None
    individual_address: str | None = Field(default=None, pattern=r"^\d{1,2}\.\d{1,2}\.\d{1,3}$")
    route_back: bool = False
    timeout: Duration = 2.0


class ChannelMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    group_address: str
    dpt: str = Field(pattern=r"^\d{1,3}(\.\d{1,3})?$")
    state_address: str | None = None

    @field_validator("group_address", "state_address", mode="before")
    @classmethod
    def _address(cls, value: Any) -> Any:
        return None if value is None else _group(str(value))

    @field_validator("dpt", mode="before")
    @classmethod
    def _quoted(cls, value: Any) -> Any:
        if isinstance(value, int | float) and not isinstance(value, bool):
            raise ValueError(f'quote the DPT, as in dpt: "{value}", because YAML reads 5.010 as the number 5.01.')
        return value

    @property
    def transcoder(self) -> type[DPTBase]:
        found = DPTBase.parse_transcoder(self.dpt)
        if found is None:
            raise ValueError(f"xknx doesn't know DPT {self.dpt}.")
        return found

    @property
    def readback(self) -> str:
        return self.state_address or self.group_address


def _words(transcoder: type[DPTBase]) -> dict[str, Any]:
    if not issubclass(transcoder, DPTEnum):
        return {}
    return {member.name.lower(): member for member in transcoder.data_type}


def _is_bool(transcoder: type[DPTBase]) -> bool:
    return transcoder.payload_type is DPTBinary and transcoder.dpt_main_number == 1


class KnxDriver(Driver):
    """KNX group addresses as channels, through a KNXnet/IP interface or router."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="knx",
        protocols=("KNXnet/IP tunneling", "KNXnet/IP tunneling over TCP", "KNXnet/IP routing"),
        hazard_default="low",
        summary="KNX building automation group addresses, with datapoint types, through xknx.",
        safe_state_support="file",
        conformance="control",
    )
    params_model: ClassVar[type[Any] | None] = KnxParams

    def __init__(self, device: DeviceFile) -> None:
        super().__init__(device)
        self.settings = KnxParams.model_validate(device.connect.params)
        self.xknx: XKNX | None = None
        self.maps: dict[str, ChannelMap] = {}
        self._values: dict[str, tuple[Any, float]] = {}
        self._sent: dict[str, float | bool | str] = {}
        self._waiters: dict[str, asyncio.Event] = {}
        self._callback: Any = None
        if device.actions:
            raise DriverError("The knx driver has no actions. Model each group address as a channel.")
        specs: dict[str, ReadChannel | WriteChannel] = {**device.read, **device.write}
        for name, spec in specs.items():
            try:
                channel_map = ChannelMap.model_validate(spec.map or {})
                transcoder = channel_map.transcoder
            except (ValidationError, ValueError) as exc:
                problems = (
                    "; ".join(f"{'.'.join(map(str, e['loc'])) or 'map'}: {e['msg']}" for e in exc.errors())
                    if isinstance(exc, ValidationError)
                    else str(exc)
                )
                raise DriverError(
                    f"{name} needs a knx map with group_address and dpt, for example "
                    f"map: {{ group_address: 1/2/3, dpt: 9.001 }}. {problems}"
                ) from None
            self._check(name, spec, transcoder)
            self.maps[name] = channel_map

    @staticmethod
    def _check(name: str, spec: ReadChannel | WriteChannel, transcoder: type[DPTBase]) -> None:
        dpt = f"DPT {transcoder.dpt_main_number}.{transcoder.dpt_sub_number or 0:03d}"
        if spec.type == "bool":
            if not _is_bool(transcoder):
                raise DriverError(f"{name}: bool channels need a 1.x DPT, not {dpt}.")
        elif spec.type == "number":
            if not issubclass(transcoder, DPTNumeric):
                raise DriverError(f"{name}: {dpt} doesn't carry a number.")
            source = mapping.device_unit(transcoder.unit)
            if source and spec.unit and source != spec.unit:
                try:
                    convert(Quantity(1.0, parse_unit(source)), spec.unit)
                except UnitError:
                    raise DriverError(
                        f"{name}: {dpt} is in {transcoder.unit}, which doesn't convert to {spec.unit}."
                    ) from None
        elif spec.type == "enum":
            words = _words(transcoder)
            if _is_bool(transcoder) or not words:
                raise DriverError(f"{name}: {dpt} isn't an enum DPT such as 20.102.")
            unknown = [value for value in spec.values if value not in words]
            if unknown:
                raise DriverError(f"{name}: {dpt} has no {', '.join(unknown)}. It has {', '.join(words)}.")
        elif spec.type == "string":
            if not issubclass(transcoder, DPTString):
                raise DriverError(f"{name}: string channels need DPT 16, not {dpt}.")
        else:
            raise DriverError(f"{name}: KNX group addresses can't carry {spec.type} values.")

    @property
    def _where(self) -> str:
        if self.settings.connection == "routing":
            return f"KNX routing on {self.settings.gateway}"
        return f"KNX interface {self.settings.gateway}:{self.settings.port}"

    @classmethod
    async def discover(cls) -> list[Discovered]:
        """Search for KNXnet/IP interfaces with a SEARCH_REQUEST, which only asks them to describe themselves."""
        from xknx.io import GatewayScanner

        try:
            scanner = GatewayScanner(XKNX(), timeout_in_seconds=2.0)
            gateways = await asyncio.wait_for(scanner.scan(), 4.0)
        except (XKNXException, OSError, TimeoutError):
            return []
        return [
            Discovered(
                driver="knx",
                address=f"{gateway.ip_addr}:{gateway.port}",
                identifiers={"name": str(gateway.name), "individual_address": str(gateway.individual_address)},
                label=f"KNXnet/IP interface {gateway.name}",
            )
            for gateway in gateways
        ]

    async def identify(self) -> dict[str, str]:
        identity = {"gateway": self.settings.gateway, "connection": self.settings.connection}
        if self.xknx is not None and self.xknx.current_address.raw:
            identity["individual_address"] = str(self.xknx.current_address)
        return identity

    async def connect(self) -> None:
        await self.close()
        connection = CONNECTIONS[self.settings.connection]
        config = ConnectionConfig(
            connection_type=connection,
            gateway_ip=None if connection is ConnectionType.ROUTING else self.settings.gateway,
            gateway_port=self.settings.port,
            local_ip=self.settings.local_ip,
            route_back=self.settings.route_back,
            individual_address=self.settings.individual_address,
            multicast_group=self.settings.gateway if connection is ConnectionType.ROUTING else "224.0.23.12",
            auto_reconnect=False,
        )
        xknx = XKNX(connection_config=config)
        self._values.clear()
        self._sent.clear()
        try:
            await asyncio.wait_for(xknx.start(), self.settings.timeout + 3)
        except TimeoutError:
            with contextlib.suppress(Exception):
                await xknx.stop()
            raise TimeoutError(f"{self._where} did not accept a connection.") from None
        except (XKNXException, OSError) as exc:
            with contextlib.suppress(Exception):
                await xknx.stop()
            raise DriverError(f"Could not connect to {self._where} ({exc}). Check the address and port 3671.") from None
        addresses: list[GroupAddress | InternalGroupAddress] = [
            GroupAddress(address) for item in self.maps.values() for address in {item.group_address, item.readback}
        ]
        self._callback = xknx.telegram_queue.register_telegram_received_cb(self._telegram, group_addresses=addresses)
        self.xknx = xknx

    def _telegram(self, telegram: Telegram) -> None:
        if isinstance(telegram.payload, GroupValueWrite | GroupValueResponse):
            address = str(telegram.destination_address)
            self._values[address] = (telegram.payload.value, time.time())
            waiter = self._waiters.get(address)
            if waiter is not None:
                waiter.set()

    async def close(self) -> None:
        xknx, self.xknx = self.xknx, None
        if xknx is None:
            return
        if self._callback is not None:
            xknx.telegram_queue.unregister_telegram_received_cb(self._callback)
            self._callback = None
        with contextlib.suppress(Exception):
            await asyncio.wait_for(xknx.stop(), 5)

    def _open(self) -> XKNX:
        xknx = self.xknx
        if xknx is None:
            raise DriverError(f"{self._where} is not connected. Connect the device first.")
        if xknx.connection_manager.state is not XknxConnectionState.CONNECTED:
            raise DriverError(f"{self._where} lost the connection. Reconnect it.")
        return xknx

    async def health(self) -> Health:
        xknx = self.xknx
        if xknx is None:
            return Health(connected=False, detail=f"{self._where} not connected")
        state = xknx.connection_manager.state
        if state is not XknxConnectionState.CONNECTED:
            return Health(connected=False, detail=f"{self._where} {state.name.lower()}")
        return Health(connected=True, detail=self._where)

    async def _send(self, xknx: XKNX, telegram: Telegram, what: str) -> None:
        try:
            await asyncio.wait_for(xknx.cemi_handler.send_telegram(telegram), self.settings.timeout + 3)
        except TimeoutError:
            raise TimeoutError(f"{self._where} didn't confirm the {what} for {telegram.destination_address}.") from None
        except (CommunicationError, XKNXException) as exc:
            raise DriverError(
                f"{self._where} didn't put the {what} for {telegram.destination_address} on the bus ({exc})."
            ) from None

    async def _request(self, xknx: XKNX, address: str) -> None:
        """Send one GroupValueRead and wait up to `timeout` for the answer. No answer leaves the value unknown."""
        arrived = self._waiters.setdefault(address, asyncio.Event())
        try:
            await self._send(
                xknx, Telegram(destination_address=GroupAddress(address), payload=GroupValueRead()), "read"
            )
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(arrived.wait(), self.settings.timeout)
        finally:
            self._waiters.pop(address, None)

    async def read(self, channel: str) -> Reading:
        channel_map = self.maps.get(channel)
        if channel_map is None:
            raise DriverError(f"This knx device has no channel {channel!r}.")
        xknx = self._open()
        unit = self.device.channel_unit(channel)
        address = channel_map.readback
        if address not in self._values:
            await self._request(xknx, address)
        found = self._values.get(address)
        if found is None:
            return Reading(channel, self._sent.get(channel), unit=unit)
        payload, at = found
        spec = self.device.write.get(channel) or self.device.read[channel]
        value = self._decode(payload, spec, channel_map, f"{address} for {channel}")
        limits = getattr(spec, "range", None)
        suspect = bool(limits is not None and isinstance(value, float) and not limits[0] <= value <= limits[1])
        return Reading(channel, value, unit=unit, at=at, suspect=suspect)

    @staticmethod
    def _decode(
        payload: DPTBinary | DPTArray, spec: ReadChannel | WriteChannel, channel_map: ChannelMap, where: str
    ) -> Any:
        transcoder = channel_map.transcoder
        if spec.type == "bool":
            if not isinstance(payload, DPTBinary):
                raise DriverError(f"{where} carried {payload}, not a 1-bit value.")
            return bool(payload.value & 1)
        try:
            value = transcoder.from_knx(payload)
        except ConversionError as exc:
            raise DriverError(f"{where} carried {payload}, which is not DPT {channel_map.dpt} ({exc}).") from None
        if spec.type == "enum":
            word = getattr(value, "name", str(value)).lower()
            if word not in spec.values:
                raise DriverError(f"{where} reported {word!r}, which is not one of {', '.join(spec.values)}.")
            return word
        if spec.type == "string":
            return str(value)
        number = float(value)
        source = mapping.device_unit(transcoder.unit)
        if source and spec.unit and source != spec.unit:
            number = convert(Quantity(number, parse_unit(source)), spec.unit)
        return number

    def _encode(self, value: float | bool | str, spec: WriteChannel, channel_map: ChannelMap) -> tuple[Any, Any]:
        transcoder = channel_map.transcoder
        if spec.type == "bool":
            return DPTBinary(1 if value else 0), bool(value)
        if spec.type == "enum":
            payload = transcoder.to_knx(_words(transcoder)[str(value)])
            return payload, str(value)
        try:
            if spec.type == "string":
                return transcoder.to_knx(str(value)), str(value)
            number = float(value)
            source = mapping.device_unit(transcoder.unit)
            if source and spec.unit and source != spec.unit:
                number = convert(Quantity(number, parse_unit(spec.unit)), source)
            payload = transcoder.to_knx(number)
            sent = float(transcoder.from_knx(payload))
        except ConversionError as exc:
            raise DriverError(f"DPT {channel_map.dpt} can't carry {value!r} ({exc}). Nothing was sent.") from None
        if source and spec.unit and source != spec.unit:
            sent = convert(Quantity(sent, parse_unit(source)), spec.unit)
        return payload, sent

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        channel_map = self.maps.get(channel)
        if channel_map is None or channel not in self.device.write:
            raise DriverError(f"This knx device has no write channel {channel!r}.")
        xknx = self._open()
        payload, sent = self._encode(value, self.device.write[channel], channel_map)
        telegram = Telegram(
            destination_address=GroupAddress(channel_map.group_address), payload=GroupValueWrite(payload)
        )
        await self._send(xknx, telegram, "change")
        self._sent[channel] = sent
        if channel_map.state_address is None:
            self._values[channel_map.group_address] = (payload, time.time())
            return Reading(channel, sent, unit=self.device.channel_unit(channel))
        return None

    async def describe(self) -> dict[str, Any] | None:
        """KNX devices can't list their group addresses. The ETS project is the source of truth."""
        return None
