# Brief: independent safety review of the kernel

## Goal

Try to break OpenHAL's safety kernel. Find any way a command can reach a driver's hardware methods while violating a rule in docs/SAFETY.md, any way an agent principal can do something reserved for humans, and any way the kernel fails open. You receive only the code and the safety documents, not the author's reasoning. Assume the author made mistakes.

## Definition of done

- docs/agents/REVIEW-safety.md lists every finding with severity (critical, high, medium, low), the rule or threat it breaks, exact reproduction steps, and a suggested fix.
- Every critical or high finding has a proof-of-concept test in tests/review_safety/ that FAILS against the current code (it demonstrates the bug). Name each test after its finding number.
- The review says explicitly which areas you checked and found sound, so the coverage of the review is clear.

## What to read

- docs/SAFETY.md and docs/THREAT_MODEL.md (the rules)
- spec/SPEC.md (the device file format, especially sections 4, 5, 7, 8, 9 and 12)
- openhal/kernel/ (all modules), openhal/drivers/base.py, openhal/drivers/mock/driver.py, openhal/audit/log.py, openhal/spec/ (models, units, expressions, loader)
- tests/kernel/ for how the kernel is driven, and tests/kernel/conftest.py for fixtures you can reuse

## Ideas to try (not exhaustive)

Unit conversion tricks, offset temperature units, percent versus dimensionless, huge or tiny magnitudes, rate limits beaten by timing or by reads that move the reference, concurrent clients, interlocks with unknown values or cross-device references, actions with effects, watchdog budgets, confirmation spoofing or replay, approval windows, routine approvals and hashes, session limits that loosen, stop and unlock races, writes during the safe state, grant forgery or reuse, drivers that try to call hardware methods, expression parser abuse, malicious device files, audit log gaps (events that are not logged), exceptions that escape and leave state inconsistent.

## Files you own

- docs/agents/REVIEW-safety.md
- tests/review_safety/ (new directory)

## What you must not do

- Do not modify any file outside the two paths above. Do not fix the kernel yourself.
- Do not send anything to real hardware. Use the mock driver only.
- Do not push, publish, or post anything. Do not start subagents.
- Do not commit. Leave your files uncommitted for the orchestrator.

## How to report

Write the review to docs/agents/REVIEW-safety.md and a short summary to docs/agents/REPORT-safety-review.md (files created, tests added, the top three findings). Run tests with `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; cd ~/code/openhal; uv run pytest tests/review_safety -q`.
