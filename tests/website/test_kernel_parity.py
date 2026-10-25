"""The website's kernel port must decide exactly like the real kernel.

This test runs every case in website/tests/kernel-parity/cases.json through the Python kernel and
compares the results with expected.json. The vitest suite in website/tests/unit compares the
TypeScript port with the same file. Together they hold the two kernels to the same status, code
and message for every command. After a deliberate kernel change, regenerate the file with
`uv run python -m tests.website.kernel_parity`.
"""

from __future__ import annotations

import json

from openhal.kernel.commands import BLOCK_CODES
from tests.website import kernel_parity

# Codes the in-browser port can't produce, because they need a real driver, a busy device or a
# crash inside the kernel. Everything else must appear in at least one case.
NOT_PORTED = {"busy", "internal_error", "driver_error", "expired", "rejected"}


def test_expected_results_match_the_python_kernel() -> None:
    expected = json.loads(kernel_parity.EXPECTED.read_text(encoding="utf-8"))
    actual = json.loads(kernel_parity.render(kernel_parity.run_all()))
    assert [case["id"] for case in actual["cases"]] == [case["id"] for case in expected["cases"]]
    for got, want in zip(actual["cases"], expected["cases"], strict=True):
        assert got == want, f"case {got['id']} changed. Regenerate expected.json if the kernel change is deliberate."
    assert actual["hashes"] == expected["hashes"]


def test_cases_cover_every_block_code_the_port_implements() -> None:
    results = json.loads(kernel_parity.EXPECTED.read_text(encoding="utf-8"))
    seen = set()
    for case in results["cases"]:
        for item in [*case["steps"], case["result"]]:
            if item.get("code"):
                seen.add(item["code"])
    assert set(BLOCK_CODES) - NOT_PORTED <= seen


def test_there_are_at_least_forty_commands() -> None:
    cases = kernel_parity.load_cases()["cases"]
    assert len(cases) >= 40
    used = {entry if isinstance(entry, str) else entry["name"] for case in cases for entry in case["devices"]}
    assert set(kernel_parity.load_cases()["files"]) <= used, "every example device file should be used"
