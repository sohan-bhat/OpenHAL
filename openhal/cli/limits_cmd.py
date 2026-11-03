"""`openhal limits`, showing and changing a channel's limits with no device file to edit.

A bare `openhal limits` shows every device's limits in one table and one change to copy, built from
the person's own devices. A narrower limit applies at once. A wider limit needs a person, so in an
interactive terminal the command shows the change and takes the typed phrase confirm, as
`openhal file confirm` does. Where no phrase can be typed, such as a script, an agent's shell or a
command run from inside an AI client, the change becomes a pending limit change for a person to
approve. At a terminal, `openhal limits set` with nothing else walks through the device, the
channel and the new value (ADR 0020).
"""

from __future__ import annotations

import difflib
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import typer
from rich.markup import escape
from rich.table import Table

from openhal.cli import _choices, _pick, _tty
from openhal.cli._choices import NO_DEVICES, Need
from openhal.cli._common import config, console, fail, handled, hub, parse_quantity_text, print_json, show, styled
from openhal.cli._pick import Option

if TYPE_CHECKING:
    from openhal.client import Client

app = typer.Typer(help="Show and change a device's limits. Narrowing applies at once, widening needs a person.")

PHRASE = "confirm"
WHAT = "widen these limits"
FIELDS = {"max": "--max", "min": "--min", "rate": "--rate"}


def _split(target: str) -> tuple[str, str | None]:
    device, dot, channel = target.partition(".")
    if not device or (dot and not channel):
        raise ValueError(
            f"Give the target as DEVICE or DEVICE.CHANNEL, for example bench-lamp.brightness. Got {target!r}."
        )
    return device, channel or None


