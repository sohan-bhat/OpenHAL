# micromanager driver

The `micromanager` driver runs research microscopes through Micro-Manager, the open source control layer for microscope hardware, with pymmcore-plus. One device file is one microscope as a Micro-Manager configuration file describes the microscope, so the same driver reaches cameras, XY stages, focus drives, objective turrets, filter wheels, shutters and light sources from Nikon, Zeiss, Olympus, Leica, ASI, Prior, Ludl, Sutter, Hamamatsu, Andor, Lumencor, CoolLED and the other makers on the Micro-Manager device list.

| | |
|---|---|
| Driver name | `micromanager` |
| Library | pymmcore-plus 0.18.1 (BSD-3-Clause) on pymmcore 12.5.1 (LGPL-2.1, unmodified) |
| Extra | `uv tool install --compile-bytecode "halkit[micromanager] @ git+https://github.com/sohan-bhat/OpenHAL"` |
| Hazard default | medium |
| Conformance | full |
| Safe state | native. Running actions end, the stages stop where they are and the shutter closes |
| Self-describe | yes, from the loaded configuration |

The driver is for lab and research microscopes. OpenHAL has no driver for clinical or patient-connected medical devices, see [ADR 0024](../adr/0024-microscopy-and-lab-drivers.md).

## What it supports

| Name | Kind | Map | MMCore call |
|---|---|---|---|
| `x`, `y` | read and write, length | `{ stage: xy, axis: x }` | `getXYPosition`, `setXYPosition` with the other axis kept |
| `z` or `focus` | read and write, length | `{ stage: focus }` | `getPosition`, `setPosition` on the focus drive |
| `image`, `snapshot` or `frame` | read, image | `{ camera: image }` | `snapImage` and `getImage`, as JPEG or PNG |
| `exposure` | read and write, time | `{ camera: exposure }` | `getExposure`, `setExposure` |
| `pixel_size` | read, length | `{ camera: pixel_size }` | `getPixelSizeUm` for the current objective |
| `shutter` | read and write, bool | `{ shutter: current }` | `getShutterOpen`, `setShutterOpen` |
| `busy` | read, bool | `{ status: busy }` | `systemBusy` |
| any name | read and write, enum, string or index | `{ state: Objective }` | `getStateLabel`, `setStateLabel`, or `getState` and `setState` for a number |
| any name | read and write, enum or string | `{ group: Channel }` | `getCurrentConfig`, `setConfig` |
| any name | read and write, any type | `{ device: LED, property: Intensity }` | `getProperty`, `setProperty` |
| `move_xy` (args `x`, `y`) | action | `{ command: move_xy }` | `setXYPosition` with both axes |
| `autofocus` (arg `span`, optional) | action | `{ command: autofocus, method: auto }` | `fullFocus`, or a sweep scored by sharpness |
| `home`, `home_xy`, `home_focus` | action | `{ command: home, stage: all }` | `home` on each stage |
| `stop` | action | `{ command: stop }` | `stop` on each stage |

A channel or action under another name takes a `map`. A stage map takes `device` to reach a stage other than the configuration's default one, such as a piezo, and positions convert to and from um. Every move waits for the device with `waitForDevice`, and the reading after a move is the position the stage reports.

`move_xy`, `autofocus` and `home` list the stage channels they move in `effects`, so the hub reads the new positions back. A file that leaves one out doesn't connect. `move_xy` fails before the stage moves when x or y falls outside the limits of the file's x or y channel, even when the action's own arguments allow more.

## Snapshots

An image channel snaps one frame and returns the frame as an image the agent can see. The driver scales a camera's 10, 12 or 16 bit frame to 8 bits, by default from the frame's 0.1 to its 99.9 percentile as Micro-Manager's display does, and never over less than 5 % of the bit depth, so a dark frame stays dark. `contrast: full` maps the whole bit depth instead. Frames are scaled down to `max_side` pixels and are for looking at, not for measuring intensity. With auto shutter on, Micro-Manager opens the shutter for the exposure, so a snapshot lights the sample.

## Autofocus

`autofocus` runs the configuration's autofocus device when the configuration has one, such as a Prior PureFocus or a Nikon Perfect Focus. Without one, or with `method: image` in the map, the driver sweeps the focus drive over `span` around the current z, scores each frame's sharpness, sweeps again in finer steps around the best frame and stops at the sharpest z. The sweep never leaves the limits of the file's focus channel and moves no faster than the channel's `max_change_per_s`, so the kernel's z limits hold for every step of a sweep whose single steps never pass through the kernel, and `steps` in the map sets the coarse sweep's frames.

## The z limit

On most microscopes one end of the focus travel moves the objective into the slide. On an inverted microscope a larger z usually raises the objective toward the slide, and the objective's front lens touches the slide one working distance past focus, often 0.2 mm or less for a 40x or 63x objective. Set the z limit toward the sample from the objective with the shortest working distance, a little past focus. `describe` reads the focus drive's direction and names which end of z is the crash limit.

