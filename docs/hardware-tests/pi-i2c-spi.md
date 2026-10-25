# Hardware test plan, pi-i2c-spi driver

This plan checks the pi-i2c-spi driver on a Raspberry Pi with a TMP102 breakout on I2C, and optionally an MCP3008 on SPI. It uses the example files. Any register-mapped chip works the same way.

Run every step on the Pi from the repository checkout. Wire with the Pi powered off.

## What you need

- A Raspberry Pi with Raspberry Pi OS, I2C and SPI enabled in `sudo raspi-config` under Interface Options, and the user in the `i2c` and `spi` groups.
- A TMP102 breakout on pins 1 (3.3 V), 3 (SDA), 5 (SCL) and 6 (ground), with ADD0 to ground so it answers at 0x48.
- Optionally an MCP3008 on SPI0 with chip select 1 (pin 26), VREF and VDD at 3.3 V, and a potentiometer between 3.3 V and ground on CH0.
- i2c-tools for an independent view of the bus, `sudo apt install i2c-tools`.
- The repository with the extra, `uv sync --extra pi-i2c-spi`.
- Copies of the examples, `cp openhal/drivers/pi_i2c_spi/examples/tmp102-temperature.hal.yaml my-tmp102.hal.yaml` and the same for `mcp3008-adc.hal.yaml`.

## The test script

Save this as `hwtest.py` in the repository root. It drives the device only through the safety kernel, as the hub does. It waits one second before a write, because the kernel measures a first write's rate of change from the moment the device connected.

```python
"""Usage: uv run python hwtest.py FILE identify|describe|read|write CHANNEL VALUE|action NAME [ARG=VALUE ...]|stop"""

import asyncio
import json
import sys

from openhal.drivers import registry
from openhal.kernel import Kernel
from openhal.kernel.commands import Action, Write
from openhal.kernel.principals import human
from openhal.spec import load


def parse(text: str) -> object:
    return {"true": True, "false": False}.get(text, text)


async def main(path: str, command: str, *rest: str) -> None:
    file = load(path)
    driver = registry.load(file.connect.driver)(file)
    if command == "identify":
        print(json.dumps(await driver.identify(), indent=2))
        return
    kernel = Kernel()
    kernel.register(file, driver)
    await kernel.connect(file.device_id)
    me = human("hardware-tester")
    try:
        if command == "describe":
            print(json.dumps(await driver.describe(), indent=2, default=str))
        elif command == "read":
            for channel in [*file.read, *file.write]:
                reading = await kernel.read(file.device_id, channel, me)
                value = f"<{len(reading.value)} bytes>" if isinstance(reading.value, bytes) else reading.value
                print(f"{channel} = {value} {reading.unit or ''}{' (suspect)' if reading.suspect else ''}")
        elif command == "write":
            channel, value = rest
            await asyncio.sleep(1.0)
            decision = await kernel.execute(Write(device=file.device_id, channel=channel, value=parse(value)), me)
            print(decision.status, decision.code or "", decision.message)
        elif command == "action":
            name, *pairs = rest
            args = {key: parse(value) for key, value in (pair.split("=", 1) for pair in pairs)}
            decision = await kernel.execute(Action(device=file.device_id, action=name, args=args), me)
            print(decision.status, decision.code or "", decision.message)
        elif command == "stop":
            report = await kernel.stop_all(me, "hardware test")
            for result in report.devices:
                print(result.device, result.status, result.detail)
        print("health", await driver.health())
    finally:
        await driver.close()


asyncio.run(main(*sys.argv[1:]))
```

## Read-only steps

### 1. The chip answers

```sh
ls /dev/i2c-1 /dev/spidev0.1
i2cdetect -y 1
i2cget -y 1 0x48 0x00 w
```

Expected. Both device nodes exist, `48` shows in the i2cdetect grid, and i2cget prints a word such as `0x8017`. SMBus words arrive low byte first, so `0x8017` is the register value `0x1780`, which is 23.5 degC.

### 2. The device file validates

