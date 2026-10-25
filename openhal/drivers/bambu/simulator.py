"""A simulated Bambu Lab printer on a local MQTT broker over TLS, for tests and the conformance case.

`PrinterBroker` is the mqtt driver's in-process MQTT 3.1.1 broker served over TLS with a fresh
self-signed certificate whose common name is the printer's serial number, as on a real printer.
It accepts only the user `bblp` with the access code. `SimulatedPrinter` lives on it and follows
the report format the printers use on `device/<serial>/report`.

- `pushing.pushall` publishes a full report. `info.get_version` publishes the module versions.
- `print.pause`, `print.resume`, `print.stop` and `print.print_speed`, and `system.ledctrl` for
  the chamber light, change the state, reply with `result: success` and the request's
  `sequence_id`, then push a status report.
- `partial=True` behaves like a P1 or A1 printer and pushes only the fields that changed. Otherwise it
  pushes full reports like an X1.

Faults. `authorization=True` refuses every control command the way firmware outside Developer Mode
does, `silent=True` stops replying to commands, and the broker's `kick_all()` and `paused` work as in
the mqtt simulator.
"""

from __future__ import annotations

import asyncio
import copy
import datetime as dt
import hashlib
import json
import shutil
import ssl
import tempfile
import threading
from concurrent.futures import Future
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openhal.drivers.mqtt.simulator import MqttBroker

ACCESS_CODE = "12345678"


