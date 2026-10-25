# Needs a human

Items that only the owner can do, in the order they should be done. Each has exact steps.

## 1. Push the local commits

The owner approved the push on 2026-10-25, and the local permission settings still block `git push` for the agent.

1. Run `git -C ~/code/openhal push origin main`.
2. Open https://github.com/sohan-bhat/OpenHAL/actions and check that the CI run passes. CI runs on Ubuntu, so it is the first Linux run of the scpi disconnect fix.

## 2. Turn on private vulnerability reporting

SECURITY.md and CODE_OF_CONDUCT.md send reports through GitHub's private channels, and private vulnerability reporting is off for the repository (checked 2026-10-25). Do this before the repository gets attention.

1. Open https://github.com/sohan-bhat/OpenHAL/settings/security_analysis.
2. Turn on "Private vulnerability reporting".
3. In Settings, Moderation options, turn on "Accept content reports" for the code of conduct route.

## 3. Run the first hardware test, the plant waterer

The plant waterer is the cheapest complete rig and its pump stays unplugged until the last step.

1. Get the parts in examples/plant-waterer/README.md (an Arduino Uno, a capacitive soil sensor, a float switch, a 5 V relay module and a small pump with its own supply).
2. Follow examples/plant-waterer/TEST-PLAN.md from step 1. Read-only steps come first.
3. Fill in its report template and save it in docs/hardware-tests/reports/. A passing report is what lets the device file say `verified-on-hardware`.

The order for every other driver is in docs/hardware-tests/README.md, lowest hazard first.

## 4. Run the WebKit browser tests on another machine

Every WebKit page load stalls on this Mac, so the website and Inspector Playwright tests ran in Chromium and Firefox only.

1. On a machine where WebKit works, run `pnpm --dir website exec playwright test --project=webkit` and `pnpm --dir dashboard exec playwright test --project=webkit`.
2. Send the output back, or fix what fails.

## 5. Decide the PyPI distribution name

The PyPI name `openhal` belongs to an unrelated project (HAL, Harmful Action Limiter, v0.1.0, March 2026). The import name and CLI stay `openhal`. The distribution is built as `openhal-hub` until you decide (ADR 0002). The name lives in one place, `openhal/_brand.py` plus `pyproject.toml`. Until something is published, every install command uses the git repository.

Options if you want a different public name, all checked free on PyPI and npm as of 2026-10-24 unless noted.
1. `openhal-hub` (current default)
2. `openhal-core`
3. `openhald` (the daemon name, free on PyPI)
4. Ask the owner of `openhal` on PyPI whether they would transfer it (https://pypi.org/project/openhal/, repository https://github.com/otherland/hal)
5. Rename the whole project. Five alternatives that searched clean on 2026-10-24, said as words where possible.
   - OpenHAIL (Open Hardware Agent Interface Layer, "open hail")
   - OpenHARI (Open Hardware Agent Runtime Interface, "open harry")
   - OpenAHI (Open Agent Hardware Interface)
   - OpenMDI (Open Model Device Interface)
   - OpenDLI (Open Device Layer Interface, not yet searched)

## 6. Domain

openhal.com and openhal.org are registered by someone else. openhal.io looked unregistered on 2026-10-24. openhal.dev could not be checked. The website is published at https://sohan-bhat.github.io/OpenHAL/ until then. Check and buy at a registrar of your choice, add it as the custom domain in the repository's Pages settings, set `OPENHAL_SITE` in .github/workflows/pages.yml to it, and drop the rebase step there, which only exists to serve the site under /OpenHAL/.
