# Contributing

OpenHAL takes drivers, device files, hardware test reports, fixes and documentation. This page says how to set up, what must pass and how each kind of contribution is made.

Code is licensed under Apache-2.0. Device files under `library/` and `spec/examples/` are released under CC0 ([ADR 0011](docs/adr/0011-device-library-license.md)). By contributing you agree to both. Everyone follows the [Code of Conduct](CODE_OF_CONDUCT.md). Report security and safety problems privately, as [SECURITY.md](SECURITY.md) describes, never in a public issue.

## Set up

OpenHAL needs Python 3.12 or newer and [uv](https://docs.astral.sh/uv/).

```
git clone https://github.com/sohan-bhat/OpenHAL
cd OpenHAL
uv sync --all-extras
uv run openhal demo
```

The demo runs a hub against the simulated plant waterer. If it prints the three exchanges, the setup works.

On Linux the MIDI and HID extras build against system headers. On Debian and Ubuntu, install them before `uv sync`.

```
sudo apt-get install -y libasound2-dev libjack-jackd2-dev libudev-dev libusb-1.0-0-dev
```

## Run the checks

Every pull request passes the checks CI runs.

```
uv run ruff check openhal tests
uv run ruff format --check openhal tests
uv run mypy openhal
uv run pytest
```

The website and the Inspector have their own tests. Run them when you change `website/` or `dashboard/`. They need Node 22 and pnpm.

```
pnpm --dir website install --frozen-lockfile
pnpm --dir website test
pnpm --dir dashboard install --frozen-lockfile
pnpm --dir dashboard check
pnpm --dir dashboard test
```

## Rules for every change

- Never weaken a safety rule. A change to `openhal/kernel/` comes with a test for the case it changes. [docs/SAFETY.md](docs/SAFETY.md) is the reference.
- Tests never touch real hardware. They use the driver's simulator or a mock.
- No comments in code. Docstrings and tool directives such as `# noqa` stay.
- Method names, error codes and terms match [ADR 0015](docs/adr/0015-openhal-hub-protocol.md) exactly.
- Numbers travel as a number and a unit apart ([ADR 0016](docs/adr/0016-one-value-format.md)).
- Docs follow the copy voice in [docs/DESIGN.md](docs/DESIGN.md). Short declarative sentences, no em dashes and none of the banned words.

## Contribute a driver

Write a driver only when no existing driver speaks the device's protocol. `uv run openhal driver list` shows every driver. [WRITING-A-DRIVER.md](docs/drivers/WRITING-A-DRIVER.md) is the contract every driver follows.

1. Scaffold it. This writes an experimental driver named `x-acme-pump` with a simulator, a conformance case, tests, a docs page and a hardware test plan.

   ```
   uv run openhal driver new acme-pump --title "Acme pump"
   ```

2. Run the conformance suite. It passes against the simulator before you change anything.

   ```
   uv run openhal driver test x-acme-pump
   ```

3. Replace the simulator transport with the real protocol, one method at a time, and keep the suite passing. Every error path gets a test.
4. Fill in `docs/drivers/x-acme-pump.md`, the hardware test plan `docs/hardware-tests/x-acme-pump.md` and the catalog entry with sources for its estimate. [docs/hardware-tests/README.md](docs/hardware-tests/README.md) lists what a plan must contain.
5. Run every check, then open a pull request. A maintainer drops the `x-` prefix once the driver passes conformance and a person has run its hardware test plan.

## Contribute a device file

A device file describes one device model for an existing driver. Library files live in `library/<driver package>/<maker>-<model>.hal.yaml`, one file per model. [Add a device](docs/guide/tutorials/add-a-device.md) walks through writing one.

- **It validates.** `uv run openhal file validate` reports it valid.
- **Every limit is suggested.** Every control channel and every action carries `suggested: true`. Limits sit at the lowest sensible maximum, and anything with heat, motion or mains power has a confirmation tier.
- **It has no `confirmed`.** Only the person who owns a device confirms its limits, on their own copy, with `uv run openhal file confirm`. Review refuses a library file that carries a confirmation.
- **It records provenance.** `provenance` names `source`, `by`, `at`, `from` (the datasheet, manual or sketch it came from) and `verification: { status: unverified }`.
- **Its identifiers are real.** `match` holds the USB ids, `*IDN?` strings, BLE names or mDNS types the driver's discovery reports, with a source for each.
- **It holds no secrets.** A parameter that needs one names an environment variable, as in `token_env: HA_TOKEN`.

Validate one file or a whole folder.

```
uv run openhal file validate examples/plant-waterer/plant-waterer.hal.yaml
uv run openhal file validate openhal/drivers
```

A file becomes `verified-on-hardware` only with a hardware test report. [docs/hardware-tests/README.md](docs/hardware-tests/README.md) says how to run a plan and file the report.

## Commits and pull requests

- One logical change per commit, about 50 to 450 changed lines.
- Conventional messages, such as `feat(drivers): add the acme pump driver` or `docs: fix the quickstart`. The type is `feat`, `fix`, `docs`, `test`, `build`, `ci` or `refactor`, with an optional scope.
- No trailers in commit messages.
- A pull request says what changed, why, and which checks ran. A driver or kernel change names the tests that cover it.