def _request(client: Client, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    from openhal.client.calls import Call

    return client.call(Call(method, path, dict, json=body))


def _limits(client: Client, device: str) -> dict[str, Any]:
    return _request(client, "GET", f"/v1/devices/{quote(device, safe='')}/limits")


def _call(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    with hub() as client:
        return _request(client, method, path, body)


def _every() -> list[dict[str, Any]]:
    with hub() as client:
        return [_limits(client, item.id) for item in client.devices()]


def _range(low: float | None, high: float | None, unit: str | None) -> str:
    return f"{show(low, unit)} to {show(high, unit)}"


def _rate(spec: dict[str, Any]) -> str:
    return f"{show(spec['rate'], spec.get('unit'))}/s" if spec.get("rate") is not None else "no limit"


def _reported(spec: dict[str, Any]) -> str:
    reported = spec.get("device_range")
    return _range(reported[0], reported[1], spec.get("unit")) if reported else "not reported"


def _quoted(text: str) -> str:
    return f'"{text}"' if " " in text else text


def _example(device: str, channel: str, spec: dict[str, Any]) -> str:
    """A narrower max for this channel as a command to copy, a quarter of the way down from the max."""
    high, low, unit = spec.get("max"), spec.get("min"), spec.get("unit")
    if high is None:
        return f"openhal limits set {device}.{channel} --rate {_quoted(show(1, unit) + '/s')}"
    span = high - (low if low is not None else 0)
    value = high - span / 4
    value = round(value) if abs(span) >= 10 else round(value, 1)
    return f"openhal limits set {device}.{channel} --max {_quoted(show(value, unit))}"


def _row(name: str, spec: dict[str, Any]) -> list[str]:
    unit = spec.get("unit")
    return [
        escape(name),
        escape(_range(spec.get("min"), spec.get("max"), unit)),
        escape(_rate(spec)),
        escape(_reported(spec)),
        escape(spec.get("confirm") or ""),
    ]


def _read_only(data: dict[str, Any]) -> None:
    if not data.get("writable"):
        console.print(
            f"{escape(str(data['device']))} has high risk entries that stay read-only. Answer their limits with "
            f"openhal file confirm {escape(str(data.get('path')))}"
        )


@app.callback(invoke_without_command=True)
@handled
def overview(ctx: typer.Context, as_json: bool = typer.Option(False, "--json", help="Print JSON.")) -> None:
    """Every device's limits in one table, and one change to copy."""
    if ctx.invoked_subcommand is not None:
        return
    every = _every()
    if as_json:
        print_json(every)
        return
    if not every:
        console.print(NO_DEVICES)
        return
    table = Table("device", "channel", "min to max", "max change", "device range", "confirm", box=None, pad_edge=False)
    for data in every:
        for name, spec in data.get("channels", {}).items():
            table.add_row(escape(str(data["device"])), *_row(name, spec))
    if not table.rows:
        console.print("No device has a number channel with limits. openhal devices lists each device's channels.")
        return
    console.print(table)
    for data in every:
        _read_only(data)
    device, channel, spec = next(
        (str(data["device"]), name, spec)
        for data in sorted(every, key=lambda item: not item.get("writable"))
        for name, spec in data.get("channels", {}).items()
    )
    console.print(
        f"Change a limit with {escape(_example(device, channel, spec))}, or pick each step with openhal limits set"
    )


def _devices() -> list[Option]:
    with hub() as client:
        found = client.devices()
    return [Option(item.id, f"{item.name}{'' if item.writable else ', read-only'}") for item in found]


def _shown_device(as_json: bool) -> str:
    spec = Need(
        "openhal limits show", "a device", "devices", placeholder="DEVICE", empty=NO_DEVICES, every="openhal devices"
    )
    return _choices.need(spec, _devices, as_json=as_json)


def _settable_device() -> str:
    """The device to change a limit on, picked from the devices that have a number channel with limits."""
    found: list[dict[str, Any]] = []

    def options() -> list[Option]:
        found.extend(data for data in _every() if data.get("channels"))
        return [
            Option(str(data["device"]), ", ".join(data["channels"]) + ("" if data.get("writable") else ", read-only"))
            for data in found
        ]

    def example(device: str) -> str:
        for data in found:
            if data["device"] == device:
                name, spec = next(iter(data["channels"].items()))
                return _example(device, name, spec)
        return f"openhal limits set {device}.CHANNEL --max VALUE"

    spec = Need(
        "openhal limits set",
        "a device",
        "devices",
        placeholder="DEVICE",
        example=example,
        empty="The hub has no device with a number channel that has limits.",
        every="openhal limits",
    )
    return _choices.need(spec, options)


def _now(spec: dict[str, Any]) -> str:
    unit = spec.get("unit")
    return (
        f"{_range(spec.get('min'), spec.get('max'), unit)}, max change {_rate(spec)}, device reports {_reported(spec)}"
    )


def _channel(data: dict[str, Any], channel: str | None) -> str:
    """The channel the person named or picks to change, which must be a number channel with limits."""
    device = str(data["device"])
    channels: dict[str, Any] = data.get("channels", {})
    if channel is not None and channel in channels:
        return channel
    if channel is not None:
        near = difflib.get_close_matches(channel, list(channels), n=3)
        hint = f" Did you mean {_choices.joined(near, 'or')}?" if near else ""
        known = f" Channels with limits are {_choices.joined(list(channels))}." if channels and not near else ""
        raise ValueError(f"{device} has no number channel {channel!r} with limits.{hint}{known}")
    need = Need(
        "openhal limits set",
        f"a channel of {device}",
        "channels",
        placeholder="CHANNEL",
        example=lambda name: _example(device, name, channels[name]),
        empty=f"{device} has no number channel with limits.",
    )
    return _choices.need(need, lambda: [Option(name, _now(limits)) for name, limits in channels.items()])


@app.command("show")
@handled
def show_limits(
    target: str = typer.Argument(None, help="DEVICE, or DEVICE.CHANNEL for one channel. A terminal shows a picker."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON."),
) -> None:
    """Show each limit and the range the device itself reports."""
    device, channel = _split(target or _shown_device(as_json))
    with hub() as client:
        data = _limits(client, device)
    channels = data.get("channels", {})
    if channel is not None:
        channels = {channel: channels[_channel(data, channel)]}
    if as_json:
        print_json({**data, "channels": channels})
        return
    table = Table("channel", "min to max", "max change", "device range", "confirm", box=None, pad_edge=False)
    for name, spec in channels.items():
        table.add_row(*_row(name, spec))
    console.print(table)
    confirmed = data.get("confirmed")
    if data.get("writable") and confirmed:
        console.print(f"confirmed by {escape(str(confirmed['by']))} on {escape(str(confirmed['at']))}")
    _read_only(data)


def _person_can_type(phrase: str | None) -> bool:
    """Whether a phrase can come from a person here. Fails for --phrase while a terminal is required."""
    require_tty = config().confirm.require_tty
    if require_tty and phrase is not None:
        fail(f"--phrase can't be used while confirm.require_tty is true. Run this in a terminal and type {PHRASE}.")
    if require_tty:
        return _tty.interactive()
    return phrase is not None or _tty.interactive()


def _new_value(device: str, channel: str, spec: dict[str, Any]) -> tuple[str, str]:
    """At a terminal, the limit to change and its new value. Anywhere else, the error with a command to copy."""
    unit = spec.get("unit")
    if not _pick.available():
        need = Need(
            "openhal limits set", "--min, --max or --rate", "now", example=lambda _: _example(device, channel, spec)
        )
        _choices.missing(need, [_now(spec)])
    field = _pick.choose(
        f"Pick the limit to change on {device}.{channel}",
        [
            Option("max", f"the most an agent may set, now {show(spec.get('max'), unit)}"),
            Option("min", f"the least an agent may set, now {show(spec.get('min'), unit)}"),
            Option("rate", f"the largest change per second, now {_rate(spec)}"),
        ],
    )
    current = _rate(spec) if field == "rate" else show(spec.get(field), unit)
    sample = f"{show(1, unit)}/s, or none" if field == "rate" else show(spec.get("max"), unit)

    def check(text: str) -> str | None:
        if field == "rate" and text.lower() == "none":
            return None
        try:
            parse_quantity_text(text, FIELDS[field])
        except ValueError as exc:
            return str(exc)
        return None

    text = _pick.ask(
        f"New {field} for {device}.{channel}",
        check,
        default="" if current in ("unknown", "no limit") else current,
        hint=f"(with its unit, such as {sample}. The device reports {_reported(spec)}.)",
    )
    return field, text


@app.command("set")
@handled
def set_limits(
    target: str = typer.Argument(
        None, help="DEVICE.CHANNEL, for example bench-lamp.brightness. A terminal shows a picker."
    ),
    low: str = typer.Option(None, "--min", help="The new min with its unit, for example 10 %."),
    high: str = typer.Option(None, "--max", help="The new max with its unit, for example 80 %."),
    rate: str = typer.Option(None, "--rate", help="The new max change per second, for example 5 %/s, or none."),
    phrase: str = typer.Option(None, "--phrase", help="Only when confirm.require_tty is false."),
) -> None:
    """Change a channel's limits. A wider limit takes a person's typed phrase or waits for a person to approve."""
    walked = target is None or "." not in target or (low is None and high is None and rate is None)
    device, channel = _split(target or _settable_device())
    with hub() as client:
        data = _limits(client, device)
    channel = _channel(data, channel)
    values = {"min": low, "max": high, "rate": rate}
    if low is None and high is None and rate is None:
        field, text = _new_value(device, channel, data["channels"][channel])
        values[field] = text
    body: dict[str, Any] = {"device": device, "channel": channel}
    for field, text in values.items():
        if text is None:
            continue
        if field == "rate" and text.strip().lower() == "none":
            body["rate"] = "none"
        else:
            body[field] = parse_quantity_text(text, FIELDS[field])
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
    if walked:
        flags = " ".join(f"{FIELDS[field]} {_quoted(text)}" for field, text in values.items() if text is not None)
        console.print(
            f"The same change in one line is openhal limits set {escape(device)}.{escape(channel)} {escape(flags)}"
        )
    if status == "blocked":
        raise typer.Exit(1)