def self_signed(common_name: str, folder: Path) -> tuple[Path, Path, str]:
    """Write a certificate and key for `common_name` and return their paths and the SHA-256 fingerprint."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = dt.datetime.now(dt.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    cert_path = folder / "printer.crt"
    key_path = folder / "printer.key"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    fingerprint = hashlib.sha256(certificate.public_bytes(serialization.Encoding.DER)).hexdigest()
    return cert_path, key_path, fingerprint


class PrinterBroker(MqttBroker):
    """The mqtt simulator's broker behind TLS, with the printer's login."""

    def __init__(self, serial: str, *, access_code: str = ACCESS_CODE) -> None:
        super().__init__(username="bblp", password=access_code)
        self.serial = serial
        self.folder = Path(tempfile.mkdtemp(prefix="openhal-bambu-"))
        self.cert_path, self.key_path, self.fingerprint = self_signed(serial, self.folder)

    def start(self) -> PrinterBroker:
        if self._thread is not None:
            return self
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(self.cert_path, self.key_path)
        ready: Future[None] = Future()
        loop = asyncio.new_event_loop()
        self._loop = loop

        async def serve() -> None:
            self._stopped = asyncio.Event()
            self._server = await asyncio.start_server(self._session, "127.0.0.1", self.port, ssl=context)
            ready.set_result(None)
            await self._stopped.wait()
            self._server.close()
            for client in list(self._clients):
                client.writer.close()
            await self._server.wait_closed()

        def run() -> None:
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(serve())
            except Exception as exc:  # noqa: BLE001
                if not ready.done():
                    ready.set_exception(exc)
            finally:
                pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
                for task in pending:
                    task.cancel()
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                loop.close()

        self._thread = threading.Thread(target=run, name="openhal-bambu-broker", daemon=True)
        self._thread.start()
        ready.result(timeout=5)
        return self

    def stop(self) -> None:
        super().stop()
        shutil.rmtree(self.folder, ignore_errors=True)


def idle_report() -> dict[str, Any]:
    """A full status report from an idle X1 Carbon, trimmed to the fields the driver uses and a few more."""
    return {
        "command": "push_status",
        "msg": 0,
        "nozzle_temper": 24.5,
        "nozzle_target_temper": 0.0,
        "bed_temper": 23.0,
        "bed_target_temper": 0.0,
        "chamber_temper": 25.0,
        "mc_percent": 0,
        "mc_remaining_time": 0,
        "gcode_state": "IDLE",
        "layer_num": 0,
        "total_layer_num": 0,
        "subtask_name": "",
        "print_error": 0,
        "spd_lvl": 2,
        "spd_mag": 100,
        "wifi_signal": "-44dBm",
        "lights_report": [{"node": "chamber_light", "mode": "off"}, {"node": "work_light", "mode": "flashing"}],
        "hms": [],
    }


@dataclass
class SimulatedPrinter:
    """A printer on the broker. `start_print()` puts it in the middle of a job."""

    broker: PrinterBroker
    serial: str
    partial: bool = False
    authorization: bool = False
    silent: bool = False
    report: dict[str, Any] = field(default_factory=idle_report)
    requests: list[dict[str, Any]] = field(default_factory=list)
    firmware: str = "01.08.05.00"

    def attach(self) -> SimulatedPrinter:
        self.broker.on(f"device/{self.serial}/request", self._request)
        return self

    @property
    def topic(self) -> str:
        return f"device/{self.serial}/report"

    def start_print(self, name: str = "bracket.3mf") -> None:
        self.report.update(
            {
                "gcode_state": "RUNNING",
                "subtask_name": name,
                "mc_percent": 37,
                "mc_remaining_time": 42,
                "layer_num": 61,
                "total_layer_num": 164,
                "nozzle_temper": 219.6,
                "nozzle_target_temper": 220.0,
                "bed_temper": 54.8,
                "bed_target_temper": 55.0,
            }
        )

    def push(self, changes: dict[str, Any] | None = None) -> None:
        """Publish a status report from outside the broker thread."""
        changes = changes or {}
        self.report.update(changes)
        body = changes if self.partial and changes else self.report
        self.broker.publish(self.topic, json.dumps({"print": {"command": "push_status", "msg": 1, **body}}))

    def _send(self, broker: MqttBroker, document: dict[str, Any]) -> None:
        broker.route(self.topic, json.dumps(document).encode(), False)

    def _status(self, broker: MqttBroker, changes: dict[str, Any]) -> None:
        self.report.update(changes)
        body = changes if self.partial else self.report
        self._send(broker, {"print": {"command": "push_status", "msg": 1, "sequence_id": "2000", **body}})

    def _request(self, broker: MqttBroker, topic: str, payload: bytes) -> None:
        try:
            document = json.loads(payload)
        except ValueError:
            return
        if not isinstance(document, dict):
            return
        self.requests.append(copy.deepcopy(document))
        if "pushing" in document and document["pushing"].get("command") == "pushall":
            self._send(broker, {"print": {"msg": 0, "sequence_id": "0", **self.report}})
            return
        if "info" in document and document["info"].get("command") == "get_version":
            modules = [
                {"name": "ota", "sw_ver": self.firmware, "hw_ver": "", "sn": self.serial},
                {"name": "mc", "sw_ver": "00.00.30.10", "hw_ver": "MC07", "sn": "MC"},
            ]
            self._send(broker, {"info": {**document["info"], "module": modules}})
            return
        section = "print" if "print" in document else "system" if "system" in document else None
        if section is None or self.silent:
            return
        body = document[section]
        reply = {"command": body.get("command"), "sequence_id": body.get("sequence_id"), "param": body.get("param", "")}
        if self.authorization:
            self._send(broker, {section: {**reply, "result": "failed", "reason": "mqtt message verify failed"}})
            return
        changes = self._apply(section, body)
        if changes is None:
            self._send(broker, {section: {**reply, "result": "failed", "reason": "unsupported command"}})
            return
        self._send(broker, {section: {**reply, "result": "success"}})
        self._status(broker, changes)

    def _apply(self, section: str, body: dict[str, Any]) -> dict[str, Any] | None:
        command = body.get("command")
        state = self.report["gcode_state"]
        if section == "print" and command == "pause":
            return {"gcode_state": "PAUSE"} if state == "RUNNING" else {}
        if section == "print" and command == "resume":
            return {"gcode_state": "RUNNING"} if state == "PAUSE" else {}
        if section == "print" and command == "stop":
            if state in ("RUNNING", "PAUSE", "PREPARE"):
                return {
                    "gcode_state": "FAILED",
                    "nozzle_target_temper": 0.0,
                    "bed_target_temper": 0.0,
                    "print_error": 0,
                }
            return {}
        if section == "print" and command == "print_speed" and str(body.get("param")) in ("1", "2", "3", "4"):
            return {"spd_lvl": int(body["param"])}
        if section == "system" and command == "ledctrl" and body.get("led_node") == "chamber_light":
            lights = [dict(entry) for entry in self.report["lights_report"]]
            for entry in lights:
                if entry["node"] == "chamber_light":
                    entry["mode"] = body.get("led_mode", "off")
            return {"lights_report": lights}
        return None
