"""Every method over both transports, against a real embedded hub with mock devices."""

from __future__ import annotations

import re

import pytest

from openhal.hub.hub import Hub
from openhal.kernel import kernel as kernel_module
from openhal.kernel.principals import agent, human
from openhal.spec import loads
from tests.kernel.conftest import FakeClock
from tests.protocol.conftest import Connect

FAN_SPEED = {"device": "desk-fan", "channel": "fan_speed"}
RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{3})?Z$")
GHOST = """
device: Ghost relay
id: ghost-relay
connect: { mock: ghost }
write:
  on: { type: bool }
interlocks:
  - if: "on == true"
    require: "nowhere.door == true"
confirmed: { by: owner, at: 2026-10-24 }
"""


async def test_devices_list_and_describe(transport: Connect, tokens: dict[str, str]) -> None:
    async with transport(tokens["reader"]) as rpc:
        await rpc.initialize()
        devices = (await rpc.call("hal/devices/list"))["devices"]
        assert [device["id"] for device in devices] == ["desk-fan", "heater", "draft-lamp"]
        assert devices[0] == {
            "id": "desk-fan",
            "name": "Desk fan",
            "model": None,
            "manufacturer": None,
            "driver": "mock",
            "hazard": "low",
            "writable": True,
            "connected": True,
            "conformance": "control",
            "verification": "unverified",
            "unavailable": None,
        }
        described = (await rpc.call("hal/devices/describe", {"device": "desk-fan"}))["device"]
        fan_speed = described["write"]["fan_speed"]
        assert (fan_speed["unit"], fan_speed["min"], fan_speed["max"], fan_speed["maxChangePerS"]) == ("%", 0, 100, 20)
        assert fan_speed["confirm"] == "none"
        assert fan_speed["confirmed"] == {"by": "owner", "at": "2026-10-24"}
        assert described["read"]["temperature"]["unit"] == "degC"
        assert described["actions"]["spin_test"]["confirm"] == "confirm"
        assert described["safeState"] == [{"fan_speed": 0}]
        assert described["confirmed"] == {"by": "owner", "at": "2026-10-24"}
        assert (described["unconfirmed"], described["file"]) == ([], "desk-fan.hal.yaml")
        heater = (await rpc.call("hal/devices/describe", {"device": "heater"}))["device"]
        assert heater["interlocks"][0]["if"] == "power > 0 W"
        assert heater["watchdog"]["maxDuration"][0]["forS"] == 60
        draft = (await rpc.call("hal/devices/describe", {"device": "draft-lamp"}))["device"]
        assert (draft["writable"], draft["unconfirmed"], draft["confirmed"]) == (False, ["write.brightness"], None)
        error = await rpc.error("hal/devices/describe", {"device": "nope"})
        assert (error["code"], error["data"]["name"], error["message"]) == (
            -32004,
            "UNKNOWN_TARGET",
            "There is no device nope",
        )


async def test_read_and_read_many(transport: Connect, tokens: dict[str, str], hub: Hub) -> None:
    async with transport(tokens["reader"]) as rpc:
        await rpc.initialize()
        reading = await rpc.call("hal/read", FAN_SPEED)
        assert (reading["device"], reading["channel"]) == ("desk-fan", "fan_speed")
        assert (reading["value"], reading["unit"], reading["suspect"]) == (20.0, "%", False)
        assert RFC3339.match(reading["at"])
        error = await rpc.error("hal/read", {"device": "desk-fan", "channel": "humidity"})
        assert error == {
            "code": -32004,
            "message": "desk-fan has no channel humidity",
            "data": {
                "name": "UNKNOWN_TARGET",
                "kernelCode": "unknown_target",
                "device": "desk-fan",
                "channel": "humidity",
            },
        }
        hub.kernel.devices["heater"].connected = False
        error = await rpc.error("hal/read", {"device": "heater", "channel": "temp"})
        assert (error["code"], error["data"]["name"]) == (-32005, "DEVICE_UNAVAILABLE")
        hub.kernel.devices["heater"].connected = True
        hub.kernel.devices["heater"].driver.settings.fail_reads = True  # type: ignore[attr-defined]
        error = await rpc.error("hal/read", {"device": "heater", "channel": "temp"})
        assert (error["code"], error["data"]["name"]) == (-32020, "DRIVER_ERROR")
        assert "<device-data" in error["data"]["kernelMessage"]
        items = [FAN_SPEED, {"device": "heater", "channel": "temp"}, {"device": "desk-fan", "channel": "humidity"}]
        readings = (await rpc.call("hal/readMany", {"items": items}))["readings"]
        assert readings[0]["value"] == 20.0
        assert readings[1]["error"]["data"]["name"] == "DRIVER_ERROR"
        assert readings[2] == {"device": "desk-fan", "channel": "humidity", "error": error | readings[2]["error"]}
        assert readings[2]["error"]["data"]["name"] == "UNKNOWN_TARGET"


