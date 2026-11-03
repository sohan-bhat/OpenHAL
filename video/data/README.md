# Film data

This folder holds the motion and the hub messages for the launch film's arm shots. A real OpenHAL hub drove a simulated SO-101 in MuJoCo, an agent sent every command through `openhal mcp`, and a person approved and stopped through the routes the Inspector uses. Nothing here is animated by hand.

`video/hub/record.py` made these files, and `check.py` checks them.

## Files

| File | Beat | Length | Frames | Messages |
|---|---|---|---|---|
| `beat-1-devices.json` | A printer, a board and a bench supply connect | 9.8 s | 1181 | 238 |
| `beat-2-pick-and-place.json` | The agent picks the cube and places it | 7.6 s | 911 | 245 |
| `beat-3-limit.json` | A move outside the workspace box, blocked with LIMIT_EXCEEDED | 3.1 s | 369 | 84 |
| `beat-4-approval.json` | The drop into the bin, held, approved, then done | 9.8 s | 1172 | 301 |
| `beat-5-stop.json` | STOP during a move, then the arm holds still | 5.3 s | 636 | 155 |
| `session.json` | The clock, the units, the scene, the model source and the beat index | | | |

The five files add up to about 1.2 MB.

## The clock

Every time is in seconds since the recording began, on one monotonic clock, in the `t` field of a frame or a message. The beats come one after another on that clock, with a second of quiet after each.

## Frames

Each beat file has `frames.columns` and `frames.rows`, one row per frame at 120 Hz, two physics steps of 1/240 s. A frame's time comes from simulated time, so the rows are exactly 1/120 s apart.

| Columns | Unit |
|---|---|
| `shoulder_pan`, `shoulder_lift`, `elbow_flex`, `wrist_flex`, `wrist_roll` | degrees, the joint angles of the model |
| `gripper` | percent open, 0 closed and 100 fully open |
| `gripper_jaw` | degrees, the gripper joint angle itself |
| `gripper_x` to `gripper_qz` | the `gripper` body's world pose |
| `tip_x` to `tip_qz` | the `gripperframe` site's world pose, the point `move_to` moves |
| `cube_x` to `cube_qz` | the cube's world pose |
| `lag_ms` | how far the physics ran behind the clock when it took the frame |

Positions are metres in the world frame, z up, with the arm's base at the origin. Quaternions are w, x, y, z. Joint names and units match the real arm in LeRobot, so the Blender rig can take the angles as they are.

The physics shares the hub's Python process, so a busy moment can leave simulated time behind the clock. The mean lag is 2 to 4 ms and the worst is about 110 ms, while the devices connect. A message at time `t` takes effect in the frames near `t` minus that frame's lag.

## Messages

Each beat file has `messages`, in order of arrival.

- `source: agent, via: mcp, kind: request`, a tool call from the agent, with its arguments.
- `source: hub, via: mcp, kind: response`, the tool's result. A blocked command carries `error` with its registry code and name, such as -32010 LIMIT_EXCEEDED. A held command has status `pending` and a `request_id`.
- `source: person, via: rest`, the person's request and the hub's response, such as `POST /v1/confirmations/<id>/approve` and `POST /v1/stop`.
- `source: hub, via: live, kind: event`, everything the hub sent on `/v1/live`. Audit events include `connect`, `action`, `write`, `confirm`, `stop` and `safe_state`, and reading events carry each polled value.

`marks` notes where each beat starts and ends and when each device was plugged in. Local paths read `OPENHAL_HOME` and `MODEL_DIR`, and no token appears anywhere.

Before the clock started, the agent made one `dry_run` of the blocked move, so the MCP server had loaded its error mapping. A dry run never reaches the device. Without it the first block takes seconds longer to come back while the server loads, which is the server starting and not the hub.

## The scene

| Item | Where |
|---|---|
| Floor | z = 0 |
| Arm base | the origin, from MuJoCo Menagerie's `robotstudio_so101` |
| Cube | 25 mm, 20 g, starting at (0.2, 0.09, 0.0125) m, turned 26.6 degrees about z |
| Bin | centred at (0.12, -0.17) m, 82 mm inside, walls 40 mm high |

`video/hub/scene.xml` has the same numbers, and `video/CREDITS.md` names the model's source and license.

## The arm's limits

`video/hub/so101-sim.hal.yaml` is the device file, confirmed by the person at the start of the run.

| Limit | Value |
|---|---|
| `move_to` workspace box | x 160 to 220 mm, y -100 to 100 mm, z 10 to 70 mm, gripper pointing down |
| Joint speed | 60 deg/s for pan, lift and elbow, 90 deg/s for wrist flex and roll |
| Gripper | 0 to 100 percent, 100 percent per second |
| `drop_in_bin` | held for a person's approval every time |
| Safe state | `hold`, every joint stays where it stands |

## Checks

`uv run python video/data/check.py` reads these files and checks each claim against a tolerance of 0.05 degrees on every joint.

- Every beat plays at 120 Hz with no gap.
- While the hub blocks the move outside the box, no joint moves more than 0.05 degrees until the beat ends.
- The arm turns at more than 5 deg/s when STOP is pressed. From the hub's reply to STOP until the beat ends, no joint moves more than 0.05 degrees.
- The connect events, the block, the pending drop and its approval, and the stop are all in the messages.

The last run's result.

```
limit beat: LIMIT_EXCEEDED, joints moved at most 0.0000 deg in 3.1 s
stop beat: turning at 38 deg/s when STOP was pressed, 1.93 deg more until the hub's reply 116 ms later, then at most 0.0180 deg in 4.3 s
```

The arm stops about 50 ms after the person presses STOP, which is most of the 1.93 degrees above, and the joints settle onto their held setpoints within about 0.1 s more.

## Recording again

```
uv run --extra mujoco --extra scpi --extra openhal-firmware python video/hub/record.py --cache <folder>
```

The run fetches the model into `--cache` and checks every file's hash, makes a temporary home, and writes this folder again. It never reads a real home or connects to a running hub, and every device in it is simulated.
