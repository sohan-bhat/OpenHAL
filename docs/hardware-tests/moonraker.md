# Hardware test plan for the moonraker driver

This plan checks the Moonraker driver on a real Klipper printer. It starts with read-only checks and ends with the smallest safe writes. Stay next to the printer for every write step. Stop at the first step that fails and send what [If something fails](#if-something-fails) lists. [README.md](README.md) has the setup and rules every plan shares.

## What you need

- A Klipper printer with Moonraker, reachable from the computer that runs OpenHAL. Mainsail or Fluidd open in a browser helps to watch it.
- The printer idle, with no print running.
- A checkout of this repository with the moonraker extra, `uv sync --extra moonraker`.
- If Moonraker requires an API key, the key in an environment variable, for example `export MOONRAKER_API_KEY=...`.

## The read-only probe

Save this as `probe.py`. It connects, identifies the printer, prints the driver's proposal and reads every channel. It holds no kernel grant, so it can't change the printer. With `transport: websocket` connecting also subscribes to the objects the file uses, which changes nothing on the printer.

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

## Step 1. Moonraker answers (read-only)

```
curl -s http://voron.local:7125/printer/info
```

Add `-H "X-Api-Key: $MOONRAKER_API_KEY"` when a key is needed. Expected. JSON with `"state": "ready"` and the host name.

## Step 2. Validate the device file (read-only)

```
cp openhal/drivers/moonraker/examples/voron-2-4.hal.yaml ./printer.hal.yaml
uv run openhal file validate ./printer.hal.yaml
```

Set `connect.moonraker` to your host, `match.moonraker.hostname` to the host name from step 1, and remove `token_env` if you have no key. Remove `chamber_temp` and `exhaust_fan` if the printer has no such objects. Add `homed_axes: { type: string, every: 2 s }` under `read`, because step 10 reads it. Expected. `valid ./printer.hal.yaml (voron, medium hazard, read-only)`.

## Step 3. Identify, describe and read (read-only)

```
uv run python probe.py ./printer.hal.yaml
```

Expected.

```
identify {"host": "voron.local", "hostname": "voron", "software_version": "v0.12.0-...", "state": "ready"}
describe { "read": {"state": ..., "extruder_temp": ...}, "write": {"extruder_target": {"max": 280.0, "suggested": true, ...}}, ... }
read state standby
read extruder_temp 24.6 degC
read bed_temp 24.1 degC
read progress 0.0 percent
read extruder_target 0.0 degC
read bed_target 0.0 degC
read fan_speed 0.0 percent
health Health(connected=True, detail='voron', ...)
```

Temperatures match Mainsail or Fluidd. Run it once with `transport: http` and once with `transport: websocket`. Paste both outputs into the report.

## Step 4. Network loss (read-only)

```
while true; do uv run python probe.py ./printer.hal.yaml; sleep 2; done
```

Unplug the printer host's network cable or turn off its Wi-Fi for ten seconds, then restore it. Expected. Runs fail with `Could not reach Moonraker` or `Could not open the Moonraker WebSocket` and work again afterwards. Stop with Ctrl-C.

## Step 5. Start the hub

Read every limit in the file. Then confirm them yourself with `uv run openhal file confirm ./printer.hal.yaml`. It lists each limit and asks you to type `confirm`. Then load the file into a fresh hub.

```
export OPENHAL_HOME="$PWD/openhal-test"
uv run openhal init --no-sample
cp ./printer.hal.yaml "$OPENHAL_HOME/devices/"
uv run openhald --verbose > "$OPENHAL_HOME/hub.log" 2>&1 &
uv run openhal devices
uv run openhal read voron.extruder_temp
```

Expected. `voron` is connected and writable.

## Step 6. The smallest safe write, the part fan

```
uv run openhal write voron.fan_speed "20 %"
uv run openhal read voron.fan_speed
uv run openhal write voron.fan_speed "0 %"
```

Expected. The part fan spins slowly, Mainsail shows about 20 %, then it stops.

## Step 7. A low bed target and the safe state

```
uv run openhal write voron.bed_target "35 degC"
uv run openhal read voron.bed_target
uv run openhal stop
uv run openhal read voron.bed_target
uv run openhal unlock
```

Expected. Mainsail shows a bed target of 35. After `openhal stop` the target is 0 and Klipper stays `ready`. The console shows `TURN_OFF_HEATERS`.

## Step 8. Klipper's own limit is reported (optional)

Do this step only when the bed's `max_temp` in printer.cfg is below the file's limit (110 in the example). Look it up first, for example 100. Then ask for a value between the two, such as 105.

```
uv run openhal write voron.bed_target "105 degC"
```

Expected. Klipper refuses it and the command fails with Klipper's message, which contains `out of range`. The target stays 0. If Mainsail shows a new target at all, set it back to 0 at once and report the step as failed.

## Step 9. A blocked write never reaches the printer

```
uv run openhal write voron.bed_target "150 degC"
```

Expected. Blocked with code `above_max`. Nothing appears in the Klipper console.

## Step 10. Homing (optional, needs a clear bed)

```
uv run openhal action voron.home axes=all
uv run openhal read voron.homed_axes
```

Expected. The printer homes. The action answers `done`, or `started` if homing takes longer than 8 s. `homed_axes` reads `xyz` afterwards, inside a `device-data` block because it is text from the printer. Stop the hub with `kill %1` when done.

## If something fails

Send what [README.md](README.md#if-a-step-fails) lists, plus the reply of the `curl` command from step 1, the Klipper and Moonraker versions from Mainsail or Fluidd, the Klipper console lines from the same minutes, and the transport you used. If a blocked command reached the device, stop the hub, power the device off and report it privately as [SECURITY.md](../../SECURITY.md) says.

## Report template

```
Plan: docs/hardware-tests/moonraker.md
Tested by and date:
OpenHAL: (uv run openhal --version, and git rev-parse --short HEAD)
Device file: (path, and the sha256 in its confirmed line)
Printer, Klipper and Moonraker versions:
Transport tested: http / websocket / both
API key in use: yes / no
Step 1 Moonraker answers:        pass / fail
Step 2 file valid:               pass / fail
Step 3 probe output:             pass / fail   (paste both)
Step 4 network loss:             pass / fail
Step 5 hub lists the device:     pass / fail
Step 6 fan write:                pass / fail
Step 7 bed target and stop:      pass / fail
Step 8 Klipper limit reported:   pass / fail / skipped   message:
Step 9 blocked write:            pass / fail
Step 10 homing:                  pass / fail / skipped   (done or started)
Audit chain: (the line uv run openhal log --verify prints)
Anything unexpected (paste exact output):
Result: verified-on-hardware / tested-reads / failed at step N
```

Save the filled-in report as `docs/hardware-tests/reports/<device id>-<date>.md`. [README.md](README.md#reports) says when it marks the device file `verified-on-hardware`.
