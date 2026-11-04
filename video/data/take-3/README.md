# take-3

One take of the demo session, recorded on 2026-11-03 by `video/hub/record_session.py`. A real OpenHAL hub 0.1.0 drove the simulated SO-101 from `video/hub/so101-demo.hal.yaml` in MuJoCo 3.10.0. A nested Claude Code session reached the hub only through `openhal mcp`, and a headless Inspector, paired as the person, approved the held drop and pressed STOP. [TAKE.md](../TAKE.md) says which take the video uses and why.

## Prompts

The person's prompts, in the order the session got them, at the time each one went to Claude Code.

| t (s) | Prompt |
|---|---|
| 19.72 | Pick up the red cube and put it in the bin. |
| 95.12 | I put the cube back on the desk. Do it again, as fast as you can. Go at 120 degrees per second. |
| 137.47 | I put the cube back on the desk. Do it at a normal speed then. |

The take ends at about 159.6 s.

## One clock

Every `t` in this folder is seconds since the take began, on one monotonic clock in the recording process. `session.json` holds `epoch0`, the Unix time of t = 0, so the Unix time of any event is `epoch0 + t`.

| Source | How its time is taken |
|---|---|
| Claude Code transcript | Each output line is stamped when the recording process read the line from the `claude -p` pipe, in `claude.times.jsonl` |
| Prompts | Stamped when the prompt was written to the session's input, in `marks.jsonl` as `t_sent` |
| Hub live events | Stamped when each event arrived on the hub's `/v1/live` socket |
| Audit log | The hub's own Unix time `at`, with `t = at - epoch0` added |
| Frames | Simulated time on the physics thread, shifted onto the clock by the moment the simulation started, as the earlier film data does |
| Inspector clicks | The browser's own time of the DOM click event, `performance.timeOrigin + event.timeStamp`, minus `epoch0` |
| Screenshots | The browser's Unix time just before each screenshot, minus `epoch0` |

All of these run on one machine, so the clocks agree to within a few milliseconds. A Claude Code line can reach the pipe a little after Claude Code wrote it, and a hub event can reach the socket a little after the hub sent it, so those stamps are upper bounds by a few milliseconds.

## Files

| File | Size | What it holds |
|---|---|---|
| `claude.stream.jsonl` | 0.41 MB | The raw `--output-format stream-json --verbose --include-partial-messages --replay-user-messages` output of one `claude -p` session, 809 lines, byte for byte as Claude Code wrote it |
| `claude.times.jsonl` | 0.04 MB | One row per transcript line, `line` counted from 1, its `t` and its `type` |
| `claude.stderr.txt` | 0.00 MB | What the session wrote to stderr |
| `hub-live.jsonl` | 0.55 MB | 2722 events from the hub's `/v1/live` socket, read with the person's token, each as `{t, source, via, kind, event}`. Audit events carry `type: audit` and readings carry `type: reading` |
| `hub-audit.jsonl` | 0.03 MB | The hub's whole audit log at the end of the take, 79 entries in order of `seq`, with the hash chain. Entries with a negative `t` come from before the take's clock started, the hub starting and the agent token being made |
| `frames.csv.gz` | 0.11 MB | The arm and the cube at 60 Hz, 9014 rows from t = 14.1411 s to t = 164.3578 s, gzipped CSV with a header row |
| `marks.jsonl` | 0.00 MB | The recording's own notes, such as each prompt sent, each turn's end, the drop held for a person, the cube set back on the desk, and each click |
| `inspector.jsonl` | 0.00 MB | Every Inspector click and screenshot. A click row has the DOM event's `t`, the button's text and label, and the times the command left the recorder and Playwright began and finished the click |
| `inspector/*.png` | | Kept in `video/out/data/take-3/inspector/`, which git ignores. Screenshots of the real Inspector, 2560 by 1440, a 1280 by 720 CSS viewport at device scale 2, dark theme |
| `session.json` | 0.00 MB | The take's setup, the exact `claude` command line, versions, the model source, the frame columns and units, and the result of the preflight device check |

Local paths in the hub files read `OPENHAL_HOME` and `MODEL_DIR`. The transcript keeps the scratch folder's paths as Claude Code saw them. No token appears in any file, and the recorder fails the take when a token shows up in one.

## Frames

| Columns | Unit |
|---|---|
| `t` | s on the take's clock |
| `shoulder_pan`, `shoulder_lift`, `elbow_flex`, `wrist_flex`, `wrist_roll` | deg, the joint angles of the model, zero at the middle of each joint's range |
| `gripper` | percent open, 0 closed and 100 fully open |
| `gripper_jaw` | deg, the gripper joint angle itself |
| `gripper_x` to `gripper_qz` | the `gripper` body's world pose |
| `tip_x` to `tip_qz` | the `gripperframe` site's world pose, the point `move_to` moves |
| `cube_x` to `cube_qz` | the cube's world pose |
| `lag_ms` | how far the physics ran behind the clock when it took the frame |

The physics shares the hub's Python process, so a busy moment can leave simulated time behind the clock. A message at time `t` takes effect in the frames near `t` minus that frame's `lag_ms`. In this take the median lag is 2.2 ms and the worst is 114 ms.

Positions are metres in the world frame, z up, with the arm's base at the origin. Quaternions are w, x, y, z. The scene is `video/hub/scene.xml`, the same desk, cube and bin as the earlier film data in `video/data/README.md`. The cube is 25 mm and starts at (0.2, 0.09, 0.0125) m. The bin's centre is at (0.12, -0.17) m.

## Inspector screenshots

This take isn't the one the video uses, so its screenshots stay out of git, in `video/out/data/take-3/inspector/` on the machine that recorded the take. `inspector.jsonl` still lists each one with its time.

| File |
|---|
| `inspector/0-devices-dark.png` |
| `inspector/1-pending-2-dark.png` |
| `inspector/1-pending-dark.png` |
| `inspector/2-approve-clicked-2-dark.png` |
| `inspector/2-approve-clicked-dark.png` |
| `inspector/3-approved-2-dark.png` |
| `inspector/3-approved-dark.png` |
| `inspector/4-before-stop-dark.png` |
| `inspector/5-stopped-dark.png` |
| `inspector/6-end-dark.png` |

`0-devices` is the arm's page before the first prompt. `1-pending` is the held `drop_in_bin` request on the Confirmations page, `2-approve-clicked` is the same page right after the click on Approve, and `3-approved` is the page once the hub finished the drop. `4-before-stop` is the arm's page with STOP showing, just before the last prompt, and `5-stopped` shows the stopped banner and UNLOCK in place of STOP after the click. A number after a name, such as `-2`, is a later approval in the same take.

## What the recording script did

- The script set the cube back at its start pose between prompts when the cube had moved, as a person putting the cube back on the desk. The next prompt then began with "I put the cube back on the desk." The row in `marks.jsonl` gives the time.
- The script clicked Approve in the Inspector after each `drop_in_bin` the hub held, 3.1 s and 3.1 s after the script first saw the held request, and clicked STOP 0.8 s into the first arm move after the last prompt.
- The script never sent a command to the arm. Every command came from the Claude Code session.
