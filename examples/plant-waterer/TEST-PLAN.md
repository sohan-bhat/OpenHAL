# Hardware test: Arduino plant waterer

The first plan in [docs/hardware-tests/README.md](../../docs/hardware-tests/README.md), which has the setup and rules every plan shares. It is for a person with the parts in [README.md](README.md). Steps 1 to 5 change nothing. Steps 6 to 10 use the relay with the pump unplugged from its supply, so nothing gets wet until step 11. Steps 7 to 9 repeat the plant waterer's two blocked waterings and its granted watering on the real board, sent by an agent. Stop at the first step that fails and send what [If something fails](#if-something-fails) lists.

## What you need

- An Arduino Uno wired as README.md describes. The soil sensor on A0, the float switch from pin 4 to ground and the relay input on pin 7.
- The pump on its own supply, unplugged until step 11.
- arduino-cli, or the Arduino IDE.
- A checkout of this repository with the openhal-firmware extra, `uv sync --extra openhal-firmware`.

## Before you start

Flash the sketch with the library from this checkout. Use the Uno's port from step 1.

```
arduino-cli core install arduino:avr
arduino-cli compile --fqbn arduino:avr:uno --library firmware/arduino/OpenHAL --upload --port /dev/ttyACM0 examples/plant-waterer
```

In the Arduino IDE instead, copy `firmware/arduino/OpenHAL` into your `libraries` folder, open `examples/plant-waterer/plant-waterer.ino` and upload it.

Make a test home and start the hub with no device files. `hub.sh` starts the hub in the background, waits until the hub responds and logs to `$OPENHAL_HOME/hub.log`.

```
export OPENHAL_HOME="$PWD/openhal-test"
uv run openhal init --yes --no-sample --no-discover --no-service
bash docs/hardware-tests/hub.sh start
```

## Read-only steps

### 1. The port is listed

```
uv run python -m serial.tools.list_ports -v
```

Expected. A port such as `/dev/ttyACM0` or `/dev/cu.usbmodem1101` with `VID:PID=2341:0043` for an Uno R3, or `1A86:7523` for a clone with a CH340.

### 2. Discovery

```
uv run openhal discover --driver openhal-firmware
```

Expected.

```
matched  OpenHAL board plant-waterer as openhal-plant-waterer
  The library has openhal-plant-waterer, and the hub has no device file for this device yet. Add the library file with openhal library add openhal-plant-waterer
```

Discovery sends only `HELLO`. The match shows that the starter library has a file for the board. This plan uses the example's own device file, so don't add the library's.

### 3. The file loads read-only

```
cp examples/plant-waterer/plant-waterer.hal.yaml "$OPENHAL_HOME/devices/"
bash docs/hardware-tests/hub.sh restart
uv run openhal devices plant-waterer
```

Expected.

```
Arduino plant waterer  plant-waterer
driver openhal-firmware, low hazard, read-only, connected
unconfirmed limits  file (interlocks, watchdog, safe state and hazard), actions.water, actions.stop
```

### 4. Soil

Run this with the sensor in dry air, then with it in a glass of water.

```
uv run openhal read plant-waterer.soil_moisture
```

Expected. A low value such as `plant-waterer.soil_moisture  3 %`, then a high one near `100 %`. If they are far from 0 % and 100 %, set `SOIL_DRY` and `SOIL_WET` in the sketch to the raw readings and flash it again.

### 5. Tank

Run this with the float down, then lifted.

```
uv run openhal read plant-waterer.tank
```

Expected. `plant-waterer.tank  empty`, then `plant-waterer.tank  ok`.

## Smallest safe actions

The pump stays unplugged from its supply. Listen for the relay click instead.

### 6. Confirm, and an agent token

Read every limit in the file. Then stop the hub, confirm the limits and start it again.

```
bash docs/hardware-tests/hub.sh stop
uv run openhal file confirm "$OPENHAL_HOME/devices/plant-waterer.hal.yaml"
bash docs/hardware-tests/hub.sh start
uv run openhal devices
```

Expected. The confirm lists `action  water`, `action  stop` and `safe state  {'action': 'stop'}`, prompts you to type `confirm`, and ends with `confirmed`. `devices` shows `plant-waterer` as `writable` and `connected`.

Make an agent token that may run low hazard commands, and save these two files in the checkout. Each is one agent session, the way an MCP client or any other client uses the hub protocol.

```
uv run openhal token create --name hwtest-agent --scope control_low --json | uv run python -c "import json, sys; print(json.load(sys.stdin)['token'])" > "$OPENHAL_HOME/hwtest-agent.token"
```

Save this as `too-long.jsonl`.

```json
{"jsonrpc": "2.0", "id": 1, "method": "hal/initialize", "params": {"protocolVersion": "0.1", "clientInfo": {"name": "hwtest", "version": "1"}}}
{"jsonrpc": "2.0", "method": "hal/initialized"}
{"jsonrpc": "2.0", "id": 2, "method": "hal/action", "params": {"device": "plant-waterer", "action": "water", "args": {"duration": {"value": 120, "unit": "s"}}}}
```

Save this as `short.jsonl`.

