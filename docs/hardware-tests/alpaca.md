# Hardware test plan for the alpaca driver

This plan checks the Alpaca driver on a real mount, and optionally a focuser. It starts with read-only checks and ends with the smallest safe moves. Stay at the mount for every move with the mount's own power switch in reach. Stop at the first step that fails and send back the report below.

## What you need

- A mount reachable over Alpaca, either natively or through ASCOM Remote on the Windows machine that runs its ASCOM driver. Note the server name, port and device number.
- A clear sky or a capped tube, a balanced mount and nothing within the swing of the tube and counterweight.
- Optional. An absolute focuser on the same server.
- OpenHAL installed with `uv pip install 'openhal-hub[alpaca]'`, on a machine on the same network.

## The read-only probe

Save this as `probe.py`. It connects, identifies the device and reads every channel. It holds no kernel grant, so it can't write anything.

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

Connecting sends GET requests to the management API and sets `Connected` to true on the device, the same thing every Alpaca client does before it can read. Nothing moves.

## Step 1. Discovery (read-only)

```
python -c "import asyncio; from openhal.drivers.alpaca.driver import AlpacaDriver; print(asyncio.run(AlpacaDriver.discover()))"
```

Expected. One `Discovered` entry per configured device, with an address such as `http://192.168.1.20:11111/api/v1/telescope/0` and the device name as the label. If nothing is found, check that the server has discovery enabled and that UDP port 32227 isn't blocked, then use the host name directly.

## Step 2. The management API answers (read-only)

```
curl -s http://<host>:11111/management/apiversions
curl -s http://<host>:11111/management/v1/configureddevices
```

Expected. `"Value":[1]` and a list that includes your telescope with its device number.

## Step 3. Validate the device file (read-only)

```
cp openhal/drivers/alpaca/examples/eq-mount.hal.yaml ./mount.hal.yaml
openhal file validate ./mount.hal.yaml
```

Set `alpaca:` to your host, and `device_number` if it isn't 0. Raise the declination minimum until the tube clears the pier and the horizon. Expected. `valid ./mount.hal.yaml (mount, medium hazard, read-only)`.

## Step 4. Identify and read (read-only)

```
python probe.py ./mount.hal.yaml
```

Expected.

```
identify {"server": "http://...:11111", "device": "telescope/0", "name": "...", "driverinfo": "...", "interfaceversion": "3", ...}
health <server name>
read right_ascension 83.6 deg
read declination 22.0 deg
read altitude 45.1 deg
read azimuth 180.2 deg
read slewing False
read at_park True
read tracking False
describe {"device": {"name": "..."}, "read": {...}, "write": {"tracking": ...}, "actions": {...
```

Right ascension is in degrees. Divide by 15 and it matches the hours your planetarium program shows. Paste the full output into the report.

## Step 5. Network loss during reads (read-only)

```
while true; do python probe.py ./mount.hal.yaml | grep declination; sleep 2; done
```

Stop the Alpaca server or unplug its network cable for ten seconds, then restore it. Expected. Runs during the outage fail with `Could not reach the Alpaca server`. Later runs succeed. Stop with Ctrl-C.

## Step 6. Start the hub

Confirm the limits by adding `confirmed: { by: <your name>, at: <today> }`, then load the file into a fresh hub.

```
export OPENHAL_HOME="$PWD/openhal-test"
openhal init
cp ./mount.hal.yaml "$OPENHAL_HOME/devices/"
openhald &
openhal devices
openhal read mount.declination
```

Expected. `mount` is connected and writable.

## Step 7. Abort while idle, the smallest action

```
openhal action mount.abort_slew
openhal read mount.slewing
```

Expected. Done, or failed with `0x408 not allowed while parked` if the mount is parked. Nothing moves.

## Step 8. Unpark and tracking on and off

```
openhal action mount.unpark
openhal write mount.tracking true
openhal read mount.tracking
openhal write mount.tracking false
```

Expected. The mount unparks without moving, or moves only to its unparked position. Tracking starts with a quiet motor sound and stops again. Reads match.

## Step 9. A blocked slew never reaches the mount

```
openhal write mount.tracking true
openhal action mount.slew_to_coordinates right_ascension="90 deg" declination="-60 deg"
```

Expected. Blocked with code `below_min`. The mount doesn't move.

## Step 10. A short slew and a stop

Pick a target a few degrees from where the mount points now, well above your horizon. Read `right_ascension` and `declination`, then add 5 degrees to the declination.

```
openhal action mount.slew_to_coordinates right_ascension="<current> deg" declination="<current + 5> deg"
openhal stop
openhal read mount.slewing
openhal read mount.tracking
openhal unlock
```

Run `openhal stop` while it is still slewing. Expected. The slew stops within a second. `slewing` reads false and `tracking` reads false. `openhal unlock` asks you to type `unlock`.

## Step 11. Park (optional)

```
openhal action mount.park
openhal read mount.at_park
```

Expected. The mount slews to its park position. The action answers `done`, or `started` if parking takes longer than 8 s. `at_park` reads true once it arrives.

## Step 12. Focuser (optional)

Write a focuser file from the describe proposal with `device_type: focuser`, confirm it, add it to the hub and move it 100 steps.

```
openhal read focuser.position
openhal write focuser.position "<current + 100> dimensionless"
openhal action focuser.halt
```

Expected. The focuser moves 100 steps. Halt answers done.

Stop the hub with `kill %1` when done.

## Report template

```
Driver: alpaca
OpenHAL version:
Mount and Alpaca server: (model, ASCOM driver or native server, server version)
Host OS and network:
Step 1 discovery:                pass / fail
Step 2 management API:           pass / fail
Step 3 file valid:               pass / fail
Step 4 probe output:             pass / fail   (paste it)
Step 5 network loss:             pass / fail
Step 6 hub lists the device:     pass / fail
Step 7 abort while idle:         pass / fail
Step 8 unpark and tracking:      pass / fail
Step 9 blocked slew:             pass / fail
Step 10 short slew and stop:     pass / fail
Step 11 park:                    pass / fail / skipped
Step 12 focuser:                 pass / fail / skipped
Anything unexpected (paste exact output):
Result: verified-on-hardware / failed at step N
```

A passing report lets the device file set `provenance.verification.status: verified-on-hardware` with `report:` pointing at the saved report.
