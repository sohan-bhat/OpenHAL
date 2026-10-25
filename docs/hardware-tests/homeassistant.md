# Hardware test plan for the homeassistant driver

This plan checks the Home Assistant bridge against a real Home Assistant instance. It starts with read-only checks and ends with the smallest safe writes, on a lamp. Stop at the first step that fails and send what [If something fails](#if-something-fails) lists. [README.md](README.md) has the setup and rules every plan shares.

## What you need

- Home Assistant 2024.1 or newer, reachable from the computer that runs OpenHAL.
- One dimmable light and one sensor in Home Assistant. A smart bulb and any temperature sensor work.
- A long-lived access token, exported as `HA_TOKEN`.
- A checkout of this repository with the homeassistant extra, `uv sync --extra homeassistant`.

## The read-only probe

Save this as `probe.py`. It connects, prints the driver's proposal for the selected entities and reads every channel. It holds no kernel grant, so it can't call any service.

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

## Step 1. Home Assistant answers (read-only)

```
curl -s -H "Authorization: Bearer $HA_TOKEN" http://homeassistant.local:8123/api/
```

Expected. `{"message": "API running."}`. Note the entity ids of the light and the sensor from Settings, Entities.

## Step 2. Write and validate a device file (read-only)

Save this as `./lamp.hal.yaml` with your entity ids.

```yaml
device: Test lamp
id: test-lamp
connect:
  homeassistant: homeassistant.local
  token_env: HA_TOKEN
  entities: [light.your_lamp, sensor.your_temperature]
read:
  temperature: { unit: degC, map: { entity: sensor.your_temperature } }
write:
  lamp: { type: bool, map: { entity: light.your_lamp } }
  lamp_brightness: { unit: percent, min: 5, max: 60, map: { entity: light.your_lamp } }
safe_state: { lamp: false }
hazard: low
```

```
uv run openhal file validate ./lamp.hal.yaml
```

Expected. `valid ./lamp.hal.yaml (test-lamp, low hazard, read-only)`.

## Step 3. Describe and read over REST (read-only)

```
uv run python probe.py ./lamp.hal.yaml
```

Expected. `describe` lists only your two entities, with the light's brightness and colour temperature and the sensor's unit. The reads match the Home Assistant dashboard. A Fahrenheit sensor reads in degC.

## Step 4. The same over WebSocket (read-only)

Add `transport: websocket` under `connect` and run the probe again. Expected. The same values. Paste both outputs into the report.

## Step 5. An entity outside the selection is refused (read-only)

Add a channel `other: { type: bool, map: { entity: switch.anything_else } }` under `read` and run `python probe.py ./lamp.hal.yaml`. Expected. The driver refuses the file with `which the file doesn't select`. Remove the channel again.

## Step 6. Unavailable device (read-only)

Unplug the bulb, or switch it off at the wall, and wait until Home Assistant shows it as unavailable. Run the probe. Expected. The lamp reads fail with `unavailable in Home Assistant` and `health` is not connected. Plug it back in.

## Step 7. Start the hub

Read every limit in the file. Then confirm them yourself with `uv run openhal file confirm ./lamp.hal.yaml`. It lists each limit and asks you to type `confirm`. Then load the file into a fresh hub.

```
export OPENHAL_HOME="$PWD/openhal-test"
uv run openhal init --yes --no-sample --no-discover --no-service
cp ./lamp.hal.yaml "$OPENHAL_HOME/devices/"
uv run openhald --verbose > "$OPENHAL_HOME/hub.log" 2>&1 &
uv run openhal devices
```

Expected. `test-lamp` is connected and writable.

## Step 8. The smallest safe writes

```
uv run openhal write test-lamp.lamp true
uv run openhal write test-lamp.lamp_brightness "20 %"
uv run openhal read test-lamp.lamp_brightness
uv run openhal stop
uv run openhal read test-lamp.lamp
uv run openhal unlock
```

Expected. The lamp turns on, dims to about 20 %, and turns off at `openhal stop`. The Home Assistant logbook shows the service calls.

## Step 9. The file's limit wins over Home Assistant's

```
uv run openhal write test-lamp.lamp_brightness "90 %"
```

Expected. Blocked with code `above_max` (the file allows 60 %), although Home Assistant itself would accept 90 %. The lamp doesn't change. Stop the hub with `kill %1` when done.

## If something fails

Send what [README.md](README.md#if-a-step-fails) lists, plus the Home Assistant version, the entity ids with their state from Developer Tools, and the logbook entries from the same minutes. Never send the token. If a blocked command reached the device, stop the hub, power the device off and report it privately as [SECURITY.md](../../SECURITY.md) says.

## Report template

```
Plan: docs/hardware-tests/homeassistant.md
Tested by and date:
OpenHAL: (uv run openhal --version, and git rev-parse --short HEAD)
Device file: (path, and the sha256 in its confirmed line)
Home Assistant version:
Entities used: (light, sensor, their integrations)
Step 1 API answers:              pass / fail
Step 2 file valid:               pass / fail
Step 3 REST probe:               pass / fail   (paste it)
Step 4 WebSocket probe:          pass / fail   (paste it)
Step 5 unselected entity:        pass / fail
Step 6 unavailable device:       pass / fail
Step 7 hub lists the device:     pass / fail
Step 8 writes and stop:          pass / fail
Step 9 file limit wins:          pass / fail
Audit chain: (the line uv run openhal log --verify prints)
Anything unexpected (paste exact output):
Result: verified-on-hardware / tested-reads / failed at step N
```

Save the filled-in report as `docs/hardware-tests/reports/<device id>-<date>.md`. [README.md](README.md#reports) says when it marks the device file `verified-on-hardware`.
