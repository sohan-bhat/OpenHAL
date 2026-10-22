"""SCPI simulators. A three-channel bench supply over a raw TCP socket, and a pyvisa-sim file.

`ScpiServer` serves `BenchSupply` on 127.0.0.1 so the driver runs through real PyVISA and
pyvisa-py (`TCPIP0::127.0.0.1::<port>::SOCKET`). The supply follows the command set of the
Rigol DP800 programming guide closely enough for tests, accepts short and long SCPI forms in any
case, and keeps an IEEE 488.2 error queue read with `SYST:ERR?`.

`PYVISA_SIM_DMM` is a pyvisa-sim definition of a simple multimeter, for the `@sim` backend.
"""

from __future__ import annotations

import contextlib
import re
import socket
import socketserver
import threading
import time
from pathlib import Path

LONG_FORMS = {
    "MEASURE": "MEAS",
    "VOLTAGE": "VOLT",
    "CURRENT": "CURR",
    "POWER": "POWE",
    "OUTPUT": "OUTP",
    "SOURCE": "SOUR",
    "APPLY": "APPL",
    "SYSTEM": "SYST",
    "ERROR": "ERR",
    "STATE": "STAT",
}
RATINGS = {1: (30.0, 3.0), 2: (30.0, 3.0), 3: (5.0, 3.0)}


def canonical(header: str) -> str:
    parts = []
    for part in header.upper().lstrip(":").split(":"):
        query = part.endswith("?")
        word = part.rstrip("?")
        number = re.match(r"^([A-Z*]+?)(\d*)$", word)
        base, suffix = (number.group(1), number.group(2)) if number else (word, "")
        parts.append(LONG_FORMS.get(base, base) + suffix + ("?" if query else ""))
    return ":".join(parts)


class BenchSupply:
    """The instrument state. Thread safe."""

    idn = "RIGOL TECHNOLOGIES,DP832,DP8C000000001,00.01.16"

    def __init__(self) -> None:
        self.voltage = {ch: 0.0 for ch in RATINGS}
        self.current = {ch: 1.0 for ch in RATINGS}
        self.output = dict.fromkeys(RATINGS, False)
        self.load_ohms = {ch: 10.0 for ch in RATINGS}
        self.errors: list[str] = []
        self.commands: list[str] = []
        self._lock = threading.RLock()

    def _error(self, text: str) -> None:
        if len(self.errors) < 20:
            self.errors.append(text)

    def _channel(self, text: str) -> int | None:
        match = re.fullmatch(r"(?:CH)?([123])", text.strip().upper())
        return int(match.group(1)) if match else None

    def measured(self, channel: int) -> tuple[float, float]:
        if not self.output[channel]:
            return 0.0, 0.0
        volts = self.voltage[channel]
        amps = volts / self.load_ohms[channel]
        if amps > self.current[channel]:
            amps = self.current[channel]
            volts = amps * self.load_ohms[channel]
        return volts, amps

    def answer(self, line: str) -> str | None:
        with self._lock:
            self.commands.append(line)
            replies = [self._one(part.strip()) for part in line.split(";") if part.strip()]
            found = [reply for reply in replies if reply is not None]
            return ";".join(found) if found else None

    def _one(self, command: str) -> str | None:
        header, _, rest = command.partition(" ")
        head = canonical(header)
        args = [item.strip() for item in rest.split(",")] if rest else []
        if head == "*IDN?":
            return self.idn
        if head == "*OPC?":
            return "1"
        if head in ("*CLS",):
            self.errors.clear()
            return None
        if head == "SYST:ERR?":
            return self.errors.pop(0) if self.errors else '0,"No error"'
        if head in ("MEAS:VOLT?", "MEAS:CURR?", "MEAS:POWE?", "MEAS?"):
            channel = self._channel(args[0]) if args else 1
            if channel is None:
                self._error('-224,"Illegal parameter value"')
                return "0"
            volts, amps = self.measured(channel)
            value = {"MEAS:VOLT?": volts, "MEAS:CURR?": amps, "MEAS:POWE?": volts * amps}.get(head, volts)
            return f"{value:.4f}"
        if head == "OUTP?":
            channel = self._channel(args[0]) if args else 1
            return "ON" if channel and self.output[channel] else "OFF"
        if head in ("OUTP", "OUTP:STAT"):
            channel, state = (self._channel(args[0]), args[1]) if len(args) == 2 else (1, args[0] if args else "")
            if channel is None or state.upper() not in ("ON", "OFF", "1", "0"):
                self._error('-224,"Illegal parameter value"')
                return None
            self.output[channel] = state.upper() in ("ON", "1")
            return None
        if head == "APPL":
            self._apply(args)
            return None
        if head == "APPL?":
            channel = self._channel(args[0]) if args else 1
            if channel is None:
                return None
            volts, amps = RATINGS[channel]
            return f"CH{channel}:{volts:g}V/{amps:g}A,{self.voltage[channel]:.3f},{self.current[channel]:.4f}"
        source = re.fullmatch(r"SOUR([123])?:(VOLT|CURR)(\?)?", head)
        if source:
            channel = int(source.group(1) or 1)
            table = self.voltage if source.group(2) == "VOLT" else self.current
            if source.group(3):
                return f"{table[channel]:.4f}"
            self._set(table, channel, args[0] if args else "", 0 if source.group(2) == "VOLT" else 1)
            return None
        self._error('-113,"Undefined header"')
        return None

    def _set(self, table: dict[int, float], channel: int, text: str, index: int) -> None:
        try:
            value = float(text)
        except ValueError:
            self._error('-224,"Illegal parameter value"')
            return
        if not 0 <= value <= RATINGS[channel][index]:
            self._error('-222,"Data out of range"')
            return
        table[channel] = value

    def _apply(self, args: list[str]) -> None:
        channel = self._channel(args[0]) if args else None
        if channel is None or len(args) < 2:
            self._error('-109,"Missing parameter"')
            return
        self._set(self.voltage, channel, args[1], 0)
        if len(args) > 2:
            self._set(self.current, channel, args[2], 1)