async def test_write_errors(transport: Connect, tokens: dict[str, str], hub: Hub, clock: FakeClock) -> None:
    async with transport(tokens["agent"]) as rpc:
        await rpc.initialize()

        async def write(device: str, channel: str, value: object, unit: str | None = None) -> dict[str, object]:
            params = {"device": device, "channel": channel, "value": value}
            return await rpc.error("hal/write", params if unit is None else params | {"unit": unit})

        unit = await write("desk-fan", "fan_speed", "60")
        assert (unit["code"], unit["data"]["name"], unit["data"]["kernelCode"]) == (-32023, "UNIT_INVALID", "bad_unit")
        assert (await write("desk-fan", "fan_speed", 60))["data"]["name"] == "UNIT_INVALID"
        bare = {"kind": "write", "device": "desk-fan", "channel": "fan_speed", "value": 40}
        decided = (await rpc.call("hal/dryRun", {"commands": [bare]}))["decisions"][0]
        assert (decided["error"]["data"]["name"], decided["error"]["data"]["requested"]) == ("UNIT_INVALID", 40)
        text = await write("desk-fan", "fan_speed", "150 %")
        assert (text["data"]["name"], text["data"]["expected"]) == ("UNIT_INVALID", {"value": 150, "unit": "%"})
        assert (
            text["message"] == 'fan_speed needs its number and unit apart, as {"value": 150, "unit": "%"}, not "150 %"'
        )
        assert (await write("heater", "mode", 3, "%"))["data"]["name"] == "UNIT_INVALID"
        step = await write("desk-fan", "fan_speed", 20.5, "%")
        assert (step["code"], step["data"]["name"], step["data"]["limit"]) == (
            -32016,
            "INVALID_VALUE",
            {"value": 1, "unit": "%"},
        )
        assert step["message"] == (
            "fan_speed 20.5 % is not a step of 1 % (desk-fan.hal.yaml, confirmed by owner 2026-10-24)"
        )
        enum = await write("heater", "mode", "turbo")
        assert (enum["data"]["name"], enum["data"]["kernelCode"]) == ("INVALID_VALUE", "bad_value")
        low = await write("desk-fan", "fan_speed", -5, "%")
        assert (
            low["message"]
            == "fan_speed -5 % is below the limit of 0 % (desk-fan.hal.yaml, confirmed by owner 2026-10-24)"
        )
        assert (low["data"]["limit"], low["data"]["requested"]) == (
            {"value": 0, "unit": "%"},
            {"value": -5, "unit": "%"},
        )
        interlock = await write("heater", "power", 10, "W")
        assert (interlock["code"], interlock["data"]["name"]) == (-32012, "INTERLOCK_BLOCKED")
        assert await rpc.call("hal/write", FAN_SPEED | {"value": 40, "unit": "%"})
        rate = await write("desk-fan", "fan_speed", 100, "%")
        assert (rate["code"], rate["data"]["name"], rate["data"]["limit"]) == (
            -32011,
            "RATE_LIMITED",
            {"value": 20, "unit": "%/s"},
        )
        unknown = await write("desk-fan", "wobble", 1, "%")
        assert (unknown["data"]["name"], unknown["message"]) == ("UNKNOWN_TARGET", "desk-fan has no channel wobble")
        draft = await write("draft-lamp", "brightness", 10, "%")
        assert (draft["code"], draft["data"]["name"]) == (-32015, "UNVERIFIED_LIMITS")
        heater = hub.kernel.devices["heater"]
        heater.rules[0].exhausted = True
        watchdog = await write("heater", "power", 50, "W")
        assert (watchdog["code"], watchdog["data"]["name"]) == (-32017, "WATCHDOG_TRIPPED")
        heater.rules[0].exhausted = False
        heater.connected = False
        assert (await write("heater", "power", 5, "W"))["data"]["name"] == "DEVICE_UNAVAILABLE"
        heater.connected = True
        clock.advance(5)
        driver = hub.kernel.devices["desk-fan"].driver
        driver.settings.fail_writes = True  # type: ignore[attr-defined]
        failed = await write("desk-fan", "fan_speed", 50, "%")
        assert (failed["code"], failed["data"]["name"]) == (-32020, "DRIVER_ERROR")
        driver.settings.fail_writes = False  # type: ignore[attr-defined]
    async with transport(tokens["reader"]) as rpc:
        await rpc.initialize()
        denied = await rpc.error("hal/write", FAN_SPEED | {"value": 10, "unit": "%"})
        assert (denied["code"], denied["data"]["name"], denied["data"]["kernelCode"]) == (
            -32003,
            "SCOPE_DENIED",
            "not_permitted",
        )


