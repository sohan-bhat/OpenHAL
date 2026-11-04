"""Record the demo video's real Claude Code session into video/data/<take> (README.md in each take).

    .venv/bin/python video/hub/record_session.py --take take-1 --scratch <folder> --cache video/assets/menagerie

The run serves a real hub on a free loopback port from a fresh home in the scratch folder, with
only the simulated SO-101 from so101-demo.hal.yaml on the mujoco driver. A nested `claude -p`
session reaches the hub through `openhal mcp` alone, with an agent token, and gets the take's
prompts one at a time. A headless Inspector, paired as the person, approves the held drop and
presses STOP while the arm moves. Nothing reaches hardware, and the run never reads a real home.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import gzip
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import menagerie
import mujoco
import numpy
import record
from record import COLUMNS, Clock, Frames, Log, confirmed, expect, live, scrub

from openhal import __version__
from openhal.client import AsyncClient, calls
from openhal.demo import rig
from openhal.drivers.mujoco.driver import MujocoDriver
from openhal.drivers.openhal_firmware.driver import PORTS_ENV
from openhal.hub import views
from openhal.hub.tokens import write_secret_file
from openhal.mcp.tools import TOOL_NAMES

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARM_FILE = HERE / "so101-demo.hal.yaml"
INSPECTOR = HERE / "inspector.mjs"
OUT = ROOT / "video" / "data"
CLAUDE = Path.home() / ".local" / "bin" / "claude"
OPENHAL = ROOT / ".venv" / "bin" / "openhal"
RATE_HZ = 60
PERSON = "owner"
AGENT = "claude"
SERVER = "openhal"
FORBIDDEN_PORTS = frozenset({4000, 7420})
VIEW = {"width": 1280, "height": 720, "scale": 2, "scheme": "dark"}
SCHEMES = ("dark",)
ALLOWED = (
    "hub_status", "list_devices", "find", "describe_device", "read", "read_many", "sample", "wait_until",
    "write", "action", "dry_run", "plan_check", "run_steps", "get_run", "list_runs", "cancel_run", "stop_all",
    "tighten_limits", "request_limit_change", "get_confirmation_status", "get_audit_log",
)  # fmt: skip
LEFT_OUT = (
    "list_routines", "get_routine", "draft_routine", "run_routine_dry", "enable_routine", "disable_routine",
    "list_drivers", "discover_devices", "list_unknown_devices", "start_driver_writer", "get_writer_session",
    "propose_device_file", "request_limits_interview", "get_test_plan", "device_file_schema",
)  # fmt: skip
"""Tools the session never sees. Discovery would probe this machine's ports and network, past the simulated arm."""
BACK = "I put the cube back on the desk."
PLAN: list[dict[str, Any]] = [
    {"prompt": "Pick up the red cube and put it in the bin."},
    {"reset": True},
    {"prompt": "Do it again at 120 degrees per second.", "after_reset": BACK},
    {"reset": True},
    {"prompt": "Do it at a normal speed then.", "after_reset": BACK, "stop": True},
]
"""Each prompt in order. A reset sets the cube back where it started when it moved, and the next prompt then
opens with its after_reset sentence, so the session hears what the person did."""


