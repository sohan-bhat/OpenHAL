"""The `openhal` command line. Each command group lives in its own module."""

from __future__ import annotations

from pathlib import Path

import typer

from openhal import __version__
from openhal._brand import CLI_NAME, PRODUCT_NAME
from openhal.cli import (
    _common,
    confirm_cmd,
    control_cmd,
    doctor_cmd,
    file_cmd,
    file_confirm_cmd,
    hub_cmd,
    init_cmd,
    log_cmd,
    mcp_cmd,
    routine_cmd,
    token_cmd,
    writer_cmd,
)

app = typer.Typer(
    name=CLI_NAME,
    help=f"{PRODUCT_NAME} lets AI agents safely read and control real hardware.",
    no_args_is_help=True,
    add_completion=False,
)

file_cmd.app.command("confirm")(file_confirm_cmd.confirm)
app.add_typer(file_cmd.app, name="file")
app.add_typer(confirm_cmd.app, name="confirm")
app.add_typer(routine_cmd.app, name="routine")
app.add_typer(writer_cmd.app, name="writer")
app.add_typer(token_cmd.app, name="token")
init_cmd.register(app)
hub_cmd.register(app)
control_cmd.register(app)
log_cmd.register(app)
token_cmd.register(app)
mcp_cmd.register(app)
doctor_cmd.register(app)


def _version(value: bool) -> None:
    if value:
        typer.echo(f"{CLI_NAME} {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", callback=_version, is_eager=True, help="Show the version."),
    url: str = typer.Option(None, "--url", envvar="OPENHAL_URL", help="Hub address. Default from config.yaml."),
    token_file: Path = typer.Option(None, "--token-file", help="Read the token from this file."),  # noqa: B008
) -> None:
    """OpenHAL command line."""
    _common.OPTIONS.url = url
    _common.OPTIONS.token_file = token_file


if __name__ == "__main__":
    app()
