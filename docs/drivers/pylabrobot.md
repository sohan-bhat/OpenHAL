# pylabrobot driver

The `pylabrobot` driver runs liquid handlers through PyLabRobot 0.2.2. Picking up tips, aspirating, dispensing and transferring are actions, and the hub holds each action until a person confirms the action. `describe` drafts a file from the deck.

## Supports

| Name | Kind | PyLabRobot call |
|---|---|---|
| `initialized` | read, bool | `LiquidHandler.setup_finished` |
| `tips_mounted` | read, dimensionless | channels whose tip tracker holds a tip |
| `channels` | read, dimensionless | `backend.num_channels` |
| `{ channel: 0 }` | read, bool | whether that channel holds a tip |
| `{ container: "plate:A1" }` | read, volume | the tracked liquid volume in that well |
| `initialize` | action | `setup()`, which homes the channels |
| `pick_up_tips`, `drop_tips` with `tips` | action | `pick_up_tips`, `drop_tips` |
| `return_tips`, `discard_tips` | action | `return_tips`, `discard_tips` |
| `aspirate`, `dispense` with `well`, `volume` | action | `aspirate`, `dispense` with the same volume in every well |
| `transfer` with `source`, `target`, `volume` | action | `aspirate` then `dispense` |

An action under another name takes `map: { op: aspirate }`. Every motion is an action, so no channel changes anything.

Addresses are `<resource>:<spot>` or `<resource>:<first>:<last>`, such as `tips:A1` or `plate:A1:H1`. Give address arguments a `pattern` or an enum so the kernel blocks anything else. Volumes convert to uL.

## The deck

The deck comes from a `layout` in the file, or from a `deck.save()` JSON file through `deck_env`.

```yaml
connect:
  pylabrobot: star
  deck: starlet
  layout:
    - { name: tips, resource: hamilton_96_tiprack_1000uL_filter, rails: 3 }
    - { name: plate, resource: cor_96_wellplate_360uL_Fb, rails: 9 }
```

`resource` names a resource factory in `pylabrobot.resources`. Hamilton and Tecan decks place by `rails`, and the Opentrons deck by `slot`. Connect checks every address in the file against the deck.

## Behavior

- Connect builds the deck and LiquidHandler without moving anything. `setup()` homes the channels, so the setup runs as the `initialize` action under the kernel unless `setup_on_connect: true`.
- PyLabRobot checks tips and tracked volumes first, so errors such as `TooLittleLiquidError` or `HasTipError` fail the action before anything is sent.
- An operation longer than `action_wait` returns `started` and finishes in the background before the next action starts.
- After a failed operation, reads are suspect until `initialize` runs again.
- Tracked volumes model what was pipetted, and wells start empty unless `volumes` sets a starting volume.

## Safe state

A stop cancels running operations after the current firmware command. Nothing moves to make the deck safe, since any move can spill or crash a tip, so keep the instrument's cover interlock closed.

## Setup

1. Install with `uv tool install --compile-bytecode "halkit[pylabrobot] @ git+https://github.com/sohan-bhat/OpenHAL"`, plus PyLabRobot's USB or HTTP extras for the instrument.
2. Start from `openhal/drivers/pylabrobot/examples/starlet.hal.yaml` or `describe`.

| Key | Default | Meaning |
|---|---|---|
| `backend` | required | `star` for Hamilton STAR and STARlet, `evo` for Tecan EVO, `opentrons` for the OT-2 or `chatterbox` for simulation |
| `deck` | by backend | `starlet`, `star`, `ot2` or `evo150` |
| `deck_env` | none | Variable holding a deck JSON path, instead of `layout` |
| `layout` | empty | Resources and positions |
| `num_channels` | 8 | Chatterbox channel count |
| `host`, `port` | none, 31950 | OT-2 address |
| `serial_number` | none | Picks one of several STARs |
| `setup_on_connect` | false | Run `setup()`, which homes the channels, on connect |
| `track_volumes` | true | PyLabRobot tip and volume tracking |
| `volumes` | empty | Starting volumes such as `{ "plate:A1": 200 uL }` |
| `action_wait` | `8 s` | Time before an action returns `started`, at most 9 s |

## Known limitations

- No 96 channel head, gripper arm or resource moves yet.
- Plate readers, heater shakers and other PyLabRobot machines need separate drivers.
- Real backends report a lost instrument only when a command fails.
- Tracking is global in PyLabRobot, so `track_volumes` affects every PyLabRobot user in the hub's process.

## Hazard defaults

`high`. Channels move fast, tips can crash and liquids can be hazardous. The example keeps `confirm-each-time` on each action.

## Sources

- PyLabRobot documentation, https://docs.pylabrobot.org/
- PyLabRobot LiquidHandler and resources source, MIT and used as a library, https://github.com/PyLabRobot/pylabrobot
