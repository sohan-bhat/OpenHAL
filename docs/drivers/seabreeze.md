# seabreeze driver

The `seabreeze` driver reads Ocean Insight and Ocean Optics spectrometers through python-seabreeze, the open source Python layer over Ocean's own SeaBreeze library. One device file is one spectrometer. A scan becomes readings an agent can use, such as the spectrum as a chart, the peak, the counts at a wavelength, and absorbance against a stored dark and reference.

| | |
|---|---|
| Driver name | `seabreeze` |
| Library | python-seabreeze 2.11 (MIT) |
| Extra | `uv tool install --compile-bytecode "halkit[seabreeze] @ git+https://github.com/sohan-bhat/OpenHAL"` |
| Hazard default | low |
| Conformance | full |
| Safe state | none. A spectrometer only measures |
| Self-describe | yes, from the spectrometer's wavelengths and integration limits |

The driver is for lab and research spectrometers. OpenHAL has no driver for clinical or patient-connected medical devices, see [ADR 0024](../adr/0024-microscopy-and-lab-drivers.md).

## What it supports

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

## How it works

- Every reading comes from a scan, the counts of each pixel for one integration time, averaged over `average` scans. Readings within `scan_age` of a scan share that scan, so reading the peak and the spectrum together costs one scan.
- seabreeze sets the integration time and reads no integration time back, so `integration_time` reads the value the driver last set, and unknown before the first write.
- A new integration time clears the stored dark and reference, because counts from another integration time don't match the new scans.
- For absorbance, block the light and run `store_dark`, put the blank in the light path and run `store_reference`, then put the sample in and read. Without both, an absorbance or transmittance read fails with the step to take.
- The chart's area takes the color of each wavelength from 380 to 750 nm, and the counts axis runs to the detector's maximum, so a saturated scan reaches the top. Numbers come from the reading channels, not the chart.
- `discover()` lists spectrometers through seabreeze's `list_devices`, which reads USB descriptors and opens no spectrometer.

## The simulated spectrometer

`seabreeze: sim` connects to a simulated USB2000+, 2048 pixels from 340 to 1025 nm with a 16 bit detector, behind the same `Spectrometer` methods the driver calls on hardware. The light path is a 2900 K halogen lamp through a cuvette of dye with one absorbance band at 520 nm. Counts grow with the integration time up to 65535, and each scan carries dark counts, shot noise and read noise. `sim:<name>` connects to a separate simulated spectrometer.

## Setup

1. Install the extra.
2. On Linux, install the udev rules with `uv run seabreeze_os_setup`, so a user can open the spectrometer. Close OceanView, which holds the spectrometer.
3. Start from [absorbance-spectrometer.hal.yaml](../../openhal/drivers/seabreeze/examples/absorbance-spectrometer.hal.yaml), or call `describe` for a draft with your spectrometer's limits.
4. Run `openhal file validate`, then confirm the limits.

## Parameters

| Key | Default | Meaning |
|---|---|---|
| `spectrometer` | `auto` | A serial number, `auto` for the first one found, or `sim` and `sim:<name>` |
| `backend` | `cseabreeze` | `cseabreeze`, which brings its own USB code, or `pyseabreeze`, which needs pyusb and libusb |
| `timeout` | `5 s` | The longest wait for a scan, every averaged scan included. At most 9 s |
| `scan_age` | `500 ms` | Readings within this long of a scan share that scan |
| `average` | 1 | Scans averaged into each reading, 1 to 100 |
| `dark_correction` | false | Subtract the detector's electric dark pixels in each scan |
| `nonlinearity_correction` | false | Apply the spectrometer's stored nonlinearity correction |

## Known limitations

- The driver doesn't use external triggers, the spectrometer's light source or shutter features, or its thermoelectric cooler.
- The integration time and the number of averaged scans must fit the timeout, so long exposures need fewer averaged scans.
- The stored dark and reference live in the hub's memory and are gone after a restart.

## Hazard defaults

The default hazard is `low`, because a spectrometer only measures. A light source in the same setup, such as a laser, is a separate device with its own file and its own hazard.

## Sources

- python-seabreeze documentation, https://python-seabreeze.readthedocs.io/en/latest/
- python-seabreeze source, the Spectrometer class and its device list, https://github.com/ap--/python-seabreeze (MIT, used as a library)
- Ocean SeaBreeze, https://www.oceanoptics.com/software/resources/seabreeze-software-development-kit/
