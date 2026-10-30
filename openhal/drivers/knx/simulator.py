"""A fake KNXnet/IP tunneling server on UDP with a simulated KNX bus, built on xknx's own frame classes.

It follows KNXnet/IP Core and Tunnelling (KNX Standard 03.08.02 and 03.08.04). It replies to
CONNECT_REQUEST, CONNECTIONSTATE_REQUEST and DISCONNECT_REQUEST, acknowledges every
TUNNELLING_REQUEST with a TUNNELLING_ACK, confirms each L_Data.req with an L_Data.con, and
sends the bus's responses as L_Data.ind. Frames are encoded and decoded with `xknx.knxip` and
`xknx.cemi`, so the bytes are the ones a real interface sends.

The bus holds a room. `1/1/1` switches a light whose actuator reports on `1/1/2` (DPT 1.001).
`1/1/3` dims it, reported on `1/1/4` (5.001). `2/1/1` is a readable room temperature (9.001).
`2/1/2` sets the heating setpoint, reported on `2/1/3` (9.001). `2/1/4` is the readable HVAC mode
(20.102). `3/1/1` has no read flag and never sends a response.

Faults. `kick()` sends a DISCONNECT_REQUEST to the client, `refuse` makes CONNECT_REQUEST fail
with E_NO_MORE_CONNECTIONS, `no_confirm` withholds L_Data.con, and `silent` stops the bus's
responses to reads.
"""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import Future
from typing import Any

from xknx.cemi.cemi_frame import CEMIFrame, CEMILData
from xknx.cemi.const import CEMIMessageCode
from xknx.dpt.dpt import DPTBase
from xknx.dpt.dpt_20 import HVACOperationMode
from xknx.dpt.payload import DPTArray, DPTBinary
from xknx.knxip import (
    HPAI,
    ConnectionStateRequest,
    ConnectionStateResponse,
    ConnectRequest,
    ConnectResponse,
    ConnectResponseData,
    DisconnectRequest,
    DisconnectResponse,
    ErrorCode,
    KNXIPFrame,
    TunnellingAck,
    TunnellingRequest,
)
from xknx.telegram import GroupAddress, IndividualAddress, Telegram
from xknx.telegram.apci import GroupValueRead, GroupValueResponse, GroupValueWrite

GATEWAY_ADDRESS = "1.1.250"
TUNNEL_ADDRESS = "1.1.251"
ACTUATOR = "1.1.10"


def encode(dpt: str, value: Any) -> DPTBinary | DPTArray:
    transcoder = DPTBase.parse_transcoder(dpt)
    assert transcoder is not None
    if dpt.startswith("1."):
        return DPTBinary(1 if value else 0)
    return transcoder.to_knx(value)


class SimulatedBus:
    """Group objects with their values, which ones respond to reads, and which addresses report which."""

    def __init__(self) -> None:
        self.values: dict[str, DPTBinary | DPTArray] = {
            "1/1/1": encode("1.001", False),
            "1/1/2": encode("1.001", False),
            "1/1/3": encode("5.001", 0),
            "1/1/4": encode("5.001", 0),
            "2/1/1": encode("9.001", 21.5),
            "2/1/2": encode("9.001", 20.0),
            "2/1/3": encode("9.001", 20.0),
            "2/1/4": encode("20.102", HVACOperationMode.COMFORT),
            "3/1/1": encode("1.001", False),
        }
        self.readable = {"1/1/2", "1/1/4", "2/1/1", "2/1/3", "2/1/4"}
        self.reports = {"1/1/1": "1/1/2", "1/1/3": "1/1/4", "2/1/2": "2/1/3", "2/1/4": "2/1/4"}
        self.silent = False

    def handle(self, telegram: Telegram) -> list[Telegram]:
        """What the bus sends back for one telegram from the tunnel."""
        address = str(telegram.destination_address)
        payload = telegram.payload
        answers: list[Telegram] = []
        if isinstance(payload, GroupValueWrite):
            self.values[address] = payload.value
            status = self.reports.get(address)
            if status is not None and status != address:
                self.values[status] = payload.value
                answers.append(self.make_telegram(status, GroupValueWrite(payload.value)))
            if address == "1/1/3":
                light = encode("1.001", payload.value != encode("5.001", 0))
                self.values["1/1/2"] = light
                answers.append(self.make_telegram("1/1/2", GroupValueWrite(light)))
        elif isinstance(payload, GroupValueRead) and address in self.readable and not self.silent:
            answers.append(self.make_telegram(address, GroupValueResponse(self.values[address])))
        return answers

    @staticmethod
    def make_telegram(address: str, payload: Any) -> Telegram:
        return Telegram(
            destination_address=GroupAddress(address), payload=payload, source_address=IndividualAddress(ACTUATOR)
        )


class _Protocol(asyncio.DatagramProtocol):
    def __init__(self, gateway: KnxGatewaySim) -> None:
        self.gateway = gateway

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        assert isinstance(transport, asyncio.DatagramTransport)
        self.gateway.transport = transport

    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]) -> None:
        self.gateway.received(data, (str(addr[0]), int(addr[1])))


