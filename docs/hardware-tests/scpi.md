# Hardware test plan for the scpi driver

This plan checks the scpi driver on a real bench power supply. Another SCPI instrument works for steps 1 to 4 with its own queries. It starts with read-only checks and ends with the smallest safe writes. Stop at the first step that fails and send back the report below.

## What you need

- A SCPI bench supply, for example a Rigol DP832, Siglent SPD3303X or Keysight E36312A, connected by USB or LAN.
- Nothing connected to the outputs, or a 1 kOhm resistor of at least 0.25 W across channel 1.
- OpenHAL installed with `uv pip install 'openhal-hub[scpi]'`, and the system libusb library for USB instruments.

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
python -m pyvisa info
python -c "import pyvisa; print(pyvisa.ResourceManager('@py').list_resources())"
```

Expected. A resource such as `USB0::0x1AB1::0x0E11::DP8C1234567::INSTR`. For LAN, use `TCPIP0::<address>::5025::SOCKET` or `TCPIP0::<address>::INSTR`.

## Step 2. Validate the device file (read-only)

```
cp openhal/drivers/scpi/examples/rigol-dp832.hal.yaml ./psu.hal.yaml
openhal file validate ./psu.hal.yaml
```

For another supply, set `match.usb` and `match.scpi_idn`, or use the queries from step 3's `describe` output. Expected. `valid ./psu.hal.yaml (bench-psu, medium hazard, read-only)`.

## Step 3. Identify, describe and read (read-only)

```
python probe.py ./psu.hal.yaml
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
while true; do python probe.py ./psu.hal.yaml; sleep 1; done
```

Unplug the USB or LAN cable for five seconds, then plug it back in. Expected. Runs fail with `Could not open`, `failed during` or a timeout while unplugged, and work again afterwards. Stop with Ctrl-C.

## Step 5. Start the hub

Confirm the limits by adding `confirmed: { by: <your name>, at: <today> }`, then load the file into a fresh hub.

```
export OPENHAL_HOME="$PWD/openhal-test"
openhal init
cp ./psu.hal.yaml "$OPENHAL_HOME/devices/"
openhald &
openhal devices
openhal read bench-psu.ch1_voltage
```

Expected. `bench-psu` is connected and writable.

## Step 6. The smallest safe write, 1 V at 10 mA

The example's action and output switch are `confirm-each-time`, so each command waits for your approval with `openhal confirm`.

```
openhal action bench-psu.set_ch1 volts="1 V" amps="0.01 A"
openhal confirm list
openhal confirm approve <request id>
openhal write bench-psu.ch1_output true
openhal confirm approve <request id>
openhal read bench-psu.ch1_voltage
openhal read bench-psu.ch1_current
```

Expected. The front panel shows 1.000 V and 0.010 A set, and the output turns on. The voltage reads about `1 V`. With the 1 kOhm resistor the current reads about `0.001 A`.

## Step 7. An instrument error is reported

Edit the file so `amps` allows `max: 5`, reload the hub, then ask for 5 A at 1 V on a 3 A channel. With nothing or only the resistor connected, even an accepted setting is harmless at 1 V.

```
openhal action bench-psu.set_ch1 volts="1 V" amps="5 A"
openhal confirm approve <request id>
```

Expected. The kernel lets it through because the file allows it, the supply refuses it, and the command fails with a message containing `-222` (or your instrument's out-of-range code). The front panel limit doesn't change. Put the limit back to `max: 1` afterwards.

## Step 8. The safe state

```
openhal stop
openhal read bench-psu.ch1_output
openhal unlock
```

Expected. The output turns off on the front panel and reads `false`.

## Step 9. A blocked write never reaches the instrument

```
openhal action bench-psu.set_ch1 volts="20 V" amps="0.01 A"
```

Expected. Blocked with code `above_max`. Nothing changes on the front panel. Stop the hub with `kill %1` when done.

## Report template

```
Driver: scpi
OpenHAL version:
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
Anything unexpected (paste exact output):
Result: verified-on-hardware / failed at step N
```

A passing report lets the device file set `provenance.verification.status: verified-on-hardware` with `report:` pointing at the saved report.
