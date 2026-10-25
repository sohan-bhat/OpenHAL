"""Propose device file sections from an OpenAPI 3 document (https://spec.openapis.org/oas/v3.1.0).

The mapping is deliberately narrow, so every proposal is something the http driver can really do.

- A GET operation without path parameters whose 200 response is a JSON object becomes one read
  channel per scalar property, one level of nesting deep.
- A PUT, POST or PATCH operation whose JSON request body is an object becomes one write channel per
  scalar property. Numbers need `minimum` and `maximum` in the schema, because a write channel
  needs limits. Every write channel is marked `suggested: true`.
- A POST operation without a request body becomes an action, also marked `suggested: true`.

The document is device data. Its text is never treated as instructions, only as structure, and
only local `$ref` pointers (`#/components/...`) are followed, at most a few levels deep.
"""

from __future__ import annotations

import re
from typing import Any, Final

_MAX_REF_DEPTH: Final = 6
_SLUG: Final = re.compile(r"[^a-z0-9]+")


def _resolve(document: dict[str, Any], schema: Any, depth: int = 0) -> Any:
    if not isinstance(schema, dict):
        return {}
    ref = schema.get("$ref")
    if isinstance(ref, str):
        if depth >= _MAX_REF_DEPTH or not ref.startswith("#/"):
            return {}
        target: Any = document
        for part in ref[2:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            if not isinstance(target, dict) or part not in target:
                return {}
            target = target[part]
        return _resolve(document, target, depth + 1)
    return schema


def _mapping(value: Any) -> dict[Any, Any]:
    return value if isinstance(value, dict) else {}


def _json_schema(document: dict[str, Any], container: Any) -> dict[str, Any]:
    if not isinstance(container, dict):
        return {}
    content = container.get("content")
    if not isinstance(content, dict):
        return {}
    for media, entry in content.items():
        if "json" in str(media) and isinstance(entry, dict):
            resolved = _resolve(document, entry.get("schema"))
            return resolved if isinstance(resolved, dict) else {}
    return {}


def _name(*parts: str) -> str:
    slug = _SLUG.sub("_", "_".join(parts).lower()).strip("_")
    if not slug or not slug[0].isalpha():
        slug = f"ch_{slug}".strip("_")
    return slug[:48].rstrip("_")


def _unique(name: str, taken: set[str]) -> str:
    candidate, index = name, 2
    while candidate in taken:
        suffix = f"_{index}"
        candidate = f"{name[: 48 - len(suffix)]}{suffix}"
        index += 1
    taken.add(candidate)
    return candidate


def _scalars(document: dict[str, Any], schema: dict[str, Any], prefix: tuple[str, ...] = ()) -> list[Any]:
    """(json path parts, resolved schema) for every scalar property, one nesting level deep."""
    found: list[Any] = []
    properties = schema.get("properties")
    if schema.get("type") not in (None, "object") or not isinstance(properties, dict):
        return found
    for key, raw in properties.items():
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_\-]*", key):
            continue
        prop = _resolve(document, raw)
        kind = prop.get("type")
        if kind in ("number", "integer", "boolean", "string"):
            found.append(((*prefix, key), prop))
        elif kind == "object" and not prefix:
            found.extend(_scalars(document, prop, (key,)))
    return found


def _unit(prop: dict[str, Any]) -> tuple[str, bool]:
    unit = prop.get("x-unit")
    if isinstance(unit, str) and unit.strip():
        return unit.strip()[:40], True
    return "dimensionless", False


