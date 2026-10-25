"""The generated schema reference is current and covers every method, notification, error and type."""

from __future__ import annotations

import json

from openhal.protocol import messages as m
from openhal.protocol import schema
from openhal.protocol.errors import REGISTRY

REGENERATE = "Run uv run python -m openhal.protocol.schema"


def test_schema_files_are_current() -> None:
    schema_json, schema_md = schema.render()
    assert schema.JSON_PATH.read_text(encoding="utf-8") == schema_json, REGENERATE
    assert schema.MARKDOWN_PATH.read_text(encoding="utf-8") == schema_md, REGENERATE


def test_schema_covers_every_message() -> None:
    document = json.loads(schema.JSON_PATH.read_text(encoding="utf-8"))
    assert list(document["methods"]) == list(m.METHODS)
    assert list(document["notifications"]) == list(m.NOTIFICATIONS)
    assert set(document["clientNotifications"]) == {"hal/initialized", "hal/shutdown"}
    assert [(item["code"], item["name"]) for item in document["errors"]] == [
        (spec.code, spec.name) for spec in REGISTRY
    ]
    assert {model.__name__ for model in schema.message_models()} <= set(document["$defs"])
    decision = document["$defs"]["Decision"]
    assert set(decision["properties"]) == {"status", "device", "target", "value", "unit", "error", "requestId"}
    assert set(decision["required"]) == {"status", "device", "target"}
    wait = document["$defs"]["Wait"]
    assert set(wait["properties"]) == {"kind", "duration"}
    assert document["methods"]["hal/write"]["result"] == {
        "anyOf": [{"$ref": "#/$defs/WriteDone"}, {"$ref": "#/$defs/Pending"}]
    }


def test_the_markdown_reference_names_every_type_and_field() -> None:
    text = schema.MARKDOWN_PATH.read_text(encoding="utf-8")
    document = json.loads(schema.JSON_PATH.read_text(encoding="utf-8"))
    for name, definition in document["$defs"].items():
        assert f"### {name}\n" in text
        for field in definition.get("properties", {}):
            assert f"| `{field}` |" in text
    for method in m.METHODS:
        assert f"| `{method}` |" in text
