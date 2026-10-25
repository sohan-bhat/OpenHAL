# Hardware test plan for the pylabrobot driver

This plan checks the PyLabRobot driver on a real liquid handler. It starts with checks that move nothing and ends with the smallest safe motions, with water only. Close the cover, keep the instrument's own stop within reach, and watch every motion. Stop at the first step that fails and send back the report below.

## What you need

- A Hamilton STAR or STARlet, a Tecan EVO or an Opentrons OT-2 that PyLabRobot already drives on this computer. Run one PyLabRobot example from its documentation first.
- One full tip rack and one empty 96 well plate, placed where the layout says, and water in well A1 of the plate.
- OpenHAL installed with `uv pip install 'openhal-hub[pylabrobot]'`.

## The probe

Save this as `probe.py`. It connects, builds the deck, identifies the setup and reads every channel. It holds no kernel grant, so it can't run any action, and connecting moves nothing.

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
        for name in file.read:
            reading = await driver.read(name)
            print("read", name, reading.value, reading.unit or "")
        print("describe", json.dumps(await driver.describe())[:600])
    finally:
        await driver.close()

asyncio.run(main(sys.argv[1]))
```

## Step 1. Validate the device file (no motion)

```
cp openhal/drivers/pylabrobot/examples/starlet.hal.yaml ./lh.hal.yaml
openhal file validate ./lh.hal.yaml
```

Set `backend` and `deck` for your instrument, and make the layout match the physical deck. Expected. `valid ./lh.hal.yaml (starlet, high hazard, read-only)`.

## Step 2. Connect and read (no motion)

```
python probe.py ./lh.hal.yaml
```

Expected.

```
identify {"backend": "star", "channels": "8", "deck": "HamiltonSTARDeck", "resources": "plate, tips, trash, ..."}
health star liquid handler, not initialized
read initialized False
read tips_mounted 0.0 dimensionless
read source_volume 0.0 uL
describe {"device": {...}, "actions": {...
```

The instrument doesn't move. Paste the full output into the report.

## Step 3. A wrong address is refused (no motion)

Add `- { name: extra, resource: no_such_rack, rails: 20 }` to the layout and run the probe. Expected. `layout extra: no_such_rack is not a PyLabRobot resource factory.` Remove the line.

## Step 4. Start the hub

Confirm the limits by adding `confirmed: { by: <your name>, at: <today> }`, then load the file into a fresh hub.

```
export OPENHAL_HOME="$PWD/openhal-test"
openhal init
cp ./lh.hal.yaml "$OPENHAL_HOME/devices/"
openhald &
openhal devices
openhal read starlet.initialized
```

Expected. `starlet` is connected, high hazard, and reads `False`.

## Step 5. A blocked action never reaches the instrument (no motion)

```
openhal action starlet.aspirate well="plate:A1" volume="500 uL"
openhal action starlet.pick_up_tips tips="plate:A1"
```

Expected. The first is blocked with `above_max`, the second with `bad_value`, because `plate:A1` doesn't match the tips pattern. Nothing moves.

## Step 6. Initialize

```
openhal action starlet.initialize
openhal read starlet.initialized
```

Expected. The instrument initializes and homes its channels, the same way PyLabRobot's setup does. The read says `True`.

## Step 7. One tip, 10 uL of water, and back

PyLabRobot tracks volumes and starts every well empty, so tell it about the water first. Add `volumes: { "plate:A1": 200 uL }` to `connect`, confirm the file again and restart the hub.

```
openhal action starlet.pick_up_tips tips="tips:A1"
openhal read starlet.tips_mounted
openhal action starlet.aspirate well="plate:A1" volume="10 uL"
openhal action starlet.dispense well="plate:A2" volume="10 uL"
openhal action starlet.drop_tips tips="tips:A1"
```

Expected. Channel 1 picks up the tip at A1, aspirates 10 uL from A1, dispenses it into A2 and puts the tip back. `tips_mounted` reads `1` while the tip is on.

## Step 8. Stop during an action

```
openhal action starlet.pick_up_tips tips="tips:B1:H1"
openhal stop
openhal read starlet.tips_mounted
openhal unlock
openhal action starlet.initialize
```

Run `openhal stop` while the channels are moving. Expected. The instrument finishes the move it is in and then stops. `tips_mounted` may be marked suspect, because the model may not match the deck. Initializing again clears that. Stop the hub with `kill %1` when done.

## Report template

```
Driver: pylabrobot
OpenHAL version:
Instrument and PyLabRobot backend:
Deck layout used (paste it):
Step 1 file valid:                pass / fail
Step 2 connect and read:          pass / fail   (paste it)
Step 3 wrong address refused:     pass / fail
Step 4 hub lists the device:      pass / fail
Step 5 blocked actions:           pass / fail
Step 6 initialize:                pass / fail
Step 7 one tip and 10 uL:         pass / fail
Step 8 stop during an action:     pass / fail
Anything unexpected (paste exact output):
Result: verified-on-hardware / failed at step N
```

A passing report lets the device file set `provenance.verification.status: verified-on-hardware` with `report:` pointing at the saved report.
