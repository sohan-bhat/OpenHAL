# Dependencies

Every third-party dependency, the version resolved in uv.lock when it was added, its license and why it is used. Driver dependencies are optional extras and are added by the driver that needs them.

Copyleft code is never copied into this repository. Libraries under weak copyleft licenses (LGPL, MPL) are used only as unmodified dependencies.

## Core

| Package | Version | License | Why |
|---|---|---|---|
| pydantic | 2.14.1 | MIT | Device file, command and API models |
| pint | 0.26.2 | BSD-3-Clause | The one unit registry (ADR 0005) |
| PyYAML | 6.0.3 | MIT | Device file parsing with a restricted safe loader |
| typer | 0.27.3 | MIT | CLI |
| rich | 15.0.0 | MIT | CLI output |
| questionary | 2.1.1 | MIT | The CLI's pickers and typed answers for a left-out argument (ADR 0020) |
| portalocker | 4.4.2 | BSD-3-Clause | The hub's and each device's lock file on macOS, Linux and Windows, in place of the Unix-only fcntl |
| prompt_toolkit | 3.0.53 | BSD-3-Clause | The terminal input and output under questionary, pointed at the controlling terminal |
| wcwidth | 0.9.4 | MIT | Character widths for prompt_toolkit. Installed with prompt_toolkit |

The CLI's pickers use questionary on prompt_toolkit, chosen on 2026-11-02 over InquirerPy. questionary had a release in August 2025, while InquirerPy's last release was in June 2022. Both are MIT and both run on Windows through prompt_toolkit's console input. questionary's select prompt filters the list as the person types. The CLI styles each picker in plain bold with no colors, so a picker matches the rich output around the picker.

## Hub extra

| Package | Version | License | Why |
|---|---|---|---|
| fastapi | 0.162.0 | MIT | Local HTTP and WebSocket API |
| uvicorn | 0.54.0 | BSD-3-Clause | ASGI server for the hub |
| websockets | 17.3 | BSD-3-Clause | Live values to the dashboard, Moonraker and Home Assistant clients |
| httpx | 0.28.1 | BSD-3-Clause | Client library, HTTP drivers and bridges |
| mcp | 2.3.0 | MIT | Official MCP Python SDK |
| zeroconf | 0.151.5 | LGPL-2.1-or-later | mDNS discovery. Used unmodified as a dependency |

## Website

The website's packages are pinned in website/package.json and website/pnpm-lock.yaml. These are the ones the palette, the phone menu, the nav highlight and the brand build rely on.

| Package | Version | License | Why |
|---|---|---|---|
| @radix-ui/colors | 3.0.0 | MIT | The palette's olive, gold and pink steps, read by website/src/lib/palette.mjs. Development only |
| culori | 4.0.2 | MIT | WCAG contrast and CIEDE2000 distance under Machado 2009 color vision simulations for the palette's checks. Development only |
| @types/culori | 4.0.1 | MIT | Types for culori in the unit tests. Development only |
| radix-ui | 1.8.1 | MIT | Dialog under shadcn/ui's Sheet, which holds a section's pages on a phone |
| shadcn/ui Sheet | new-york-v4 registry, 2026-11-01 | MIT | The phone's page sheet, copied from the registry and themed with design/tokens.css |
| tw-animate-css | 1.4.0 | MIT | The Sheet's slide in and out |
| motion | 14.2.0 | MIT | The nav highlight's slide between sections |
| lucide-react | 1.57.0 | ISC | The Sheet's close icon and its button's chevron |
| fonttools | 4.67.0 | MIT | Draws the wordmark, the mark and the favicon from the brand face, run through uv by scripts/readme/build.py |
| @fontsource-variable/ibm-plex-sans | 5.3.0 | OFL-1.1 | IBM Plex Sans, the text and wordmark face. The package's Latin WOFF2 files are copied into design/fonts, so the package is not installed |
| @fontsource/ibm-plex-mono | 5.3.0 | OFL-1.1 | IBM Plex Mono, the code face, copied into design/fonts the same way at the weights in use |

## Development

| Package | Version | License | Why |
|---|---|---|---|
| pytest | 9.1.1 | MIT | Tests |
| pytest-asyncio | 1.4.0 | Apache-2.0 | Async tests |
| pytest-cov | 7.1.0 | MIT | Coverage |
| hypothesis | 6.170.9 | MPL-2.0 | Property tests for the safety kernel. Development only |
| ruff | 0.17.2 | MIT | Lint and format |
| mypy | 2.4.0 | MIT | Type checks |
