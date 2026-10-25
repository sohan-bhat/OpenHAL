"""Attack family 8. Confirmation spoofing.

An agent poses as a person, forges a session, tries a cross-site request, pipes a phrase in, or reads
and approves another principal's requests. Approval needs a human principal, a cookie session needs
the anti-CSRF header, and one principal can't see or learn another's request ids.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from openhal.cli import _tty
from openhal.hub.hub import Hub
from openhal.kernel import Action, agent, human
from openhal.mcp import Tools
from tests.redteam.conftest import Rest, Tokens, run_cli, writes

SPIN = Action(device="desk-fan", action="spin_test", args={"seconds": "2 s"})


async def queue_for(hub: Hub, who: agent) -> str:
    decision = await hub.kernel.execute(SPIN, who)
    assert decision.status == "pending"
    assert decision.request_id is not None
    return decision.request_id


async def test_a_forged_session_cookie_is_rejected(hub: Hub, rest: Rest) -> None:
    async with rest(cookie="ohal_made-up-session", headers={"X-OpenHAL-Request": "1"}) as client:
        assert (await client.get("/v1/status")).status_code == 401
        assert (await client.post("/v1/stop", json={})).status_code == 401
    async with rest(cookie="not-even-a-token", headers={"X-OpenHAL-Request": "1"}) as client:
        assert (await client.get("/v1/status")).status_code == 401


async def test_a_cookie_session_needs_the_anti_csrf_header(hub: Hub, rest: Rest, tokens: Tokens) -> None:
    async with rest(cookie=tokens.human) as client:
        assert (await client.get("/v1/status")).status_code == 200
        assert (await client.post("/v1/stop", json={"reason": "x"})).status_code == 403
    assert not hub.kernel.stopped
    async with rest(cookie=tokens.human, headers={"X-OpenHAL-Request": "1"}) as client:
        assert (await client.post("/v1/stop", json={"reason": "x"})).status_code == 200
    assert hub.kernel.stopped


async def test_an_agent_cannot_see_or_learn_another_agents_request(hub: Hub, rest: Rest, tokens: Tokens) -> None:
    mine = await queue_for(hub, agent("claude", "control_medium"))
    theirs = await queue_for(hub, agent("other", "control_medium"))
    async with rest(tokens.agent) as client:
        listed = (await client.get("/v1/confirmations")).json()
        ids = {item["id"] for item in listed}
        assert mine in ids
        assert theirs not in ids
        others = (await client.get(f"/v1/confirmations/{theirs}")).status_code
        unknown = (await client.get("/v1/confirmations/deadbeefdeadbeef")).status_code
        assert others == unknown == 404


async def test_an_agent_cannot_approve_any_request(hub: Hub, rest: Rest, tokens: Tokens) -> None:
    mine = await queue_for(hub, agent("claude", "control_medium"))
    theirs = await queue_for(hub, agent("other", "control_medium"))
    async with rest(tokens.agent) as client:
        assert (await client.post(f"/v1/confirmations/{mine}/approve")).status_code == 403
        assert (await client.post(f"/v1/confirmations/{theirs}/approve")).status_code == 403
        assert (await client.post(f"/v1/confirmations/{theirs}/reject", json={})).status_code == 403
    assert hub.kernel.queue.get(mine).status == "pending"
    assert hub.kernel.queue.get(theirs).status == "pending"
    assert writes(hub, "desk-fan") == []


async def test_the_mcp_server_refuses_a_human_token(
    hub: Hub, mcp_tools: Callable[[str], Tools], tokens: Tokens
) -> None:
    tools = mcp_tools(tokens.human)
    with pytest.raises(ToolError, match="agent token"):
        await tools.hub_status()


async def test_confirmation_status_tool_cannot_reach_another_principal(
    hub: Hub, mcp_tools: Callable[[str], Tools], tokens: Tokens
) -> None:
    theirs = await queue_for(hub, agent("other", "control_medium"))
    tools = mcp_tools(tokens.agent)
    with pytest.raises(ToolError):
        await tools.get_confirmation_status(theirs)
    status = await tools.get_confirmation_status()
    assert all(request.id != theirs for request in status.requests)


async def test_a_protocol_client_cannot_approve_or_learn_ids(transport, hub: Hub, tokens: Tokens) -> None:
    theirs = await queue_for(hub, agent("other", "control_medium"))
    async with transport(tokens.agent) as rpc:
        await rpc.initialize()
        mine = await queue_for(hub, agent("claude", "control_medium"))
        error = await rpc.error("hal/confirmations/approve", {"requestId": theirs})
        assert error["data"]["name"] == "SCOPE_DENIED"
        listed = await rpc.call("hal/confirmations/list", {})
        ids = {item["requestId"] for item in listed["requests"]}
        assert mine in ids
        assert theirs not in ids


def test_a_phrase_piped_to_stdin_does_not_unlock(cli, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENHAL_TOKEN", cli.tokens.human)
    monkeypatch.setattr(_tty, "interactive", lambda: False)
    cli.run(cli.hub.kernel.stop_all(human(), "operator stop"))
    code, out = run_cli("unlock", input="unlock\n")
    assert code == 1
    assert cli.hub.kernel.stopped
    assert "interactive terminal" in out
