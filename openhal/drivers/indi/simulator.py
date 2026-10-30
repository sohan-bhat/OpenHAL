"""An INDI server simulator on a local TCP port, using the INDI 1.7 XML protocol.

It serves three devices named like INDI's own simulators. "Telescope Simulator", "Focuser
Simulator" and "CCD Simulator". Each defines CONNECTION and DRIVER_INFO, and defines its
standard properties only after a client turns CONNECTION on, as real drivers do. Slews,
focuser moves, exposures and cooling report Busy and finish in simulated time. A value the device can't take
ends in the Alert state with a message. Updates go to every connected client.

Fault hooks. `silent` stops all output, `drop_clients()` closes every connection and `inject()`
sends raw bytes, for malformed XML tests.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
import time
from collections.abc import Callable
from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring

from openhal.drivers.indi.protocol import ProtocolError, Stream, parse_number


class Prop:
    """One simulated property vector."""

    def __init__(
        self,
        kind: str,
        name: str,
        members: dict[str, Any],
        *,
        perm: str = "rw",
        rule: str | None = None,
        limits: dict[str, tuple[float, float, float]] | None = None,
    ) -> None:
        self.kind = kind
        self.name = name
        self.members = dict(members)
        self.perm = perm
        self.rule = rule
        self.limits = limits or {}
        self.state = "Idle"
        self.message = ""

    def _text(self, value: Any) -> str:
        if self.kind == "switch":
            return "On" if value else "Off"
        if self.kind == "number":
            return f"{float(value):.6f}"
        return str(value)

    def define(self, device: str) -> Element:
        tag = self.kind.capitalize()
        attrs = {"device": device, "name": self.name, "label": self.name.title(), "group": "Main", "state": self.state}
        if self.kind != "light":
            attrs["perm"] = self.perm
        if self.rule:
            attrs["rule"] = self.rule
        element = Element(f"def{tag}Vector", attrs)
        for member, value in self.members.items():
            child = SubElement(element, f"def{tag}", {"name": member, "label": member.title()})
            if member in self.limits:
                low, high, step = self.limits[member]
                child.set("format", "%g")
                child.set("min", f"{low:g}")
                child.set("max", f"{high:g}")
                child.set("step", f"{step:g}")
            child.text = self._text(value)
        return element

    def update(self, device: str) -> Element:
        tag = self.kind.capitalize()
        element = Element(f"set{tag}Vector", {"device": device, "name": self.name, "state": self.state})
        if self.message:
            element.set("message", self.message)
        for member, value in self.members.items():
            SubElement(element, f"one{tag}", {"name": member}).text = self._text(value)
        return element


class SimDevice:
    def __init__(self, server: IndiServerSim, name: str, driver: str, interface: str) -> None:
        self.server = server
        self.name = name
        self.connected = False
        self.base = {
            "CONNECTION": Prop("switch", "CONNECTION", {"CONNECT": False, "DISCONNECT": True}, rule="OneOfMany"),
            "DRIVER_INFO": Prop(
                "text",
                "DRIVER_INFO",
                {"DRIVER_NAME": name, "DRIVER_EXEC": driver, "DRIVER_VERSION": "1.0", "DRIVER_INTERFACE": interface},
                perm="ro",
            ),
        }
        self.extra: dict[str, Prop] = {}

    def now(self) -> float:
        return time.monotonic() * self.server.time_scale

    def props(self) -> list[Prop]:
        return [*self.base.values(), *(self.extra.values() if self.connected else [])]

    def prop(self, name: str) -> Prop | None:
        return next((item for item in self.props() if item.name == name), None)

    def receive(self, prop: Prop, values: dict[str, Any]) -> list[Element]:
        if prop.name == "CONNECTION":
            return self._connection(prop, values)
        return self.handle(prop, values)

    def _connection(self, prop: Prop, values: dict[str, Any]) -> list[Element]:
        want = values.get("CONNECT") is True or values.get("DISCONNECT") is False
        out: list[Element] = []
        if want and not self.connected:
            if self.server.refuse_connect:
                prop.state, prop.message = "Alert", "Cannot open the serial port."
                return [prop.update(self.name)]
            self.connected = True
            out += [item.define(self.name) for item in self.extra.values()]
        elif not want and self.connected:
            self.connected = False
            out += [Element("delProperty", {"device": self.name, "name": name}) for name in self.extra]
        prop.members = {"CONNECT": want, "DISCONNECT": not want}
        prop.state, prop.message = "Ok", ""
        return [prop.update(self.name), *out]

    def refuse(self, prop: Prop, message: str) -> list[Element]:
        prop.state, prop.message = "Alert", message
        return [prop.update(self.name)]

    def accept(self, prop: Prop, values: dict[str, Any], state: str = "Ok") -> list[Element]:
        if prop.kind == "switch" and prop.rule in ("OneOfMany", "AtMostOne") and any(values.values()):
            prop.members = dict.fromkeys(prop.members, False)
        prop.members.update(values)
        prop.state, prop.message = state, ""
        return [prop.update(self.name)]

    def handle(self, prop: Prop, values: dict[str, Any]) -> list[Element]:
        return self.accept(prop, values)

    def tick(self) -> list[Element]:
        return []


class Telescope(SimDevice):
    def __init__(self, server: IndiServerSim) -> None:
        super().__init__(server, "Telescope Simulator", "indi_simulator_telescope", "5")
        self.slew_s = 1.0
        self.target: tuple[float, float] | None = None
        self.until = 0.0
        self.extra = {
            "EQUATORIAL_EOD_COORD": Prop(
                "number",
                "EQUATORIAL_EOD_COORD",
                {"RA": 5.5, "DEC": 22.0},
                limits={"RA": (0, 24, 0), "DEC": (-90, 90, 0)},
            ),
            "HORIZONTAL_COORD": Prop(
                "number",
                "HORIZONTAL_COORD",
                {"ALT": 45.0, "AZ": 180.0},
                perm="ro",
                limits={"ALT": (-90, 90, 0), "AZ": (0, 360, 0)},
            ),
            "ON_COORD_SET": Prop(
                "switch", "ON_COORD_SET", {"TRACK": True, "SLEW": False, "SYNC": False}, rule="OneOfMany"
            ),
            "TELESCOPE_ABORT_MOTION": Prop("switch", "TELESCOPE_ABORT_MOTION", {"ABORT": False}, rule="AtMostOne"),
            "TELESCOPE_PARK": Prop("switch", "TELESCOPE_PARK", {"PARK": False, "UNPARK": True}, rule="OneOfMany"),
            "TELESCOPE_TRACK_STATE": Prop(
                "switch", "TELESCOPE_TRACK_STATE", {"TRACK_ON": False, "TRACK_OFF": True}, rule="OneOfMany"
            ),
        }

    @property
    def parked(self) -> bool:
        return bool(self.extra["TELESCOPE_PARK"].members["PARK"]) and self.extra["TELESCOPE_PARK"].state != "Busy"

    def handle(self, prop: Prop, values: dict[str, Any]) -> list[Element]:
        coords, track = self.extra["EQUATORIAL_EOD_COORD"], self.extra["TELESCOPE_TRACK_STATE"]
        if prop.name == "EQUATORIAL_EOD_COORD":
            ra, dec = float(values.get("RA", coords.members["RA"])), float(values.get("DEC", coords.members["DEC"]))
            if self.parked:
                return self.refuse(prop, "Mount is parked. Unpark it first.")
            if not (0 <= ra < 24 and -90 <= dec <= 90):
                return self.refuse(prop, f"RA {ra} or DEC {dec} is out of range.")
            mode = next(name for name, on in self.extra["ON_COORD_SET"].members.items() if on)
            if mode == "SYNC":
                return self.accept(prop, {"RA": ra, "DEC": dec})
            self.target, self.until = (ra, dec), self.now() + self.slew_s
            prop.state, prop.message = "Busy", "Slewing"
            return [prop.update(self.name)]
        if prop.name == "TELESCOPE_ABORT_MOTION":
            out = self.accept(prop, {"ABORT": False})
            if self.target is not None:
                self.target = None
                coords.state, coords.message = "Alert", "Slew aborted."
                out.append(coords.update(self.name))
            park = self.extra["TELESCOPE_PARK"]
            if park.state == "Busy":
                park.state, park.message = "Alert", "Parking aborted."
                park.members = {"PARK": False, "UNPARK": True}
                out.append(park.update(self.name))
            return out
        if prop.name == "TELESCOPE_PARK":
            if values.get("PARK"):
                self.target, self.until = None, self.now() + self.slew_s
                prop.members = {"PARK": True, "UNPARK": False}
                prop.state = "Busy"
                track.members = {"TRACK_ON": False, "TRACK_OFF": True}
                return [prop.update(self.name), track.update(self.name)]
            return self.accept(prop, {"PARK": False, "UNPARK": True})
        if prop.name == "TELESCOPE_TRACK_STATE" and values.get("TRACK_ON") and self.parked:
            return self.refuse(prop, "Mount is parked.")
        return self.accept(prop, values)

    def tick(self) -> list[Element]:
        if self.now() < self.until:
            return []
        out: list[Element] = []
        park = self.extra["TELESCOPE_PARK"]
        if park.state == "Busy":
            park.state = "Ok"
            out.append(park.update(self.name))
        if self.target is not None:
            coords = self.extra["EQUATORIAL_EOD_COORD"]
            coords.members = {"RA": self.target[0], "DEC": self.target[1]}
            coords.state, coords.message = "Ok", "Slew complete."
            self.target = None
            out.append(coords.update(self.name))
            if self.extra["ON_COORD_SET"].members["TRACK"]:
                out += self.accept(self.extra["TELESCOPE_TRACK_STATE"], {"TRACK_ON": True})
        return out


class Focuser(SimDevice):
    def __init__(self, server: IndiServerSim) -> None:
        super().__init__(server, "Focuser Simulator", "indi_simulator_focus", "8")
        self.speed = 5000.0
        self.goal: float | None = None
        self.last = 0.0
        self.extra = {
            "ABS_FOCUS_POSITION": Prop(
                "number",
                "ABS_FOCUS_POSITION",
                {"FOCUS_ABSOLUTE_POSITION": 10000.0},
                limits={"FOCUS_ABSOLUTE_POSITION": (0, 100000, 1)},
            ),
            "FOCUS_ABORT_MOTION": Prop("switch", "FOCUS_ABORT_MOTION", {"ABORT": False}, rule="AtMostOne"),
            "FOCUS_TEMPERATURE": Prop(
                "number", "FOCUS_TEMPERATURE", {"TEMPERATURE": 12.5}, perm="ro", limits={"TEMPERATURE": (-50, 70, 0)}
            ),
        }

    def handle(self, prop: Prop, values: dict[str, Any]) -> list[Element]:
        position = self.extra["ABS_FOCUS_POSITION"]
        if prop.name == "ABS_FOCUS_POSITION":
            goal = float(values.get("FOCUS_ABSOLUTE_POSITION", 0))
            if not 0 <= goal <= 100000:
                return self.refuse(prop, f"Position {goal:g} is outside 0 to 100000.")
            self.goal, self.last = goal, self.now()
            prop.state, prop.message = "Busy", ""
            return [prop.update(self.name)]
        if prop.name == "FOCUS_ABORT_MOTION":
            out = self.accept(prop, {"ABORT": False})
            if self.goal is not None:
                self.goal = None
                position.state = "Idle"
                out.append(position.update(self.name))
            return out
        return self.accept(prop, values)

    def tick(self) -> list[Element]:
        if self.goal is None:
            return []
        position = self.extra["ABS_FOCUS_POSITION"]
        now = self.now()
        step = self.speed * (now - self.last)
        self.last = now
        current = float(position.members["FOCUS_ABSOLUTE_POSITION"])
        if abs(self.goal - current) <= step:
            position.members["FOCUS_ABSOLUTE_POSITION"] = self.goal
            position.state, self.goal = "Ok", None
        else:
            position.members["FOCUS_ABSOLUTE_POSITION"] = current + step * (1 if self.goal > current else -1)
        return [position.update(self.name)]


class Camera(SimDevice):
    def __init__(self, server: IndiServerSim) -> None:
        super().__init__(server, "CCD Simulator", "indi_simulator_ccd", "22")
        self.cool_rate = 2.0
        self.last = 0.0
        self.setpoint: float | None = None
        self.ends: float | None = None
        self.extra = {
            "CCD_EXPOSURE": Prop(
                "number", "CCD_EXPOSURE", {"CCD_EXPOSURE_VALUE": 0.0}, limits={"CCD_EXPOSURE_VALUE": (0, 3600, 0)}
            ),
            "CCD_ABORT_EXPOSURE": Prop("switch", "CCD_ABORT_EXPOSURE", {"ABORT": False}, rule="AtMostOne"),
            "CCD_TEMPERATURE": Prop(
                "number",
                "CCD_TEMPERATURE",
                {"CCD_TEMPERATURE_VALUE": 18.0},
                limits={"CCD_TEMPERATURE_VALUE": (-50, 50, 0)},
            ),
            "CCD_COOLER": Prop("switch", "CCD_COOLER", {"COOLER_ON": False, "COOLER_OFF": True}, rule="OneOfMany"),
        }

    def handle(self, prop: Prop, values: dict[str, Any]) -> list[Element]:
        exposure = self.extra["CCD_EXPOSURE"]
        if prop.name == "CCD_EXPOSURE":
            duration = float(values.get("CCD_EXPOSURE_VALUE", 0))
            if not 0 < duration <= 3600:
                return self.refuse(prop, f"Exposure {duration:g} s is outside 0 to 3600 s.")
            if self.ends is not None:
                return self.refuse(prop, "An exposure is already running.")
            self.ends = self.now() + duration
            prop.members["CCD_EXPOSURE_VALUE"] = duration
            prop.state, prop.message = "Busy", ""
            return [prop.update(self.name)]
        if prop.name == "CCD_ABORT_EXPOSURE":
            out = self.accept(prop, {"ABORT": False})
            if self.ends is not None:
                self.ends = None
                exposure.members["CCD_EXPOSURE_VALUE"] = 0.0
                exposure.state = "Idle"
                out.append(exposure.update(self.name))
            return out
        if prop.name == "CCD_TEMPERATURE":
            self.setpoint, self.last = float(values.get("CCD_TEMPERATURE_VALUE", 0)), self.now()
            prop.state = "Busy"
            cooler = self.accept(self.extra["CCD_COOLER"], {"COOLER_ON": True})
            return [prop.update(self.name), *cooler]
        return self.accept(prop, values)

    def tick(self) -> list[Element]:
        out: list[Element] = []
        now = self.now()
        exposure = self.extra["CCD_EXPOSURE"]
        if self.ends is not None:
            left = self.ends - now
            exposure.members["CCD_EXPOSURE_VALUE"] = max(0.0, left)
            if left <= 0:
                exposure.state, self.ends = "Ok", None
            out.append(exposure.update(self.name))
        if self.setpoint is not None:
            temperature = self.extra["CCD_TEMPERATURE"]
            current = float(temperature.members["CCD_TEMPERATURE_VALUE"])
            step = self.cool_rate * (now - self.last)
            self.last = now
            if abs(self.setpoint - current) <= step:
                temperature.members["CCD_TEMPERATURE_VALUE"] = self.setpoint
                temperature.state, self.setpoint = "Ok", None
            else:
                temperature.members["CCD_TEMPERATURE_VALUE"] = current + step * (1 if self.setpoint > current else -1)
            out.append(temperature.update(self.name))
        return out


class IndiServerSim:
    """A local INDI server. `await start()` returns the port."""

    def __init__(self) -> None:
        self.time_scale = 1.0
        self.silent = False
        self.refuse_connect = False
        self.received: list[Element] = []
        self.telescope = Telescope(self)
        self.focuser = Focuser(self)
        self.camera = Camera(self)
        self.devices: dict[str, SimDevice] = {item.name: item for item in (self.telescope, self.focuser, self.camera)}
        self.port = 0
        self._server: asyncio.Server | None = None
        self._clients: list[asyncio.StreamWriter] = []
        self._ticker: asyncio.Task[None] | None = None

    async def start(self) -> int:
        self._server = await asyncio.start_server(self._client, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]
        self._ticker = asyncio.create_task(self._tick())
        return self.port

    def received_names(self, tag: str) -> list[str]:
        return [str(item.get("name")) for item in self.received if item.tag == tag]

    def _send(self, elements: list[Element], to: list[asyncio.StreamWriter] | None = None) -> None:
        if self.silent or not elements:
            return
        data = b"".join(tostring(element) + b"\n" for element in elements)
        for writer in to if to is not None else list(self._clients):
            with contextlib.suppress(Exception):
                writer.write(data)

    def inject(self, data: bytes) -> None:
        for writer in list(self._clients):
            with contextlib.suppress(Exception):
                writer.write(data)

    def drop_clients(self) -> None:
        for writer in list(self._clients):
            with contextlib.suppress(Exception):
                writer.close()
        self._clients.clear()

    async def _tick(self) -> None:
        while True:
            await asyncio.sleep(0.02)
            for device in self.devices.values():
                if device.connected:
                    self._send(device.tick())

    async def _client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._clients.append(writer)
        stream = Stream()
        try:
            while data := await reader.read(65536):
                for element in stream.feed(data):
                    self.received.append(element)
                    self._handle(element, writer)
        except (ProtocolError, OSError):
            pass
        finally:
            if writer in self._clients:
                self._clients.remove(writer)
            with contextlib.suppress(Exception):
                writer.close()

    def _handle(self, element: Element, writer: asyncio.StreamWriter) -> None:
        if element.tag == "getProperties":
            wanted, name = element.get("device"), element.get("name")
            definitions = [
                prop.define(device.name)
                for device in self.devices.values()
                if wanted in (None, device.name)
                for prop in device.props()
                if name in (None, prop.name)
            ]
            self._send(definitions, [writer])
            return
        if not (element.tag.startswith("new") and element.tag.endswith("Vector")):
            return
        device = self.devices.get(element.get("device") or "")
        prop = device.prop(element.get("name") or "") if device else None
        if device is None or prop is None or prop.perm == "ro":
            return
        values: dict[str, Any] = {}
        for child in element:
            text = (child.text or "").strip()
            member = child.get("name") or ""
            if member not in prop.members:
                continue
            if prop.kind == "switch":
                values[member] = text == "On"
            elif prop.kind == "number":
                try:
                    values[member] = parse_number(text)
                except ProtocolError:
                    self._send(device.refuse(prop, f"{text!r} is not a number."))
                    return
            else:
                values[member] = text
        self._send(device.receive(prop, values))

    async def stop(self) -> None:
        if self._ticker is not None:
            self._ticker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ticker
        self.drop_clients()
        if self._server is not None:
            self._server.close()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._server.wait_closed(), 1.0)


class ServerThread:
    """Runs a simulated server on its own event loop in a daemon thread, for synchronous setup."""

    def __init__(self, sim: IndiServerSim) -> None:
        self.sim = sim
        self.port = 0
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> int:
        ready = threading.Event()

        def run() -> None:
            loop = asyncio.new_event_loop()
            self._loop = loop
            self.port = loop.run_until_complete(self.sim.start())
            ready.set()
            loop.run_forever()
            loop.run_until_complete(self.sim.stop())
            loop.close()

        self._thread = threading.Thread(target=run, name="openhal-indi-sim", daemon=True)
        self._thread.start()
        if not ready.wait(5):
            raise RuntimeError("the INDI simulator didn't start")
        return self.port

    def call(self, function: Callable[[], Any]) -> None:
        """Run a fault hook such as drop_clients on the server's own loop."""
        if self._loop is not None:
            self._loop.call_soon_threadsafe(function)

    def stop(self) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(5)