async def test_a_session_limit_never_cites_the_file(
    transport: Connect, tokens: dict[str, str], hub: Hub, clock: FakeClock
) -> None:
    hub.kernel.tighten(agent("claude", "control_medium"), "desk-fan", "fan_speed", max="70 %")
    clock.advance(10)
    async with transport(tokens["agent"]) as rpc:
        await rpc.initialize()
        error = await rpc.error("hal/write", FAN_SPEED | {"value": 80, "unit": "%"})
    assert error["message"] == "fan_speed 80 % exceeds the session limit of 70 % (tightened by claude)"
    assert error["data"]["tightenedBy"] == "claude"
    assert "file" not in error["data"]
    assert "confirmedBy" not in error["data"]


async def test_busy_queue_full_and_misconfigured(transport: Connect, tokens: dict[str, str], hub: Hub) -> None:
    patch = pytest.MonkeyPatch()
    patch.setattr(kernel_module, "LOCK_TIMEOUT_S", 0.05)
    try:
        async with transport(tokens["agent"]) as rpc:
            await rpc.initialize()
            runtime = hub.kernel.devices["desk-fan"]
            await runtime.lock.acquire()
            try:
                busy = await rpc.error("hal/write", FAN_SPEED | {"value": 30, "unit": "%"})
            finally:
                runtime.lock.release()
            assert (busy["code"], busy["data"]["name"]) == (-32018, "BUSY")
            patch.setattr(hub.kernel.queue, "per_principal", 0)
            spin = {"device": "desk-fan", "action": "spin_test", "args": {"seconds": {"value": 5, "unit": "s"}}}
            full = await rpc.error("hal/action", spin)
            assert (full["code"], full["data"]["name"]) == (-32019, "QUEUE_FULL")
            hub.add_device(loads(GHOST))
            wrong = await rpc.error("hal/write", FAN_SPEED | {"value": 30, "unit": "%"})
            assert (wrong["code"], wrong["data"]["name"]) == (-32021, "MISCONFIGURED")
            hub.kernel.unregister("ghost-relay")
    finally:
        patch.undo()


async def test_dry_run_and_plan_check(transport: Connect, tokens: dict[str, str], clock: FakeClock) -> None:
    async with transport(tokens["agent"]) as rpc:
        await rpc.initialize()
        commands = [
            {"kind": "write", "device": "desk-fan", "channel": "fan_speed", "value": 150, "unit": "%"},
            {"kind": "write", "device": "desk-fan", "channel": "fan_speed", "value": 60, "unit": "%"},
            {
                "kind": "action",
                "device": "desk-fan",
                "action": "spin_test",
                "args": {"seconds": {"value": 5, "unit": "s"}},
            },
        ]
        blocked, allowed, waiting = (await rpc.call("hal/dryRun", {"commands": commands}))["decisions"]
        assert blocked["status"] == "blocked"
        assert (blocked["value"], blocked["unit"]) == (None, "%")
        assert blocked["error"]["data"]["name"] == "LIMIT_EXCEEDED"
        assert blocked["error"]["data"]["limit"] == {"value": 100, "unit": "%"}
        assert allowed == {
            "status": "allowed",
            "device": "desk-fan",
            "target": "write:fan_speed",
            "value": 60.0,
            "unit": "%",
        }
        assert waiting["status"] == "needs_confirmation"
        assert "error" not in waiting
        assert (await rpc.call("hal/read", FAN_SPEED))["value"] == 20.0
        clock.advance(5)
        fast = [commands[1], {"kind": "write", "device": "desk-fan", "channel": "fan_speed", "value": 100, "unit": "%"}]
        result = await rpc.call("hal/planCheck", {"steps": fast})
        assert result["ok"] is False
        assert result["decisions"][1]["error"]["data"]["name"] == "RATE_LIMITED"
        paced = await rpc.call(
            "hal/planCheck", {"steps": [fast[0], {"kind": "wait", "duration": {"value": 2, "unit": "s"}}, fast[1]]}
        )
        assert (paced["ok"], paced["problems"], len(paced["decisions"])) == (True, [], 2), paced
        queued = await rpc.call("hal/planCheck", {"steps": [commands[2]]})
        assert queued["ok"] is False
        assert queued["decisions"][0]["status"] == "needs_confirmation"
        assert queued["decisions"][0]["error"]["data"]["name"] == "CONFIRMATION_REQUIRED"
        bad = await rpc.call("hal/planCheck", {"steps": [{"kind": "wait", "duration": {"value": 2, "unit": "h"}}]})
        assert bad["problems"] == ["steps[0] wait may be at most 1 h"]
        invalid = await rpc.error("hal/planCheck", {"steps": [{"kind": "wait", "wait": "2 s"}]})
        assert invalid["data"]["name"] == "INVALID_PARAMS"


