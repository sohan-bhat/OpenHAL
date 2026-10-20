# Report: safety review

Saved by the orchestrator from the reviewer's hand-back, because the reviewer's harness did not allow it to write report files.

The full review is in docs/agents/REVIEW-safety.md. It lists 22 findings (1 critical, 6 high, 10 medium, 5 low) and records which areas were checked and found sound. The top three are F01 (unknown same-device values are read as the bare word of their own name, so interlocks and preconditions pass on unknown state), F03 (stop reports a device safe while an older in-flight write is still landing, and that write wins) and F02 (cross-device interlocks are checked against stale state during concurrent writes). The other high findings are F04 (a brief dip resets a max_duration budget), F05 (action effects reset the rate reference), F06 (unexpected driver exceptions escape `execute()` without an audit entry) and F07 (a backtracking string pattern freezes the kernel and the stop path).

There are 17 proof-of-concept tests in tests/review_safety/, all failing against the reviewed code as intended. The reviewer modified no other file, committed nothing, and did not review openhal/hub/ or openhal/conformance/.
