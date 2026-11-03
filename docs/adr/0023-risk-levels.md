# 0023 Risk levels decide what an agent may do at once

## Context

On 2026-11-02 the owner's own agent tried to fade an LED on a real ESP8266 through OpenHAL. The agent hit a 25 %/s rate cap, a 60 % maximum from the limits interview, and a hub too old to run timed steps. The owner's words, verbatim, follow.

> i dont want claude coding it for me the hub should give all perms to the agent but just its a bridge, in order to fix this issue you should not have a pwm method or whatever, u should just fully give access to the entire thing to the agent

The owner was then asked how agent access should work by default. The options were bridge by default, pure bridge, or unlock only the owner's board, and the owner answered "dynamically catogarize based on risk level". Asked whether agents should reach every pin on a board, not just what the firmware names, the owner chose "Yes, every pin".

Until this decision every device file loaded read-only until a person confirmed every limit, and the interview suggested a slow rate for every channel. Those rules fit a heater and a robot arm. For an LED they got in the agent's way and protected nothing.

## Decision

### Three levels

The hub gives every readable channel, write channel and action one of three levels, low, medium or high, from what each one is. The rules live in one table in `openhal/spec/risk.py`, and docs/SAFETY.md repeats the table.

- Reading is always low.
- A write channel or action takes the highest level any rule gives, and medium when no rule applies. Any doubt raises the level.
- The rules use nothing but the device file and the device's own description, with no list of device names or ids. They draw on the file's `hazard`, the unit's physical quantity and the maximum it allows, the words in the channel's or action's name, the device's name when the channel's name has no such word, the channels an action changes, how many motion axes the device has, and the pin each channel drives.
- A missing unit (dimensionless) or a unit the table doesn't list moves the level up one.
- Channels and actions mapped to the same pin share the highest level among them, so a pin can't reach what a high risk channel drives.
- Three or more angle or length channels on one device make each of them high, so an arm's joints are high whichever driver serves the arm.

Typical low targets are LED brightness, a display, a buzzer and a status light. Typical medium targets are small motors, pumps and servos. Typical high targets are heaters and temperature setpoints, mains relays, robot arm joints, printer motion and anything a device file marks high hazard.

### Defaults by level

| Level | Default |
|---|---|
| low | Writes at once within the device's full reported range. No read-only start, no interview, no rate cap and no approval unless a person adds one |
| medium | Writes at once within the device's own reported range and rate. No interview and no approval unless a person adds one |
| high | As before. Read-only until a person confirms the limits, and an action that can't be undone is held for a person at least once |

- Stop, the safe state, the watchdog and the audit log apply at every level.
- A limit a person set always applies on top of these defaults. A low channel ignores a rate only while the rate is still `suggested`, the device's own suggestion.
- A high hazard device still holds every command for a person each time.
- The scope a target needs follows the device's hazard class, or the target's own level when that is lower. A low target on a device with no declared hazard needs `control_low`.
- An action can be undone when every effect it lists is a write channel the hub can set back, or when the safe state runs it.

### A person changes a level

- `openhal risk show DEVICE` lists each level with its reasons. `openhal risk set DEVICE.NAME LEVEL` changes one.
- Raising a level applies at once.
- Lowering a level gives an agent more, so it takes a person's typed phrase `confirm`, under the same terminal and human token rules as widening a limit. Without the phrase it becomes a pending change that a person approves with `approve`.
- Agents see every level through `describe_device`, `find` and `GET /v1/devices/{id}/risk`, and change none.
- A change is written into the device file as the entry's `risk`, with `by` and `at`, and into the audit log, so it survives a restart. A `risk` without `by` only raises, and a draft from a device, a library or an agent loses any `by`. `risk` stays out of the limits hash, so adding the field leaves every confirmed file confirmed.

### Every pin

- The OpenHAL Arduino library's `pins()` lists every free pin with its modes from the Arduino core's own macros, and leaves out the pins the board needs, the pins the sketch names with `.pin()` or `reserve()`, and the pins the sketch set to output before `begin()`.
- The firmware protocol gains `PIN` and the `io`, `pb` and `ab` keys of `DESC`. A stop or a lost heartbeat returns every pin the hub set to input.
- The driver turns each pin into `pin<N>`, `pin<N>_pwm`, `pin<N>_analog` and `pin<N>_mode`, and changes the pin's mode as each command needs.
- A plain pin is medium, because the file has no word for what is wired to the pin. A person can raise or lower that level.
- The library's version is 0.2.0, and the BareBoard example calls `pins()`. Flashing a board stays a person's step.

### The interview and existing files

- `openhal init`, `openhal file confirm`, the writer and the Inspector ask only about high risk targets. A draft that doesn't load yet still gets every question.
- A file a person already confirmed keeps its limits. A person who wants the old interview's limits wider runs `openhal limits set DEVICE.CHANNEL --max 100 % --rate none` and types confirm.
- A limit change on an entry that had no person's limits confirms that one entry, by the person who made it.

### What changed in the spec

`spec/v0.1/safety.md` and `spec/v0.1/device-files.md` changed these MUST rules, all at the owner's decision above.

1. Guarantee 3. A high risk target MUST stay read-only until a human confirmed its limits. Low and medium targets take commands within the Device File's range without one.
2. Check 3 blocks a command to a high risk target whose limits are unconfirmed, instead of every command to a file with any unconfirmed limit.
3. Check 5 measures scope against the lower of the target's level and the device's hazard class.
4. Check 10 skips a `max_change_per_s` that is still `suggested` on a low risk channel.
5. Check 14 holds a high risk action that can't be undone for a person at least once.
6. A new section, Risk levels, adds the MUST rules for reading, the table, unknown units, shared pins, overrides, who changes a level and the audit.
7. Device files section 12. Only high risk targets and the file-level limits that guard them need a confirmation.

## Consequences

- An agent fades an LED or sets a free pin at once, and a heater on the same hub stays read-only until a person confirms it.
- Low and medium targets of a fresh device run within limits the device or a library suggested rather than limits a person confirmed. The owner chose that trade for those targets. High targets keep every guard they had.
- The word lists are a heuristic. Doubtful cases go high, and a person corrects a level with one command.
- Tests that relied on any unconfirmed file being read-only now use a high risk channel for that check.
- The website and DESIGN.md still describe every limit as confirmed by a person. The lead updates that wording.
