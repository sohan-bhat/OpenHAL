"""The error registry matches ADR 0015 and covers every kernel code exactly once."""

from __future__ import annotations

import re
from pathlib import Path

from openhal.kernel.commands import BLOCK_CODES
from openhal.protocol import errors

ROOT = Path(__file__).parents[2]
ADR = ROOT / "docs" / "adr" / "0015-openhal-hub-protocol.md"
KERNEL = ROOT / "openhal" / "kernel"


def adr_rows() -> list[tuple[int, str, tuple[str, ...]]]:
    text = ADR.read_text(encoding="utf-8")
    section = text.split("### Error registry", 1)[1].split("###", 1)[0]
    rows = []
    for line in section.splitlines():
        match = re.match(r"^\| (-\d+) \| ([A-Z_]+) \|([^|]*)\|", line)
        if match:
            kernel = tuple(re.findall(r"`([a-z_]+)`", match.group(3)))
            rows.append((int(match.group(1)), match.group(2), kernel))
    return rows


def emitted_kernel_codes() -> set[str]:
    found: set[str] = set()
    for path in KERNEL.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        found |= set(re.findall(r'Block\(\s*"([a-z_]+)"', source))
        found |= set(re.findall(r'code="([a-z_]+)"', source))
        found |= set(re.findall(r'"code": "([a-z_]+)"', source))
    return found


def test_registry_matches_the_adr_table() -> None:
    rows = adr_rows()
    assert len(rows) == 24
    assert [(spec.code, spec.name, spec.kernel_codes) for spec in errors.REGISTRY] == rows


def test_codes_and_names_are_unique() -> None:
    assert len(errors.BY_CODE) == len(errors.REGISTRY)
    assert len(errors.BY_NAME) == len(errors.REGISTRY)


def test_every_kernel_code_maps_to_exactly_one_name() -> None:
    codes = emitted_kernel_codes() | set(BLOCK_CODES)
    assert {"above_max", "rate_limited", "queue_full", "busy"} <= codes
    for code in sorted(codes):
        owners = [spec.name for spec in errors.REGISTRY if code in spec.kernel_codes]
        assert len(owners) == 1, f"kernel code {code} maps to {owners}"
    claimed = {code for spec in errors.REGISTRY for code in spec.kernel_codes}
    assert claimed <= codes, f"the registry names codes the kernel never emits: {sorted(claimed - codes)}"


def test_limit_exceeded_reason_reads_like_the_adr() -> None:
    error = errors.from_kernel(
        "above_max",
        {
            "device": "desk-fan",
            "channel": "fan_speed",
            "requested": "150 %",
            "limit": {"max": "100 %"},
            "file": "desk-fan.hal.yaml",
            "confirmedBy": "sohan",
            "confirmedAt": "2026-11-02",
        },
    )
    assert error.reason == (
        "fan_speed 150 % exceeds the limit of 100 % (desk-fan.hal.yaml, confirmed by sohan 2026-11-02)"
    )
    body = error.to_object()
    assert body["code"] == -32010
    assert body["data"]["name"] == "LIMIT_EXCEEDED"
    assert body["data"]["kernelCode"] == "above_max"


def test_every_template_renders_without_data() -> None:
    for spec in errors.REGISTRY:
        text = spec.template({"name": spec.name})
        assert text
        assert not text.endswith(".")
        assert ";" not in text


def test_unknown_kernel_codes_are_internal_errors() -> None:
    assert errors.from_kernel("something_new").name == "INTERNAL_ERROR"
    assert errors.from_kernel(None).name == "INTERNAL_ERROR"
