# pylabrobot driver

The `pylabrobot` driver runs liquid handlers through PyLabRobot. Picking up tips, aspirating, dispensing and transferring are actions, and on a high hazard device each action waits for a person to confirm the action.

| | |
|---|---|
| Driver name | `pylabrobot` |
| Library | PyLabRobot 0.2.2 (MIT) |
| Extra | `uv tool install --compile-bytecode "openhal-hub[pylabrobot] @ git+https://github.com/sohan-bhat/OpenHAL"` |
| Hazard default | high |
| Conformance | full |
| Safe state | native. Running operations are cancelled after their current firmware command |
| Self-describe | yes, from the deck |

## What it supports

| Name | Kind | PyLabRobot call |
|---|---|---|
| `initialized` | read, bool | `LiquidHandler.setup_finished` |
| `tips_mounted` | read, dimensionless | channels whose tip tracker holds a tip |
| `channels` | read, dimensionless | `backend.num_channels` |
| `{ channel: 0 }` | read, bool | whether that channel holds a tip |
| `{ container: "plate:A1" }` | read, volume | the tracked liquid volume in that well |
| `initialize` | action | `setup()`, which homes the channels |
| `pick_up_tips`, `drop_tips` (arg `tips`) | action | `pick_up_tips`, `drop_tips` |
| `return_tips`, `discard_tips` | action | `return_tips`, `discard_tips` |
| `aspirate`, `dispense` (args `well`, `volume`) | action | `aspirate`, `dispense` with the same volume in every well |
| `transfer` (args `source`, `target`, `volume`) | action | `aspirate` then `dispense` |

An action under another name takes `map: { op: aspirate }`. Because every motion is an action, the driver has no channels that change.

Tip spots and wells are addressed as `<resource>:<spot>` or `<resource>:<first>:<last>`, such as `tips:A1` or `plate:A1:H1`. Give address arguments a `pattern` or an enum of allowed addresses, so the kernel refuses anything else before PyLabRobot receives the address. Volumes are converted to uL.

## The deck

The deck comes from a layout in the file, or from a JSON file saved with PyLabRobot's `deck.save()`.

```yaml
connect:
  pylabrobot: star
  deck: starlet
  layout:
    - { name: tips, resource: hamilton_96_tiprack_1000uL_filter, rails: 3 }
    - { name: plate, resource: cor_96_wellplate_360uL_Fb, rails: 9 }
```

`resource` is the name of a resource factory in `pylabrobot.resources`. Hamilton and Tecan decks place by `rails`, and the Opentrons deck places by `slot`. connect() checks every address the file names against the deck.

## How it works

- connect() builds the deck and the LiquidHandler and checks the file, but doesn't move anything. PyLabRobot's `setup()` homes the channels, so it runs as the `initialize` action under the kernel, unless `setup_on_connect: true`.
- PyLabRobot checks tips and tracked volumes before anything moves, so a refusal such as `TooLittleLiquidError` or `HasTipError` fails the action before anything is sent.
- An operation longer than `action_wait` returns `started` and finishes in the background, and the next action waits for that operation to finish.
- When an operation fails while it runs, the tip and volume model may no longer match the deck, so reads are marked suspect until `initialize` runs again.
- Tracked volumes are PyLabRobot's model of what was pipetted rather than a measurement, and every well starts empty unless `volumes` sets another volume.

## Safe state

A stop cancels running operations, and the instrument finishes the firmware command it is executing and then stops. Because any move on a liquid handler can spill or crash a tip, the driver moves nothing to make the deck safe, so keep the instrument's own cover interlock closed.

## Setup

1. Install the extra with `uv tool install --compile-bytecode "openhal-hub[pylabrobot] @ git+https://github.com/sohan-bhat/OpenHAL"`, plus PyLabRobot's USB or HTTP extras for your instrument.
2. Lay out the deck in the file to match the physical deck, or save one from PyLabRobot.
3. Start from `openhal/drivers/pylabrobot/examples/starlet.hal.yaml`, or call `describe` for a proposal.
4. Run `openhal file validate`, then confirm the limits by hand.

## Parameters

| Key | Default | Meaning |
|---|---|---|
| `backend` | required | `star` (Hamilton STAR and STARlet), `evo` (Tecan EVO), `opentrons` (OT-2) or `chatterbox` (simulation) |
| `deck` | by backend | `starlet`, `star`, `ot2` or `evo150` |
| `deck_env` | none | An environment variable that holds the path of a PyLabRobot deck JSON file, instead of `layout`. A device file never names the path itself |
| `layout` | empty | Resources and where they go |
| `num_channels` | 8 | Channels of the chatterbox simulation |
| `host`, `port` | none, 31950 | The OT-2's address |
| `serial_number` | none | Which STAR to open when several are plugged in |
| `setup_on_connect` | false | Run `setup()`, which homes the channels, during connect |
| `track_volumes` | true | Turn on PyLabRobot's tip and volume tracking |
| `volumes` | empty | Starting volumes, such as `{ "plate:A1": 200 uL }`. Every well starts empty otherwise |
| `action_wait` | `8 s` | How long an action waits before returning `started`. At most 9 s |

## Known limitations

- The 96 channel head, the gripper arm and resource moves are not exposed yet.
- PyLabRobot's plate readers, heater shakers and other machines need drivers of their own.
- Real backends report a lost instrument only when a command fails.
- Tracking is global in PyLabRobot, so `track_volumes` affects every PyLabRobot user in the hub's process.

## Hazard defaults

The default hazard is `high`, because channels move fast across the deck, tips can crash, and liquids can be hazardous. Every action waits for a person's approval, and the example keeps `confirm-each-time` on each action.

## Sources

- PyLabRobot documentation, https://docs.pylabrobot.org/
- PyLabRobot LiquidHandler and resources source, https://github.com/PyLabRobot/pylabrobot (MIT, used as a library)