class Inspector:
    """The real Inspector in headless Chromium, driven one command at a time by inspector.mjs."""

    def __init__(self, folder: Path, clock: Clock, epoch0: float) -> None:
        self.folder = folder
        self.clock = clock
        self.epoch0 = epoch0
        self.events: list[dict[str, Any]] = []
        self.count = 0
        self.process: asyncio.subprocess.Process | None = None

    async def start(self, log: Path) -> None:
        node = shutil.which("node")
        expect(node is not None, "node is not on PATH")
        assert node is not None
        self.errors = log.open("w", encoding="utf-8")
        self.process = await asyncio.create_subprocess_exec(
            node, str(INSPECTOR), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=self.errors
        )

    def t(self, epoch_ms: float) -> float:
        return round(epoch_ms / 1000 - self.epoch0, 4)

    async def send(self, cmd: str, **fields: Any) -> dict[str, Any]:
        assert self.process is not None
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        self.count += 1
        self.process.stdin.write((json.dumps({"id": self.count, "cmd": cmd, **fields}) + "\n").encode())
        await self.process.stdin.drain()
        reply: dict[str, Any] = json.loads(await asyncio.wait_for(self.process.stdout.readline(), 60))
        expect(bool(reply.get("ok")), f"the Inspector's {cmd} failed: {reply.get('error')}")
        return reply

    async def shots(self, name: str) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        for scheme in SCHEMES:
            file = self.folder / f"{name}-{scheme}.png"
            reply = await self.send("shot", file=str(file), scheme=scheme)
            self.events.append({"t": self.t(reply["taken_ms"]), "kind": "screenshot", "file": f"inspector/{file.name}"})
        await self.send("scheme", scheme=VIEW["scheme"])

    async def click(self, what: str, **target: Any) -> dict[str, Any]:
        sent = self.clock.now()
        reply = await self.send("click", **target)
        event = reply.get("event") or {}
        entry = {
            "kind": "click",
            "what": what,
            "t": self.t(event["event_ms"]) if event else None,
            "epoch_ms": event.get("event_ms"),
            "button": event.get("button"),
            "aria_label": event.get("label"),
            "t_command_sent": sent,
            "t_playwright_before": self.t(reply["before_ms"]),
            "t_playwright_after": self.t(reply["after_ms"]),
        }
        self.events.append(entry)
        return entry

    async def close(self) -> None:
        if self.process is None:
            return
        with contextlib.suppress(Exception):
            await self.send("close")
        with contextlib.suppress(Exception):
            await asyncio.wait_for(self.process.wait(), 15)
        if self.process.returncode is None:
            self.process.kill()
            await self.process.wait()
        self.errors.close()


class Claude:
    """A nested `claude -p` session on stream-json, every output line kept as it arrived."""

    def __init__(self, argv: list[str], env: dict[str, str], cwd: Path, folder: Path, clock: Clock) -> None:
        self.argv, self.env, self.cwd, self.folder, self.clock = argv, env, cwd, folder, clock
        self.turns: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.times: list[dict[str, Any]] = []
        self.process: asyncio.subprocess.Process | None = None

    async def start(self) -> None:
        self.errors = (self.folder / "claude.stderr.txt").open("w", encoding="utf-8")
        self.process = await asyncio.create_subprocess_exec(
            *self.argv, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=self.errors,
            cwd=self.cwd, env=self.env, limit=64 * 1024 * 1024,
        )  # fmt: skip
        self.reader = asyncio.create_task(self._read())

    async def _read(self) -> None:
        assert self.process is not None
        assert self.process.stdout is not None
        with (self.folder / "claude.stream.jsonl").open("wb") as raw:
            number = 0
            while line := await self.process.stdout.readline():
                t = self.clock.now()
                raw.write(line)
                raw.flush()
                number += 1
                with contextlib.suppress(ValueError):
                    message = json.loads(line)
                    self.times.append({"line": number, "t": t, "type": message.get("type")})
                    if message.get("type") == "result":
                        self.turns.put_nowait(message)

    async def say(self, text: str) -> float:
        assert self.process is not None
        assert self.process.stdin is not None
        body = {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": text}]}}
        t = self.clock.now()
        self.process.stdin.write((json.dumps(body) + "\n").encode())
        await self.process.stdin.drain()
        return t

    async def close(self) -> None:
        if self.process is None:
            return
        if self.process.stdin is not None:
            self.process.stdin.close()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self.process.wait(), 60)
        if self.process.returncode is None:
            self.process.terminate()
            await self.process.wait()
        await self.reader
        self.errors.close()


