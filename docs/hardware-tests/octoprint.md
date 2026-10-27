# Hardware test plan for the octoprint driver

This plan checks the OctoPrint driver against a real OctoPrint server with a printer attached. The plan starts with read-only checks and ends with the smallest safe writes. Stay next to the printer for every write step. Stop at the first step that fails and send what [If something fails](#if-something-fails) lists. [README.md](README.md) has the setup and rules every plan shares.

## What you need

- OctoPrint 1.9 or newer with a printer connected and idle.
- An application key for OpenHAL (Settings, Application Keys), exported as `OCTOPRINT_API_KEY`.
- A checkout of this repository with the octoprint extra, `uv sync --extra octoprint`.

## The read-only probe

Save this as `probe.py`. The probe connects, identifies the server, prints the driver's proposal and reads every channel. The probe holds no kernel grant, so the probe can't change the printer.

```python
import asyncio, json, sys
from openhal.drivers import registry
from openhal.spec import load

async def main(path):
    file = load(path)
    driver = registry.load(file.connect.driver)(file)
    await driver.connect()
    try:
        print("identify", json.dumps(await driver.identify()))
        print("describe", json.dumps(await driver.describe(), indent=2, default=str))
        for name in [*file.read, *file.write]:
            try:
                reading = await driver.read(name)
                print("read", name, reading.value, reading.unit or "")
            except Exception as exc:
                print("read", name, "ERROR", type(exc).__name__, exc)
        print("health", await driver.health())
    finally:
        await driver.close()

asyncio.run(main(sys.argv[1]))
```

## Step 1. OctoPrint answers (read-only)

```
curl -s -H "X-Api-Key: $OCTOPRINT_API_KEY" http://octopi.local/api/version
```

Expected. `{"api": "0.1", "server": "1.10.2", "text": "OctoPrint 1.10.2"}` or similar.

## Step 2. Validate the device file (read-only)

```
cp openhal/drivers/octoprint/examples/prusa-mk3s-octopi.hal.yaml ./printer.hal.yaml
uv run openhal file validate ./printer.hal.yaml
```

Set `connect.octoprint` to your host and the limits to your printer. Expected. `valid ./printer.hal.yaml (mk3s, medium hazard, read-only)`.

## Step 3. Identify, describe and read (read-only)

```
uv run python probe.py ./printer.hal.yaml
```

Expected.

```
identify {"host": "octopi.local", "server": "1.10.2", "api": "0.1"}
describe { "device": {"name": "..."}, "read": {...}, "write": {...}, ... }
read state standby
read extruder_temp 24.0 degC
read bed_temp 23.5 degC
read progress None percent
read extruder_target 0.0 degC
read bed_target 0.0 degC
read fan_speed None percent
health Health(connected=True, detail='OctoPrint 1.10.2', ...)
```

Temperatures match OctoPrint's temperature tab. Paste the full output into the report.

## Step 4. Printer disconnected in OctoPrint (read-only)

Press Disconnect in OctoPrint's connection panel, run the probe, then press Connect again.

```
uv run python probe.py ./printer.hal.yaml
```

Expected. `state` reads `offline`, the temperature reads fail with `can't do this now`, and `health` is not connected. After reconnecting in OctoPrint the probe works again.

## Step 5. Start the hub

Read every limit in the file, then confirm them yourself. The confirm lists each limit and asks you to type `confirm`. Then the file goes into a fresh test home and hub.

```
export OPENHAL_HOME="$PWD/openhal-test"
uv run openhal init --yes --no-sample --no-discover --no-service
uv run openhal file confirm ./printer.hal.yaml
cp ./printer.hal.yaml "$OPENHAL_HOME/devices/"
bash docs/hardware-tests/hub.sh start
uv run openhal devices
uv run openhal read mk3s.extruder_temp
```

Expected. `mk3s` is connected and writable.

## Step 6. The smallest safe write, the part fan

```
uv run openhal write mk3s.fan_speed "20 %"
uv run openhal read mk3s.fan_speed
uv run openhal write mk3s.fan_speed "0 %"
```

Expected. The part fan spins slowly, OctoPrint's terminal shows `M106 P0 S51`, then `M106 P0 S0`.

## Step 7. A low bed target and the safe state

```
uv run openhal write mk3s.bed_target "35 degC"
uv run openhal read mk3s.bed_target
uv run openhal stop
uv run openhal read mk3s.bed_target
uv run openhal unlock
```

Expected. OctoPrint shows a bed target of 35, then 0 after `openhal stop`.

## Step 8. A blocked write never reaches the printer

```
uv run openhal write mk3s.bed_target "150 degC"
```

Expected. Blocked with code `above_max`. Nothing appears in OctoPrint's terminal.

## Step 9. Homing (optional, needs a clear bed)

```
uv run openhal action mk3s.home axes=all
```

Expected. `done  Done. home ran.`, because OctoPrint accepted the command into its queue, and the printer homes. Stop the hub with `bash docs/hardware-tests/hub.sh stop` when done.

## If something fails

Send what [README.md](README.md#if-a-step-fails) lists, plus the reply of the `curl` command from step 1, OctoPrint's terminal lines from the same minutes, and the printer model and firmware. If a blocked command reached the device, stop the hub, power the device off and report it privately as [SECURITY.md](../../SECURITY.md) says.

## Report template

```
Plan: docs/hardware-tests/octoprint.md
Tested by and date:
OpenHAL: (uv run openhal --version, and git rev-parse --short HEAD)
Device file: (path, and the sha256 in its confirmed line)
OctoPrint version and printer:
Step 1 OctoPrint answers:        pass / fail
Step 2 file valid:               pass / fail
Step 3 probe output:             pass / fail   (paste it)
Step 4 disconnected printer:     pass / fail
Step 5 hub lists the device:     pass / fail
Step 6 fan write:                pass / fail
Step 7 bed target and stop:      pass / fail
Step 8 blocked write:            pass / fail
Step 9 homing:                   pass / fail / skipped
Audit chain: (the line uv run openhal log --verify prints)
Anything unexpected (paste exact output):
Result: verified-on-hardware / tested-reads / failed at step N
```

Save the filled-in report as `docs/hardware-tests/reports/<device id>-<date>.md`. [README.md](README.md#reports) says when it marks the device file `verified-on-hardware`.
