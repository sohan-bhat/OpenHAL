"""Where the client finds the hub and its token.

Token lookup order, first match wins.
1. The `token` argument.
2. The `OPENHAL_TOKEN` environment variable.
3. The human token file, `$OPENHAL_HOME/human.token` or `~/.openhal/human.token`.

The MCP server skips step 3 on purpose. An agent must never run with the human token.

Hub address order. The `url` argument, the `OPENHAL_URL` environment variable, then `api.host`
and `api.port` from `config.yaml`, then http://127.0.0.1:7420.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import yaml

from openhal._brand import DEFAULT_HOST, DEFAULT_PORT, config_dir

TOKEN_ENV: Final = "OPENHAL_TOKEN"  # noqa: S105 (a variable name, not a secret)
URL_ENV: Final = "OPENHAL_URL"
HUMAN_TOKEN_FILE: Final = "human.token"  # noqa: S105 (a file name)


@dataclass(frozen=True, slots=True)
class TokenSource:
    """A token and a short description of where it came from, used in error messages."""

    token: str | None
    origin: str

    def describe(self) -> str:
        return self.origin


def home_dir(home: Path | str | None = None) -> Path:
    return Path(home).expanduser() if home is not None else config_dir()


def human_token_path(home: Path | str | None = None) -> Path:
    return home_dir(home) / HUMAN_TOKEN_FILE


def read_token_file(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    return text or None


def resolve_token(
    token: str | None = None, *, home: Path | str | None = None, use_human_file: bool = True
) -> TokenSource:
    """Find the token to send. Returns a source with `token=None` when there is none."""
    if token:
        return TokenSource(token.strip(), "the token argument")
    env = os.environ.get(TOKEN_ENV, "").strip()
    if env:
        return TokenSource(env, f"the {TOKEN_ENV} environment variable")
    if use_human_file:
        path = human_token_path(home)
        found = read_token_file(path)
        if found:
            return TokenSource(found, str(path))
        return TokenSource(None, f"no token argument, no {TOKEN_ENV} and no {path}")
    return TokenSource(None, f"no token argument and no {TOKEN_ENV}")


def resolve_url(url: str | None = None, *, home: Path | str | None = None) -> str:
    """Find the hub's base URL."""
    if url:
        return url.rstrip("/")
    env = os.environ.get(URL_ENV, "").strip()
    if env:
        return env.rstrip("/")
    host, port = DEFAULT_HOST, DEFAULT_PORT
    try:
        from openhal.hub.config import load_config

        config = load_config(home_dir(home))
        host, port = config.api.host, config.api.port
    except (ValueError, OSError, yaml.YAMLError):
        pass
    if host in ("0.0.0.0", "::", ""):  # noqa: S104 (a listen address, mapped to loopback for clients)
        host = DEFAULT_HOST
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"http://{host}:{port}"
