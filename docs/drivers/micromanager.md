# micromanager driver

The `micromanager` driver runs research microscopes through Micro-Manager with pymmcore-plus 0.18.1 on pymmcore 12.5.1, LGPL-2.1 and unmodified. One device file is one microscope from a Micro-Manager configuration file, with cameras, stages, focus drives, turrets, filter wheels, shutters and light sources from any maker on the Micro-Manager device list. `describe` drafts a file from the configuration.

The driver is for lab and research microscopes. OpenHAL has no driver for clinical or patient-connected medical devices, see [ADR 0024](../adr/0024-microscopy-and-lab-drivers.md).

## Supports

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
| `move_xy` with `x`, `y` | action | `{ command: move_xy }` | `setXYPosition` with both axes |
| `autofocus` with optional `span` | action | `{ command: autofocus, method: auto }` | `fullFocus`, or a sweep scored by sharpness |
| `home`, `home_xy`, `home_focus` | action | `{ command: home, stage: all }` | `home` on each stage |
| `stop` | action | `{ command: stop }` | `stop` on each stage |

Other names take a `map`, and a stage map's `device` picks a non-default stage such as a piezo. Every move ends with `waitForDevice` and reads back the reported position.

`move_xy`, `autofocus` and `home` must list every stage channel each action moves in `effects`. `move_xy` also stays inside the x and y channel limits.

## Snapshots and autofocus

An image channel snaps one frame, stretched from the 0.1 to 99.9 percentile to 8 bits so a dark frame stays dark, or over the whole bit depth with `contrast: full`. Frames are for viewing, not intensity measurement. With auto shutter on, a snapshot lights the sample.

`autofocus` runs the configuration's autofocus device, such as a Prior PureFocus or Nikon Perfect Focus. Without one, or with `method: image`, the driver sweeps focus over `span` in `steps` frames and stops at the sharpest z, inside the focus channel's limits and `max_change_per_s`.

## The z limit

On an inverted microscope a larger z usually raises the objective, and the front lens touches the slide one working distance past focus, often 0.2 mm or less at 40x or 63x. Set the z limit a little past focus for the objective with the shortest working distance. `describe` names which end of z is the crash limit.

## Safe state

A stop cancels running actions, stops every stage in place and closes the shutter. Light sources keep their level unless the file's safe state sets the light.

## The simulated microscope

`micromanager: sim` connects to a simulated inverted fluorescence microscope on pymmcore-plus's UniMMCore, with no hardware or Micro-Manager install. `sim:<name>` makes a separate simulated microscope. The camera images a real micrograph of human cells at true scale, the stage pans, the 20x, 40x and 63x objectives and DAPI, GFP, dual and TRITC filters change the view, and the slide is sharp at z = 1500 um. Past the working distance the focus drive stalls with an error.

1. Install the extra with `uv sync --extra micromanager` in a checkout.
2. Copy [the example file](../../openhal/drivers/micromanager/examples/simulated-microscope.hal.yaml) into `~/.openhal/devices/`, or the devices folder under `OPENHAL_HOME`.
3. Confirm the limits with `uv run openhal file confirm <the copied file>`, since x, y, z and the objective are high risk.
4. Start the hub with `uv run openhal start`, and read `microscope.image` for a snapshot.

## Setup

1. Install device adapters with `uv run mmcore install`, or point `adapters_env` at a Micro-Manager folder.
2. Build and check a configuration with Micro-Manager's hardware configuration wizard.
3. Run `export MICROMANAGER_CONFIG=/path/to/MMConfig.cfg`.
4. Start from [inverted-microscope.hal.yaml](../../openhal/drivers/micromanager/examples/inverted-microscope.hal.yaml) or `describe`.

| Key | Default | Meaning |
|---|---|---|
| `config` | required | `sim`, `sim:<name>`, or a variable holding the configuration path |
| `adapters_env` | none | Variable holding the adapter folder. Not needed after `mmcore install` |
| `timeout` | `5 s` | Longest call, 0.5 s to 9 s |
| `action_wait` | `8 s` | Time before an action returns `started`, at most 9 s |
| `image_format` | `jpeg` | `jpeg` or `png` |
| `jpeg_quality` | 85 | 1 to 100 |
| `max_side` | 1024 | Longer snapshot side in pixels |
| `contrast` | `auto` | `auto` stretches deep frames, `full` maps the whole bit depth |
| `auto_shutter` | the configuration's | Set auto shutter on connect |

## Known limitations

- MMCore reports no stage travel, so `describe` proposes ranges around the current position for a person to set.
- No sequence or multi-dimensional acquisition and no ROIs.
- One MMCore call at a time, so reads queue behind stage moves.
- Some stages home toward the sample.
- pymmcore-plus logs to the user's data folder unless `PYMM_LOG_FILE` is set.

## Hazard defaults

`medium`, with every length channel high risk. Use `high` with a laser above class 2.

## Sources

- pymmcore-plus documentation, https://pymmcore-plus.github.io/pymmcore-plus/
- pymmcore-plus source, CMMCorePlus and UniMMCore, BSD-3-Clause and used as a library, https://github.com/pymmcore-plus/pymmcore-plus
- Micro-Manager device support, https://micro-manager.org/Device_Support
- MMCore API, https://github.com/micro-manager/mmCoreAndDevices
- Slide image by ZEISS Microscopy, CC BY 2.0, https://commons.wikimedia.org/wiki/File:SK8-18-2_human_derived_cells,_fluorescence_microscopy_(29942101073).jpg
