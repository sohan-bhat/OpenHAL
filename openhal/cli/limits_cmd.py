"""`openhal limits`, showing and changing a channel's limits with no device file to edit.

A narrower limit applies at once. A wider limit needs a person, so in an interactive terminal the
command shows the change and asks for the typed phrase confirm, as `openhal file confirm` does.
Where no phrase can be typed, such as a script, an agent's shell or a command run from inside an AI
client, the change waits as a pending limit change for a person to approve.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import typer
from rich.markup import escape
from rich.table import Table

from openhal.cli import _tty
from openhal.cli._common import config, console, fail, handled, hub, parse_quantity_text, print_json, show, styled

app = typer.Typer(help="Show and change a device's limits. Narrowing applies at once, widening needs a person.")

PHRASE = "confirm"
WHAT = "widen these limits"


def _split(target: str, *, channel_needed: bool) -> tuple[str, str | None]:
    device, dot, channel = target.partition(".")
    if not device or (dot and not channel) or (channel_needed and not channel):
        shape = "DEVICE.CHANNEL" if channel_needed else "DEVICE or DEVICE.CHANNEL"
        raise ValueError(f"Give the target as {shape}, for example bench-lamp.brightness. Got {target!r}.")
    return device, channel or None


def _call(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    from openhal.client.calls import Call

    def parse(data: Any) -> dict[str, Any]:
        return dict(data)

    with hub() as client:
        return client.call(Call(method, path, parse, json=body))


def _range(low: float | None, high: float | None, unit: str | None) -> str:
    return f"{show(low, unit)} to {show(high, unit)}"


@app.command("show")
@handled
def show_limits(
    target: str = typer.Argument(..., help="DEVICE, or DEVICE.CHANNEL for one channel."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON."),
) -> None:
    """Show each limit and the range the device itself reports."""
    device, channel = _split(target, channel_needed=False)
    data = _call("GET", f"/v1/devices/{quote(device, safe='')}/limits")
    channels = data.get("channels", {})
    if channel is not None:
        if channel not in channels:
            raise ValueError(f"{device} has no number channel {channel!r} with limits.")
        channels = {channel: channels[channel]}
    if as_json:
        print_json({**data, "channels": channels})
        return
    table = Table("channel", "min to max", "max change", "device range", "confirm", box=None, pad_edge=False)
    for name, spec in channels.items():
        unit = spec.get("unit")
        rate = f"{show(spec['rate'], unit)}/s" if spec.get("rate") is not None else "no limit"
        reported = spec.get("device_range")
        table.add_row(
            escape(name),
            escape(_range(spec.get("min"), spec.get("max"), unit)),
            escape(rate),
            escape(_range(reported[0], reported[1], unit) if reported else "not reported"),
            escape(spec.get("confirm") or ""),
        )
    console.print(table)
    confirmed = data.get("confirmed")
    if data.get("writable") and confirmed:
        console.print(f"confirmed by {escape(str(confirmed['by']))} on {escape(str(confirmed['at']))}")
    elif not data.get("writable"):
        console.print(f"read-only. Answer each limit first with openhal file confirm {escape(str(data.get('path')))}")


def _person_can_type(phrase: str | None) -> bool:
    """Whether a phrase can come from a person here. Fails for --phrase while a terminal is required."""
    require_tty = config().confirm.require_tty
    if require_tty and phrase is not None:
        fail(f"--phrase can't be used while confirm.require_tty is true. Run this in a terminal and type {PHRASE}.")
    if require_tty:
        return _tty.interactive()
    return phrase is not None or _tty.interactive()


@app.command("set")
@handled
def set_limits(
    target: str = typer.Argument(..., help="DEVICE.CHANNEL, for example bench-lamp.brightness."),
    low: str = typer.Option(None, "--min", help="The new min with its unit, for example 10 %."),
    high: str = typer.Option(None, "--max", help="The new max with its unit, for example 80 %."),
    rate: str = typer.Option(None, "--rate", help="The new max change per second, for example 5 %/s, or none."),
    phrase: str = typer.Option(None, "--phrase", help="Only when confirm.require_tty is false."),
) -> None:
    """Change a channel's limits. A wider limit takes a person's typed phrase or waits for a person to approve."""
    device, channel = _split(target, channel_needed=True)
    if low is None and high is None and rate is None:
        raise ValueError("Give --min, --max or --rate.")
    body: dict[str, Any] = {"device": device, "channel": channel}
    if low is not None:
        body["min"] = parse_quantity_text(low, "--min")
    if high is not None:
        body["max"] = parse_quantity_text(high, "--max")
    if rate is not None:
        body["rate"] = "none" if rate.strip().lower() == "none" else parse_quantity_text(rate, "--rate")
    planned = _call("POST", "/v1/limits", {**body, "dry_run": True})
    if planned.get("status") == "blocked":
        code = escape(str(planned.get("code")))
        console.print(f"{styled('blocked')} [dim]{code}[/dim]  {escape(planned['message'])}")
        raise typer.Exit(1)
    console.print(f"[bold]{escape(device)}.{escape(str(channel))}[/bold]")
    for name, step in planned.get("changes", {}).items():
        console.print(f"{name:<5} {escape(step['from'])} to {escape(step['to'])}")
    if planned.get("loosens"):
        with hub() as client:
            human = client.whoami().kind == "human"
        if human and _person_can_type(phrase):
            body["phrase"] = _tty.require_phrase(PHRASE, WHAT, given=phrase)
    result = _call("POST", "/v1/limits", body)
    status = str(result.get("status"))
    code = f" [dim]{escape(str(result['code']))}[/dim]" if result.get("code") else ""
    console.print(f"{styled(status)}{code}  {escape(str(result.get('message', '')))}")
    if status == "blocked":
        raise typer.Exit(1)
