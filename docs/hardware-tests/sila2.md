# Hardware test plan for the sila2 driver

This plan checks the SiLA 2 driver on a real SiLA 2 device. It starts with read-only checks and ends with the smallest safe change. Use an empty device for the change steps, with no plate, sample or liquid, and stay next to it. Stop at the first step that fails and send back the report below.

## What you need

- A device or gateway with a SiLA 2 server, its host and port, and its CA certificate as a PEM file.
- The names of one property, one command that sets a value and one command that stops the device, from its documentation or the describe proposal.
- OpenHAL installed with `uv pip install 'openhal-hub[sila2]'`.

## The read-only probe

Save this as `probe.py`. It connects, identifies the server and reads every channel. It holds no kernel grant, so it can't change anything.

```python
import asyncio, json, sys
from openhal.drivers import registry
from openhal.spec import load

async def main(path):
    file = load(path)
    driver = registry.load(file.connect.driver)(file)
    await driver.connect()
    try:
        await asyncio.sleep(1)
        print("identify", json.dumps(await driver.identify()))
        print("health", (await driver.health()).detail)
        for name in [*file.read, *file.write]:
            try:
                reading = await driver.read(name)
                print("read", name, reading.value, reading.unit or "")
            except Exception as exc:
                print("read", name, "ERROR", type(exc).__name__, exc)
        print("describe", json.dumps(await driver.describe())[:600])
    finally:
        await driver.close()

asyncio.run(main(sys.argv[1]))
```

Connecting asks SiLAService for the implemented features and their definitions, and subscribes to the observable properties the file names. It changes nothing.

## Step 1. Discovery (read-only)

```
python -c "import asyncio; from openhal.drivers.sila2.driver import Sila2Driver; print(asyncio.run(Sila2Driver.discover()))"
```

Expected. An entry with the server's address, such as `sila://192.168.1.30:50052`. If nothing appears, the network may block mDNS. Use the host and port directly.

## Step 2. Validate the device file (read-only)

```
cp openhal/drivers/sila2/examples/thermoshaker.hal.yaml ./device.hal.yaml
openhal file validate ./device.hal.yaml
```

Set the host, port and `ca_file`, and change the feature, property and command names to your device's. Expected. `valid ./device.hal.yaml (thermoshaker, medium hazard, read-only)`.

## Step 3. Identify and read (read-only)

```
python probe.py ./device.hal.yaml
```

Expected.

```
identify {"server": "...:50052", "ServerName": "...", "ServerType": "...", "ServerUUID": "...", "ServerVersion": "..."}
health ... at ...:50052
read temperature 22.4 degC
read speed 0.0 rpm
read lid_closed True
read target 22.0 degC
describe {"device": {"name": "SiLA 2 device"}, "read": {...
```

Values match the device's own display or software. Paste the full output into the report.

## Step 4. A wrong name is refused (read-only)

Change one property name in the file to one the device doesn't have, and run the probe again. Expected. The connect fails with `... has no property ...`. Put the name back.

## Step 5. Network loss during reads (read-only)

```
while true; do python probe.py ./device.hal.yaml | grep temperature; sleep 2; done
```

Unplug this machine's network cable for ten seconds, then plug it back in. Expected. Runs during the outage fail with a connection error. Later runs succeed. Stop with Ctrl-C.

## Step 6. Start the hub

Confirm the limits by adding `confirmed: { by: <your name>, at: <today> }`, then load the file into a fresh hub.

```
export OPENHAL_HOME="$PWD/openhal-test"
openhal init
cp ./device.hal.yaml "$OPENHAL_HOME/devices/"
openhald &
openhal devices
openhal read thermoshaker.temperature
```

Expected. `thermoshaker` is connected and its limits are confirmed.

## Step 7. A blocked change never reaches the device

```
openhal write thermoshaker.target "90 degC"
```

Expected. Blocked with code `above_max`. The device's display doesn't change.

## Step 8. The smallest safe change, then stop

```
openhal write thermoshaker.target "25 degC"
openhal read thermoshaker.target
openhal stop
openhal read thermoshaker.target
openhal unlock
```

Expected. The device's target becomes 25 degC and the read says so. After the stop the file's safe state runs, the stop command and then 22 degC. `openhal unlock` asks you to type `unlock`.

## Step 9. A short command (optional)

```
openhal action thermoshaker.shake rpm="200 rpm" seconds="5 s"
openhal read thermoshaker.speed
```

Expected. The device runs for 5 s at 200 rpm and the action answers `done`. The speed stream shows 200 rpm while it runs.

Stop the hub with `kill %1` when done.

## Report template

```
Driver: sila2
OpenHAL version:
Device, SiLA server and its version:
Encryption used (CA file or insecure):
Step 1 discovery:                pass / fail / skipped
Step 2 file valid:               pass / fail
Step 3 probe output:             pass / fail   (paste it)
Step 4 wrong name refused:       pass / fail
Step 5 network loss:             pass / fail
Step 6 hub lists the device:     pass / fail
Step 7 blocked change:           pass / fail
Step 8 smallest change and stop: pass / fail
Step 9 short command:            pass / fail / skipped
Anything unexpected (paste exact output):
Result: verified-on-hardware / failed at step N
```

A passing report lets the device file set `provenance.verification.status: verified-on-hardware` with `report:` pointing at the saved report.
