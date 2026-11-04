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

## 3. Try the release on TestPyPI

TestPyPI is PyPI's practice index. .github/workflows/testpypi.yml runs only by hand. The workflow builds the same files the release builds, uploads them to TestPyPI through trusted publishing, then installs only `halkit` from TestPyPI, with its dependencies from PyPI, and runs the demo.

1. Sign in at https://test.pypi.org, which uses an account apart from pypi.org, and open Your account, then Publishing.
2. Under Add a new pending publisher, pick GitHub and fill in the form exactly as below. Then click Add.
   - PyPI Project Name `halkit`
   - Owner `sohan-bhat`
   - Repository name `OpenHAL`
   - Workflow name `testpypi.yml`
   - Environment name `testpypi`
3. On GitHub, open the repository's Settings, then Environments, then New environment. Name the environment `testpypi`, add yourself under Required reviewers and add no secrets.
4. To upload, open Actions, pick TestPyPI, click Run workflow on main, then approve the `testpypi` deployment.
5. Check that https://test.pypi.org/project/halkit/ shows 0.1.0 and that the verify job passed. TestPyPI keeps each version once, so a second run with the same version stops at the upload.

## 4. Publish 0.1.0

The version is 0.1.0 in pyproject.toml, openhal/__init__.py, uv.lock and docs/api/openapi.json. CHANGELOG.md has the entry and docs/releases/v0.1.0.md has the text for the GitHub release. The pending publisher for `halkit` on pypi.org is in place. A pending publisher doesn't reserve the name, so push the tag soon after merging. .github/workflows/release.yml publishes through trusted publishing, so the repository holds no PyPI token.

1. On GitHub, open Settings, then Environments, then New environment. Name the environment `pypi`. Under Deployment branches and tags, choose Selected branches and tags and add a tag rule with the pattern `v*`. Add yourself under Required reviewers and add no secrets.
2. Make a second environment named `ghcr` the same way. The tag also starts the Container workflow, which pushes the image to GHCR from the `ghcr` environment, so the reviewer rule makes the image a separate approval. Without the environment, GitHub makes one with no rules on the first run, and the image goes out with the tag.
3. If the release day isn't 2026-11-03, change the date on the 0.1.0 line of CHANGELOG.md.
4. Merge to main and check that CI passes, the install matrix included. Then open Actions, pick Clean machine and click Run workflow, and read each system's step times in the job summary.
5. Tag the commit and push the tag.

   ```text
   git tag v0.1.0
   git push origin v0.1.0
   ```

   The tag starts the Release workflow. The workflow stops before building anything if the tag isn't `v` plus the version in pyproject.toml. Otherwise the workflow runs the tests, builds `halkit-0.1.0.tar.gz` and `halkit-0.1.0-py3-none-any.whl`, installs the wheel in a fresh venv, checks that `openhal --version` prints `openhal 0.1.0` and uploads both files to PyPI once you approve the `pypi` deployment.
6. Check https://pypi.org/project/halkit/ for version 0.1.0, then run `uvx halkit demo` in a terminal. The one-line installers look PyPI up on every run, so from then on the installers take OpenHAL from PyPI with no change.
7. To publish the GitHub release, open Releases, then Draft a new release, pick the tag v0.1.0, set the title to OpenHAL 0.1.0, paste docs/releases/v0.1.0.md without its first line and publish.
8. To publish the container image, approve the `ghcr` deployment. A new GHCR package starts private, so open the package's settings on GitHub and set the visibility to public.
9. Turn on the uv and pipx tabs. In website/src/config/install.json, change `"onPyPI": false` to `"onPyPI": true`. That one value adds the uv and pipx tabs to the home page's install box and moves the install guide's uv and pipx commands from GitHub to PyPI.
10. Run `uv run python scripts/install_docs.py`, so docs/guide/install.md shows the PyPI commands, then `uv run pytest tests/docs/test_install_docs.py tests/packaging -q`.
11. Commit, push to main and wait for the Website workflow to finish.
12. Open https://sohan-bhat.github.io/OpenHAL/ and check that the install box shows macOS and Linux, Windows, uv and pipx. Then run the macOS and Linux command in a terminal. The installer should print `Installing OpenHAL from PyPI` and then `OpenHAL 0.1.0 is now in` followed by the folder.

