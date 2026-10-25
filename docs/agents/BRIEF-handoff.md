# Brief: handoff documents (M15)

Read docs/agents/COMMON.md first. Then read README.md, docs/DESIGN.md (voice and banned words), docs/research/OPENHAL_RESEARCH.md, drivers/catalog.json, docs/drivers/WRITING-A-DRIVER.md, docs/SAFETY.md, docs/THREAT_MODEL.md, NEEDS_HUMAN.md, every file in docs/hardware-tests/ and examples/plant-waterer/TEST-PLAN.md.

## Goal

The documents a new contributor, a security reporter and the owner need after the build.

1. **CONTRIBUTING.md** at the root. How to set up (uv), run the checks, and contribute a driver (the SDK commands `openhal driver new` and `openhal driver test`) and a device file (validation, suggested limits, no `confirmed`, provenance). The rules for commits. Short.
2. **CODE_OF_CONDUCT.md.** The Contributor Covenant 2.1, with the reporting route through GitHub's private channels. No personal email address.
3. **SECURITY.md.** Supported versions, how to report privately (GitHub private vulnerability reporting), what counts as a safety issue (anything that lets a command past the kernel), and the response steps.
4. **docs/ROADMAP.md.** Next drivers (from drivers/planned.json and the coverage plan), Windows support, MHS import and export, a hosted device library, vendor app protocol learning (with legal review), and a business model sketch (hosted remote access, classroom and lab plans, a verified library, hardware partnerships).
5. **docs/LAUNCH.md.** Drafts only, never posted. A Show HN post with a plan for the HAL 9000 jokes people will make, and one post each for r/arduino, r/esp32, r/3Dprinting, r/klippers, r/homeassistant, r/raspberry_pi, r/astrophotography, r/synthesizers and r/labrats, each in that community's tone and honest about what is tested only on simulators.
6. **docs/hardware-tests/README.md.** Every test plan in one ordered list, lowest hazard first, read-only plans first, with the plant waterer plan (examples/plant-waterer/TEST-PLAN.md) as the first test to run. Then check every plan has exact commands, expected output, what to send back on failure and a report template whose filled-in form is enough to mark the device file `verified-on-hardware`. Fill the gaps in the plans.

## Copy

Formal and exact like a good spec. Short declarative sentences. Every rule in COMMON.md and the banned list in docs/DESIGN.md applies. Every command you write must run as written against this repo.

## Files you own

CONTRIBUTING.md, CODE_OF_CONDUCT.md, SECURITY.md, docs/ROADMAP.md, docs/LAUNCH.md, docs/hardware-tests/ and examples/plant-waterer/TEST-PLAN.md.

## Not yours

README.md, the spec, code and everything else.