## Safe state

A stop cancels running actions, stops every stage the file uses where the stage stands and closes the core's shutter, which takes the excitation light off the sample. Nothing moves to make the microscope safe. A light source stays at its level unless the file's own safe state sets it, so add the light channel to the safe state on a microscope with a laser.

## The simulated microscope

`micromanager: sim` connects to a simulated inverted fluorescence microscope that needs no hardware and no Micro-Manager install. The simulator is pymmcore-plus's UniMMCore with Python devices in place of device adapters, so the driver calls the same MMCore methods the driver calls on real hardware.

- The camera images a real micrograph of human cells, vimentin in green and nuclei in blue, from ZEISS Microscopy under CC BY 2.0, at the micrograph's true scale.
- The stage pans the field of view across the slide, and the turret's 20x, 40x and 63x objectives set the magnification and the pixel size.
- The filter wheel's DAPI, GFP, dual and TRITC positions pick what reaches the camera, and exposure and LED intensity set the brightness.
- The slide is sharp at z = 1500 um, tilted a little across the stage, and defocus blurs the frame by the objective's aperture.
- A larger z moves toward the slide. Past the objective's working distance the focus drive stalls at the slide and returns an error, and the stage holds still until the objective moves back down.

`sim:<name>` connects to a separate simulated microscope. [The example file](../../openhal/drivers/micromanager/examples/simulated-microscope.hal.yaml) runs the simulator in a hub.

1. Install the extra with `uv sync --extra micromanager` in a checkout.
2. Copy `openhal/drivers/micromanager/examples/simulated-microscope.hal.yaml` into the hub's devices folder, `~/.openhal/devices/` unless `OPENHAL_HOME` names another.
3. Confirm the limits with `uv run openhal file confirm <the copied file>`, because x, y, z and the objective are high risk.
4. Start the hub with `uv run openhal start`, and read `microscope.image` for a snapshot.

## Setup

1. Install Micro-Manager's device adapters with `uv run mmcore install`, or point `adapters_env` at an existing Micro-Manager folder.
2. Make a configuration file with Micro-Manager's hardware configuration wizard, and check the configuration in Micro-Manager first.
3. Set an environment variable to the configuration file's path, such as `export MICROMANAGER_CONFIG=/path/to/MMConfig.cfg`.
4. Start from [inverted-microscope.hal.yaml](../../openhal/drivers/micromanager/examples/inverted-microscope.hal.yaml) or call `describe` for a draft with your device labels.
5. Run `openhal file validate`, then confirm the limits by hand.

## Parameters

| Key | Default | Meaning |
|---|---|---|
| `config` | required | `sim`, `sim:<name>`, or the name of an environment variable that holds the configuration file's path |
| `adapters_env` | none | An environment variable that holds the Micro-Manager folder with the device adapters. pymmcore-plus finds an installation from `mmcore install` without the variable |
| `timeout` | `5 s` | The longest wait for a move, a snapshot or any other call. Between 0.5 s and 9 s |
| `action_wait` | `8 s` | How long an action waits before returning `started`. At most 9 s |
| `image_format` | `jpeg` | `jpeg` or `png` |
| `jpeg_quality` | 85 | JPEG quality from 1 to 100 |
| `max_side` | 1024 | The longer side of a snapshot in pixels |
| `contrast` | `auto` | `auto` stretches a deep frame, `full` maps the whole bit depth |
| `auto_shutter` | the configuration's | `true` or `false` sets Micro-Manager's auto shutter on connect |

## Known limitations

- MMCore reports no stage travel, so `describe` proposes ranges around the current position and a person sets the real ones.
- Sequence acquisition, multi-dimensional acquisitions and ROIs are not exposed. A snapshot is one frame.
- The driver sends one MMCore call at a time, so a read waits while a stage moves.
- Homing follows the hardware, and some stages home toward the sample. Check the direction before confirming a home action.
- pymmcore-plus writes its log file into the user's data folder unless `PYMM_LOG_FILE=0` is set.

## Hazard defaults

The default hazard is `medium`. Stages and focus drives move with little force, but a focus move past the working distance can crack a slide or an objective's front lens, and every length channel is high risk under the hub's risk table. Set the device's hazard to `high` on a microscope with a laser above class 2.

## Sources

- pymmcore-plus documentation, https://pymmcore-plus.github.io/pymmcore-plus/
- pymmcore-plus source, CMMCorePlus and UniMMCore, https://github.com/pymmcore-plus/pymmcore-plus (BSD-3-Clause, used as a library)
- Micro-Manager device support, https://micro-manager.org/Device_Support
- MMCore API, https://github.com/micro-manager/mmCoreAndDevices
- Slide image, https://commons.wikimedia.org/wiki/File:SK8-18-2_human_derived_cells,_fluorescence_microscopy_(29942101073).jpg (ZEISS Microscopy, CC BY 2.0)