async def test_stop_and_unlock(transport: Connect, tokens: dict[str, str]) -> None:
    async with transport(tokens["agent"]) as rpc:
        await rpc.initialize()
        stopped = await rpc.call("hal/stop", {"reason": "smoke near the fan"})
        assert stopped["devices"][0] == {"device": "desk-fan", "status": "safe", "detail": "smoke near the fan"}
        assert {item["device"]: item["status"] for item in stopped["devices"]} == {
            "desk-fan": "safe",
            "heater": "safe",
            "draft-lamp": "no_safe_state",
        }
        note = await rpc.note("hal/stopped")
        assert note["params"] == {
            "reason": "smoke near the fan",
            "by": "agent:claude",
            "devices": [
                {"device": "desk-fan", "status": "safe"},
                {"device": "draft-lamp", "status": "no_safe_state"},
                {"device": "heater", "status": "safe"},
            ],
        }
        blocked = await rpc.error("hal/write", FAN_SPEED | {"value": 10, "unit": "%"})
        assert (blocked["code"], blocked["data"]["name"]) == (-32014, "STOPPED")
        denied = await rpc.error("hal/unlock", {"phrase": "unlock"})
        assert (denied["code"], denied["data"]["name"], denied["data"]["kernelCode"]) == (
            -32003,
            "SCOPE_DENIED",
            "not_permitted",
        )
        assert (denied["message"], denied["data"]["method"]) == ("Only a human can call hal/unlock", "hal/unlock")
    async with transport(tokens["human"]) as rpc:
        await rpc.initialize()
        wrong = await rpc.error("hal/unlock", {"phrase": "please"})
        assert (wrong["data"]["name"], wrong["data"]["kernelCode"]) == ("INVALID_PARAMS", "bad_request")
        assert await rpc.call("hal/unlock", {"phrase": "unlock"}) == {"ok": True}


async def test_action_and_confirmations(transport: Connect, tokens: dict[str, str], clock: FakeClock) -> None:
    spin = {"device": "desk-fan", "action": "spin_test", "args": {"seconds": {"value": 5, "unit": "s"}}}
    async with transport(tokens["agent"]) as bench, transport(tokens["human"]) as person:
        await bench.initialize()
        await person.initialize()
        done = await person.call("hal/action", spin)
        assert done == {
            "status": "done",
            "result": {"device": "desk-fan", "action": "spin_test", "args": {"seconds": {"value": 5, "unit": "s"}}},
        }
        missing = await bench.error("hal/action", {"device": "desk-fan", "action": "spin_test", "args": {}})
        assert missing["data"]["name"] == "INVALID_PARAMS"
        pending = await bench.call("hal/action", spin)
        assert (pending["status"], pending["expiresInS"]) == ("pending", 300.0)
        request_id = pending["requestId"]
        requested = (await person.note("hal/confirmationRequested"))["params"]["request"]
        assert requested["requestId"] == request_id
        assert requested["command"] == {
            "kind": "action",
            "device": "desk-fan",
            "action": "spin_test",
            "args": spin["args"],
        }
        assert (requested["status"], requested["requestedBy"]) == ("pending", "agent:claude")
        assert RFC3339.match(requested["createdAt"])
        assert RFC3339.match(requested["expiresAt"])
        assert "decidedBy" not in requested
        listed = (await bench.call("hal/confirmations/list"))["requests"]
        assert [item["requestId"] for item in listed] == [request_id]
        for method in ("hal/confirmations/approve", "hal/confirmations/reject"):
            denied = await bench.error(method, {"requestId": request_id})
            assert (denied["code"], denied["data"]["name"]) == (-32003, "SCOPE_DENIED")
        approved = await person.call("hal/confirmations/approve", {"requestId": request_id})
        assert approved == {
            "status": "done",
            "device": "desk-fan",
            "target": "action:spin_test",
            "value": {"seconds": {"value": 5, "unit": "s"}},
            "unit": None,
        }
        again = await person.error("hal/confirmations/approve", {"requestId": request_id})
        assert (again["code"], again["data"]["name"], again["data"]["requestId"]) == (
            -32022,
            "REQUEST_CLOSED",
            request_id,
        )
        clock.advance(1)
        second = (await bench.call("hal/action", spin | {"args": {"seconds": {"value": 6, "unit": "s"}}}))["requestId"]
        rejected = await person.call("hal/confirmations/reject", {"requestId": second, "reason": "not while it dries"})
        assert (rejected["status"], rejected["decidedBy"]) == ("rejected", "human:owner")
        closed = await person.error("hal/confirmations/approve", {"requestId": second})
        assert (closed["data"]["name"], closed["data"]["kernelCode"]) == ("REQUEST_CLOSED", "rejected")
        unknown = await person.error("hal/confirmations/reject", {"requestId": "feedface"})
        assert unknown["data"]["name"] == "REQUEST_CLOSED"
        assert (await person.call("hal/confirmations/list"))["requests"] == []
        rejected_list = (await person.call("hal/confirmations/list", {"status": "rejected"}))["requests"]
        assert [item["requestId"] for item in rejected_list] == [second]
    async with transport(tokens["other"]) as other:
        await other.initialize()
        assert (await other.call("hal/confirmations/list", {"status": "rejected"}))["requests"] == []