def describe_openapi(document: Any, *, limit: int = 64) -> dict[str, Any]:
    """Map an OpenAPI document into device file sections. Never raises for odd documents."""
    if not isinstance(document, dict) or not str(document.get("openapi", "")).startswith("3"):
        return {"notes": "The openapi document is not an OpenAPI 3 JSON document, so nothing was proposed."}
    info = _mapping(document.get("info"))
    reads: dict[str, Any] = {}
    writes: dict[str, Any] = {}
    actions: dict[str, Any] = {}
    taken: set[str] = set()
    skipped: list[str] = []
    no_unit: list[str] = []
    paths = _mapping(document.get("paths"))
    for path, item in paths.items():
        if not isinstance(path, str) or not isinstance(item, dict) or not path.startswith("/"):
            continue
        if "{" in path:
            skipped.append(f"{path} (path parameters)")
            continue
        base = path.strip("/").replace("/", "_") or "root"
        get = item.get("get")
        if isinstance(get, dict):
            responses = _mapping(get.get("responses"))
            schema = _json_schema(document, _resolve(document, responses.get("200") or responses.get(200)))
            for parts, prop in _scalars(document, schema):
                if len(reads) + len(writes) >= limit:
                    break
                name = _unique(_name(base, *parts), taken)
                channel: dict[str, Any] = {"map": {"path": path, "json": "$." + ".".join(parts)}}
                kind = prop.get("type")
                if kind in ("number", "integer"):
                    unit, known = _unit(prop)
                    channel = {"unit": unit, **channel}
                    if not known:
                        no_unit.append(name)
                elif kind == "boolean":
                    channel = {"type": "bool", **channel}
                elif isinstance(prop.get("enum"), list) and all(isinstance(x, str) for x in prop["enum"]):
                    channel = {"type": "enum", "values": list(prop["enum"]), **channel}
                else:
                    channel = {"type": "string", **channel}
                reads[name] = channel
        for method in ("put", "post", "patch"):
            operation = item.get(method)
            if not isinstance(operation, dict):
                continue
            body = _resolve(document, operation.get("requestBody"))
            schema = _json_schema(document, body)
            if method == "post" and not body:
                name = _unique(_name(base), taken)
                actions[name] = {"map": {"path": path, "method": "POST"}, "suggested": True}
                summary = operation.get("summary")
                if isinstance(summary, str) and summary.strip():
                    actions[name]["description"] = summary.strip()[:200]
                continue
            for parts, prop in _scalars(document, schema):
                if len(parts) != 1 or len(reads) + len(writes) >= limit:
                    continue
                key = parts[0]
                known = True
                wmap = {"path": path, "method": method.upper(), "body": {key: "{value}"}}
                kind = prop.get("type")
                entry: dict[str, Any]
                if kind in ("number", "integer"):
                    low, high = prop.get("minimum"), prop.get("maximum")
                    if not isinstance(low, int | float) or not isinstance(high, int | float) or low > high:
                        skipped.append(f"{method.upper()} {path} {key} (no minimum and maximum in the schema)")
                        continue
                    unit, known = _unit(prop)
                    entry = {"unit": unit, "min": low, "max": high}
                    if kind == "integer":
                        entry["step"] = 1
                elif kind == "boolean":
                    entry = {"type": "bool"}
                elif isinstance(prop.get("enum"), list) and all(isinstance(x, str) for x in prop["enum"]):
                    entry = {"type": "enum", "values": list(prop["enum"])}
                elif isinstance(prop.get("maxLength"), int) and 1 <= prop["maxLength"] <= 4096:
                    entry = {"type": "string", "max_length": prop["maxLength"]}
                else:
                    skipped.append(f"{method.upper()} {path} {key} (string without maxLength)")
                    continue
                name = _unique(_name("set", base, key), taken)
                if entry.get("unit") == "dimensionless" and not known:
                    no_unit.append(name)
                writes[name] = {**entry, "map": wmap, "suggested": True}
    result: dict[str, Any] = {}
    title = info.get("title")
    if isinstance(title, str) and title.strip():
        result["device"] = {"name": title.strip()[:120]}
    if reads:
        result["read"] = reads
    if writes:
        result["write"] = writes
    if actions:
        result["actions"] = actions
    notes = ["Proposed from the device's OpenAPI document. Every write and action is suggested until a human confirms."]
    if no_unit:
        notes.append(f"These channels had no x-unit in the schema and use dimensionless: {', '.join(no_unit[:20])}.")
    if skipped:
        notes.append(f"Skipped: {'; '.join(skipped[:20])}.")
    result["notes"] = " ".join(notes)[:4000]
    return result
