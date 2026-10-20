"""F07 (high). An agent's string value can freeze the kernel through a backtracking `pattern`.

`checks.normalize` runs `re.fullmatch(spec.pattern, raw)` with no time limit, inside the
synchronous `evaluate`. One write ties up the event loop, so stop, heartbeats and watchdogs
can't run until the regex finishes. The value below takes a few seconds; with the allowed
4096 characters it would not finish in practice.
"""

from __future__ import annotations

import time

from openhal.kernel import Kernel, Write, agent
from tests.kernel.conftest import AddDevice

SIGN = """
device: Shop sign
id: sign
connect: { mock: sign }
write:
  text: { type: string, max_length: 64, pattern: "^([a-z]+ ?)+$" }
safe_state: { text: "" }
hazard: low
confirmed: { by: tester, at: 2026-10-24 }
"""


async def test_f07_string_check_is_bounded_in_time(kernel: Kernel, add: AddDevice) -> None:
    await add(SIGN)
    hostile = "a" * 22 + "!"

    started = time.perf_counter()
    decision = kernel.evaluate(Write(device="sign", channel="text", value=hostile), agent("a", "control_low"))
    took = time.perf_counter() - started

    assert decision.status == "blocked"
    assert took < 0.5, f"one 23 character write held the kernel (and the event loop) for {took:.1f} s"