```json
{"jsonrpc": "2.0", "id": 1, "method": "hal/initialize", "params": {"protocolVersion": "0.1", "clientInfo": {"name": "hwtest", "version": "1"}}}
{"jsonrpc": "2.0", "method": "hal/initialized"}
{"jsonrpc": "2.0", "id": 2, "method": "hal/action", "params": {"device": "plant-waterer", "action": "water", "args": {"duration": {"value": 2, "unit": "s"}}}}
```

### 7. Too long

Lift the float, then send the 120 s watering as the agent.

```
uv run openhal --token-file "$OPENHAL_HOME/hwtest-agent.token" rpc < too-long.jsonl
```

Expected. The first line is the `hal/initialize` result with `"principal":{"kind":"agent","name":"hwtest-agent","scope":"control_low"}`. Then a `hal/blocked` notification and the response, which starts `{"jsonrpc":"2.0","id":2,"error":{"code":-32010,"message":"water duration 120 s exceeds the limit of 30 s (plant-waterer.hal.yaml, confirmed by` and your name and today's date, with `"name":"LIMIT_EXCEEDED"` in `data`. No click.

### 8. Empty tank

Let the float drop, then send the 2 s watering.

```
uv run openhal --token-file "$OPENHAL_HOME/hwtest-agent.token" rpc < short.jsonl
```

Expected. An error with `"code":-32012`, the message `pump can't run while tank is empty` and `"name":"INTERLOCK_BLOCKED"`. No click.

### 9. Short run

Lift the float and send the 2 s watering again.

```
uv run openhal --token-file "$OPENHAL_HOME/hwtest-agent.token" rpc < short.jsonl
```

Expected. `{"jsonrpc":"2.0","id":2,"result":{"status":"done",` and the action, a click on, and a click off about 2 s later.

### 10. The board falls safe on its own

The board turns the pump off when the hub's heartbeats stop for 3 s. This step kills the hub with SIGKILL, so it can't send anything on its way out.

```
uv run openhal action plant-waterer.water duration=20s &
sleep 2
bash docs/hardware-tests/hub.sh kill
```

Expected. The relay clicks on, and within 3 s of the kill it clicks off on its own. The background action then ends with an error because the hub is gone. Time how long the relay stayed on after the kill.

## Water

### 11. A real run

Start the hub again. Plug the pump into its supply, put the outlet in the pot and water for 5 s.

```
bash docs/hardware-tests/hub.sh start
uv run openhal action plant-waterer.water duration=5s
uv run openhal read plant-waterer.soil_moisture
```

Expected. `done  Done. water ran.`, water for about 5 s, and soil moisture rising over the next readings. Read it a few times over a minute.

### 12. Runs per hour

The file allows 3 runs per hour. Repeat this until the hub blocks the run.

```
uv run openhal action plant-waterer.water duration=2s
```

Expected. `blocked rate_limited  Blocked. water may run at most 3 times per 1 h. It ran 3 times in that window.` and the wait. Steps 9, 10 and 11 used the three runs, so the hub blocks the first try. A restart doesn't reset the count, because the hub reads recent runs back from its audit log. If the first try runs, write that down, since the hub then didn't count the run of step 10.

### 13. Stop and the audit chain

```
uv run openhal stop
uv run openhal log --verify
uv run openhal unlock
bash docs/hardware-tests/hub.sh stop
```

Expected. `plant-waterer  safe`, the relay stays off, `intact  The audit chain verifies.` and the head hash, and `unlock` prompts you to type `unlock`.

## If something fails

Send what [docs/hardware-tests/README.md](../../docs/hardware-tests/README.md#if-a-step-fails) lists, plus the arduino-cli or IDE version and the `arduino:avr` core version, the board and its USB id from step 1, your `SOIL_DRY` and `SOIL_WET` if you changed them, and what the relay did. If the relay clicked for a command the hub blocked, unplug the board and report it privately as [SECURITY.md](../../SECURITY.md) describes.

## Report

```
Plan: examples/plant-waterer/TEST-PLAN.md
Tested by and date:
OpenHAL: (uv run openhal --version, and git rev-parse --short HEAD)
Board and core: (for example Arduino Uno R3, arduino:avr 1.8.8)
Host OS and port path:
Device file: (path, and the sha256 in its confirmed line)
Step 1 port listed:              pass / fail
Step 2 discovery:                pass / fail
Step 3 read-only file:           pass / fail
Step 4 soil:                     pass / fail   dry and wet readings:
Step 5 tank:                     pass / fail
Step 6 confirm and token:        pass / fail
Step 7 too long:                 pass / fail   (paste the response)
Step 8 empty tank:               pass / fail   (paste the response)
Step 9 short run:                pass / fail
Step 10 board falls safe:        pass / fail   seconds from the kill to relay off:
Step 11 real run:                pass / fail   soil moisture before and after:
Step 12 runs per hour:           pass / fail   blocked on the first try:
Step 13 stop and audit chain:    pass / fail
Audit chain: (the line uv run openhal log --verify prints)
Anything unexpected (paste exact output):
Result: verified-on-hardware / tested-reads / failed at step N
```

Save the filled-in report as `docs/hardware-tests/reports/plant-waterer-<date>.md`. [docs/hardware-tests/README.md](../../docs/hardware-tests/README.md#reports) lists when a report marks the device file `verified-on-hardware`.
