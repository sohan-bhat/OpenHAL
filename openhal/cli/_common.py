"""Shared pieces of the CLI. Options, the hub client, error handling and output helpers.

Exit codes. 0 success, 1 blocked or failed, 2 usage error, 3 hub not running, 4 token problem.
"""

from __future__ import annotations

import datetime as dt
import functools
import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn

import typer
from rich.console import Console
from rich.markup import escape

from openhal.client.settings import home_dir, read_token_file
from openhal.spec.units import split_quantity

if TYPE_CHECKING:
    import httpx

    from openhal.client import Client
    from openhal.client.models import Decision
    from openhal.hub.config import HubConfig

console = Console(highlight=False, soft_wrap=True)
err = Console(stderr=True, highlight=False, soft_wrap=True)

EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_NO_HUB = 3
EXIT_TOKEN = 4


@dataclass
class Options:
    url: str | None = None
    token_file: Path | None = None


OPTIONS = Options()
TRANSPORT: httpx.BaseTransport | None = None
"""Set by tests to serve the API in-process. Always None in normal use."""


def home() -> Path:
    return home_dir()


def config() -> HubConfig:
    from openhal.hub.config import HubConfig, load_config

    try:
        return load_config(home())
    except (ValueError, OSError) as exc:
        err.print(f"[yellow]note[/yellow]  {home() / 'config.yaml'} could not be read ({exc}). Using defaults.")
        return HubConfig(home=home())


def hub() -> Client:
    """A client for the hub, using the global options and the usual token lookup."""
    from openhal.client import Client

    token = None
    if OPTIONS.token_file is not None:
        token = read_token_file(OPTIONS.token_file.expanduser())
        if token is None:
            fail(f"The token file {OPTIONS.token_file} is missing or empty.", EXIT_TOKEN)
    return Client(OPTIONS.url, token, transport=TRANSPORT)


def fail(message: str, code: int = EXIT_FAILED) -> NoReturn:
    err.print(f"[red]error[/red]  {escape(message)}")
    raise typer.Exit(code)


@contextmanager
def errors() -> Iterator[None]:
    """Turn client exceptions into one clear line and an exit code."""
    from openhal.client import HubNotRunning, NotSupported, OpenHALError, Unauthorized

    try:
        yield
    except HubNotRunning as exc:
        fail(str(exc), EXIT_NO_HUB)
    except Unauthorized as exc:
        fail(str(exc), EXIT_TOKEN)
    except NotSupported as exc:
        fail(str(exc))
    except OpenHALError as exc:
        fail(str(exc))
    except ValueError as exc:
        fail(str(exc), EXIT_USAGE)


def handled[**P, R](command: Callable[P, R]) -> Callable[P, R]:
    """Decorator form of `errors()` for command functions."""

    @functools.wraps(command)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        with errors():
            return command(*args, **kwargs)
        raise AssertionError("unreachable")  # pragma: no cover

    return wrapper


def print_json(data: Any) -> None:
    from pydantic import BaseModel

    def plain(item: Any) -> Any:
        if isinstance(item, BaseModel):
            return item.model_dump(mode="json", by_alias=True)
        if isinstance(item, list):
            return [plain(value) for value in item]
        return item

    typer.echo(json.dumps(plain(data), indent=2, sort_keys=False, default=str))


def when(at: float | None) -> str:
    if at is None:
        return ""
    return dt.datetime.fromtimestamp(at).strftime("%Y-%m-%d %H:%M:%S")


def show(value: Any, unit: str | None = None) -> str:
    from openhal.client.models import Image

    if value is None:
        return "unknown"
    if isinstance(value, Image):
        size = f", {value.width} x {value.height}" if value.width and value.height else ""
        return f"{value.mime_type}{size}, {value.bytes} bytes"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        value = f"{value:.6g}"
    if unit:
        return f"{value} {'%' if unit == 'percent' else unit}"
    return str(value)


STATUS_STYLE = {
    "done": "green",
    "allowed": "green",
    "ok": "green",
    "safe": "green",
    "blocked": "red",
    "failed": "red",
    "rejected": "red",
    "pending": "yellow",
    "needs_confirmation": "yellow",
    "partial": "yellow",
    "no_safe_state": "yellow",
    "expired": "dim",
    "cancelled": "dim",
}


def styled(status: str | None) -> str:
    text = status or ""
    style = STATUS_STYLE.get(text)
    return f"[{style}]{escape(text)}[/{style}]" if style else escape(text)


def print_decision(decision: Decision, *, prefix: str = "") -> None:
    code = f" [dim]{escape(decision.code)}[/dim]" if decision.code and decision.status != "done" else ""
    console.print(f"{prefix}{styled(decision.status)}{code}  {escape(decision.message)}")
    if decision.pending and decision.request_id:
        console.print(
            f"{prefix}  held for a person. Approve with openhal confirm approve {decision.request_id}",
            style="yellow",
        )


def exit_for(decision: Decision) -> None:
    if decision.status in ("blocked", "failed"):
        raise typer.Exit(EXIT_FAILED)


def parse_bool(text: str) -> bool:
    lowered = text.strip().lower()
    if lowered in ("true", "on", "yes", "1"):
        return True
    if lowered in ("false", "off", "no", "0"):
        return False
    raise ValueError(f"Use true or false, not {text!r}.")


def parse_quantity_text(text: str, name: str) -> dict[str, Any]:
    """Typed text such as `60%` or `2 s` as the Quantity mapping the hub takes (ADR 0016)."""
    found = split_quantity(text)
    if found is None:
        raise ValueError(f"{name} needs a number with a unit, for example 60 % or 2 s. Got {text!r}.")
    return found


def typed(text: str, kind: str | None, name: str) -> Any:
    """Typed text in the shape a channel or argument of `kind` takes. Numbers become Quantity mappings."""
    if kind == "bool":
        return parse_bool(text)
    if kind == "number":
        return parse_quantity_text(text, name)
    return text


def parse_pairs(pairs: list[str], types: dict[str, str] | None = None) -> dict[str, Any]:
    """Parse key=value arguments. Bool arguments become true or false, numbers become Quantity mappings."""
    parsed: dict[str, Any] = {}
    for pair in pairs:
        key, eq, value = pair.partition("=")
        if not eq or not key:
            raise ValueError(f"Arguments look like key=value, for example seconds=2s. Got {pair!r}.")
        parsed[key] = typed(value, (types or {}).get(key), key)
    return parsed
