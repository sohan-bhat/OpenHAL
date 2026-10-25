"""`openhal init`, which sets up the config folder, the human token and a sample device."""

from __future__ import annotations

import getpass
from pathlib import Path
from typing import Final

import typer
from rich.markup import escape

from openhal._brand import DAEMON_NAME, DEFAULT_PORT
from openhal.cli._common import console, home

CONFIG_TEMPLATE: Final = f"""\
# OpenHAL hub settings. Every setting has a safe default, so this file can stay as it is.
api:
  host: 127.0.0.1
  port: {DEFAULT_PORT}
  allow_lan: false        # true lets other machines connect with a paired token
confirm:
  require_tty: true       # confirm, unlock and routine enable need a terminal and a typed phrase
  ttl_s: 300              # how long a request waits for a person
routines:
  agent_enable_low_hazard: false
"""

SAMPLE_NAME: Final = "plant-waterer.hal.yaml"


def sample_device() -> str:
    """The plant waterer mock (examples/plant-waterer/mock/) without its confirmation.

    The file shipped with OpenHAL was confirmed by the person who wrote it. Your copy is yours to
    confirm, so it loads read-only until you run openhal file confirm.
    """
    from openhal.demo.scenario import example_file

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
    finally:
        store.close()
    write_secret_file(token_path, token)
    return "rotated" if existing else "created"


def register(app: typer.Typer) -> None:
    @app.command()
    def init(
        new_token: bool = typer.Option(False, "--new-token", help="Create a new human token even if one works."),
        sample: bool = typer.Option(True, "--sample/--no-sample", help="Add the simulated plant waterer."),
    ) -> None:
        """Create the config folder, the human token (mode 0600) and the simulated plant waterer."""
        from openhal.hub.config import HubConfig
        from openhal.spec.loader import validate_path

        config = HubConfig(home=home())
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

        sample_path = config.devices_dir / SAMPLE_NAME
        if sample and not sample_path.exists():
            sample_path.write_text(sample_device(), encoding="utf-8")
            report = validate_path(sample_path)
            if not report.ok:  # pragma: no cover (the sample is tested)
                raise typer.Exit(1)
            console.print(f"sample device  {escape(str(sample_path))} created, read-only until you confirm it")
        elif sample:
            console.print(f"sample device  {escape(str(sample_path))} kept")

        console.print("\nNext steps")
        steps = [
            f"Confirm the sample's limits with openhal file confirm {sample_path}" if sample else None,
            f"Start the hub with {DAEMON_NAME}, then check it with openhal status",
            "Create a token for your AI client with openhal token create --agent --scope control_low --name claude",
            "Add openhal mcp to the client. docs/interfaces/MCP.md has the config for each client",
            "Run openhal doctor whenever something looks wrong",
        ]
        for number, step in enumerate((step for step in steps if step), start=1):
            console.print(f"{number}. {escape(step)}")