```sh
uv run openhal file validate my-tmp102.hal.yaml
```

Expected. `valid  my-tmp102.hal.yaml  (enclosure-tmp102, low hazard, read-only)`.

### 3. Identify and discover

```sh
uv run python hwtest.py my-tmp102.hal.yaml identify
uv run python -c "import asyncio; from openhal.drivers.pi_i2c_spi.driver import PiBusDriver; print(asyncio.run(PiBusDriver.discover()))"
```

Expected. The first prints `i2c` and `i2c-1 address 0x48`. The second lists `i2c-1` and the `spi0.0` and `spi0.1` nodes.

### 4. Read every channel

```sh
uv run python hwtest.py my-tmp102.hal.yaml read
```

Expected. `temperature` within 1 degC of a thermometer next to the board, `alert_high = 80.0 degC` and `alert_low = 75.0 degC` (the power-on defaults), and `shutdown = False`. Hold a finger on the chip and read again. The temperature rises.

### 5. SPI reads (optional)

```sh
uv run python hwtest.py my-mcp3008.hal.yaml read
```

Expected. `potentiometer` follows the knob from about `0.0 V` to `3.3 V`. Unused inputs float and read random values, which is normal.

### 6. A missing chip

Power the Pi off, disconnect the TMP102's SDA wire, power on and run step 4 again.

Expected. `DriverError` saying nothing acknowledged at `i2c-1 address 0x48`, with the i2cdetect hint. Power off, reconnect the wire, power on and run step 4. It reads normally.

## Write steps

### 7. Confirm the limits

Read the file, decide the limits are right, and add this line yourself.

```yaml
confirmed: { by: <your name>, at: <today's date> }
```

`uv run openhal file validate my-tmp102.hal.yaml` should now say `writable`.

### 8. The smallest safe write

```sh
uv run python hwtest.py my-tmp102.hal.yaml write alert_high "79.5 degC"
i2cget -y 1 0x48 0x03 w
uv run python hwtest.py my-tmp102.hal.yaml write alert_high "80 degC"
```

Expected. `done` for each write. i2cget prints `0x804f` between them, which is the register value `0x4F80`, 79.5 degC. The alert pin doesn't change at room temperature.

### 9. A preserved bit

```sh
uv run python hwtest.py my-tmp102.hal.yaml write shutdown true
i2cget -y 1 0x48 0x01 w
uv run python hwtest.py my-tmp102.hal.yaml write shutdown false
i2cget -y 1 0x48 0x01 w
```

Expected. `done` for each write. The first i2cget prints `0xa061` and the second `0xa060`. Only bit 8 changed, so the conversion rate bits kept their value.

### 10. Stop

```sh
uv run python hwtest.py my-tmp102.hal.yaml stop
```

Expected. `enclosure-tmp102 no_safe_state`, because the example has no safe state, and nothing is written. i2cget on register 0x01 still prints `0xa060`.

## If something fails

Send the full output of the failing step, the output of `i2cdetect -y 1` and of the i2cget command for the same register, the breakout's make and model, `uname -a`, and your device file.

## Report template

Save the filled-in report as `reports/<device-id>-<date>.md` and set `provenance.verification` in the device file to `{ status: verified-on-hardware, report: reports/<device-id>-<date>.md }`.

```markdown
# Hardware report, pi-i2c-spi driver

- Device: <chip, breakout make, address or chip select>
- Board: <Raspberry Pi model, operating system, kernel>
- OpenHAL commit: <git rev-parse --short HEAD>
- Tested by: <name>, <date>

| Step | Result | Notes |
|---|---|---|
| 1 the chip answers | pass / fail | |
| 2 the device file validates | pass / fail | |
| 3 identify and discover | pass / fail | |
| 4 read every channel | pass / fail | |
| 5 SPI reads | pass / fail / skipped | |
| 6 a missing chip | pass / fail | |
| 7 confirm limits | done | |
| 8 the smallest safe write | pass / fail | |
| 9 a preserved bit | pass / fail | |
| 10 stop | pass / fail | |

Anything unexpected:
```
