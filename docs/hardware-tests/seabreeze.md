# Hardware test plan for the seabreeze driver

This plan checks the seabreeze driver on a real Ocean spectrometer. A spectrometer only measures, so every step reads, and the only setting the plan changes is the integration time. Use a lamp you can block by hand, such as a tungsten halogen source on a fiber, and a cuvette holder if you have one. [README.md](README.md) has the setup and rules every plan shares.

## What you need

- An Ocean USB spectrometer that OceanView already reads on this computer. Close OceanView before each step.
- A light source on the spectrometer's fiber, and something to block the light.
- A checkout of this repository with the seabreeze extra, `uv sync --extra seabreeze`, and on Linux the udev rules from `uv run seabreeze_os_setup`.

## The probe

Save this as `probe.py`. The probe connects, identifies the spectrometer, reads every channel and saves the chart as `spectrum.png`. The probe holds no kernel grant, so the probe changes nothing.

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
        for name in [*file.read, *file.write]:
            try:
                reading = await driver.read(name)
            except Exception as exc:
                print("read", name, "failed", exc)
                continue
            if isinstance(reading.value, bytes):
                open("spectrum.png", "wb").write(reading.value)
                print("read", name, len(reading.value), "bytes, saved as spectrum.png")
            else:
                print("read", name, reading.value, reading.unit or "")
        print("describe", json.dumps(await driver.describe())[:800])
    finally:
        await driver.close()

asyncio.run(main(sys.argv[1]))
```

## Step 1. Find the spectrometer

```
uv run python -c "import asyncio; from openhal.drivers.seabreeze.driver import SeabreezeDriver; print(asyncio.run(SeabreezeDriver.discover()))"
```

Expected. One entry with the spectrometer's model and serial number, the same ones OceanView shows.

## Step 2. Validate the file and read (no change)

```
cp openhal/drivers/seabreeze/examples/absorbance-spectrometer.hal.yaml ./spectrometer.hal.yaml
uv run openhal file validate ./spectrometer.hal.yaml
uv run python probe.py ./spectrometer.hal.yaml
```

Set `spectrometer` to the serial number from step 1. Expected. `identify` names the model, the serial number and the pixel count, the peak wavelength sits where OceanView shows the lamp's peak, the absorbance reads fail with "Store a dark and a reference spectrum first", and `spectrum.png` looks like OceanView's scope view.

## Step 3. Integration time through the kernel

```
export OPENHAL_HOME="$PWD/openhal-test"
uv run openhal init --yes --no-clients --no-sample --no-discover --no-service
cp ./spectrometer.hal.yaml "$OPENHAL_HOME/devices/"
bash docs/hardware-tests/hub.sh start
uv run openhal write absorbance-spectrometer.integration_time "10 ms"
uv run openhal read absorbance-spectrometer.peak_intensity absorbance-spectrometer.saturated
uv run openhal write absorbance-spectrometer.integration_time "20 ms"
uv run openhal read absorbance-spectrometer.peak_intensity
uv run openhal write absorbance-spectrometer.integration_time "5 s"
```

Expected. The peak counts about double from 10 ms to 20 ms, `saturated` reads false below the detector's maximum, and 5 s is blocked with `above_max`.

## Step 4. Dark, reference and absorbance

Block the light and run `uv run openhal action absorbance-spectrometer.store_dark`. Unblock the light with the blank in the path and run `uv run openhal action absorbance-spectrometer.store_reference`. Read `absorbance_520` and `transmittance_520`.

Expected. Absorbance near 0 and transmittance near 100 % with the blank still in place. A neutral density filter or a dye in the path raises the absorbance. Stop the hub with `bash docs/hardware-tests/hub.sh stop` when done.

## If something fails

Send what [README.md](README.md#if-a-step-fails) lists, plus the spectrometer model and serial number, the python-seabreeze version (`uv run python -c "import seabreeze; print(seabreeze.__version__)"`), the backend in the file, and `spectrum.png`.

## Report template

```
Plan: docs/hardware-tests/seabreeze.md
Tested by and date:
OpenHAL: (uv run openhal --version, and git rev-parse --short HEAD)
Spectrometer model and serial number:
python-seabreeze version and backend:
Step 1 found:                     pass / fail
Step 2 validate and read:         pass / fail   (paste it)
Step 3 integration time:          pass / fail
Step 4 dark, reference, absorbance: pass / fail   (the values)
Anything unexpected (paste exact output):
Result: verified-on-hardware / tested-reads / failed at step N
```

Save the filled-in report as `docs/hardware-tests/reports/<device id>-<date>.md`. [README.md](README.md#reports) lists when a report marks the device file `verified-on-hardware`.
