"""`openhal token`, client tokens for agents and people (ADR 0012), and `openhal pair` for the dashboard.

Token commands use the hub's token routes when the hub has them. When the hub is not running, or is
older and has no token routes, they work on the hub database in the config folder directly, the same
way `openhal init` creates the first human token. Only the person who owns the config folder can do
that, because it is readable by its owner alone.
"""

from __future__ import annotations

import typer
from rich.markup import escape
from rich.table import Table

from openhal.cli._common import EXIT_FAILED, config, console, err, fail, handled, hub, print_json, when
from openhal.client import HubNotRunning, NotSupported
from openhal.client.models import NewToken, TokenInfo

app = typer.Typer(help="Create, list and revoke tokens for agents and people.", no_args_is_help=True)

SCOPES = ("read", "control_low", "control_medium")


def _local_store() -> object:
    from openhal.hub.tokens import TokenStore

    path = config().db_path
    if not path.exists():
        fail("There is no hub database yet. Run openhal init first.")
    return TokenStore(path)


def _note_local(reason: str) -> None:
    err.print(f"[dim]{escape(reason)} Working on {escape(str(config().db_path))} directly.[/dim]")


@app.command()
@handled
def create(
    name: str = typer.Option(..., "--name", "-n", help="Who uses it, for example claude or cursor."),
    agent: bool = typer.Option(True, "--agent/--human", help="An agent token (default) or a human token."),
    scope: str = typer.Option("read", "--scope", "-s", help="read, control_low or control_medium. Agents only."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON."),
) -> None:
    """Create a token and print it once. The hub keeps only its hash."""
    if scope not in SCOPES:
        raise ValueError(f"--scope must be one of {', '.join(SCOPES)}.")
    kind = "agent" if agent else "human"
    try:
        with hub() as client:
            created = client.create_token(name, kind=kind, scope=scope)
    except (HubNotRunning, NotSupported) as exc:
        _note_local("The hub is not running." if isinstance(exc, HubNotRunning) else "The hub has no token routes.")
        from openhal.hub.tokens import TokenStore

        store = _local_store()
        assert isinstance(store, TokenStore)
        token, info = store.create(name, kind, scope)  # type: ignore[arg-type]
        store.close()
        created = NewToken(
            token=token,
            token_id=info.token_id,
            name=info.name,
            kind=info.kind,
            scope=info.scope,
            created_at=info.created_at,
        )
    if as_json:
        print_json(created)
        return
    console.print(
        f"Created {escape(created.kind)} token {escape(created.token_id)} for {escape(created.name)}, "
        f"scope {escape(created.scope)}."
    )
    console.print("This is the only time it is shown. Store it in your MCP client config as OPENHAL_TOKEN.")
    typer.echo(created.token)


def _list() -> list[TokenInfo]:
    try:
        with hub() as client:
            return client.tokens()
    except (HubNotRunning, NotSupported) as exc:
        _note_local("The hub is not running." if isinstance(exc, HubNotRunning) else "The hub has no token routes.")
        from openhal.hub.tokens import TokenStore

        store = _local_store()
        assert isinstance(store, TokenStore)
        found = [
            TokenInfo(
                token_id=info.token_id,
                name=info.name,
                kind=info.kind,
                scope=info.scope,
                created_at=info.created_at,
                revoked=info.revoked,
            )
            for info in store.list()
        ]
        store.close()
        return found


@app.command("list")
@handled
def list_tokens(
    show_revoked: bool = typer.Option(False, "--all", help="Include revoked tokens."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON."),
) -> None:
    """List tokens. Tokens themselves are never shown again, only their ids."""
    tokens = [info for info in _list() if show_revoked or not info.revoked]
    if as_json:
        print_json(tokens)
        return
    table = Table("id", "name", "kind", "scope", "created", "state", box=None, pad_edge=False)
    for info in tokens:
        state = "[red]revoked[/red]" if info.revoked else "[green]active[/green]"
        table.add_row(
            escape(info.token_id),
            escape(info.name),
            escape(info.kind),
            escape(info.scope),
            when(info.created_at),
            state,
        )
    console.print(table)


@app.command()
@handled
def revoke(token_id: str = typer.Argument(..., help="The token id from openhal token list.")) -> None:
    """Revoke a token. Clients using it get 401 from then on."""
    try:
        with hub() as client:
            client.revoke_token(token_id)
    except (HubNotRunning, NotSupported) as exc:
        _note_local("The hub is not running." if isinstance(exc, HubNotRunning) else "The hub has no token routes.")
        from openhal.hub.tokens import TokenStore

        store = _local_store()
        assert isinstance(store, TokenStore)
        revoked = store.revoke(token_id)
        store.close()
        if not revoked:
            fail(f"There is no active token {token_id}.")
    console.print(f"revoked {escape(token_id)}")


def register(root: typer.Typer) -> None:
    @root.command()
    @handled
    def pair() -> None:
        """Print a one-time code that pairs a browser with the dashboard as you. Needs the human token."""
        with hub() as client:
            code = client.new_pairing_code()
            url = client.url
        console.print(
            f"Open {escape(url)}/ and enter this code. It works once and expires in {code.expires_in_s:.0f} s."
        )
        typer.echo(code.code)
        if not code.code.isdigit():
            raise typer.Exit(EXIT_FAILED)