## 5. Publish the Arduino library

The Arduino Library Manager and PlatformIO read a library from a repository of its own, with library.properties at the root. firmware/arduino/OpenHAL passes `arduino-lint --library-manager submit --compliance strict`, and `pio pkg pack` builds the PlatformIO package.

1. Make an empty public repository named `OpenHAL-Arduino` under `sohan-bhat` on GitHub.
2. In a clone of OpenHAL, split the library folder with its history and push the result.

   ```text
   git subtree split --prefix=firmware/arduino/OpenHAL -b arduino-library
   git push https://github.com/sohan-bhat/OpenHAL-Arduino arduino-library:main
   ```

3. In the new repository, set `url=https://github.com/sohan-bhat/OpenHAL-Arduino` in library.properties and the repository URL in library.json to `https://github.com/sohan-bhat/OpenHAL-Arduino.git`. Commit, then tag the version library.properties gives and push the tag.

   ```text
   git tag 0.2.0
   git push origin 0.2.0
   ```

4. Run `arduino-lint --library-manager submit --compliance strict` in the new repository's root, and fix anything it reports.
5. For the Arduino Library Manager, open a pull request on https://github.com/arduino/library-registry that adds `https://github.com/sohan-bhat/OpenHAL-Arduino` to repositories.txt. The registry's bot checks the library, and after the merge the index picks up each new tag on its own.
6. For PlatformIO, install PlatformIO Core, run `pio account login` and then `pio pkg publish` in the new repository's root.
7. The folder in this repository stays the source. Before each new library version, bump `version` in both library.properties and library.json, then run the split and push from step 2 and tag the new version.

## 6. List OpenHAL in the MCP directories

Each listing is a public post, so each one is yours to approve. List OpenHAL after 0.1.0 is on PyPI, because each listing runs `uvx --from halkit openhal mcp`.

- **Glama.** Add the repository at https://glama.ai/mcp/servers, then use Claim ownership. glama.json names `sohan-bhat` as the maintainer.
- **Docker MCP catalog.** Fork https://github.com/docker/mcp-registry and add servers/openhal/server.yaml as that repository's CONTRIBUTING.md describes, with this repository and a commit. The Dockerfile at the root starts `openhal mcp` with a simulated plant waterer.
- **Cline.** Open an issue on https://github.com/cline/mcp-marketplace with the repository URL, docs/assets/logo-400.png and a reason to list OpenHAL. Cline installs from README.md and llms-install.md.
- **Claude Code.** The repository is a plugin marketplace already. A person installs the plugin with `/plugin marketplace add sohan-bhat/OpenHAL` and then `/plugin install openhal@openhal`.
- **Gemini CLI.** The repository is a Gemini extension already. A person installs the extension with `gemini extensions install https://github.com/sohan-bhat/OpenHAL`.
- **The official MCP Registry.** Its terms require users to be 18 or older, so OpenHAL stays off the registry for now.

## 7. Domain

openhal.com and openhal.org are registered by someone else. openhal.io looked unregistered on 2026-10-24. openhal.dev could not be checked. The website is published at https://sohan-bhat.github.io/OpenHAL/ until then. Buy one of the unregistered domains at a registrar of your choice. Then set that domain as the custom domain in the repository's Pages settings, set `OPENHAL_SITE` in .github/workflows/pages.yml to the domain, and drop the rebase step in that workflow, which only exists to serve the site under /OpenHAL/. The one-line installers carry the site's address too, so set `site` in website/src/config/install.json and `SITE` in website/public/install.sh to the new address, run `uv run python scripts/install_docs.py`, and change the address in llms-install.md and the `SITE` value in .github/workflows/clean-machine.yml. The old address keeps working, because GitHub Pages redirects the old address to the custom domain.
