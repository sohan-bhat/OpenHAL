"""Generate the Python SDK reference for the website from openhal.client's docstrings.

Run `uv run python -m tests.website.python_api` to rewrite
website/src/content/generated/python-api.json. tests/website/test_python_api.py checks it is current.
"""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path
from typing import Any

import openhal.client as client

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "website" / "src" / "content" / "generated" / "python-api.json"

GROUPS = {
    "Connect": ["connect", "aconnect", "Client", "AsyncClient"],
    "Commands": ["Write", "Action"],
    "Results": [
        "Decision",
        "Reading",
        "Image",
        "HubStatus",
        "DeviceSummary",
        "DeviceView",
        "StopReport",
        "ConfirmationRequest",
    ],
    "Routines and audit": ["RoutineSummary", "Routine", "AuditEntry", "WriterSession"],
    "Errors": [
        "OpenHALError",
        "HubNotRunning",
        "Unauthorized",
        "NotFound",
        "NotSupported",
        "Refused",
        "BadRequest",
        "HubError",
    ],
}


def clean_signature(obj: Any) -> str:
    try:
        text = str(inspect.signature(obj))
    except (TypeError, ValueError):
        return "()"
    text = re.sub(r"<([\w.]+) object at 0x[0-9a-f]+>", r"\1", text)
    text = re.sub(r"<function ([\w.]+) at 0x[0-9a-f]+>", r"\1", text)
    text = re.sub(r"\bm\.", "", text.replace("'", ""))
    return text.replace("openhal.client.", "").replace("openhal.kernel.commands.", "")


def doc_of(obj: Any) -> str:
    return inspect.cleandoc(obj.__doc__) if obj.__doc__ else ""


def is_pydantic(obj: Any) -> bool:
    return hasattr(obj, "model_fields")


def fields_of(obj: Any) -> list[dict[str, str]]:
    out = []
    for name, field in obj.model_fields.items():
        annotation = field.annotation
        type_text = getattr(annotation, "__name__", None) or str(annotation)
        type_text = type_text.replace("typing.", "").replace("openhal.client.models.", "")
        out.append({"name": name, "type": type_text, "doc": field.description or ""})
    return out


def methods_of(obj: Any) -> list[dict[str, str]]:
    out = []
    for name, member in inspect.getmembers(obj):
        if name.startswith("_") or not (inspect.isfunction(member) or inspect.iscoroutinefunction(member)):
            continue
        if member.__qualname__.split(".")[0] != obj.__name__:
            continue
        prefix = "async " if inspect.iscoroutinefunction(member) else ""
        signature = clean_signature(member).replace("(self, ", "(").replace("(self)", "()")
        out.append({"name": name, "signature": f"{prefix}{name}{signature}", "doc": doc_of(member)})
    return sorted(out, key=lambda item: item["name"])


def describe(name: str) -> dict[str, Any]:
    obj = getattr(client, name)
    if inspect.isclass(obj):
        entry: dict[str, Any] = {"name": name, "kind": "class", "doc": doc_of(obj)}
        if issubclass(obj, Exception):
            entry["kind"] = "exception"
            entry["bases"] = [base.__name__ for base in obj.__bases__]
        elif is_pydantic(obj):
            entry["fields"] = fields_of(obj)
        else:
            entry["signature"] = f"{name}{clean_signature(obj)}"
            entry["methods"] = methods_of(obj)
        return entry
    prefix = "async " if inspect.iscoroutinefunction(obj) else ""
    return {"name": name, "kind": "function", "signature": f"{prefix}{name}{clean_signature(obj)}", "doc": doc_of(obj)}


def generate() -> dict[str, Any]:
    return {
        "module": "openhal.client",
        "doc": doc_of(client),
        "groups": [{"name": group, "items": [describe(name) for name in names]} for group, names in GROUPS.items()],
    }


def render(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(render(generate()), encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
