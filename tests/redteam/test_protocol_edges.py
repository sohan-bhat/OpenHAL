"""Attack family 9. Protocol edge cases.

Messages before initialize, batches, huge and deeply nested payloads, duplicate ids, a method above
the hub's conformance level, and tokens in the message log. None may execute a command or leak a
token, and a malformed frame must come back as an error, not crash the connection.
"""

from __future__ import annotations

from openhal.hub.hub import Hub
from openhal.protocol.dispatch import Dispatcher
from tests.protocol.conftest import VERSION, Connect
from tests.redteam.conftest import Tokens, writes

INIT = {"protocolVersion": VERSION, "clientInfo": {"name": "pytest", "version": "1"}}


def write_msg(value: object, request_id: int = 2) -> dict:
    params = {"device": "desk-fan", "channel": "fan_speed", "value": value}
    return {"jsonrpc": "2.0", "id": request_id, "method": "hal/write", "params": params}


async def opened(hub: Hub, level: str = "full") -> tuple[Dispatcher, object]:
    disp = Dispatcher(hub, level=level)
    session = disp.open()
    token = hub.tokens.create("edge", "agent", "control_medium")[0]
    init = {"jsonrpc": "2.0", "id": 1, "method": "hal/initialize", "params": {**INIT, "token": token}}
    await disp.handle(session, init)
    return disp, session


async def test_a_batch_is_refused(hub: Hub) -> None:
    disp, session = await opened(hub)
    response = await disp.handle(session, [{"jsonrpc": "2.0", "id": 2, "method": "hal/devices/list"}])
    assert response["error"]["data"]["name"] == "INVALID_REQUEST"


async def test_methods_before_initialize_do_nothing(transport: Connect, hub: Hub, tokens: Tokens) -> None:
    async with transport(tokens.agent) as rpc:
        for method, params in (
            ("hal/write", {"device": "desk-fan", "channel": "fan_speed", "value": "30 %"}),
            ("hal/stop", {}),
            ("hal/unlock", {"phrase": "unlock"}),
        ):
            error = await rpc.error(method, params)
            assert error["data"]["name"] == "NOT_INITIALIZED"
    assert not hub.kernel.stopped
    assert writes(hub, "desk-fan") == []


async def test_a_method_above_the_conformance_level_is_not_found(hub: Hub) -> None:
    disp, session = await opened(hub, level="core")
    error = await disp.handle(session, write_msg("30 %"))
    assert error["error"]["data"]["name"] == "METHOD_NOT_FOUND"
    assert writes(hub, "desk-fan") == []


async def test_duplicate_ids_are_each_answered(hub: Hub) -> None:
    disp, session = await opened(hub)
    first = await disp.handle(session, {"jsonrpc": "2.0", "id": 7, "method": "hal/devices/list"})
    second = await disp.handle(session, {"jsonrpc": "2.0", "id": 7, "method": "hal/devices/list"})
    assert first["id"] == second["id"] == 7
    assert "result" in first
    assert "result" in second


async def test_a_huge_numeric_value_is_blocked_quickly(hub: Hub) -> None:
    disp, session = await opened(hub)
    response = await disp.handle(session, write_msg("9" * 5000 + " %"))
    assert "error" in response
    assert response["error"]["data"]["name"] in ("LIMIT_EXCEEDED", "UNIT_INVALID")
    assert writes(hub, "desk-fan") == []


async def test_a_deeply_nested_value_is_refused(hub: Hub) -> None:
    disp, session = await opened(hub)
    nested: dict = {"value": 1, "unit": "%"}
    for _ in range(2000):
        nested = {"value": nested, "unit": "%"}
    response = await disp.handle(session, write_msg(nested))
    assert "error" in response
    assert writes(hub, "desk-fan") == []


async def test_a_token_in_params_is_redacted_from_the_message_log(
    transport: Connect, hub: Hub, rest, tokens: Tokens
) -> None:
    secret = hub.tokens.create("leaky", "agent", "control_medium")[0]
    async with transport() as rpc:
        await rpc.call("hal/initialize", {**INIT, "token": secret})
    async with rest(tokens.human) as client:
        entries = (await client.get("/v1/rpc/log")).json()
    bodies = str([entry["message"] for entry in entries])
    assert secret not in bodies
    assert "[redacted]" in bodies


RT04 = "RT-04: the message log stores the client name verbatim, so a token in clientInfo.name is not redacted"


async def test_rt04_a_token_in_the_client_name_does_not_leak(
    transport: Connect, hub: Hub, rest, tokens: Tokens
) -> None:
    secret = hub.tokens.create("sneaky", "agent", "control_medium")[0]
    async with transport() as rpc:
        await rpc.call(
            "hal/initialize",
            {"protocolVersion": VERSION, "clientInfo": {"name": f"client {secret}", "version": "1"}, "token": secret},
        )
    async with rest(tokens.human) as client:
        entries = (await client.get("/v1/rpc/log")).json()
    assert secret not in str(entries), "a token placed in clientInfo.name reached the log unredacted"


RT03 = "RT-03: a deeply nested JSON frame raises RecursionError in parse instead of answering PARSE_ERROR"


async def test_rt03_deeply_nested_json_frame_is_a_parse_error(hub: Hub) -> None:
    disp = Dispatcher(hub)
    session = disp.open()
    raw = "[" * 1500 + "1" + "]" * 1500
    raised: BaseException | None = None
    try:
        disp.parse(session, raw)
    except RecursionError as exc:
        raised = exc
    assert raised is None, "parse raised RecursionError instead of answering PARSE_ERROR"
    pending = session.pending()
    assert pending, "parse should have queued a response"
    assert pending[-1]["error"]["data"]["name"] == "PARSE_ERROR"