class KnxGatewaySim:
    """Start with `start()` from any thread. It runs on its own event loop."""

    def __init__(self) -> None:
        self.bus = SimulatedBus()
        self.port = 0
        self.channel = 7
        self.transport: asyncio.DatagramTransport | None = None
        self.control: tuple[str, int] | None = None
        self.data: tuple[str, int] | None = None
        self.sequence = 0
        self.received_telegrams: list[Telegram] = []
        self.connects = 0
        self.refuse = False
        self.no_confirm = False
        self._loop = asyncio.new_event_loop()
        self._thread: threading.Thread | None = None

    def start(self) -> KnxGatewaySim:
        ready: Future[None] = Future()

        def run() -> None:
            asyncio.set_event_loop(self._loop)

            async def open_socket() -> None:
                await self._loop.create_datagram_endpoint(lambda: _Protocol(self), local_addr=("127.0.0.1", 0))
                assert self.transport is not None
                self.port = int(self.transport.get_extra_info("sockname")[1])

            self._loop.run_until_complete(open_socket())
            ready.set_result(None)
            self._loop.run_forever()
            if self.transport is not None:
                self.transport.close()
            self._loop.run_until_complete(asyncio.sleep(0))
            self._loop.close()

        self._thread = threading.Thread(target=run, name="openhal-knx-gateway", daemon=True)
        self._thread.start()
        ready.result(timeout=5)
        return self

    def stop(self) -> None:
        if self._thread is None:
            return
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)
        self._thread = None

    def __enter__(self) -> KnxGatewaySim:
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.stop()

    def kick(self) -> None:
        """Close the tunnel from the server side, as a gateway does when it restarts."""
        self._loop.call_soon_threadsafe(self._kick)

    def report(self, address: str, dpt: str, value: Any) -> None:
        """A device on the bus sends a GroupValueWrite, as a sensor does on change."""
        payload = encode(dpt, value)

        def send() -> None:
            self.bus.values[address] = payload
            self._indicate(SimulatedBus.make_telegram(address, GroupValueWrite(payload)))

        self._loop.call_soon_threadsafe(send)

    def _kick(self) -> None:
        if self.control is not None:
            body = DisconnectRequest(
                communication_channel_id=self.channel, control_endpoint=HPAI("127.0.0.1", self.port)
            )
            self._send(body, self.control)
        self.control = self.data = None

    def _send(self, body: Any, address: tuple[str, int]) -> None:
        if self.transport is not None:
            self.transport.sendto(KNXIPFrame.init_from_body(body).to_knx(), address)

    @staticmethod
    def _endpoint(hpai: HPAI, source: tuple[str, int]) -> tuple[str, int]:
        return source if hpai.route_back else hpai.addr_tuple

    def received(self, data: bytes, source: tuple[str, int]) -> None:
        try:
            frame, _ = KNXIPFrame.from_knx(data)
        except Exception:  # noqa: BLE001
            return
        body = frame.body
        if isinstance(body, ConnectRequest):
            if self.refuse or self.control is not None:
                self._send(
                    ConnectResponse(status_code=ErrorCode.E_NO_MORE_CONNECTIONS),
                    self._endpoint(body.control_endpoint, source),
                )
                return
            self.control = self._endpoint(body.control_endpoint, source)
            self.data = self._endpoint(body.data_endpoint, source)
            self.sequence = 0
            self.connects += 1
            response = ConnectResponse(
                communication_channel=self.channel,
                data_endpoint=HPAI("127.0.0.1", self.port),
                crd=ConnectResponseData(individual_address=IndividualAddress(TUNNEL_ADDRESS)),
            )
            self._send(response, self.control)
        elif isinstance(body, ConnectionStateRequest):
            status = ErrorCode.E_NO_ERROR if self.control is not None else ErrorCode.E_CONNECTION_ID
            self._send(
                ConnectionStateResponse(communication_channel_id=body.communication_channel_id, status_code=status),
                self._endpoint(body.control_endpoint, source),
            )
        elif isinstance(body, DisconnectRequest):
            self._send(
                DisconnectResponse(communication_channel_id=body.communication_channel_id),
                self._endpoint(body.control_endpoint, source),
            )
            self.control = self.data = None
        elif isinstance(body, TunnellingRequest) and self.data is not None:
            self._send(
                TunnellingAck(communication_channel_id=self.channel, sequence_counter=body.sequence_counter), self.data
            )
            self._tunnelled(body.raw_cemi)

    def _tunnelled(self, raw_cemi: bytes) -> None:
        cemi = CEMIFrame.from_knx(raw_cemi)
        if cemi.code is not CEMIMessageCode.L_DATA_REQ or not isinstance(cemi.data, CEMILData):
            return
        if not self.no_confirm:
            self._tunnel(CEMIFrame(code=CEMIMessageCode.L_DATA_CON, data=cemi.data))
        telegram = cemi.data.telegram()
        self.received_telegrams.append(telegram)
        for answer in self.bus.handle(telegram):
            self._indicate(answer)

    def _indicate(self, telegram: Telegram) -> None:
        self._tunnel(CEMIFrame(code=CEMIMessageCode.L_DATA_IND, data=CEMILData.init_from_telegram(telegram)))

    def _tunnel(self, cemi: CEMIFrame) -> None:
        if self.data is None:
            return
        request = TunnellingRequest(
            communication_channel_id=self.channel, sequence_counter=self.sequence, raw_cemi=cemi.to_knx()
        )
        self.sequence = (self.sequence + 1) & 0xFF
        self._send(request, self.data)