async def test_routines_and_audit(transport: Connect, tokens: dict[str, str], hub: Hub) -> None:
    hub.routines.create(
        human("owner"),
        "keep-cool",
        "yaml",
        "id: keep-cool\ntriggers:\n  - every: 30 s\nsteps:\n"
        "  - write: { device: desk-fan, channel: fan_speed, value: 150 % }\n"
        "  - action: { device: desk-fan, action: spin_test, args: { seconds: 5 s } }\n",
    )
    async with transport(tokens["agent"]) as rpc:
        await rpc.initialize()
        routines = (await rpc.call("hal/routines/list"))["routines"]
        assert len(routines) == 1
        summary = routines[0]
        assert {key: summary[key] for key in ("id", "kind", "enabled", "devices", "maxHazard", "triggers")} == {
            "id": "keep-cool",
            "kind": "yaml",
            "enabled": False,
            "devices": ["desk-fan"],
            "maxHazard": "low",
            "triggers": ["every 30 s"],
        }
        dry = await rpc.call("hal/routines/dryRun", {"routineId": "keep-cool"})
        assert dry["ok"] is False
        first, second = dry["decisions"]
        assert first["error"]["data"]["name"] == "LIMIT_EXCEEDED"
        assert (second["error"]["code"], second["error"]["data"]["name"]) == (-32013, "CONFIRMATION_REQUIRED")
        missing = await rpc.error("hal/routines/dryRun", {"routineId": "nope"})
        assert (missing["data"]["name"], missing["message"]) == ("UNKNOWN_TARGET", "There is no routine nope")
        await rpc.error("hal/write", FAN_SPEED | {"value": 150, "unit": "%"})
        entries = (await rpc.call("hal/audit/query", {"device": "desk-fan", "status": "blocked", "limit": 1}))[
            "entries"
        ]
        assert len(entries) == 1
        entry = entries[0]
        assert (entry["event"], entry["code"], entry["principal"]) == ("write", "above_max", "agent:claude")
        assert entry["body"]["requested"] == {"value": 150, "unit": "%"}
        assert RFC3339.match(entry["at"])
        assert (await rpc.call("hal/audit/query", {"since": entry["seq"] + 10_000}))["entries"] == []
        assert await rpc.error("hal/audit/query", {"limit": 6000})


async def test_internal_errors_say_nothing_was_sent(transport: Connect, tokens: dict[str, str], hub: Hub) -> None:
    def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError("boom")

    hub.kernel.dry_run = broken  # type: ignore[method-assign]
    async with transport(tokens["agent"]) as rpc:
        await rpc.initialize()
        error = await rpc.error("hal/dryRun", {"commands": []})
    assert (error["code"], error["data"]["name"]) == (-32603, "INTERNAL_ERROR")
    assert "boom" not in error["message"]
