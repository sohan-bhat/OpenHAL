# Hardware test plan for the scpi driver

This plan checks the scpi driver on a real bench power supply. Another SCPI instrument works for steps 1 to 4 with its own queries. It starts with read-only checks and ends with the smallest safe writes. Stop at the first step that fails and send what [If something fails](#if-something-fails) lists. [README.md](README.md) has the setup and rules every plan shares.

## What you need

- A SCPI bench supply, for example a Rigol DP832, Siglent SPD3303X or Keysight E36312A, connected by USB or LAN.
- Nothing connected to the outputs, or a 1 kOhm resistor of at least 0.25 W across channel 1.
- A checkout of this repository with the scpi extra, `uv sync --extra scpi`, and the system libusb library for USB instruments.

## The read-only probe

Save this as `probe.py`. It connects, sends `*IDN?`, prints the driver's proposal and reads every channel. It holds no kernel grant, so it can't change the instrument. Connecting also drains `SYST:ERR?`, which only empties the error queue.

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

## Step 1. The instrument is listed (read-only)

```
uv run python -m pyvisa info
uv run python -c "import pyvisa; print(pyvisa.ResourceManager('@py').list_resources())"
```

Expected. A resource such as `USB0::0x1AB1::0x0E11::DP8C1234567::INSTR`. For LAN, use `TCPIP0::<address>::5025::SOCKET` or `TCPIP0::<address>::INSTR`.

## Step 2. Validate the device file (read-only)

```
cp openhal/drivers/scpi/examples/rigol-dp832.hal.yaml ./psu.hal.yaml
uv run openhal file validate ./psu.hal.yaml
```

For another supply, set `match.usb` and `match.scpi_idn`, or use the queries from step 3's `describe` output. Expected. `valid ./psu.hal.yaml (bench-psu, medium hazard, read-only)`.

## Step 3. Identify, describe and read (read-only)

```
uv run python probe.py ./psu.hal.yaml
```

Expected.

```
identify {"resource": "USB0::...", "idn": "RIGOL TECHNOLOGIES,DP832,...", "manufacturer": "RIGOL TECHNOLOGIES", "model": "DP832", ...}
describe { "device": {...}, "match": {"scpi_idn": "^RIGOL\\ TECHNOLOGIES,DP832"}, "read": {...}, ... }
read ch1_voltage 0.0 V
read ch1_current 0.0 A
read ch1_output False
health Health(connected=True, ...)
```

The readings match the front panel. Paste the full output into the report.

## Step 4. Unplug during reads (read-only)

```
while true; do uv run python probe.py ./psu.hal.yaml; sleep 1; done
```

Unplug the USB or LAN cable for five seconds, then plug it back in. Expected. Runs fail with `Could not open`, `failed during` or a timeout while unplugged, and work again afterwards. Stop with Ctrl-C.

## Step 5. Start the hub

Read every limit in the file. Then confirm them yourself with `uv run openhal file confirm ./psu.hal.yaml`. It lists each limit and asks you to type `confirm`. Then load the file into a fresh hub.

```
export OPENHAL_HOME="$PWD/openhal-test"
uv run openhal init --no-sample
cp ./psu.hal.yaml "$OPENHAL_HOME/devices/"
uv run openhald --verbose > "$OPENHAL_HOME/hub.log" 2>&1 &
uv run openhal devices
uv run openhal read bench-psu.ch1_voltage
```

Expected. `bench-psu` is connected and writable.

## Step 6. The smallest safe write, 1 V at 10 mA

The example's action and output switch are `confirm-each-time`. A command sent with your own human token counts as your confirmation, so this step sends both as an agent would and approves each one. That also tests the confirmation queue on the real instrument. Create an agent token in `agent.token` and send the setting.

```
uv run openhal token create --name hwtest-agent --scope control_medium --json | uv run python -c "import json, sys; print(json.load(sys.stdin)['token'])" > agent.token
uv run openhal --token-file agent.token action bench-psu.set_ch1 volts="1 V" amps="0.01 A"
```

Expected. `pending needs_confirmation  Waiting for a human to approve action:set_ch1 on bench-psu.` and a line with the request id. The front panel doesn't change yet. Approve it with that id, then do the same for the output switch.

```
uv run openhal confirm list
uv run openhal confirm approve <request id>
uv run openhal --token-file agent.token write bench-psu.ch1_output true
uv run openhal confirm approve <request id>
uv run openhal read bench-psu.ch1_voltage bench-psu.ch1_current
```

Expected. Each approval shows the request, asks you to type `approve`, checks the command again and prints `done`. The front panel shows 1.000 V and 0.010 A set, and the output turns on. The voltage reads about `1 V`. With the 1 kOhm resistor the current reads about `0.001 A`.

## Step 7. An instrument error is reported

A changed limit makes the file read-only until you confirm it again. Stop the hub, set `amps` to `max: 5` in `$OPENHAL_HOME/devices/psu.hal.yaml`, confirm the file and start the hub. Then ask for 5 A at 1 V on a 3 A channel. With nothing or only the resistor connected, even an accepted setting is harmless at 1 V.

```
kill %1
uv run openhal file confirm "$OPENHAL_HOME/devices/psu.hal.yaml"
uv run openhald --verbose > "$OPENHAL_HOME/hub.log" 2>&1 &
uv run openhal action bench-psu.set_ch1 volts="1 V" amps="5 A"
```

Expected. The kernel lets it through because the file allows it, the supply refuses it, and the command ends `failed driver_error` with a message containing `-222` (or your instrument's out-of-range code). The front panel limit doesn't change. Put the limit back to `max: 1` the same way, by stopping the hub, editing the file, confirming it and starting the hub.

## Step 8. The safe state

```
uv run openhal stop
uv run openhal read bench-psu.ch1_output
uv run openhal unlock
```

Expected. The output turns off on the front panel and reads `false`.

## Step 9. A blocked write never reaches the instrument

```
uv run openhal action bench-psu.set_ch1 volts="20 V" amps="0.01 A"
```

Expected. `blocked above_max  Blocked. The volts limit is 12 V (max). Asked for 20 V.` Nothing changes on the front panel. Stop the hub with `kill %1` and delete `agent.token` when done.

## If something fails

Send what [README.md](README.md#if-a-step-fails) lists, plus the `*IDN?` reply from step 3, the output of `uv run python -m pyvisa info`, the resource string, and what the front panel showed at the time. If a blocked command reached the device, stop the hub, power the device off and report it privately as [SECURITY.md](../../SECURITY.md) says.

## Report template

```
Plan: docs/hardware-tests/scpi.md
Tested by and date:
OpenHAL: (uv run openhal --version, and git rev-parse --short HEAD)
Device file: (path, and the sha256 in its confirmed line)
Instrument: (IDN reply)
Transport and resource string:
VISA library: (@py, or NI-VISA version)
Step 1 resource listed:         pass / fail
Step 2 file valid:              pass / fail
Step 3 probe output:            pass / fail   (paste it)
Step 4 unplug and replug:       pass / fail
Step 5 hub lists the device:    pass / fail
Step 6 1 V at 10 mA:            pass / fail   readings:
Step 7 instrument error:        pass / fail   message:
Step 8 safe state:              pass / fail
Step 9 blocked write:           pass / fail
Audit chain: (the line uv run openhal log --verify prints)
Anything unexpected (paste exact output):
Result: verified-on-hardware / tested-reads / failed at step N
```

Save the filled-in report as `docs/hardware-tests/reports/<device id>-<date>.md`. [README.md](README.md#reports) says when it marks the device file `verified-on-hardware`.
