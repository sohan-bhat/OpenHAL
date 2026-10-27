# Hardware test plan for the indi driver

This plan checks the INDI driver on a real mount, and optionally a focuser. The plan starts with read-only checks and ends with the smallest safe moves. Stay at the mount for every step that moves it, with its power switch in reach. Stop at the first step that fails and send what [If something fails](#if-something-fails) lists. [README.md](README.md) has the setup and rules every plan shares.

## What you need

- A mount on `indiserver` (for example `indi_eqmod_telescope`), reachable from this machine on port 7624. Note the device name from the INDI control panel.
- A balanced mount, a capped tube or a clear sky, and nothing within the swing of the tube and counterweight.
- Optional. An absolute focuser on the same server.
- A checkout of this repository, `uv sync`. The INDI driver needs no extra.

## The read-only probe

Save this as `probe.py`. The probe connects, identifies the device and reads every channel. The probe holds no kernel grant, so the probe can't change anything.

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
uv run python -c "import asyncio; from openhal.drivers.indi.driver import IndiDriver; print(asyncio.run(IndiDriver.discover()))"
```

Expected. One entry per device, such as `indi://127.0.0.1:7624/EQMod Mount`, with `indi.driver` set. The mount stays disconnected if it was.

## Step 2. Validate the device file (read-only)

```
cp openhal/drivers/indi/examples/eq6-mount.hal.yaml ./mount.hal.yaml
uv run openhal file validate ./mount.hal.yaml
```

Set `indi:` to the server host and `device:` to your mount's name. Raise the declination minimum until the tube clears the pier and the horizon. Expected. `valid ./mount.hal.yaml (eq6, medium hazard, read-only)`.

## Step 3. Identify and read

```
uv run python probe.py ./mount.hal.yaml
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
while true; do uv run python probe.py ./mount.hal.yaml | grep declination; sleep 2; done
```

Stop `indiserver` for ten seconds, then start it again with the same drivers. Expected. Runs during the outage fail with `Could not reach the INDI server`. Later runs succeed. Stop with Ctrl-C.

## Step 5. Start the hub

Read every limit in the file, then confirm them yourself. The confirm lists each limit and asks you to type `confirm`. Then the file goes into a fresh test home and hub.

```
export OPENHAL_HOME="$PWD/openhal-test"
uv run openhal init --yes --no-sample --no-discover --no-service
uv run openhal file confirm ./mount.hal.yaml
cp ./mount.hal.yaml "$OPENHAL_HOME/devices/"
bash docs/hardware-tests/hub.sh start
uv run openhal devices
uv run openhal read eq6.declination
```

Expected. `eq6` is connected and its limits are confirmed.

## Step 6. Abort while idle, the smallest action

```
uv run openhal action eq6.abort
uv run openhal read eq6.slewing
```

Expected. Done. Nothing moves. The control panel shows TELESCOPE_ABORT_MOTION as Ok.

## Step 7. Unpark and tracking on and off

```
uv run openhal action eq6.unpark
uv run openhal write eq6.tracking true
uv run openhal read eq6.tracking
uv run openhal write eq6.tracking false
```

Expected. Unpark answers done. Tracking starts and stops, and the reads match the control panel.

## Step 8. A blocked slew never reaches the mount

```
uv run openhal action eq6.slew_to_coordinates right_ascension="90 deg" declination="-60 deg"
```

Expected. Blocked with code `below_min`. The mount doesn't move and the control panel shows no new target.

## Step 9. A short slew and a stop

Read `right_ascension` and `declination`, then slew 5 degrees north of where the mount points now. Open a second terminal in the checkout and run `export OPENHAL_HOME="$PWD/openhal-test"` there, so the stop can go in while the slew runs.

In the first terminal, start the slew.

```
uv run openhal action eq6.slew_to_coordinates right_ascension="<current> deg" declination="<current + 5> deg"
```

In the second terminal, while the mount is still slewing, stop it.

```
uv run openhal stop
uv run openhal read eq6.slewing eq6.tracking
uv run openhal unlock
```

Expected. The slew stops within a second. The stop reports `eq6  safe`, `slewing` reads `false` and `tracking` reads `false`. The first terminal's action ends with `done` or `started`. The control panel shows EQUATORIAL_EOD_COORD in Alert or Idle, which is how drivers report an aborted slew. `openhal unlock` asks you to type `unlock`.

## Step 10. Park (optional)

```
uv run openhal action eq6.park
uv run openhal read eq6.parked
```

Expected. The mount slews to its park position. The action answers `done`, or `started` if parking takes longer than 8 s. `parked` reads true once it arrives.

## Step 11. Focuser (optional)

Save this as `./focuser.hal.yaml`, with `indi` set to your server, `device` set to the focuser's name in the INDI control panel and `max` set to its FOCUS_MAX.

```yaml
device: Focuser
id: focuser
connect: { indi: astro-pi.local, port: 7624, device: "ZWO EAF", kind: focuser, timeout: 5 s, action_wait: 8 s }
read:
  moving: { type: bool, every: 1 s }
write:
  position: { unit: dimensionless, min: 0, max: 10000, step: 1 }
actions:
  abort: { description: "Stop the focuser at once (FOCUS_ABORT_MOTION)." }
safe_state: { action: abort }
hazard: low
```

Stop the hub, confirm the file, add it and start the hub again. Then move the focuser 100 steps.

```
bash docs/hardware-tests/hub.sh stop
uv run openhal file confirm ./focuser.hal.yaml
cp ./focuser.hal.yaml "$OPENHAL_HOME/devices/"
bash docs/hardware-tests/hub.sh start
uv run openhal devices
uv run openhal read focuser.position
uv run openhal write focuser.position "<current + 100> dimensionless"
uv run openhal action focuser.abort
```

Expected. `devices` lists `focuser` as connected and writable. The focuser moves 100 steps, and `abort` answers `done  Done. abort ran.`

Stop the hub with `bash docs/hardware-tests/hub.sh stop` when done.

## If something fails

Send what [README.md](README.md#if-a-step-fails) lists, plus the indiserver output from the same minutes, a screenshot of the INDI control panel's properties, and the INDI driver name and version. If a blocked command reached the device, stop the hub, power the device off and report it privately as [SECURITY.md](../../SECURITY.md) says.

## Report template

```
Plan: docs/hardware-tests/indi.md
Tested by and date:
OpenHAL: (uv run openhal --version, and git rev-parse --short HEAD)
Device file: (path, and the sha256 in its confirmed line)
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
Audit chain: (the line uv run openhal log --verify prints)
Anything unexpected (paste exact output):
Result: verified-on-hardware / tested-reads / failed at step N
```

Save the filled-in report as `docs/hardware-tests/reports/<device id>-<date>.md`. [README.md](README.md#reports) says when it marks the device file `verified-on-hardware`.
