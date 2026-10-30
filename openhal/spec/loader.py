"""Load device files safely and report problems with their exact location.

YAML anchors, aliases and custom tags are load errors (spec section 0), which also rules out
billion-laughs style expansion. Files are size-limited before parsing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import yaml
from pydantic import ValidationError

from openhal.spec.models import DeviceFile

MAX_FILE_BYTES: Final = 256 * 1024


class DeviceFileError(ValueError):
    """A device file could not be loaded. `problems` lists each issue with its location."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("; ".join(problems))


_ALLOWED_TAGS: Final = frozenset(
    {"!"} | {f"tag:yaml.org,2002:{name}" for name in ("str", "int", "float", "bool", "null", "seq", "map", "timestamp")}
)


class _NoAliasLoader(yaml.SafeLoader):
    """A safe loader that raises an error on anchors, aliases and non-standard tags."""

    def compose_node(self, parent: Any, index: Any) -> Any:
        event: Any = self.peek_event()  # type: ignore[no-untyped-call]
        mark: Any = getattr(event, "start_mark", None)
        if type(event).__name__ == "AliasEvent":
            raise yaml.constructor.ConstructorError(None, None, "YAML aliases are not allowed in device files.", mark)
        anchor = getattr(event, "anchor", None)
        if anchor is not None:
            raise yaml.constructor.ConstructorError(None, None, "YAML anchors are not allowed in device files.", mark)
        tag = getattr(event, "tag", None)
        if tag is not None and tag not in _ALLOWED_TAGS:
            raise yaml.constructor.ConstructorError(
                None, None, f"Custom YAML tags such as {tag} are not allowed.", mark
            )
        return super().compose_node(parent, index)


_NoAliasLoader.yaml_implicit_resolvers = {
    key: [(tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:bool"]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_NoAliasLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
    list("tTfF"),
)


def _location(loc: tuple[int | str, ...]) -> str:
    parts: list[str] = []
    for item in loc:
        if isinstance(item, int):
            parts.append(f"[{item}]")
        elif item not in ("function-after[_cross_checks()]",) and not str(item).startswith(
            ("function-", "json-or-python")
        ):
            parts.append(f".{item}" if parts else str(item))
    return "".join(parts) or "file"


def parse_yaml(text: str) -> Any:
    """Parse YAML text with the restricted loader."""
    if len(text.encode("utf-8")) > MAX_FILE_BYTES:
        raise DeviceFileError([f"The file is larger than {MAX_FILE_BYTES // 1024} KiB."])
    try:
        return yaml.load(text, Loader=_NoAliasLoader)  # noqa: S506 (restricted safe loader)
    except yaml.YAMLError as exc:
        raise DeviceFileError([f"YAML error: {exc}"]) from exc


def from_data(data: Any) -> DeviceFile:
    """Validate already-parsed data as a device file."""
    try:
        return DeviceFile.model_validate(data)
    except ValidationError as exc:
        problems = []
        for error in exc.errors():
            message = str(error["msg"]).removeprefix("Value error, ")
            location = _location(tuple(error["loc"]))
            problems.append(message if location == "file" else f"{location}: {message}")
        raise DeviceFileError(problems) from exc


def loads(text: str) -> DeviceFile:
    """Parse and validate device file text."""
    return from_data(parse_yaml(text))


def load(path: str | Path) -> DeviceFile:
    """Read, parse and validate a device file from disk."""
    file_path = Path(path)
    if file_path.stat().st_size > MAX_FILE_BYTES:
        raise DeviceFileError([f"The file is larger than {MAX_FILE_BYTES // 1024} KiB."])
    return loads(file_path.read_text(encoding="utf-8"))


@dataclass
class Report:
    """What `openhal file validate` prints for one file."""

    path: str
    file: DeviceFile | None = None
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.file is not None and not self.problems


def warnings_for(device: DeviceFile) -> list[str]:
    """Problems that don't stop a file loading but that a human should see."""
    found: list[str] = []
    if (device.write or device.actions) and not device.safe_state:
        if device.safe_state_note:
            found.append(f"No safe state. Reason given: {device.safe_state_note}")
        else:
            found.append(
                "Writable device with no safe_state. Stop can't make it safe. Add safe_state or safe_state_note."
            )
    unconfirmed = device.unconfirmed()
    if unconfirmed:
        found.append("Loads read-only until a human confirms limits for " + ", ".join(unconfirmed) + ".")
    if device.confirmed is not None and device.confirmed.sha256 is None and (device.write or device.actions):
        found.append("The confirmation isn't bound to the file content. Run openhal file confirm to bind it.")
    if device.hazard is None and (device.write or device.actions):
        found.append("No hazard class given, so it is treated as medium.")
    return found


def validate_path(path: str | Path) -> Report:
    """Validate one file and collect problems and warnings."""
    report = Report(path=str(path))
    try:
        report.file = load(path)
    except DeviceFileError as exc:
        report.problems = exc.problems
        return report
    except OSError as exc:
        report.problems = [f"Could not read the file: {exc.strerror or exc}"]
        return report
    report.warnings = warnings_for(report.file)
    return report
