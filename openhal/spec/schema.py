"""Export the device file JSON Schema from the reference models."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from openhal._brand import SPEC_VERSION
from openhal.spec.models import DeviceFile


def device_file_schema() -> dict[str, Any]:
    """The JSON Schema for a device file, as published in spec/schema/."""
    schema = DeviceFile.model_json_schema(by_alias=True, mode="validation")
    schema["properties"].pop("extensions", None)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"https://openhal.dev/schema/{SPEC_VERSION}/device-file.schema.json"
    schema["title"] = "OpenHAL device file"
    schema["description"] = f"An OpenHAL device file, spec version {SPEC_VERSION}. See spec/SPEC.md."
    schema["patternProperties"] = {"^x-": {}}
    for name in ("device", "safe_state"):
        prop = schema["properties"][name]
        if name == "device":
            schema["properties"][name] = {"anyOf": [{"type": "string", "minLength": 1, "maxLength": 120}, prop]}
        else:
            schema["properties"][name] = {"anyOf": [{"type": "object"}, prop]}
    return schema


def write_schema(path: Path) -> None:
    """Write the schema with stable formatting so diffs stay readable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(device_file_schema(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    write_schema(Path(__file__).resolve().parents[2] / "spec" / "schema" / "device-file.schema.json")
