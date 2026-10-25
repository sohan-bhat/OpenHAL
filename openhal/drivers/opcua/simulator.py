"""A simulated pump skid on asyncua's own OPC UA server, run in a background thread.

The address space lives in the namespace `urn:openhal:sim:pump` with string node ids.

    Pump               object
      Speed            Double, writable, rpm (UNECE RPM), EURange 0 to 3000
      Setpoint         Int32, writable, percent (P1), EURange 0 to 100
      Mode             String, writable
      Running          Boolean, read only
      Temperature      Double, read only, degC (CEL)
      Start(Rate)      method, Rate is a Double, returns a Boolean
      Stop()           method
      Prime()          method, refused with BadInvalidState unless the pump runs
    Tank               object
      Level            Float, read only, percent, EURange 0 to 100
      Pressure         Double, read only, kPa (KPA)
      TempF            Double, read only, degF (FAH)
      Odd              Double, read only, a unit OpenHAL doesn't know

Starting asyncua's server loads the whole standard address space and takes seconds, so tests
and the conformance case share one server per process through `shared()`.
"""

from __future__ import annotations

import asyncio
import contextlib
import socket
import threading
import time
from collections.abc import Coroutine
from typing import Any, TypeVar

from openhal.drivers.opcua.units import code_id

URI = "urn:openhal:sim:pump"
T = TypeVar("T")
DEFAULTS: dict[str, Any] = {
    "Pump.Speed": 0.0,
    "Pump.Setpoint": 0,
    "Pump.Mode": "auto",
    "Pump.Running": False,
    "Pump.Temperature": 21.5,
    "Tank.Level": 64.0,
    "Tank.Pressure": 101.3,
    "Tank.TempF": 70.0,
    "Tank.Odd": 1.0,
}


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class OpcuaSim:
    """The server and its nodes. Every method here is called from the test's thread."""

    def __init__(self) -> None:
        self.port = 0
        self.endpoint = ""
        self.namespace = 0
        self.calls: list[tuple[str, list[Any]]] = []
        self.nodes: dict[str, Any] = {}
        self._server: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> str:
        ready = threading.Event()
        failure: list[BaseException] = []

        def run() -> None:
            loop = asyncio.new_event_loop()
            self._loop = loop
            try:
                loop.run_until_complete(self._start())
            except BaseException as exc:  # noqa: BLE001
                failure.append(exc)
                ready.set()
                return
            ready.set()
            loop.run_forever()
            with contextlib.suppress(Exception):
                loop.run_until_complete(self._server.stop())
            loop.close()

        self._thread = threading.Thread(target=run, name="openhal-opcua-sim", daemon=True)
        self._thread.start()
        if not ready.wait(120):
            raise RuntimeError("the OPC UA simulator didn't start within 120 s")
        if failure:
            raise RuntimeError(f"the OPC UA simulator failed to start ({failure[0]})")
        return self.endpoint

    async def _start(self) -> None:
        import logging

        from asyncua import ua as typed_ua

        ua: Any = typed_ua
        from asyncua.common.methods import uamethod
        from asyncua.server.server import Server

        logging.getLogger("asyncua").setLevel(logging.ERROR)
        self.port = _free_port()
        self.endpoint = f"opc.tcp://127.0.0.1:{self.port}/openhal/sim/"
        server = Server()
        await server.init()
        server.set_endpoint(self.endpoint)
        server.set_server_name("OpenHAL OPC UA simulator")
        index = await server.register_namespace(URI)
        self.namespace = index
        pump = await server.nodes.objects.add_object(ua.NodeId("Pump", index), ua.QualifiedName("Pump", index))
        tank = await server.nodes.objects.add_object(ua.NodeId("Tank", index), ua.QualifiedName("Tank", index))
        kinds = {"Pump.Setpoint": ua.VariantType.Int32, "Tank.Level": ua.VariantType.Float}
        for name, value in DEFAULTS.items():
            parent = pump if name.startswith("Pump.") else tank
            kind = kinds.get(name)
            variant = ua.Variant(value, kind) if kind else value
            node = await parent.add_variable(
                ua.NodeId(name, index), ua.QualifiedName(name.split(".")[1], index), variant
            )
            if name in ("Pump.Speed", "Pump.Setpoint", "Pump.Mode"):
                await node.set_writable()
            self.nodes[name] = node
        for name, code, low, high in (
            ("Pump.Speed", "RPM", 0.0, 3000.0),
            ("Pump.Setpoint", "P1", 0.0, 100.0),
            ("Pump.Temperature", "CEL", None, None),
            ("Tank.Level", "P1", 0.0, 100.0),
            ("Tank.Pressure", "KPA", None, None),
            ("Tank.TempF", "FAH", None, None),
            ("Tank.Odd", "", None, None),
        ):
            information = ua.EUInformation()
            information.NamespaceUri = "http://www.opcfoundation.org/UA/units/un/cefact"
            information.UnitId = code_id(code) if code else -1
            information.DisplayName = ua.LocalizedText(code.lower() if code else "zorp")
            await self.nodes[name].add_property(0, "EngineeringUnits", information)
            if low is not None and high is not None:
                await self.nodes[name].add_property(0, "EURange", ua.Range(Low=low, High=high))

        @uamethod
        async def start(parent: Any, rate: float) -> bool:
            self.calls.append(("Start", [rate]))
            await self.nodes["Pump.Speed"].write_value(float(rate))
            await self.nodes["Pump.Running"].write_value(True)
            return True

        @uamethod
        async def stop(parent: Any) -> bool:
            self.calls.append(("Stop", []))
            await self.nodes["Pump.Speed"].write_value(0.0)
            await self.nodes["Pump.Running"].write_value(False)
            return True

        async def prime(parent: Any) -> Any:
            self.calls.append(("Prime", []))
            if not await self.nodes["Pump.Running"].read_value():
                return ua.StatusCode(ua.StatusCodes.BadInvalidState)
            return [ua.Variant(True, ua.VariantType.Boolean)]

        rate = ua.Argument(Name="Rate", DataType=ua.NodeId(ua.ObjectIds.Double), ValueRank=-1)
        rate.Description = ua.LocalizedText("Pump speed in rpm")
        await pump.add_method(
            ua.NodeId("Pump.Start", index), ua.QualifiedName("Start", index), start, [rate], [ua.VariantType.Boolean]
        )
        await pump.add_method(
            ua.NodeId("Pump.Stop", index), ua.QualifiedName("Stop", index), stop, [], [ua.VariantType.Boolean]
        )
        await pump.add_method(
            ua.NodeId("Pump.Prime", index), ua.QualifiedName("Prime", index), prime, [], [ua.VariantType.Boolean]
        )
        await server.start()
        self._server = server

    def run(self, coroutine: Coroutine[Any, Any, T], timeout: float = 10.0) -> T:
        """Run a coroutine on the server's loop and wait for it."""
        assert self._loop is not None
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop).result(timeout)

    def get(self, name: str) -> Any:
        return self.run(self.nodes[name].read_value())

    def set(self, name: str, value: Any) -> None:
        self.run(self.nodes[name].write_value(value))

    def set_status(self, name: str, status: str) -> None:
        """Give a variable a status code such as BadSensorFailure or UncertainLastUsableValue."""
        from asyncua import ua as typed_ua

        ua: Any = typed_ua

        node = self.nodes[name]

        async def apply() -> None:
            value = (await node.read_data_value(raise_on_bad_status=False)).Value.Value
            code = ua.StatusCode(getattr(ua.StatusCodes, status))
            await node.write_value(
                ua.DataValue(ua.Variant(value, await node.read_data_type_as_variant_type()), StatusCode=code)
            )

        self.run(apply())

    def reset(self) -> None:
        """Put every variable back to its default with a Good status."""
        from asyncua import ua as typed_ua

        ua: Any = typed_ua

        self.calls.clear()
        kinds = {"Pump.Setpoint": ua.VariantType.Int32, "Tank.Level": ua.VariantType.Float}
        for name, value in DEFAULTS.items():
            kind = kinds.get(name)
            self.set(name, ua.DataValue(ua.Variant(value, kind) if kind else ua.Variant(value)))

    def hang(self, seconds: float) -> None:
        """Block the server's loop, so it stops answering for a while, like a stalled PLC."""
        assert self._loop is not None
        self._loop.call_soon_threadsafe(time.sleep, seconds)

    def stop(self) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(10)


_SHARED: OpcuaSim | None = None
_LOCK = threading.Lock()


def shared() -> OpcuaSim:
    """The one simulator for this process, started on first use and reset on every call."""
    global _SHARED
    with _LOCK:
        if _SHARED is None:
            sim = OpcuaSim()
            sim.start()
            _SHARED = sim
    _SHARED.reset()
    return _SHARED
