# rpi-gpio driver

The rpi-gpio driver drives Raspberry Pi GPIO pins through gpiozero, with digital outputs for relays and LEDs, digital inputs for buttons and switches, PWM for fans and dimmers, and servo pulses. Pins are named in the device file and channels use those names. `watch_stop_button` turns a GPIO input into a physical stop button for the hub.

## Supports

| Channel | Device | Value |
|---|---|---|
| read, `bool` | digital input with pull-up, pull-down or none | true while active |
| write, `bool` | digital output | on or off |
| write, number in `percent` or `dimensionless` | PWM output | duty cycle, 0 to 100 % or 0 to 1 |
| write, number in an angle unit, map `mode: servo` | servo | angle |

Writes read back gpiozero's state. A servo reads as no value until the first write, since the servo gets no pulse before then.

## Setup

gpiozero uses lgpio, which comes with Raspberry Pi OS Bookworm or later.

```sh
uv tool install --compile-bytecode "halkit[rpi-gpio] @ git+https://github.com/sohan-bhat/OpenHAL"
sudo apt install -y python3-lgpio    # if the hub's virtual environment can't see it
```

Join the `gpio` group. Off a Pi, `pin_factory: mock` uses gpiozero's mock pins.

| Parameter | Default | Meaning |
|---|---|---|
| `pins` | required | Names to BCM GPIO numbers, `{ relay: 17, door: 22 }`. `rpi-gpio: { relay: 17 }` is shorthand |
| `active_high` | `true` | `false` inverts outputs for relay boards that switch on low |
| `pull` | `up` | Default input pull, `up`, `down` or `none` |
| `bounce` | none | Default input debounce such as `50 ms` |
| `on_connect` | `off` | `off` starts digital outputs inactive, `keep` leaves the pin level |
| `pin_factory` | `auto` | `auto`, `lgpio`, `rpigpio`, `pigpio`, `native` or `mock` |

Pins are BCM numbers 0 to 27, so GPIO 17 is header pin 11. Pins in `pins` that no channel uses are allowed, which is how a stop button pin is declared.

## Channel maps

Without a map a channel uses the pin of the same name.

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
| `pin` | the channel's name | A name from `pins` or a BCM number |
| `mode` | from the channel type | `servo` for servos, otherwise number outputs are PWM |
| `active_high` | the parameter | Per-pin inversion. Inputs use the setting only with `pull: none` |
| `pull`, `bounce` | the parameters | Per-input pull and debounce |
| `frequency` | `100` | PWM frequency in Hz |
| `min_angle`, `max_angle` | `-90`, `90` | Servo range in degrees |
| `min_pulse_ms`, `max_pulse_ms`, `frame_ms` | `1`, `2`, `20` | Servo pulse widths and frame |

With a pull-up a button wired to ground reads true when pressed, and with a pull-down a pin driven high reads true. With `pull: none`, `active_high` sets the active level. PWM limits must fit 0 to 100 % or 0 to 1, and servo limits `min_angle` to `max_angle`, or the file fails to load.

## The stop button

```python
from openhal.drivers.rpi_gpio import watch_stop_button

button = watch_stop_button(27, kernel_stop, loop=asyncio.get_running_loop())
...
button.close()
```

`watch_stop_button(pin, on_press, *, pull_up=True, active_state=None, bounce_s=0.05, loop=None, pin_factory=None)` calls `on_press` on each press of BCM `pin`. With `loop` the call runs on that loop, a coroutine function as a task, and otherwise on gpiozero's thread. The function never touches an output. `RpiGpioDriver.stop_button_pin()` returns a `stop_button` pin named in `pins` and unused by channels. The hub wires the button up, and the driver never calls `watch_stop_button`.

A GPIO stop button only sends a stop request, so keep a hardware e-stop that cuts power.

## Example

`openhal/drivers/rpi_gpio/examples/greenhouse-vent.hal.yaml` drives an active-low relay, a PWM fan and a vent servo, reads a door switch, declares a stop button pin, and has an interlock and a watchdog rule. `spec/examples/rpi-relay.hal.yaml` is a single relay.

## Errors and health

- Pins held by another program, a missing pin library or a non-Pi host raise `DriverError` on connect.
- Channels without a pin, two channels on one pin, non-bool inputs and outputs that aren't bool or number fail at load.
- `health()` reports disconnected if any pin was released.

## Limitations

- No analog inputs, since the Pi has no ADC. Use an ADC board through another driver.
- No I2C, SPI or one-wire.
- Software PWM jitters at high frequencies, so use GPIO 12, 13, 18 or 19 for hardware PWM.

## Hazard default and safe state

Low, since a pin drives 3.3 V at a few milliamps. Set the hazard from what the relay or transistor drives. `safe_state_support` is `file`.

On close or hub exit, gpiozero releases the pins, which usually become inputs. An active-low relay board without an input pull-up can then switch on, so fit a pull resistor that makes a released pin mean off and note the resistor in `safe_state_note`.

## Sources

- gpiozero documentation, https://gpiozero.readthedocs.io/en/stable/
- Raspberry Pi GPIO documentation, https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#gpio
- Raspberry Pi pinout, https://pinout.xyz/
- lgpio Python documentation, https://abyz.me.uk/lg/py_lgpio.html