def moving(driver: MujocoDriver) -> bool:
    """Whether a move that turns an arm joint, not only the gripper, is going."""
    world = driver.world
    assert world is not None
    arm = {writer.actuator for name, writer in driver.writers.items() if name != "gripper_goal"}
    return any(motion.actuators() & arm for motion in list(world.motions))


def put_cube_back(driver: MujocoDriver) -> bool:
    """The cube back at its start pose on the desk, as a person would set it down. False if it is there."""
    world = driver.world
    assert world is not None
    model, data = world.model, world.data
    joint = model.joint("cube").id
    address, dof = int(model.jnt_qposadr[joint]), int(model.jnt_dofadr[joint])
    start = numpy.array(model.key("ready").qpos[address : address + 7])
    with world._lock:  # noqa: SLF001
        if numpy.linalg.norm(data.qpos[address : address + 3] - start[:3]) < 0.005:
            return False
        data.qpos[address : address + 7] = start
        data.qvel[dof : dof + 6] = 0.0
        mujoco.mj_forward(model, data)
    return True


class Take:
    """One take, the hub, the person's Inspector and the agent's session on one clock."""

    def __init__(self, options: argparse.Namespace, hub: Any, url: str, owner: AsyncClient, person: str) -> None:
        self.options, self.hub, self.url, self.owner, self.person = options, hub, url, owner, person
        self.out = out = options.out / options.take
        self.driver: MujocoDriver = hub.kernel.devices["arm"].driver
        self.clock = Clock()
        self.epoch0 = time.time() - (time.monotonic() - self.clock.origin)
        self.log = Log(self.clock)
        self.inspector = Inspector(out / "inspector", self.clock, self.epoch0)
        self.armed = False
        self.held: set[str] = set()
        self.approvals = 0
        self.reset_done = False

    def mark(self, text: str, **extra: Any) -> None:
        self.log.marks.append({"t": self.clock.now(), "text": text, **extra})

    async def approve_drops(self) -> None:
        """Approve every held drop_in_bin in the Inspector after a pause, and leave anything else pending."""
        while True:
            for request in await self.owner.confirmations():
                if request.id in self.held or request.status != "pending":
                    continue
                self.held.add(request.id)
                command = request.command
                self.mark("request held for a person", request_id=request.id, command=command)
                if command.get("kind") == "action" and command.get("action") == "drop_in_bin":
                    await self.approve(request.id, time.monotonic())
            await asyncio.sleep(0.1)

    async def approve(self, request_id: str, seen: float) -> None:
        self.approvals += 1
        suffix = "" if self.approvals == 1 else f"-{self.approvals}"
        card = f'[aria-labelledby="req-{request_id}"]'
        await self.inspector.send("goto", hash="#/confirmations")
        await self.inspector.send("wait", selector=card)
        await self.inspector.send("reveal", selector=card)
        await asyncio.sleep(0.8)
        await self.inspector.shots(f"1-pending{suffix}")
        await asyncio.sleep(max(0.0, seen + self.options.approve_after - time.monotonic()))
        click = await self.inspector.click("Approve", name="Approve and", exact=False)
        self.mark("Approve clicked in the Inspector", request_id=request_id, t_click=click["t"])
        await self.inspector.shots(f"2-approve-clicked{suffix}")
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if (await self.owner.confirmation(request_id)).status not in ("pending", "approved"):
                break
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.6)
        await self.inspector.shots(f"3-approved{suffix}")
        await self.inspector.send("goto", hash="#/devices/arm")

    async def press_stop(self) -> None:
        """Press STOP in the Inspector once an armed prompt's move has run for stop_after seconds."""
        while True:
            await asyncio.sleep(0.005)
            if not self.armed or not moving(self.driver):
                continue
            began = time.monotonic()
            while moving(self.driver) and time.monotonic() - began < self.options.stop_after:  # noqa: ASYNC110
                await asyncio.sleep(0.005)
            if not moving(self.driver) or not self.armed:
                continue
            self.armed = False
            click = await self.inspector.click("STOP", name="STOP every device", exact=True)
            self.mark("STOP clicked in the Inspector", t_click=click["t"])
            await self.inspector.send("wait", selector="button.unlock")
            await asyncio.sleep(0.5)
            await self.inspector.shots("5-stopped")
            return

    async def quiet(self, settle_s: float = 1.5, within_s: float = 90.0) -> None:
        """Wait until no arm move is going and no drop waits for a person, for settle_s in a row."""
        deadline = time.monotonic() + within_s
        calm_since: float | None = None
        while time.monotonic() < deadline:
            drops = [
                request
                for request in await self.owner.confirmations()
                if request.status == "pending" and request.command.get("action") == "drop_in_bin"
            ]
            busy = bool(drops) or bool(self.driver.world and self.driver.world.motions)
            calm_since = None if busy else (calm_since or time.monotonic())
            if calm_since is not None and time.monotonic() - calm_since >= settle_s:
                return
            await asyncio.sleep(0.05)
        self.mark("the arm was still busy when the wait ended")

    async def run(self, claude: Claude, plan: list[dict[str, Any]]) -> None:
        listener = asyncio.create_task(live(self.url, self.person, self.log))
        frames = Frames(self.driver, self.clock, RATE_HZ)
        self.frames = frames
        helpers = [asyncio.create_task(self.approve_drops()), asyncio.create_task(self.press_stop())]
        try:
            await self.inspector.send("goto", hash="#/devices/arm")
            await asyncio.sleep(1.0)
            await self.inspector.shots("0-devices")
            await claude.start()
            for number, step in enumerate(plan, start=1):
                await self.quiet()
                if step.get("reset") and put_cube_back(self.driver):
                    self.reset_done = True
                    self.mark("cube set back at its start pose by the recording script")
                    await asyncio.sleep(1.0)
                if "prompt" in step:
                    text = step["prompt"]
                    if self.reset_done and step.get("after_reset"):
                        text = f"{step['after_reset']} {text}"
                    self.reset_done = False
                    if step.get("stop"):
                        await self.inspector.send("goto", hash="#/devices/arm")
                        await self.inspector.shots("4-before-stop")
                    self.armed = bool(step.get("stop"))
                    sent = await claude.say(text)
                    self.mark("prompt sent", step=number, prompt=text, t_sent=sent)
                    result = await asyncio.wait_for(claude.turns.get(), self.options.turn_timeout)
                    self.mark("turn ended", step=number, subtype=result.get("subtype"), is_error=result.get("is_error"))
                    self.armed = False
            await asyncio.sleep(2.0)
            if self.hub.kernel.stopped:
                await self.inspector.shots("6-end")
        finally:
            for task in helpers:
                task.cancel()
            await claude.close()
            frames.remove()
            listener.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await asyncio.gather(listener, *helpers, return_exceptions=True)


