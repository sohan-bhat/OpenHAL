# Hardware test plan for the octoprint driver

This plan checks the OctoPrint driver against a real OctoPrint server with a printer attached. It starts with read-only checks and ends with the smallest safe writes. Stay next to the printer for every write step. Stop at the first step that fails and send back the report below.

## What you need

- OctoPrint 1.9 or newer with a printer connected and idle.
- An application key for OpenHAL (Settings, Application Keys), exported as `OCTOPRINT_API_KEY`.
- OpenHAL installed with `uv pip install 'openhal-hub[octoprint]'`.

## The read-only probe

Save this as `probe.py`. It connects, identifies the server, prints the driver's proposal and reads every channel. It holds no kernel grant, so it can't change the printer.

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
openhal file validate ./printer.hal.yaml
```

Set `connect.octoprint` to your host and the limits to your printer. Expected. `valid ./printer.hal.yaml (mk3s, medium hazard, read-only)`.

## Step 3. Identify, describe and read (read-only)

```
python probe.py ./printer.hal.yaml
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
python probe.py ./printer.hal.yaml
```

Expected. `state` reads `offline`, the temperature reads fail with `can't do this now`, and `health` is not connected. After reconnecting in OctoPrint the probe works again.

## Step 5. Start the hub

Confirm the limits by adding `confirmed: { by: <your name>, at: <today> }`, then load the file into a fresh hub.

```
export OPENHAL_HOME="$PWD/openhal-test"
openhal init
cp ./printer.hal.yaml "$OPENHAL_HOME/devices/"
openhald &
openhal devices
openhal read mk3s.extruder_temp
```

Expected. `mk3s` is connected and writable.

## Step 6. The smallest safe write, the part fan

```
openhal write mk3s.fan_speed "20 %"
openhal read mk3s.fan_speed
openhal write mk3s.fan_speed "0 %"
```

Expected. The part fan spins slowly, OctoPrint's terminal shows `M106 P0 S51`, then `M106 P0 S0`.

## Step 7. A low bed target and the safe state

```
openhal write mk3s.bed_target "35 degC"
openhal read mk3s.bed_target
openhal stop
openhal read mk3s.bed_target
openhal unlock
```

Expected. OctoPrint shows a bed target of 35, then 0 after `openhal stop`.

## Step 8. A blocked write never reaches the printer

```
openhal write mk3s.bed_target "150 degC"
```

Expected. Blocked with code `above_max`. Nothing appears in OctoPrint's terminal.

## Step 9. Homing (optional, needs a clear bed)

```
openhal action mk3s.home axes=all
```

Expected. The answer is `done` with status `queued`, and the printer homes. Stop the hub with `kill %1` when done.

## Report template

```
Driver: octoprint
OpenHAL version:
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
Anything unexpected (paste exact output):
Result: verified-on-hardware / failed at step N
```

A passing report lets the device file set `provenance.verification.status: verified-on-hardware` with `report:` pointing at the saved report.
