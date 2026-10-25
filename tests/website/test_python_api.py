"""The website's Python API reference must match openhal.client's docstrings and signatures."""

from __future__ import annotations

import json

import openhal.client as client
from tests.website import python_api


def test_reference_is_current() -> None:
    saved = json.loads(python_api.OUTPUT.read_text(encoding="utf-8"))
    assert saved == json.loads(python_api.render(python_api.generate())), (
        "Run uv run python -m tests.website.python_api."
    )


def test_every_public_name_is_documented() -> None:
    listed = {name for names in python_api.GROUPS.values() for name in names}
    public = set(client.__all__) - {"split_target"}
    assert public <= listed, f"Add these to python_api.GROUPS: {sorted(public - listed)}"