class ScpiServer:
    """Serves one instrument model on a local TCP port, one line per command."""

    def __init__(self, model: BenchSupply | None = None) -> None:
        self.model = model or BenchSupply()
        self.latency_s = 0.0
        self.garble = False
        self.connections: list[socket.socket] = []
        outer = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self) -> None:
                outer.connections.append(self.connection)
                with contextlib.suppress(OSError):
                    for raw in self.rfile:
                        line = raw.decode("ascii", errors="replace").strip()
                        if not line:
                            continue
                        reply = outer.model.answer(line)
                        if reply is None:
                            continue
                        if outer.latency_s:
                            time.sleep(outer.latency_s)
                        if outer.garble:
                            reply = "#~" + reply[::-1]
                        self.wfile.write((reply + "\n").encode("ascii"))

        class Server(socketserver.ThreadingTCPServer):
            daemon_threads = True
            allow_reuse_address = True

        self._server = Server(("127.0.0.1", 0), Handler)
        self.port = self._server.server_address[1]
        self.resource = f"TCPIP0::127.0.0.1::{self.port}::SOCKET"
        self._thread = threading.Thread(target=self._server.serve_forever, name="openhal-scpi-sim", daemon=True)
        self._thread.start()

    def drop_connections(self) -> None:
        """Close every open connection, like pulling the LAN cable. New connections still work."""
        for connection in list(self.connections):
            with contextlib.suppress(OSError):
                connection.shutdown(socket.SHUT_RDWR)
            with contextlib.suppress(OSError):
                connection.close()
        self.connections.clear()

    def close(self) -> None:
        self.drop_connections()
        self._server.shutdown()
        self._server.server_close()


PYVISA_SIM_DMM = """
spec: "1.1"
devices:
  dmm:
    eom:
      USB INSTR:
        q: "\\n"
        r: "\\n"
    error:
      error_queue:
        - q: "SYST:ERR?"
          default: '0,"No error"'
          command_error: '-113,"Undefined header"'
    dialogues:
      - q: "*IDN?"
        r: "Keysight Technologies,34461A,MY00000001,A.03.01-02.40-03.01-00.52-01-01"
      - q: "*OPC?"
        r: "1"
      - q: "MEAS:VOLT:DC?"
        r: "+1.23456789E+00"
      - q: "MEAS:RES?"
        r: "+9.99800000E+03"
    properties:
      nplc:
        default: 10.0
        getter:
          q: "VOLT:DC:NPLC?"
          r: "{:+.8E}"
        setter:
          q: "VOLT:DC:NPLC {:f}"
        specs:
          min: 0.02
          max: 100
          type: float
resources:
  USB0::0x2A8D::0x1301::MY00000001::0::INSTR:
    device: dmm
"""


def pyvisa_sim_file(folder: Path) -> str:
    """Write the multimeter definition into `folder` and return the `visa_library` value for it."""
    path = folder / "openhal-dmm.yaml"
    path.write_text(PYVISA_SIM_DMM, encoding="utf-8")
    return f"{path}@sim"
