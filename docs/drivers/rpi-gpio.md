# rpi-gpio driver

The rpi-gpio driver drives Raspberry Pi GPIO pins through gpiozero. Digital outputs for relays and LEDs, digital inputs for buttons and switches, PWM for fans and dimmers, and servo pulses. Pins are named in the device file, and channels use those names. The package also has `watch_stop_button`, which turns a GPIO input into a physical stop button for the hub.

## What it supports

| Channel | Device | Value |
|---|---|---|
| read, `bool` | digital input with pull-up, pull-down or none | true while active |
| write, `bool` | digital output | on or off |
| write, number in `percent` or `dimensionless` | PWM output | duty cycle, 0 to 100 % or 0 to 1 |
| write, number in an angle unit, map `mode: servo` | servo | angle |

Write channels read back the state gpiozero holds (on or off, the duty cycle, the angle). A servo that has not been moved since connecting reads as no value, because it gets no pulse until the first write.

## Setup

On Raspberry Pi OS Bookworm or later, gpiozero uses lgpio, which comes with the OS.

```sh
uv tool install --compile-bytecode "openhal-hub[rpi-gpio] @ git+https://github.com/sohan-bhat/OpenHAL"
sudo apt install -y python3-lgpio    # if the hub's virtual environment can't see it
```

Your user needs to be in the `gpio` group. Off a Pi, set `pin_factory: mock` to run against gpiozero's mock pins.

## Parameters

| Parameter | Default | Meaning |
|---|---|---|
| `pins` | required | Names to BCM GPIO numbers, `{ relay: 17, door: 22 }`. The shorthand `rpi-gpio: { relay: 17 }` sets it |
| `active_high` | `true` | `false` inverts outputs, for relay boards that switch on a low level |
| `pull` | `up` | Default input pull, `up`, `down` or `none` |
| `bounce` | none | Default input debounce time, such as `50 ms` |
| `on_connect` | `off` | `off` starts digital outputs inactive. `keep` leaves them at whatever level the pin has |
| `pin_factory` | `auto` | `auto`, `lgpio`, `rpigpio`, `pigpio`, `native` or `mock` |

Pins are BCM GPIO numbers 0 to 27, not header pin numbers. GPIO 17 is header pin 11. A pin named in `pins` but not used by a channel is allowed, which is how a stop button pin is declared.

## Channel maps

The map is optional. Without one, a channel uses the pin with its own name.

```yaml
connect: { rpi-gpio: { heat_mat: 17, fan: 18, vent: 12, door_closed: 22 }, active_high: false }
read:
  door_closed: { type: bool }
write:
  heat_mat: { type: bool }
  fan: { unit: percent, min: 0, max: 100, map: { active_high: true, frequency: 25000 } }
  vent: { unit: degree, min: 0, max: 80, map: { mode: servo } }
```

| Key | Default | Meaning |
|---|---|---|
| `pin` | the channel's name | A name from `pins`, or a BCM number |
| `mode` | from the channel type | `servo` for servo outputs. Number outputs are PWM otherwise |
| `active_high` | the parameter | Per-pin inversion. For inputs it only applies with `pull: none` |
| `pull`, `bounce` | the parameters | Per-input pull and debounce |
| `frequency` | `100` | PWM frequency in Hz |
| `min_angle`, `max_angle` | `-90`, `90` | The servo's angle range in degrees |
| `min_pulse_ms`, `max_pulse_ms`, `frame_ms` | `1`, `2`, `20` | Servo pulse widths and frame |

Inputs take their active level from the pull resistor. With a pull-up, a button wired to ground reads true when pressed. With a pull-down, a signal that drives the pin high reads true. With `pull: none`, `active_high` decides.

The driver checks at load time that PWM limits fit 0 to 100 % (or 0 to 1) and that servo limits fit `min_angle` to `max_angle`, so the file can't ask for something the pin can't do.

## The stop button

```python
from openhal.drivers.rpi_gpio import watch_stop_button

button = watch_stop_button(27, kernel_stop, loop=asyncio.get_running_loop())
...
button.close()
```

`watch_stop_button(pin, on_press, *, pull_up=True, active_state=None, bounce_s=0.05, loop=None, pin_factory=None)` calls `on_press` every time the button on BCM `pin` is pressed. With `loop`, the call runs on that event loop, and a coroutine function runs as a task there. Without `loop`, the call runs on gpiozero's thread. `watch_stop_button` never touches an output. `RpiGpioDriver.stop_button_pin()` returns the number of a `stop_button` pin named in `pins` but not used by a channel, so the hub can find the pin in a device file. The hub wires up the stop button, and the driver doesn't call `watch_stop_button` on its own.

A GPIO stop button only asks the hub to stop. Keep a hardware e-stop that cuts power on anything that can hurt someone.

## Example

`openhal/drivers/rpi_gpio/examples/greenhouse-vent.hal.yaml` drives an active-low relay, a PWM fan and a vent servo, reads a door switch, declares a stop button pin, and has an interlock and a watchdog rule. `spec/examples/rpi-relay.hal.yaml` is a single relay.

## Errors and health

- Pins another program holds, a missing pin library, or not being on a Pi raise `DriverError` when connecting.
- Channels without a pin, two channels on one pin, input channels that aren't bool and outputs that aren't bool or number raise `DriverError` when the file loads.
- `health()` reports the device as disconnected if any pin was released.

## Limitations

- No analog inputs. The Pi has no ADC, so use an ADC board through another driver.
- No I2C, SPI or one-wire.
- Software PWM through lgpio jitters at high frequencies. Use GPIO 12, 13, 18 or 19 for hardware PWM where it matters.

## Hazard default and safe state

The default hazard is low, because a GPIO pin drives 3.3 V at a few milliamps. What it switches can be anything, so set the hazard in the device file from what the relay or transistor drives. GPIO has no emergency behavior, so `safe_state_support` is `file`, and the hub applies the device file's `safe_state` with ordinary writes.

When the driver closes or the hub exits, gpiozero releases the pins and the pin library usually turns them into inputs, so they stop being driven. An active-low relay board without a pull-up on its input can then switch on. Fit a pull resistor so a released pin means off, and say so in the device file's `safe_state_note`.

## Sources

- gpiozero documentation, https://gpiozero.readthedocs.io/en/stable/
- Raspberry Pi GPIO documentation, https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#gpio
- Raspberry Pi pinout, https://pinout.xyz/
- lgpio Python documentation, https://abyz.me.uk/lg/py_lgpio.html
