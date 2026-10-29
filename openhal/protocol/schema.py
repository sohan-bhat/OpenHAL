"""The schema reference, generated from the message models and never written by hand (ADR 0015).

`uv run python -m openhal.protocol.schema` writes schema.json, a JSON Schema for every message, and
schema.md, a reference with every type and field, into the latest version's folder, such as
spec/v0.1/. A test checks both files are current.
"""

from __future__ import annotations

import inspect
import json
import types
from pathlib import Path
from typing import Any, Final, Union, get_args, get_origin

from pydantic.json_schema import models_json_schema

from openhal.protocol import messages as m
from openhal.protocol.errors import REGISTRY
from openhal.protocol.version import LATEST, label

ROOT: Final = Path(__file__).resolve().parents[2]
TARGET_DIR: Final = ROOT / "spec" / label(LATEST)
JSON_PATH: Final = TARGET_DIR / "schema.json"
MARKDOWN_PATH: Final = TARGET_DIR / "schema.md"
REF: Final = "#/$defs/{model}"


def message_models() -> list[type[m.Message]]:
    """Every protocol model, in the order the messages module defines them."""
    found = [
        item
        for _, item in inspect.getmembers(m, inspect.isclass)
        if issubclass(item, m.Message) and item is not m.Message and item.__module__ == m.__name__
    ]
    return sorted(found, key=lambda item: inspect.getsourcelines(item)[1])


def _ref(model: type[m.Message]) -> dict[str, str]:
    return {"$ref": REF.format(model=model.__name__)}


def _result(result: Any) -> dict[str, Any]:
    if get_origin(result) in (Union, types.UnionType):
        return {"anyOf": [_ref(item) for item in get_args(result)]}
    return _ref(result)


def document() -> dict[str, Any]:
    """The whole schema as one JSON Schema document."""
    _, defs = models_json_schema([(model, "validation") for model in message_models()], by_alias=True, ref_template=REF)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": f"OpenHAL hub protocol {label(LATEST)}",
        "description": "Generated from openhal/protocol/messages.py by python -m openhal.protocol.schema.",
        "protocolVersion": LATEST,
        "methods": {
            name: {
                "level": spec.level,
                "humanOnly": spec.human_only,
                "params": _ref(spec.params),
                "result": _result(spec.result),
            }
            for name, spec in m.METHODS.items()
        },
        "notifications": {
            name: {"level": level, "params": _ref(params)} for name, (params, level) in m.NOTIFICATIONS.items()
        },
        "clientNotifications": {name: {"params": _ref(params)} for name, params in m.CLIENT_NOTIFICATIONS.items()},
        "errors": [
            {"code": spec.code, "name": spec.name, "kernelCodes": list(spec.kernel_codes), "meaning": spec.meaning}
            for spec in REGISTRY
        ],
        "$defs": defs["$defs"],
    }


def _anchor(name: str) -> str:
    return name.lower()


def _type(prop: dict[str, Any]) -> str:
    """A field's type as short Markdown, with links to other types."""
    if "$ref" in prop:
        name = prop["$ref"].rsplit("/", 1)[-1]
        return f"[{name}](#{_anchor(name)})"
    if "const" in prop:
        return f"`{json.dumps(prop['const'])}`"
    if "enum" in prop:
        return " or ".join(f"`{json.dumps(value)}`" for value in prop["enum"])
    for key in ("anyOf", "oneOf"):
        if key in prop:
            return " or ".join(dict.fromkeys(_type(item) for item in prop[key]))
    kind = prop.get("type")
    if kind == "array":
        return f"list of {_type(prop.get('items', {}))}"
    if kind == "object":
        extra = prop.get("additionalProperties")
        if isinstance(extra, dict) and extra:
            return f"map of {_type(extra)}"
        return "object"
    if isinstance(kind, str):
        return kind
    return "any"


def _cell(text: str) -> str:
    return " ".join(text.replace("|", "\\|").split())


def _type_section(name: str, schema: dict[str, Any]) -> list[str]:
    lines = [f"### {name}", ""]
    if schema.get("description"):
        lines += [_cell(schema["description"]), ""]
    if "enum" in schema:
        lines += ["One of " + ", ".join(f"`{value}`" for value in schema["enum"]) + ".", ""]
        return lines
    properties = schema.get("properties", {})
    if not properties:
        lines += ["No fields.", ""]
        return lines
    required = set(schema.get("required", []))
    lines += ["| Field | Type | Required | Description |", "|---|---|---|---|"]
    for field, prop in properties.items():
        shown = "yes" if field in required else "no"
        lines.append(f"| `{field}` | {_type(prop)} | {shown} | {_cell(prop.get('description', ''))} |")
    if schema.get("additionalProperties") is True:
        lines += ["", "Other fields may be added in later versions."]
    lines.append("")
    return lines


def markdown(schema: dict[str, Any]) -> str:
    """The schema as a Markdown reference."""
    lines = [
        f"# Schema reference, {label(LATEST)}",
        "",
        "Generated from the reference models by `uv run python -m openhal.protocol.schema`. Do not edit it by hand.",
        "The JSON Schema is [schema.json](schema.json). Field names are as they travel on the wire.",
        "",
        "## Methods",
        "",
        "| Method | Level | Params | Result |",
        "|---|---|---|---|",
    ]
    for name, method in schema["methods"].items():
        level = method["level"].capitalize() + (", human only" if method["humanOnly"] else "")
        lines.append(f"| `{name}` | {level} | {_type(method['params'])} | {_type(method['result'])} |")
    lines += ["", "## Notifications", "", "| Notification | Sent by | Level | Params |", "|---|---|---|---|"]
    for name, item in schema["notifications"].items():
        lines.append(f"| `{name}` | Hub | {item['level'].capitalize()} | {_type(item['params'])} |")
    for name, item in schema["clientNotifications"].items():
        lines.append(f"| `{name}` | Client | Core | {_type(item['params'])} |")
    lines += ["", "## Errors", "", "| Code | Name | Kernel codes | Meaning |", "|---|---|---|---|"]
    for error in schema["errors"]:
        kernel = ", ".join(f"`{code}`" for code in error["kernelCodes"])
        lines.append(f"| {error['code']} | {error['name']} | {kernel} | {_cell(error['meaning'])} |")
    lines += ["", "## Types", ""]
    for name in sorted(schema["$defs"]):
        lines += _type_section(name, schema["$defs"][name])
    return "\n".join(lines).rstrip() + "\n"


def render() -> tuple[str, str]:
    """The contents of schema.json and schema.md."""
    schema = document()
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n", markdown(schema)


def main() -> None:
    schema_json, schema_md = render()
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(schema_json, encoding="utf-8")
    MARKDOWN_PATH.write_text(schema_md, encoding="utf-8")
    print(f"Wrote {JSON_PATH.relative_to(ROOT)} and {MARKDOWN_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
