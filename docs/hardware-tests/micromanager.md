# Hardware test plan for the micromanager driver

This plan checks the micromanager driver on a real microscope that Micro-Manager already runs. The plan starts with checks that move nothing and ends with the smallest moves, a few um of focus and a short stage move, with the objective far from the slide. Use a fixed test slide, keep a hand near the microscope's own stop or power switch, and watch every move. Stop at the first step that fails and send what [If something fails](#if-something-fails) lists. [README.md](README.md) has the setup and rules every plan shares.

## What you need

- A motorized microscope with a camera, an XY stage and a focus drive, and a Micro-Manager configuration file that already works in Micro-Manager on this computer.
- Micro-Manager's device adapters, from the Micro-Manager install the configuration uses or from `uv run mmcore install`.
- A test slide in the stage insert.
- A checkout of this repository with the micromanager extra, `uv sync --extra micromanager`.

Close Micro-Manager before each step, because most device adapters open their serial or USB port for one program at a time.

## The probe

Save this as `probe.py`. The probe connects, identifies the configuration, reads every channel and saves one snapshot as `snapshot.jpg`. The probe holds no kernel grant, so the probe can't move anything, and a snapshot only opens the shutter for the exposure.

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
            reading = await driver.read(name)
            if isinstance(reading.value, bytes):
                open("snapshot.jpg", "wb").write(reading.value)
                print("read", name, len(reading.value), "bytes, saved as snapshot.jpg")
            else:
                print("read", name, reading.value, reading.unit or "")
        print("describe", json.dumps(await driver.describe())[:1500])
    finally:
        await driver.close()

asyncio.run(main(sys.argv[1]))
```

## Step 1. Validate the device file (no motion)

```
export MICROMANAGER_CONFIG=/path/to/MMConfig.cfg
cp openhal/drivers/micromanager/examples/inverted-microscope.hal.yaml ./scope.hal.yaml
uv run openhal file validate ./scope.hal.yaml
```

Change the labels under `map` to the labels in your configuration file, and the objective and filter values to your state labels. Expected. `valid ./scope.hal.yaml (inverted-microscope, medium hazard, read-only)`.

## Step 2. Connect, read and snap (no motion)

```
uv run python probe.py ./scope.hal.yaml
```

Expected. `identify` names the MMCore version and the camera, every channel reads a value, `snapshot.jpg` shows what Micro-Manager's live view shows at the same settings, and `describe` lists your devices. Nothing moves. Paste the full output into the report, without the snapshot if the slide is private.

## Step 3. Set the z limit with the microscope's own controls (no driver motion)

Focus on the slide with the microscope's own focus knob or Micro-Manager, under the objective with the shortest working distance. Note z from step 2's probe at focus. Set z's limit toward the sample to about 20 um past focus, and z's other limit to where the objective is clear of the slide. Set x and y to a 2 mm square around the slide's center. Run step 2 again to read the new values.

## Step 4. Start the hub and see a blocked move (no motion)

Read every limit in the file, then confirm the limits yourself. The confirm lists each limit and prompts you to type `confirm`.

```
export OPENHAL_HOME="$PWD/openhal-test"
uv run openhal init --yes --no-clients --no-sample --no-discover --no-service
uv run openhal file confirm ./scope.hal.yaml
cp ./scope.hal.yaml "$OPENHAL_HOME/devices/"
bash docs/hardware-tests/hub.sh start
uv run openhal read inverted-microscope.z
uv run openhal write inverted-microscope.z "100000 um"
```

Expected. The write is blocked with `above_max`, and the focus drive doesn't move.

## Step 5. Move the focus away from the slide by 5 um

Write z to the value step 4 read, minus 5 um if a larger z moves toward the sample, or plus 5 um if a smaller z does, then read z back.

```
uv run openhal write inverted-microscope.z "<z away from the slide> um"
uv run openhal read inverted-microscope.z
```

Expected. The objective moves away from the slide, and z reads the new value within the drive's step size.

## Step 6. A short stage move and a snapshot

```
uv run openhal action inverted-microscope.move_xy x="0.1 mm" y="0 mm"
uv run openhal read inverted-microscope.x inverted-microscope.image
```

Expected. The stage moves 100 um, x reads 0.1 mm, and the image read reports a JPEG.

## Step 7. Autofocus within the limits

Focus by hand first, then move 10 um away from focus as in step 5.

```
uv run openhal action inverted-microscope.autofocus span="20 um"
uv run openhal read inverted-microscope.z
```

Expected. With an autofocus device, the device's own autofocus runs. Without one, the focus steps through 20 um around the start and back to the sharpest frame, never past z's limits. z reads within a few um of focus.

## Step 8. Stop during a move

Open a second terminal in the checkout and run `export OPENHAL_HOME="$PWD/openhal-test"` there. In the first terminal, start a 1 mm stage move.

```
uv run openhal action inverted-microscope.move_xy x="1 mm" y="1 mm"
```

In the second terminal, while the stage moves, stop it.

```
uv run openhal stop
uv run openhal read inverted-microscope.x inverted-microscope.shutter
uv run openhal unlock
```

Expected. The stop reports `inverted-microscope  safe`, the stage stops short of 1 mm and the shutter reads `false`. Stop the hub with `bash docs/hardware-tests/hub.sh stop` when done.

## If something fails

Send what [README.md](README.md#if-a-step-fails) lists, plus the pymmcore-plus and Micro-Manager versions (`uv run mmcore --version` and the probe's identify line), your configuration file with serial numbers removed, and the microscope and stage models. If a blocked command reached the microscope, stop the hub, power the stage controller off and report it privately as [SECURITY.md](../../.github/SECURITY.md) describes.

## Report template

```
Plan: docs/hardware-tests/micromanager.md
Tested by and date:
OpenHAL: (uv run openhal --version, and git rev-parse --short HEAD)
Device file: (path, and the sha256 in its confirmed line)
Microscope, camera, stage, focus drive and autofocus device:
pymmcore-plus and Micro-Manager versions:
Step 1 file valid:                pass / fail
Step 2 connect, read and snap:    pass / fail   (paste it)
Step 3 limits set:                pass / fail   (z at focus, z limits)
Step 4 blocked move:              pass / fail
Step 5 focus 5 um away:           pass / fail
Step 6 stage move and snapshot:   pass / fail
Step 7 autofocus:                 pass / fail   (method, z found)
Step 8 stop during a move:        pass / fail
Audit chain: (the line uv run openhal log --verify prints)
Anything unexpected (paste exact output):
Result: verified-on-hardware / tested-reads / failed at step N
```

Save the filled-in report as `docs/hardware-tests/reports/<device id>-<date>.md`. [README.md](README.md#reports) lists when a report marks the device file `verified-on-hardware`.
