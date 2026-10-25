# Hardware test plan for the opcua driver

This plan checks the OPC UA driver against a real OPC UA server, such as a PLC. It starts with read-only checks and ends with the smallest safe change. Use a variable that drives nothing physical for the first change, or a machine that is safe to run with its own e-stop in reach. Stop at the first step that fails and send what [If something fails](#if-something-fails) lists. [README.md](README.md) has the setup and rules every plan shares.

## What you need

- An OPC UA server reachable from this machine, its endpoint URL and, if it needs one, a user and password.
- The node ids of two readable variables, one with engineering units, and of one writable variable that is safe to change, from the PLC tool or UaExpert.
- Optional. A method that is safe to call.
- A checkout of this repository with the opcua extra, `uv sync --extra opcua`.

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
        print("identify", json.dumps(await driver.identify()))
        print("health", (await driver.health()).detail)
        for name in [*file.read, *file.write]:
            try:
                reading = await driver.read(name)
                print("read", name, reading.value, reading.unit or "", "suspect" if reading.suspect else "")
            except Exception as exc:
                print("read", name, "ERROR", type(exc).__name__, exc)
        print("describe", json.dumps(await driver.describe())[:600])
    finally:
        await driver.close()

asyncio.run(main(sys.argv[1]))
```

Connecting opens a session and reads node classes, data types, access levels and properties. It changes nothing.

## Step 1. Discovery (read-only)

```
uv run python -c "import asyncio; from openhal.drivers.opcua.driver import OpcuaDriver; OpcuaDriver.discovery_urls = ['opc.tcp://<plc>:4840']; print(asyncio.run(OpcuaDriver.discover()))"
```

Expected. At least one entry whose address is the server's endpoint and whose label is its application name.

## Step 2. Validate the device file (read-only)

```
cp openhal/drivers/opcua/examples/dosing-pump.hal.yaml ./plc.hal.yaml
uv run openhal file validate ./plc.hal.yaml
```

Set the endpoint and replace the node ids with yours. If the server needs a login, add `user` and `token_env`, and export the password in that variable. Expected. `valid ./plc.hal.yaml (dosing, medium hazard, read-only)`.

## Step 3. Identify and read (read-only)

```
uv run python probe.py ./plc.hal.yaml
```

Expected.

```
identify {"endpoint": "opc.tcp://...", "product": "...", "manufacturer": "...", "version": "..."}
health opc.tcp://...
read temperature 21.5 degC
read running False
read tank_level 64.0 percent
read speed 0.0 rpm
describe {"device": {...}, "read": {...
```

The values match the PLC tool. A variable with EngineeringUnits shows the converted unit. Paste the full output into the report.

## Step 4. A unit mismatch is refused (read-only)

Change one channel's unit to something that can't convert from the node's unit, for example `unit: V` on a temperature, and run the probe again.

Expected. The connect fails with `... is in degC, which doesn't convert to the file's V.` Put the unit back.

## Step 5. Network loss during reads (read-only)

```
while true; do uv run python probe.py ./plc.hal.yaml | grep tank_level; sleep 2; done
```

Unplug this machine's network cable for ten seconds, then plug it back in. Expected. Runs during the outage fail with a connection or timeout error. Later runs succeed. Stop with Ctrl-C.

## Step 6. Start the hub

Read every limit in the file, then confirm them yourself. The confirm lists each limit and asks you to type `confirm`. Then the file goes into a fresh test home and hub.

```
export OPENHAL_HOME="$PWD/openhal-test"
uv run openhal init --yes --no-sample --no-discover --no-service
uv run openhal file confirm ./plc.hal.yaml
cp ./plc.hal.yaml "$OPENHAL_HOME/devices/"
bash docs/hardware-tests/hub.sh start
uv run openhal devices
uv run openhal read dosing.tank_level
```

Expected. `dosing` is connected and its limits are confirmed.

## Step 7. A blocked change never reaches the server

```
uv run openhal write dosing.speed "5000 rpm"
```

Expected. Blocked with code `above_max`. The PLC tool shows no change.

## Step 8. The smallest safe change, then stop

```
uv run openhal write dosing.speed "100 rpm"
uv run openhal read dosing.speed
uv run openhal stop
uv run openhal read dosing.speed
uv run openhal unlock
```

Expected. The PLC tool shows 100, and the read says `100 rpm`. After the stop the file's safe state runs, the Stop method if you kept it, then 0, and the read says `0 rpm`. `openhal unlock` asks you to type `unlock`.

## Step 9. A method call (optional)

```
uv run openhal action dosing.stop
```

Expected. Done. The PLC tool shows the method ran.

Stop the hub with `bash docs/hardware-tests/hub.sh stop` when done.

## If something fails

Send what [README.md](README.md#if-a-step-fails) lists, plus the endpoint and security mode, what UaExpert or the PLC tool shows for the node (data type, access level, engineering units), and the server's product and version. If a blocked command reached the device, stop the hub, power the device off and report it privately as [SECURITY.md](../../SECURITY.md) says.

## Report template

```
Plan: docs/hardware-tests/opcua.md
Tested by and date:
OpenHAL: (uv run openhal --version, and git rev-parse --short HEAD)
Device file: (path, and the sha256 in its confirmed line)
Server: (PLC or product, firmware, OPC UA stack)
Security and login used:
Step 1 discovery:                pass / fail
Step 2 file valid:               pass / fail
Step 3 probe output:             pass / fail   (paste it)
Step 4 unit mismatch refused:    pass / fail
Step 5 network loss:             pass / fail
Step 6 hub lists the device:     pass / fail
Step 7 blocked change:           pass / fail
Step 8 smallest change and stop: pass / fail
Step 9 method call:              pass / fail / skipped
Audit chain: (the line uv run openhal log --verify prints)
Anything unexpected (paste exact output):
Result: verified-on-hardware / tested-reads / failed at step N
```

Save the filled-in report as `docs/hardware-tests/reports/<device id>-<date>.md`. [README.md](README.md#reports) says when it marks the device file `verified-on-hardware`.