def claude_command(config: Path, model: str | None) -> list[str]:
    allowed = ",".join(f"mcp__{SERVER}__{name}" for name in ALLOWED)
    left_out = ",".join(f"mcp__{SERVER}__{name}" for name in LEFT_OUT)
    argv = [
        str(CLAUDE), "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
        "--include-partial-messages", "--replay-user-messages", "--setting-sources", "project",
        "--strict-mcp-config", "--mcp-config", str(config), "--tools", "", "--allowedTools", allowed,
        "--disallowedTools", left_out, "--permission-mode", "dontAsk", "--disable-slash-commands",
        "--no-session-persistence",
    ]  # fmt: skip
    return [*argv, "--model", model] if model else argv


def claude_env(token: str) -> dict[str, str]:
    """A bare environment for the nested session, with the agent token only in OPENHAL_AGENT_TOKEN."""
    keep = {name: os.environ[name] for name in ("HOME", "USER", "LOGNAME", "TMPDIR") if name in os.environ}
    return {**keep, "SHELL": "/bin/zsh", "LANG": "en_US.UTF-8", "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "OPENHAL_AGENT_TOKEN": token}  # fmt: skip


async def preflight(hub: Any, url: str, token: str, home: Path) -> list[dict[str, Any]]:
    """The simulated arm must be the only device, in the hub and through the MCP server, before any write."""
    expect(set(hub.kernel.devices) == {"arm"}, f"the hub has {sorted(hub.kernel.devices)}")
    driver = hub.kernel.devices["arm"].driver
    expect(isinstance(driver, MujocoDriver) and driver.simulated, "the arm isn't the simulated mujoco arm")
    expect(hub.kernel.devices["arm"].connected, "the simulated arm didn't connect")
    async with rig.mcp_session(url, token, home) as agent:
        listed = await agent.call("list_devices", {})
    expect([item["id"] for item in listed] == ["arm"], f"list_devices through MCP gave {listed}")
    return list(listed)


def lines(items: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(item, separators=(",", ":")) + "\n" for item in items)


def write_outputs(take: Take, claude: Claude, home: Path, scene: Path, extra: dict[str, Any]) -> None:
    out = take.out
    paths = {str(home.resolve()): "OPENHAL_HOME", str(home): "OPENHAL_HOME", str(scene.parent): "MODEL_DIR"}
    (out / "claude.times.jsonl").write_text(lines(claude.times), encoding="utf-8")
    (out / "hub-live.jsonl").write_text(lines(scrub(take.log.items, paths)), encoding="utf-8")
    entries = sorted(take.hub.audit.entries(limit=1_000_000), key=lambda entry: entry.seq)
    audit = [
        {"t": round(entry.at - take.epoch0, 4), "seq": entry.seq, "at": entry.at, "event": entry.event,
         "principal": entry.principal, "device": entry.device, "target": entry.target, "status": entry.status,
         "code": entry.code, "details": views.audit_details(entry.device, entry.body.get("details", {})),
         "hash": entry.hash}
        for entry in entries
    ]  # fmt: skip
    (out / "hub-audit.jsonl").write_text(lines(scrub(audit, paths)), encoding="utf-8")
    (out / "inspector.jsonl").write_text(lines(take.inspector.events), encoding="utf-8")
    (out / "marks.jsonl").write_text(lines(take.log.marks), encoding="utf-8")
    rows = take.frames.rows()
    with gzip.open(out / "frames.csv.gz", "wt", encoding="utf-8", newline="") as frames:
        frames.write(",".join(COLUMNS) + "\n")
        frames.writelines(",".join(repr(value) for value in row) + "\n" for row in rows)
    session = {
        "take": take.options.take,
        "recorded_with": "video/hub/record_session.py",
        "recorded_on": time.strftime("%Y-%m-%d"),
        "clock": "t is seconds since the take began on one monotonic clock. Wall time is epoch0 + t.",
        "epoch0": round(take.epoch0, 6),
        "openhal": __version__,
        "mujoco": mujoco.__version__,
        "claude_command": [part for part in claude.argv if "mcp.json" not in part],
        "frames": {"rate_hz": RATE_HZ, "rows": len(rows), "columns": list(COLUMNS), "units": record.UNITS},
        "inspector_view": VIEW,
        "model": {"source": "MuJoCo Menagerie robotstudio_so101", "commit": menagerie.COMMIT, "license": "Apache-2.0"},
        "device_file": "video/hub/so101-demo.hal.yaml",
        "plan": take.options.plan_steps,
        "approve_after_s": take.options.approve_after,
        "stop_after_s": take.options.stop_after,
        **extra,
    }
    (out / "session.json").write_text(json.dumps(session, indent=2) + "\n", encoding="utf-8")


def check_no_secrets(out: Path, secrets: list[str]) -> None:
    """Fail when any token shows up in what the take wrote, frames included."""
    for path in sorted(out.rglob("*")):
        if not path.is_file() or path.suffix == ".png":
            continue
        data = gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()
        for secret in secrets:
            expect(secret.encode() not in data, f"a token appears in {path.name}")


async def main_async(options: argparse.Namespace) -> None:
    expect(set(ALLOWED) | set(LEFT_OUT) == set(TOOL_NAMES), "the MCP tool list changed, so update ALLOWED")
    scratch = (options.scratch / options.take).resolve()
    expect(not scratch.exists(), f"{scratch} exists already, so pick a new take name")
    home, cwd = scratch / "home", scratch / "cwd"
    cwd.mkdir(parents=True)
    os.environ.pop(PORTS_ENV, None)
    scene = menagerie.scene(options.cache)
    os.environ["OPENHAL_SO101_SCENE"] = str(scene)
    person = rig.set_up_home(home, PERSON)
    text, _file = confirmed(ARM_FILE.read_text(encoding="utf-8"), PERSON)
    (home / "devices" / "arm.hal.yaml").write_text(text, encoding="utf-8")
    async with rig.serving(home) as (hub, url):
        port = int(url.rsplit(":", 1)[1])
        expect(url.startswith("http://127.0.0.1:") and port not in FORBIDDEN_PORTS, f"the hub came up on {url}")
        async with AsyncClient(url, person, use_human_token_file=False) as owner:
            token = (await owner.create_token(AGENT, kind="agent", scope="control_medium")).token
            write_secret_file(scratch / "agent.token", token)
            listed = await preflight(hub, url, token, home)
            env = {"OPENHAL_HOME": str(home), "OPENHAL_URL": url, "OPENHAL_TOKEN": "${OPENHAL_AGENT_TOKEN}"}
            server = {"type": "stdio", "command": str(OPENHAL), "args": ["mcp", "--no-start"], "env": env}
            config = scratch / "mcp.json"
            write_secret_file(config, json.dumps({"mcpServers": {SERVER: server}}, indent=2))
            take = Take(options, hub, url, owner, person)
            take.out.mkdir(parents=True, exist_ok=True)
            code = (await owner.call(calls.new_pairing_code())).code
            await take.inspector.start(scratch / "inspector.stderr.txt")
            claude = Claude(claude_command(config, options.model), claude_env(token), cwd, take.out, take.clock)
            try:
                await take.inspector.send("open", url=url + "/", code=code, **VIEW)
                take.mark("take begins", devices=[item["id"] for item in listed])
                await take.run(claude, options.plan_steps)
            finally:
                await take.inspector.close()
            write_outputs(take, claude, home, scene, {"hub_port": port, "preflight_list_devices": listed})
            check_no_secrets(take.out, [person, token, code])
    print(f"wrote {take.out}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Record one take of the demo session from a real hub.")
    parser.add_argument("--take", required=True, help="The take's folder name in video/data.")
    parser.add_argument("--scratch", type=Path, required=True, help="A scratch folder for the home and tokens.")
    parser.add_argument("--cache", type=Path, required=True, help="A folder for the Menagerie model.")
    parser.add_argument("--out", type=Path, default=OUT, help="Where takes go, video/data by default.")
    parser.add_argument("--plan", type=Path, help="A JSON list of steps in place of the default plan.")
    parser.add_argument("--model", help="The model for the nested session, its default when left out.")
    parser.add_argument("--approve-after", type=float, default=3.0, help="Seconds a held drop waits for Approve.")
    parser.add_argument("--stop-after", type=float, default=0.8, help="Seconds into the armed move before STOP.")
    parser.add_argument("--turn-timeout", type=float, default=480.0, help="Seconds one prompt's turn may take.")
    options = parser.parse_args(argv)
    options.plan_steps = json.loads(options.plan.read_text(encoding="utf-8")) if options.plan else PLAN
    sys.setswitchinterval(record.SWITCH_S)
    asyncio.run(main_async(options))


if __name__ == "__main__":
    main()
