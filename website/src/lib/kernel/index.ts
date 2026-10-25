/**
 * The in-browser kernel. A demo-only TypeScript port of openhal/kernel and openhal/spec, checked
 * against the Python kernel by tests/website/test_kernel_parity.py and the vitest parity suite.
 */

export * from "./kernel";
export { effectiveLimits, normalize, checkRate } from "./checks";
export {
  type DeviceFile,
  type WriteChannel,
  type ReadChannel,
  type ActionSpec,
  DeviceFileError,
  loadDeviceFile,
  deviceId,
  effectiveHazard,
  channelUnit,
  unconfirmed,
  writable,
  limitsSha256,
} from "./model";
export { UnitError, formatQuantity, parseQuantity, convert } from "./units";
export { formatG, pyFloatRepr } from "./pyformat";
