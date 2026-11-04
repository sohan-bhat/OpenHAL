# 0024 Microscopes and lab equipment through framework drivers and the device library

## Context

On 2026-11-03 the owner asked for a microscope or other biology hardware in the demo video, and for drivers for that kind of equipment. The owner then widened the request to biomedical equipment and to "sicentific equipment that is genuinly useful". The owner then asked how OpenHAL would work with a device no driver knows, and pointed at the answer OpenHAL already has.

> u are independly building each driver but if openhal has not encountered a driver how would it work

The driver writer (ADR 0006, openhal/writer/) turns an unknown device into a confirmed device file through a library match, a protocol driver's own description, an Arduino sketch, a pasted manual or the user's AI, then the limits interview. The protocol drivers, such as serial, http, modbus and scpi, then run the device. A bespoke driver for one balance or one pump works against that design.

Researchers use a long tail of lab equipment. Some of it sits behind a framework that already speaks to a whole family of hardware, such as Micro-Manager for microscopes. The rest speaks a documented command set over serial or HTTP, such as Mettler Toledo's MT-SICS for balances, the New Era and Harvard Apparatus pump protocols and the Opentrons HTTP API.

## Options considered

1. A driver for each instrument family, such as a balance driver, a syringe pump driver and an Opentrons driver.
2. Framework drivers only where one library reaches a family of hardware no protocol driver can reach, and device files through the driver writer for instruments with a documented command set, with fixes to the general writer and protocol drivers where they fall short.

## Decision

Option 2.

- A new driver is written only for a framework that covers a family of hardware, such as Micro-Manager through pymmcore-plus. Each one meets the full bar, a simulator, conformance, tests, a docs page, a hardware test plan and an optional extra.
- An instrument with a documented serial or HTTP command set becomes a device file in the device library, drafted by the driver writer from the instrument's public manual, confirmed through the limits interview and run by an existing protocol driver. A test loads the file and runs the file through the kernel.
- Where the writer or a protocol driver can't handle such an instrument, the fix goes into the general code, with a test, so every similar instrument benefits.
- The `micromanager` driver is the first framework driver of this kind. One device file is one microscope as a Micro-Manager configuration file describes the microscope. Stage, focus, objective, filter, exposure, shutter and light channels map onto MMCore calls, snapshots return images the agent sees, and autofocus runs the configuration's autofocus device or an image sweep that never leaves the file's z limits.
- The micromanager simulator is pymmcore-plus's UniMMCore with Python devices in place of device adapters. The simulated camera images a real micrograph under CC BY 2.0 at the objective's magnification, defocus blurs the frame, and a focus move past the objective's working distance stalls at the slide with an error.

### The boundary

OpenHAL covers lab and research equipment only. OpenHAL has no driver, simulator or library file for clinical or patient-connected medical devices, such as infusion pumps, ventilators, patient monitors, dialysis machines or anything connected to a person for diagnosis or treatment. Those devices are regulated medical devices, and an agent controlling one is outside what OpenHAL is built and tested for. A syringe pump on a lab bench is lab equipment. The same pump connected to a patient is not, and no OpenHAL file may describe such a use.

## Consequences

- Most lab instruments arrive as library files, so the count of drivers grows slowly while the count of covered instruments grows with the library.
- A framework driver carries the framework's own dependency as an extra. pymmcore-plus pulls in pymmcore, which is LGPL-2.1 and used unmodified.
- The micromanager driver reaches the roughly 250 device adapters Micro-Manager lists, and none of them is verified on hardware yet.
- MMCore reports no stage travel, so a person sets x, y and z ranges, and the z limit toward the sample is the one that protects the objective and the slide.
- The README, the roadmap and the driver docs state the boundary, and a pull request that adds a file for a clinical or patient-connected device is closed in review.
