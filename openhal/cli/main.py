"""The `openhal` command line. Each command group lives in its own module."""

from __future__ import annotations

import typer

from openhal import __version__
from openhal._brand import CLI_NAME, PRODUCT_NAME
from openhal.cli import file_cmd

app = typer.Typer(
    name=CLI_NAME,
    help=f"{PRODUCT_NAME} lets AI agents safely read and control real hardware.",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(file_cmd.app, name="file")


def _version(value: bool) -> None:
    if value:
        typer.echo(f"{CLI_NAME} {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", callback=_version, is_eager=True, help="Show the version."),
) -> None:
    """OpenHAL command line."""


if __name__ == "__main__":
    app()
