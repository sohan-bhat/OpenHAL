# seabreeze driver

The `seabreeze` driver reads Ocean Insight and Ocean Optics spectrometers through python-seabreeze 2.11, the open source Python layer over Ocean's SeaBreeze library. One device file is one spectrometer, and each scan becomes readings such as the spectrum as a chart, the peak, the counts at a wavelength, and absorbance against a stored dark and reference. `describe` drafts a file from the spectrometer's wavelengths and integration limits.

The driver is for lab and research spectrometers. OpenHAL has no driver for clinical or patient-connected medical devices, see [ADR 0024](../adr/0024-microscopy-and-lab-drivers.md).

## Supports

| Name | Kind | Map | What the driver reads |
|---|---|---|---|
| `spectrum` | read, image | `{ spectrum: plot }` | the scan as a PNG chart, wavelength against counts |
| `peak_wavelength` | read, length | `{ peak: wavelength }` | the wavelength of the highest pixel |
| `peak_intensity` | read, dimensionless | `{ peak: intensity }` | the highest pixel's counts |
| any name | read, dimensionless | `{ wavelength: 532 nm }` | the counts at one wavelength, averaged over 5 pixels |
| any name | read, dimensionless | `{ band: [500 nm, 550 nm] }` | the mean counts over a band |
| any name | read, dimensionless | `{ absorbance: 520 nm }` | -log10 of the sample over the reference, both less the dark |
| any name | read, percent | `{ transmittance: 520 nm }` | the sample over the reference, both less the dark |
| `saturated` | read, bool | `{ status: saturated }` | true when any pixel reaches the detector's maximum |
| `integration_time` | write, time | `{ setting: integration_time }` | `integration_time_micros` |
| `store_dark`, `store_reference`, `clear_references` | action | `{ command: store_dark }` | keep the next scan, or forget both |

## Behavior

- Every reading comes from a scan averaged over `average` scans, and readings within `scan_age` share one scan.
- `integration_time` reads the value last set, or unknown before the first write, since seabreeze reads no integration time back.
- A new integration time clears the stored dark and reference.
- For absorbance, block the light and run `store_dark`, put the blank in and run `store_reference`, then read the sample. Without both, absorbance and transmittance reads fail with the missing step.
- The chart colors each wavelength from 380 to 750 nm, and the counts axis runs to the detector maximum, so a saturated scan reaches the top. Numbers come from the reading channels.
- `discover()` lists spectrometers from USB descriptors without opening any.

## The simulated spectrometer

`seabreeze: sim` is a simulated USB2000+, 2048 pixels from 340 to 1025 nm with a 16 bit detector, behind the same `Spectrometer` methods as hardware. A 2900 K halogen lamp shines through a cuvette of dye with one absorbance band at 520 nm. Counts grow with integration time up to 65535, with dark counts, shot noise and read noise. `sim:<name>` makes a separate simulated spectrometer.

## Setup

1. Install with `uv tool install --compile-bytecode "halkit[seabreeze] @ git+https://github.com/sohan-bhat/OpenHAL"`.
2. On Linux, install the udev rules with `uv run seabreeze_os_setup`, and close OceanView, which holds the spectrometer.
3. Start from [absorbance-spectrometer.hal.yaml](../../openhal/drivers/seabreeze/examples/absorbance-spectrometer.hal.yaml) or `describe`.

| Key | Default | Meaning |
|---|---|---|
| `spectrometer` | `auto` | Serial number, `auto` for the first found, or `sim` and `sim:<name>` |
| `backend` | `cseabreeze` | `cseabreeze` with built-in USB code, or `pyseabreeze`, which needs pyusb and libusb |
| `timeout` | `5 s` | Longest scan, every averaged scan included, at most 9 s |
| `scan_age` | `500 ms` | Scan reuse window |
| `average` | 1 | Scans averaged per reading, 1 to 100 |
| `dark_correction` | false | Subtract the detector's electric dark pixels |
| `nonlinearity_correction` | false | Apply the stored nonlinearity correction |

## Known limitations

- No external triggers, light source or shutter features, or thermoelectric cooler.
- Integration time times averaged scans must fit `timeout`.
- The stored dark and reference are lost on a hub restart.

## Hazard defaults

`low`, with no safe state, since a spectrometer only measures. A light source such as a laser needs a separate device file with a separate hazard.

## Sources

- python-seabreeze documentation, https://python-seabreeze.readthedocs.io/en/latest/
- python-seabreeze source, the Spectrometer class and device list, MIT and used as a library, https://github.com/ap--/python-seabreeze
- Ocean SeaBreeze, https://www.oceanoptics.com/software/resources/seabreeze-software-development-kit/
