"""`openhal init`, which sets up the config folder, tokens, devices, AI clients and the service.

On a terminal the command shows a few short questions, and for each device with high risk entries it
offers the limits interview, so the person answers each of those limits once. Low and medium risk
channels and actions take commands at once within the device's own range (ADR 0020). `--yes` takes
the safe defaults without prompting and leaves high risk entries read-only. A run that can't prompt and
has no `--yes`, such as a script, does only the config folder, the human token and the sample. In
every mode only the person's own answers at the terminal confirm a limit, and the service is
installed only when the person asks.
"""

from __future__ import annotations

import asyncio
import getpass
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, cast

import click
import typer
import yaml
from rich.markup import escape

from openhal._brand import DEFAULT_PORT, DEVICE_FILE_SUFFIX, PRODUCT_NAME, START_COMMAND
from openhal.cli import _interview, _live, _tty, service_cmd
from openhal.cli._common import console, home
from openhal.kernel.principals import Scope

if TYPE_CHECKING:
    from openhal.hub.config import HubConfig

CONFIG_TEMPLATE: Final = f"""\
# OpenHAL hub settings. Every setting has a safe default, so this file can stay as it is.
api:
  host: 127.0.0.1
  port: {DEFAULT_PORT}
  allow_lan: false        # true accepts connections from other machines with a paired token
confirm:
  require_tty: true       # confirm, unlock and routine enable need a terminal and a typed phrase
  ttl_s: 300              # how long a request is held for a person
routines:
  agent_enable_low_hazard: false
runs:
  max_steps: 200          # steps in one run, counting every repeat
  max_seconds: 600        # longest run, wait or sample
  per_agent: 2            # runs, waits and samples one token may have going at once
"""

SAMPLE_NAME: Final = "plant-waterer.hal.yaml"
AGENT_TOKEN_FILE: Final = "agent.token"  # noqa: S105 (a file name)
AGENT_TOKEN_NAME: Final = "ai-client"  # noqa: S105 (a token label)
AGENT_SCOPES: Final[tuple[Scope, ...]] = ("read", "control_low", "control_medium")
Mode = Literal["ask", "yes", "quiet"]


@dataclass
class Added:
    """A device file init saved, and whether a person confirmed its limits during init."""

    path: Path
    device_id: str
    writable: bool = False


def sample_device() -> str:
    """The plant waterer mock (examples/plant-waterer/mock/) without its confirmation.

    The file shipped with OpenHAL was confirmed by the person who wrote it. Your copy is yours to
    confirm, so it loads read-only until you run openhal file confirm.
    """
    from openhal.demo.plant import example_file

    lines = example_file().read_text(encoding="utf-8").splitlines()
    return "\n".join(line for line in lines if not line.startswith("confirmed:")) + "\n"


def _human_token(db_path: Path, token_path: Path, rotate: bool) -> str:
    from openhal.hub.tokens import TokenStore, read_secret_file, write_secret_file

    store = TokenStore(db_path)
    try:
        existing = read_secret_file(token_path)
        if existing and not rotate and store.principal(existing) is not None:
            token_path.chmod(0o600)
            return "kept"
        token, _ = store.create(getpass.getuser() or "owner", "human")
        write_secret_file(token_path, token)
        if existing:
            store.revoke_secret(existing)
    finally:
        store.close()
    return "rotated" if existing else "created"


def _agent_token(db_path: Path, token_path: Path, scope: Scope) -> str:
    """An agent token for AI clients, kept while it works and has the requested scope.

    A replaced token is revoked once the new one is saved, so an old copy stops working.
    """
    from openhal.hub.tokens import TokenStore, read_secret_file, write_secret_file

    store = TokenStore(db_path)
    try:
        existing = read_secret_file(token_path)
        principal = store.principal(existing) if existing else None
        if principal is not None and principal.kind == "agent" and principal.scope == scope:
            token_path.chmod(0o600)
            return "kept"
        token, _ = store.create(AGENT_TOKEN_NAME, "agent", scope)
        write_secret_file(token_path, token)
        if existing:
            store.revoke_secret(existing)
    finally:
        store.close()
    return "rotated" if existing else "created"


def _mode(yes: bool) -> Mode:
    if yes:
        return "yes"
    return "ask" if _tty.interactive() else "quiet"


def _choose(mode: Mode, flag: bool | None, question: str, default: bool) -> bool:
    """A yes or no step. A flag sets the answer first, then the person, then the safe default."""
    if flag is not None:
        return flag
    if mode == "ask":
        return typer.confirm(question, default=default)
    return default if mode == "yes" else False


