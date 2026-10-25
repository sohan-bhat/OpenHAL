# Hardware test plan, bambu driver

This plan checks the bambu driver against a real Bambu Lab printer on the local network. It was made for a P1S with the example file. X1, P1 and A1 printers work the same way. Read the local access status in docs/drivers/bambu.md first.

Run every step from the repository checkout, on a computer on the same network as the printer. Stay next to the printer during the steps that change anything.

## What you need

- A Bambu Lab printer with current firmware, in LAN-only mode with Developer Mode on (the network settings on the printer's screen).
- The printer's address, serial number and access code from that screen.
- openssl, to read the printer's certificate.
- The repository with the extra, `uv sync --extra bambu`.
- A copy of the example, `cp openhal/drivers/bambu/examples/p1s-lan.hal.yaml my-printer.hal.yaml`, with your address and serial number.
- The access code in the environment, `export BAMBU_ACCESS_CODE=<code>`.
- For steps 12 and 13, filament loaded and a small model on the printer's storage, such as a 20 mm calibration cube, started from the printer's screen.

## The test script

Save this as `hwtest.py` in the repository root. It drives the device only through the safety kernel, as the hub does. `set` waits one second first, because the kernel measures the first change's rate from the moment the device connected.

```python
"""Usage: uv run python hwtest.py FILE identify|describe|read|set CHANNEL VALUE|action NAME [ARG=VALUE ...]|stop"""

import asyncio
import json
import sys

from openhal.drivers import registry
from openhal.kernel import Kernel
from openhal.kernel.commands import Action, Write
from openhal.kernel.principals import human
from openhal.spec import load


def parse(text: str) -> object:
    return {"true": True, "false": False}.get(text, text)


async def main(path: str, command: str, *rest: str) -> None:
    file = load(path)
    driver = registry.load(file.connect.driver)(file)
    if command == "identify":
        print(json.dumps(await driver.identify(), indent=2))
        return
    kernel = Kernel()
    kernel.register(file, driver)
    await kernel.connect(file.device_id)
    me = human("hardware-tester")
    try:
        if command == "describe":
            print(json.dumps(await driver.describe(), indent=2, default=str))
        elif command == "read":
            for channel in [*file.read, *file.write]:
                reading = await kernel.read(file.device_id, channel, me)
                value = f"<{len(reading.value)} bytes>" if isinstance(reading.value, bytes) else reading.value
                print(f"{channel} = {value} {reading.unit or ''}{' (suspect)' if reading.suspect else ''}")
        elif command == "set":
            channel, value = rest
            await asyncio.sleep(1.0)
            decision = await kernel.execute(Write(device=file.device_id, channel=channel, value=parse(value)), me)
            print(decision.status, decision.code or "", decision.message)
        elif command == "action":
            name, *pairs = rest
            args = {key: parse(value) for key, value in (pair.split("=", 1) for pair in pairs)}
            decision = await kernel.execute(Action(device=file.device_id, action=name, args=args), me)
            print(decision.status, decision.code or "", decision.message)
        elif command == "stop":
            report = await kernel.stop_all(me, "hardware test")
            for result in report.devices:
                print(result.device, result.status, result.detail)
        print("health", await driver.health())
    finally:
        await driver.close()


asyncio.run(main(*sys.argv[1:]))
```

## Read-only steps

### 1. Developer Mode is on

Open the network settings on the printer's screen.

Expected. LAN-only mode and Developer Mode are both on, and the screen shows the access code.

### 2. The printer's certificate

```sh
openssl s_client -connect 192.168.1.50:8883 </dev/null 2>/dev/null | openssl x509 -noout -subject -fingerprint -sha256
```

Expected. A subject whose CN is the serial number, and a line `sha256 Fingerprint=AB:CD:...`. Put the part after the equals sign in `cert_sha256` in quotes, `cert_sha256: "AB:CD:..."`.

### 3. The device file validates

```sh
uv run openhal file validate my-printer.hal.yaml
```

Expected. `valid  my-printer.hal.yaml  (workshop-p1s, medium hazard, read-only)`.

### 4. Discover and identify

```sh
uv run python -c "import asyncio; from openhal.drivers.bambu.driver import BambuDriver; print(asyncio.run(BambuDriver.discover()))"
uv run python hwtest.py my-printer.hal.yaml identify
```

Expected. The first lists the printer with its serial number, model code and `mode` `lan`, or an empty list if no announcement came within 3 seconds. Run it again a few times before you call it a failure. The second prints the serial number and the address.

### 5. Read every channel

```sh
uv run python hwtest.py my-printer.hal.yaml read
```

Expected. `state = idle`, the nozzle and bed temperatures as the printer's screen shows them, `speed_level = standard` and `chamber_light` matching the light. The health line names the printer and `IDLE`.

### 6. Describe

```sh
uv run python hwtest.py my-printer.hal.yaml describe
```

Expected. Proposed read channels for every field the printer reported, `speed_level` and `chamber_light` marked suggested, and pause, resume and stop.

### 7. A wrong pin

Change one digit of `cert_sha256` and run step 5 again.

Expected. `DriverError` saying the certificate's fingerprint is not the pinned one and the access code was not sent. Put the right fingerprint back.

### 8. Network loss

Run step 5, turn the printer's Wi-Fi off, and run step 5 again.

Expected. The second run fails with `TimeoutError` or `DriverError` saying the printer did not answer or could not be reached. Turn Wi-Fi back on, wait for the printer to show its address, and run step 5. It reads normally.

## Steps that change the device

### 9. Confirm the limits

Read the file, decide the limits are right, and add this line yourself.

```yaml
confirmed: { by: <your name>, at: <today's date> }
```

`uv run openhal file validate my-printer.hal.yaml` should now say `writable`.

### 10. The smallest safe change

```sh
uv run python hwtest.py my-printer.hal.yaml set chamber_light true
uv run python hwtest.py my-printer.hal.yaml read
uv run python hwtest.py my-printer.hal.yaml set chamber_light false
```

Expected. `done` for each command, the chamber light turns on and off, and the read in between shows `chamber_light = True`.

### 11. Speed level

```sh
uv run python hwtest.py my-printer.hal.yaml set speed_level silent
uv run python hwtest.py my-printer.hal.yaml read
uv run python hwtest.py my-printer.hal.yaml set speed_level standard
```

Expected. `done` for each command, and the read shows `speed_level = silent`.

### 12. Pause and resume

Start the small model from the printer's screen and wait until the state reads `running`.

```sh
uv run python hwtest.py my-printer.hal.yaml action pause
uv run python hwtest.py my-printer.hal.yaml read
uv run python hwtest.py my-printer.hal.yaml action resume
```

Expected. `done` for each action. The printer pauses and parks the head, the read shows `state = pause`, and the print continues after resume.

### 13. Stop

With the print still running, run

```sh
uv run python hwtest.py my-printer.hal.yaml stop
```

Expected. `workshop-p1s safe`, the printer ends the print, the nozzle and bed targets go to 0 and the head parks. The state reads `failed` or `finish` afterwards, depending on the firmware.

### 14. Without Developer Mode

Turn Developer Mode off on the printer's screen, then run

```sh
uv run python hwtest.py my-printer.hal.yaml set chamber_light true
```

Expected. `failed` with the printer's reason and the hint to turn on Developer Mode, and the light stays off. If the printer refuses the login instead, note that in the report. Turn Developer Mode back on.

## If something fails

Send the full output of the failing step, the printer model and firmware version (the `firmware` field from step 4), whether LAN-only mode and Developer Mode were on, and your device file without the access code.

## Report template

Save the filled-in report as `reports/<device-id>-<date>.md` and set `provenance.verification` in the device file to `{ status: verified-on-hardware, report: reports/<device-id>-<date>.md }`.

```markdown
# Hardware report, bambu driver

- Device: <model, serial number with the last digits hidden>
- Firmware: <version from identify>
- Host: <computer, operating system>
- OpenHAL commit: <git rev-parse --short HEAD>
- Tested by: <name>, <date>

| Step | Result | Notes |
|---|---|---|
| 1 Developer Mode is on | pass / fail | |
| 2 the printer's certificate | pass / fail | |
| 3 the device file validates | pass / fail | |
| 4 discover and identify | pass / fail | |
| 5 read every channel | pass / fail | |
| 6 describe | pass / fail | |
| 7 a wrong pin | pass / fail | |
| 8 network loss | pass / fail | |
| 9 confirm limits | done | |
| 10 the smallest safe change | pass / fail | |
| 11 speed level | pass / fail | |
| 12 pause and resume | pass / fail | |
| 13 stop | pass / fail | |
| 14 without Developer Mode | pass / fail | |

Anything unexpected:
```
