# Hardware test plan for the indi driver

This plan checks the INDI driver on a real mount, and optionally a focuser. It starts with read-only checks and ends with the smallest safe moves. Stay at the mount for every step that moves it, with its power switch in reach. Stop at the first step that fails and send back the report below.

## What you need

- A mount on `indiserver` (for example `indi_eqmod_telescope`), reachable from this machine on port 7624. Note the device name from the INDI control panel.
- A balanced mount, a capped tube or a clear sky, and nothing within the swing of the tube and counterweight.
- Optional. An absolute focuser on the same server.
- OpenHAL installed with `uv pip install openhal-hub`. The INDI driver needs no extra.

## The read-only probe

Save this as `probe.py`. It connects, identifies the device and reads every channel. It holds no kernel grant, so it can't change anything.

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
        print("health", (await driver.health()).detail)
        for name in [*file.read, *file.write]:
            try:
                reading = await driver.read(name)
                print("read", name, reading.value, reading.unit or "")
            except Exception as exc:
                print("read", name, "ERROR", type(exc).__name__, exc)
        print("describe", json.dumps(await driver.describe())[:400])
    finally:
        await driver.close()

asyncio.run(main(sys.argv[1]))
```

Connecting sends `getProperties` and turns the device's CONNECTION switch on, the same thing the INDI control panel's Connect button does. Nothing moves.

## Step 1. Discovery (read-only)

On the machine that runs `indiserver`.

```
python -c "import asyncio; from openhal.drivers.indi.driver import IndiDriver; print(asyncio.run(IndiDriver.discover()))"
```

Expected. One entry per device, such as `indi://127.0.0.1:7624/EQMod Mount`, with `indi.driver` set. The mount stays disconnected if it was.

## Step 2. Validate the device file (read-only)

```
cp openhal/drivers/indi/examples/eq6-mount.hal.yaml ./mount.hal.yaml
openhal file validate ./mount.hal.yaml
```

Set `indi:` to the server host and `device:` to your mount's name. Raise the declination minimum until the tube clears the pier and the horizon. Expected. `valid ./mount.hal.yaml (eq6, medium hazard, read-only)`.

## Step 3. Identify and read

```
python probe.py ./mount.hal.yaml
```

Expected.

```
identify {"server": "astro-pi.local:7624", "device": "EQMod Mount", "driver_name": "EQMod Mount", "driver_exec": "indi_eqmod_telescope", ...}
health EQMod Mount on astro-pi.local:7624
read right_ascension 83.6 deg
read declination 22.0 deg
read altitude 45.1 deg
read azimuth 180.2 deg
read slewing False
read parked True
read tracking False
describe {"device": {"name": "EQMod Mount"}, ...
```

Right ascension is in degrees. Divide by 15 and it matches the hours in the control panel. The control panel now shows the mount connected. Paste the full output into the report.

## Step 4. Server loss during reads (read-only)

```
while true; do python probe.py ./mount.hal.yaml | grep declination; sleep 2; done
```

Stop `indiserver` for ten seconds, then start it again with the same drivers. Expected. Runs during the outage fail with `Could not reach the INDI server`. Later runs succeed. Stop with Ctrl-C.

## Step 5. Start the hub

Confirm the limits by adding `confirmed: { by: <your name>, at: <today> }`, then load the file into a fresh hub.

```
export OPENHAL_HOME="$PWD/openhal-test"
openhal init
cp ./mount.hal.yaml "$OPENHAL_HOME/devices/"
openhald &
openhal devices
openhal read eq6.declination
```

Expected. `eq6` is connected and its limits are confirmed.

## Step 6. Abort while idle, the smallest action

```
openhal action eq6.abort
openhal read eq6.slewing
```

Expected. Done. Nothing moves. The control panel shows TELESCOPE_ABORT_MOTION as Ok.

## Step 7. Unpark and tracking on and off

```
openhal action eq6.unpark
openhal write eq6.tracking true
openhal read eq6.tracking
openhal write eq6.tracking false
```

Expected. Unpark answers done. Tracking starts and stops, and the reads match the control panel.

## Step 8. A blocked slew never reaches the mount

```
openhal action eq6.slew_to_coordinates right_ascension="90 deg" declination="-60 deg"
```

Expected. Blocked with code `below_min`. The mount doesn't move and the control panel shows no new target.

## Step 9. A short slew and a stop

Read `right_ascension` and `declination`, then slew 5 degrees north of where the mount points now.

```
openhal action eq6.slew_to_coordinates right_ascension="<current> deg" declination="<current + 5> deg"
openhal stop
openhal read eq6.slewing
openhal read eq6.tracking
openhal unlock
```

Run `openhal stop` while it is still slewing. Expected. The slew stops within a second, `slewing` reads false and `tracking` reads false. The control panel shows EQUATORIAL_EOD_COORD in Alert or Idle, which is how drivers report an aborted slew. `openhal unlock` asks you to type `unlock`.

## Step 10. Park (optional)

```
openhal action eq6.park
openhal read eq6.parked
```

Expected. The mount slews to its park position. The action answers `done`, or `started` if parking takes longer than 8 s. `parked` reads true once it arrives.

## Step 11. Focuser (optional)

Make a focuser file with `kind: focuser` and the focuser's device name from the describe proposal, confirm it, add it to the hub and move it 100 steps.

```
openhal read focuser.position
openhal write focuser.position "<current + 100> dimensionless"
openhal action focuser.abort
```

Expected. The focuser moves 100 steps and the abort answers done.

Stop the hub with `kill %1` when done.

## Report template

```
Driver: indi
OpenHAL version:
Mount, INDI driver and indiserver version:
Host OS and network:
Step 1 discovery:                pass / fail
Step 2 file valid:               pass / fail
Step 3 probe output:             pass / fail   (paste it)
Step 4 server loss:              pass / fail
Step 5 hub lists the device:     pass / fail
Step 6 abort while idle:         pass / fail
Step 7 unpark and tracking:      pass / fail
Step 8 blocked slew:             pass / fail
Step 9 short slew and stop:      pass / fail
Step 10 park:                    pass / fail / skipped
Step 11 focuser:                 pass / fail / skipped
Anything unexpected (paste exact output):
Result: verified-on-hardware / failed at step N
```

A passing report lets the device file set `provenance.verification.status: verified-on-hardware` with `report:` pointing at the saved report.
