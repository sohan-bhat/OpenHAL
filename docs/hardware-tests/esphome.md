# Hardware test plan for the esphome driver

This plan checks the ESPHome driver on a real node. The plan starts with read-only checks and ends with the smallest safe writes, on an LED. Stop at the first step that fails and send what [If something fails](#if-something-fails) lists. [README.md](README.md) has the setup and rules every plan shares.

## What you need

- An ESP32 or ESP8266 board flashed with ESPHome 2024.6 or newer, on the same network as the computer that runs OpenHAL.
- A checkout of this repository with the esphome extra, `uv sync --extra esphome`.
- The node's YAML with at least these parts. The onboard LED is the only output.

```yaml
esphome:
  name: openhal-test
api:
  encryption:
    key: "<your base64 key>"
sensor:
  - platform: wifi_signal
    name: WiFi signal
    id: wifi_signal_db
    update_interval: 10s
  - platform: uptime
    name: Uptime
binary_sensor:
  - platform: status
    name: Status
switch:
  - platform: gpio
    pin: GPIO2
    name: Test LED
    id: test_led
button:
  - platform: restart
    name: Restart
```

Export the key with `export ESPHOME_TEST_PSK="<your base64 key>"`.

## The read-only probe

Save this as `probe.py`. The probe connects, prints the device info, the driver's proposal and every channel. The probe holds no kernel grant, so the probe can't send any command.

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

## Step 1. The node is on the network (read-only)

```
ping -c 3 openhal-test.local
nc -vz openhal-test.local 6053
```

Expected. Replies, and the port is open.

## Step 2. Write and validate a device file (read-only)

Save this as `./node.hal.yaml`.

```yaml
device: ESPHome test node
id: test-node
match: { esphome: { name: "openhal-test" } }
connect: { esphome: openhal-test.local, noise_psk_env: ESPHOME_TEST_PSK }
read:
  wifi_signal: { unit: dimensionless }
  uptime: { unit: s }
  status: { type: bool }
write:
  test_led: { type: bool }
actions:
  restart: {}
safe_state: { test_led: false }
hazard: low
```

```
uv run openhal file validate ./node.hal.yaml
```

Expected. `valid ./node.hal.yaml (test-node, low hazard, read-only)`.

## Step 3. Identify, describe and read (read-only)

```
uv run python probe.py ./node.hal.yaml
```

Expected.

```
identify {"host": "openhal-test.local", "name": "openhal-test", "model": "esp32dev", "esphome_version": "2026.10.1", ...}
describe { "read": {"wifi_signal": {"unit": "dimensionless"}, "uptime": {"unit": "s"}, ...}, "write": {"test_led": ...}, "actions": {"restart": ...} }
read wifi_signal -54.0
read uptime 1234.0 s
read status True
read test_led False
health Health(connected=True, detail='openhal-test', ...)
```

`wifi_signal` reports dBm, which has no unit in the registry, so it reads as dimensionless. Paste the full output into the report.

## Step 4. Wrong key and missing entity (read-only)

Run the probe with a wrong key, then with a channel the node doesn't have.

```
ESPHOME_TEST_PSK="QRTIErOb/fcE9Ez4PO8kZpfR/Q8k8U5fhvM2ttUzJw8=" python probe.py ./node.hal.yaml
```

Expected. `Could not connect to ESPHome` with a hint about `noise_psk_env`. Then add `ghost: { type: bool }` under `read` and run the probe with the right key. Expected. `the device has no entity 'ghost'` and the list of entities it has. Remove the channel again.

## Step 5. Power loss (read-only)

```
while true; do uv run python probe.py ./node.hal.yaml; sleep 2; done
```

Unplug the node for ten seconds, then plug it back in. Expected. Runs fail while it is off and work again once it has booted and joined Wi-Fi. Stop with Ctrl-C.

## Step 6. Start the hub

Read every limit in the file, then confirm them yourself. The confirm lists each limit and asks you to type `confirm`. Then the file goes into a fresh test home and hub.

```
export OPENHAL_HOME="$PWD/openhal-test"
uv run openhal init --yes --no-sample --no-discover --no-service
uv run openhal file confirm ./node.hal.yaml
cp ./node.hal.yaml "$OPENHAL_HOME/devices/"
bash docs/hardware-tests/hub.sh start
uv run openhal devices
```

Expected. `test-node` is connected and writable.

## Step 7. The smallest safe write, the LED

```
uv run openhal write test-node.test_led true
uv run openhal read test-node.test_led
uv run openhal stop
uv run openhal read test-node.test_led
uv run openhal unlock
```

Expected. The LED turns on and reads `true`, then turns off at `openhal stop`. The node's log (`esphome logs`) shows each switch command.

## Step 8. A button action

```
uv run openhal action test-node.restart
uv run openhal devices
```

Expected. The node restarts. The hub shows it disconnected for a few seconds, then connected again. Stop the hub with `bash docs/hardware-tests/hub.sh stop` when done.

## If something fails

Send what [README.md](README.md#if-a-step-fails) lists, plus the `esphome logs` output from the same minutes, the node's YAML without its keys, and the ESPHome version. If a blocked command reached the device, stop the hub, power the device off and report it privately as [SECURITY.md](../../SECURITY.md) says.

## Report template

```
Plan: docs/hardware-tests/esphome.md
Tested by and date:
OpenHAL: (uv run openhal --version, and git rev-parse --short HEAD)
Device file: (path, and the sha256 in its confirmed line)
Board and ESPHome version:
Encryption in use: yes / no
Step 1 node on the network:      pass / fail
Step 2 file valid:               pass / fail
Step 3 probe output:             pass / fail   (paste it)
Step 4 wrong key and entity:     pass / fail
Step 5 power loss:               pass / fail
Step 6 hub lists the device:     pass / fail
Step 7 LED write and stop:       pass / fail
Step 8 button action:            pass / fail
Audit chain: (the line uv run openhal log --verify prints)
Anything unexpected (paste exact output):
Result: verified-on-hardware / tested-reads / failed at step N
```

Save the filled-in report as `docs/hardware-tests/reports/<device id>-<date>.md`. [README.md](README.md#reports) says when it marks the device file `verified-on-hardware`.
