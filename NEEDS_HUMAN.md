# Needs a human

These items need the owner, in the order listed. Each item has exact steps.

## 1. Run the first hardware test, the plant waterer

The plant waterer is the cheapest complete rig and its pump stays unplugged until the last step.

1. Get the parts in examples/plant-waterer/README.md (an Arduino Uno, a capacitive soil sensor, a float switch, a 5 V relay module and a small pump with its own supply).
2. Follow examples/plant-waterer/TEST-PLAN.md from step 1. Read-only steps come first.
3. Fill in the report template at the end of TEST-PLAN.md and save the report in docs/hardware-tests/reports/. A passing report lets the device file say `verified-on-hardware`.

The order for every other driver is in docs/hardware-tests/README.md, lowest hazard first.

## 2. Run the WebKit browser tests on another machine

Every WebKit page load stalls on this Mac, so the website and Inspector Playwright tests ran in Chromium and Firefox only.

1. On a machine where WebKit works, run `pnpm --dir website exec playwright test --project=webkit` and `pnpm --dir dashboard exec playwright test --project=webkit`.
2. Send the output back, or fix what fails.

## 3. Publish the first release to PyPI

The distribution is `ohal` (ADR 0002). The import package and the CLI stay `openhal`. Nothing is on PyPI yet, so every install command uses the git repository until the first release. .github/workflows/release.yml publishes through PyPI trusted publishing, so the repository holds no PyPI token.

1. Sign in at https://pypi.org and open Your account, then Publishing (https://pypi.org/manage/account/publishing/).
2. Under Add a new pending publisher, pick GitHub and fill in the form exactly as below. Then click Add.
   - PyPI Project Name `ohal`
   - Owner `sohan-bhat`
   - Repository name `OpenHAL`
   - Workflow name `release.yml`
   - Environment name `pypi`
3. A pending publisher doesn't reserve the name `ohal` until the first upload, so do the remaining steps soon after.
4. On GitHub, open the OpenHAL repository's Settings, then Environments, then New environment. Name the environment `pypi` and click Configure environment. Add no secrets.
5. Under Deployment branches and tags, choose Selected branches and tags and add a tag rule with the pattern `v*`, so only a release tag can deploy to `pypi`. To approve every upload yourself, also add yourself under Required reviewers.
6. Set the version to 0.1.0. pyproject.toml says `version = "0.1.0.dev0"` and openhal/__init__.py says `__version__ = "0.1.0.dev0"`. Change both to `"0.1.0"`, then run `uv lock` and `uv run python -m openhal.hub.openapi`, so uv.lock and docs/api/openapi.json carry 0.1.0 too. SECURITY.md lists `main` (0.1.0.dev0) and says OpenHAL has no release yet, so update SECURITY.md in the same commit.
7. Commit, push to main and check that CI passes.
8. Tag that commit and push the tag.

   ```text
   git tag v0.1.0
   git push origin v0.1.0
   ```

   The tag starts the Release workflow. The workflow stops before building anything if the tag isn't `v` plus the version in pyproject.toml. Otherwise the workflow runs the tests, builds `ohal-0.1.0.tar.gz` and `ohal-0.1.0-py3-none-any.whl`, installs the wheel in a fresh venv, checks that `openhal --version` prints `openhal 0.1.0` and uploads both files to PyPI.
9. Check https://pypi.org/project/ohal/ for version 0.1.0. After that the install pages can switch from the git commands to `uv tool install ohal` and `pipx install ohal`.

## 4. Domain

openhal.com and openhal.org are registered by someone else. openhal.io looked unregistered on 2026-10-24. openhal.dev could not be checked. The website is published at https://sohan-bhat.github.io/OpenHAL/ until then. Buy one of the unregistered domains at a registrar of your choice. Then set that domain as the custom domain in the repository's Pages settings, set `OPENHAL_SITE` in .github/workflows/pages.yml to the domain, and drop the rebase step in that workflow, which only exists to serve the site under /OpenHAL/.
