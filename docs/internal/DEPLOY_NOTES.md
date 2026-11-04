# Deploy notes

Checked on 2026-10-29 by website-16, before any change to the site.

## What we found

The pipeline works. Every push to main runs `.github/workflows/pages.yml`, and the last 40 runs since 2026-10-27 all deployed except three, which GitHub cancelled because a newer push was already queued in the same `pages` group, and that newer run deployed.

| Check | Result |
|---|---|
| `git status` and `git log -5` against `origin/main` | Nothing uncommitted or unpushed, main at 975636c on both |
| `gh run list --workflow pages.yml -L 40` | 37 successful runs and 3 superseded ones, none failed |
| Live HTML against a local build of 975636c | Home, docs and the spec page byte for byte the same, the Playground different only in Astro's random island id |
| Response headers of the live home page | `last-modified` one minute after the last run, `cache-control: max-age=600` |

So the live site showed exactly what main held. The old page the owner saw has three causes, in order of size.

1. **Work reached main hours after it was done.** Round 14 sat on its branch for about 13 hours, and its merge commit sat on the orchestrator's machine for about 2 hours before the push, so the live site kept round 13 for that whole time. Nothing in the pipeline can fix a push that hasn't happened.
2. **GitHub Pages caches every page for 10 minutes.** It sends `cache-control: max-age=600`, which GitHub doesn't let a site change, so a browser or the CDN can show the previous deploy for up to 10 minutes after the run finishes. Assets don't go stale, because Astro names them by their hash.
3. **The machine's clock runs one hour slow.** Commit times read an hour early next to GitHub's run times, so a push looked an hour late when it wasn't. This misleads anyone comparing the two and doesn't affect the site.

## What changed

- The build writes `version.json` at the site's root with the commit and the run, so `curl https://sohan-bhat.github.io/OpenHAL/version.json?now` says exactly which commit is live.
- A third job, `verify`, waits after the deploy until the live `version.json` names the pushed commit, with a fresh query string on every attempt so no cache answers. It fails the run if the live site still serves another commit after 10 minutes, so a deploy that never lands shows as a red run instead of passing quietly.
- Both jobs run on `ubuntu-24.04` instead of `ubuntu-latest`, which GitHub moves to Ubuntu 26 from 2026-10-19, so the Chromium install for the social images can't break on a new image without anyone changing the workflow.

## Checking a deploy

1. Push to main and wait for the Website run to finish, `verify` included.
2. Open `version.json?now` on the live site and compare its commit with `git rev-parse origin/main`.
3. Reload the page itself with the cache bypassed (Shift and Reload), or wait 10 minutes.