def _parse_known(values: list[str] | None) -> list[tuple[str, str]]:
    known = []
    for value in values or []:
        driver, eq, address = value.partition("=")
        if not eq or not driver or not address:
            raise typer.BadParameter(
                f"Give a device as DRIVER=ADDRESS, for example openhal-firmware=/dev/ttyACM0. Got {value!r}."
            )
        known.append((driver.strip(), address.strip()))
    return known


def _levels(path: Path) -> str:
    """How many entries of a saved file are at each risk level, and what stays read-only."""
    from openhal.spec.loader import load
    from openhal.spec.risk import assess

    file = load(path)
    targets = [target for target in assess(file) if not target.startswith("read:")]
    found = [assess(file)[target].level for target in targets]
    counts = ", ".join(f"{found.count(level)} {level}" for level in ("low", "medium", "high") if level in found)
    waiting = sum(1 for target in targets if file.read_only(target))
    tail = f", {waiting} read-only until you confirm the limits" if waiting else ", every one takes commands"
    return f"risk {counts or 'nothing to control'}{tail if found else ''}"


def _set_limits(path: Path, label: str) -> bool:
    """Walk the limits interview for a file init just saved. Returns True when the file is now writable."""
    from openhal.spec.loader import load, parse_yaml
    from openhal.writer import interview

    if not interview.questions(parse_yaml(path.read_text(encoding="utf-8"))):
        return load(path).writable
    if not typer.confirm(
        f"Answer the high risk limits of {label} now? Those stay read-only until a person does.", default=True
    ):
        return False
    require_tty = _interview.require_person(None)
    who = (getpass.getuser() or "owner").strip()[:80]
    try:
        confirmed = _interview.confirm(parse_yaml(path.read_text(encoding="utf-8")), by=who, require_tty=require_tty)
    except typer.Exit:
        console.print(f"read-only      {escape(str(path))} kept read-only. openhal file confirm asks again")
        return False
    path.write_text(yaml.safe_dump(confirmed, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8")
    writable = load(path).writable
    console.print(f"confirmed      {escape(str(path))} by {escape(who)}, {'writable' if writable else 'read-only'}")
    return writable


def _writable(path: Path) -> bool:
    from openhal.spec.loader import load

    return load(path).writable


def _devices(
    mode: Mode, devices_dir: Path, discover: bool | None, drivers: list[str], known: list[tuple[str, str]]
) -> list[Added]:
    """Offer found devices as read-only device files, and in a terminal offer the limits interview."""
    from openhal.hub.discovery import DISCOVER_TIMEOUT_S
    from openhal.service import devices

    look = _choose(mode, discover, "Search for devices? Discovery only sends read-only identify commands.", True)
    if not look and not known:
        return []
    if look:
        console.print(f"\nLooking for devices, for up to {DISCOVER_TIMEOUT_S:g} s")
    existing = devices.Existing.scan(devices_dir)
    found = asyncio.run(devices.find(existing, discover=look, drivers=drivers or None, known=known))
    added: list[Added] = []
    for offer in found.offers:
        where = f"{offer.label} at {offer.address}"
        if offer.data is None:
            console.print(f"[yellow]skipped[/yellow]  {escape(where)}. {escape(offer.problem or '')}")
            continue
        kind = "from the device library" if offer.source == "library" else "described by the device"
        console.print(f"found          {escape(where)} ({escape(offer.driver)}, {kind})")
        explicit = True if (offer.driver, offer.address) in known else None
        if not _choose(mode, explicit, "Add the device as a read-only device file?", True):
            continue
        path = devices.save(offer, devices_dir, existing)
        console.print(f"device         {escape(str(path))} added, {escape(_levels(path))}")
        entry = Added(path, path.name.removesuffix(DEVICE_FILE_SUFFIX))
        entry.writable = _set_limits(path, offer.label) if mode == "ask" else _writable(path)
        added.append(entry)
    for offer in found.unknown:
        console.print(
            f"unknown        {escape(offer.label)} at {escape(offer.address)} ({escape(offer.driver)}). "
            f"Describe the device with openhal writer start --driver {escape(offer.driver)}"
        )
    for kept in found.kept:
        console.print(f"kept           {escape(kept)}, it has a device file already")
    for error in found.errors:
        console.print(f"[yellow]note[/yellow]  {escape(error)}")
    if found.skipped_drivers:
        console.print(
            f"drivers        {len(found.skipped_drivers)} skipped, their extras aren't installed. "
            "openhal doctor lists them"
        )
    if look and not (found.offers or found.unknown or found.kept):
        console.print("No devices found.")
    return added


def _agent(mode: Mode, scope: str | None, config_home: Path, db_path: Path) -> Path | None:
    """The agent token AI clients use. Read scope unless the person picks another."""
    if scope is None:
        if mode == "quiet":
            return None
        scope = "read"
        if mode == "ask":
            choices = click.Choice([*AGENT_SCOPES, "skip"])
            scope = typer.prompt(
                "Token for your AI client. Scope read, control_low, control_medium or skip",
                default="read",
                type=choices,
                show_choices=False,
            )
            if scope == "skip":
                return None
    path = config_home / AGENT_TOKEN_FILE
    state = _agent_token(db_path, path, cast("Scope", scope))
    console.print(f"agent token    {escape(str(path))} {state}, scope {scope} (mode 0600)")
    return path


def _clients(mode: Mode, token_file: Path, write: list[str]) -> bool:
    """Print the setup for every client, then register OpenHAL with each installed client the person picks."""
    from openhal.service import clients
    from openhal.service.runner import RunError

    platform = "macos" if sys.platform == "darwin" else "linux"
    user_home = Path.home()
    command = clients.cli_command()
    console.print("\nMCP clients")
    for client in clients.known_clients(user_home, platform):
        entry = clients.server_entry(client, command, token_file)
        where = "run this" if client.key == "claude-code" else f"add to {client.path}"
        console.print(f"[bold]{client.title}[/bold], {escape(where)}")
        console.print(escape(clients.setup_text(client, entry)), style="dim")
    chosen = list(write)
    if not chosen and mode in ("ask", "yes"):
        found = clients.installed(user_home, platform)
        if found:
            console.print(f"\nFound {escape(', '.join(client.title for client in found))}")
        for client in found:
            if mode == "yes" or typer.confirm(f"Add OpenHAL to {client.title}?", default=True):
                chosen.append(client.key)
    ok = True
    for key in chosen:
        try:
            client = clients.client_for(key, user_home, platform)
            backup, by_cli = clients.register(
                client, clients.server_entry(client, command, token_file), service_cmd.runner_for(False)
            )
        except (clients.ClientConfigError, RunError, OSError) as exc:
            console.print(f"[red]error[/red]  {escape(str(exc))}")
            ok = False
            continue
        saved = f", backup of {client.path} at {backup}" if backup else ""
        if by_cli:
            console.print(
                f"client         {escape(client.title)} updated at user scope with claude mcp add{escape(saved)}. "
                f"New {escape(client.title)} sessions start openhal mcp"
            )
        else:
            backup_note = f", backup at {backup}" if backup else ""
            where = escape(str(client.path))
            console.print(f"client         {where} updated{escape(backup_note)}. Restart {escape(client.title)}")
    return ok


def _service(mode: Mode, flag: bool | None) -> tuple[bool, bool]:
    """Install the service if asked. Returns whether it runs, and whether every step worked."""
    from openhal.service.background import ServiceError
    from openhal.service.runner import RunError

    try:
        service = service_cmd.build_service()
    except ServiceError as exc:
        if flag:
            console.print(f"[red]error[/red]  {escape(str(exc))}")
        return False, not flag
    if service.path.exists() and flag is None:
        return True, True
    if not _choose(mode, flag, "Run the hub in the background, starting at login?", False):
        return False, True
    try:
        notes = service.install()
    except RunError as exc:
        console.print(f"[red]error[/red]  {escape(str(exc))}")
        return False, False
    console.print(f"service        {escape(str(service.path))} installed, the hub is starting")
    for note in notes:
        console.print(escape(note))
    return True, True


def _installed() -> bool:
    from openhal.service.background import ServiceError

    try:
        return service_cmd.build_service().path.exists()
    except ServiceError:
        return False


def _base(config: HubConfig, new_token: bool, sample: bool) -> Path | None:
    """The config folder, config.yaml, the human token and the sample. Returns the sample's path."""
    from openhal.spec.loader import validate_path

    config.ensure_dirs()
    console.print(f"config folder  {escape(str(config.home))} (mode 0700)")
    config_file = config.home / "config.yaml"
    if config_file.exists():
        console.print(f"settings       {escape(str(config_file))} kept")
    else:
        config_file.write_text(CONFIG_TEMPLATE, encoding="utf-8")
        config_file.chmod(0o600)
        console.print(f"settings       {escape(str(config_file))} created")

    state = _human_token(config.db_path, config.human_token_path, new_token)
    config.db_path.chmod(0o600)
    console.print(f"human token    {escape(str(config.human_token_path))} {state} (mode 0600)")

    if not sample:
        return None
    sample_path = config.devices_dir / SAMPLE_NAME
    if sample_path.exists():
        console.print(f"sample device  {escape(str(sample_path))} kept")
        return sample_path
    sample_path.write_text(sample_device(), encoding="utf-8")
    report = validate_path(sample_path)
    if not report.ok:  # pragma: no cover (the sample is tested)
        raise typer.Exit(1)
    console.print(f"sample device  {escape(str(sample_path))} created, {escape(_levels(sample_path))}")
    return sample_path


def _load(added: list[Added]) -> None:
    """Load each new file into a running OpenHAL that serves this config folder, so no restart is needed."""
    if not added or not _live.hub_runs_here():
        return
    for entry in added:
        loaded = _live.load(entry.path, entry.device_id)
        console.print(f"loaded         {escape(_live.sentence(loaded, writable=entry.writable))}")


def _next_steps(
    sample_path: Path | None, running: bool, has_agent_token: bool, looked: bool, added: list[Added]
) -> None:
    hub = (
        "Check the hub with openhal status"
        if running
        else f"Start {PRODUCT_NAME} with {START_COMMAND}, then check the hub with openhal status"
    )
    if has_agent_token:
        clients = ["Add openhal to your MCP client with the setup above"]
    else:
        clients = [
            "Create a token for your AI client with openhal token create --agent --scope control_low --name claude",
            "Add openhal mcp to the client. docs/interfaces/MCP.md has the config for each client",
        ]
    steps = [
        *[
            f"Answer the high risk limits of {entry.device_id} with openhal file confirm {entry.path}"
            for entry in added
            if not entry.writable
        ],
        *(
            [f"Confirm the sample's high risk limits with openhal file confirm {sample_path}"]
            if sample_path and not _writable(sample_path)
            else []
        ),
        hub,
        *clients,
        *(["Look for devices with openhal init --yes, or openhal discover"] if looked else []),
        "Run openhal doctor whenever something looks wrong",
    ]
    console.print("\nNext steps")
    for number, step in enumerate(steps, start=1):
        console.print(f"{number}. {escape(step)}")


def register(app: typer.Typer) -> None:
    @app.command()
    def init(
        new_token: bool = typer.Option(False, "--new-token", help="Create a new human token even if one works."),
        sample: bool = typer.Option(True, "--sample/--no-sample", help="Add the simulated plant waterer."),
        yes: bool = typer.Option(False, "--yes", "-y", help="Take the safe defaults without prompting."),
        discover: bool = typer.Option(None, "--discover/--no-discover", help="Search for devices. On with --yes."),
        drivers: list[str] = typer.Option(None, "--driver", help="Look only with this driver. Repeat for more."),  # noqa: B008
        device: list[str] = typer.Option(None, "--device", help="A self-describing device at DRIVER=ADDRESS."),  # noqa: B008
        agent_scope: str = typer.Option(None, "--agent-scope", help="Scope of the AI client token. read with --yes."),
        client: list[str] = typer.Option(None, "--client", help="Write this MCP client's config, after a backup."),  # noqa: B008
        service: bool = typer.Option(None, "--service/--no-service", help="Install the background service."),
    ) -> None:
        """Set up the config folder, tokens, devices, MCP clients and the background service."""
        from openhal.hub.config import HubConfig

        known = _parse_known(device)
        if agent_scope is not None and agent_scope not in AGENT_SCOPES:
            raise typer.BadParameter(f"The scope is read, control_low or control_medium, not {agent_scope}.")
        mode = _mode(yes)
        config = HubConfig(home=home())
        sample_path = _base(config, new_token, sample)
        added = _devices(mode, config.devices_dir, discover, drivers or [], known)
        token_file = _agent(mode, agent_scope, config.home, config.db_path)
        ok = _clients(mode, token_file, client or []) if token_file is not None else True
        if client and token_file is None:
            console.print("[red]error[/red]  --client needs an agent token. Add --agent-scope read")
            ok = False
        installed_before = _installed()
        running, service_ok = _service(mode, service)
        if installed_before or not running:
            _load(added)
        _next_steps(sample_path, running, token_file is not None, mode == "quiet" and not known, added)
        if not (ok and service_ok):
            raise typer.Exit(1)
