// A Vite plugin that compiles spec/schema/device-file.schema.json into a standalone validator at
// build time. The playground imports `virtual:device-schema-validator` and ships only the compiled
// checks, not the schema compiler. The schema file is read from the repository on every build,
// so it is never copied by hand.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";
import standaloneCode from "ajv/dist/standalone/index.js";

const ID = "virtual:device-schema-validator";
const RESOLVED = `\0${ID}`;
export const SCHEMA_PATH = fileURLToPath(new URL("../../../spec/schema/device-file.schema.json", import.meta.url));

export function deviceSchemaValidator() {
  return {
    name: "openhal-device-schema-validator",
    resolveId(source) {
      return source === ID ? RESOLVED : null;
    },
    load(id) {
      if (id !== RESOLVED) return null;
      this.addWatchFile(SCHEMA_PATH);
      const schema = JSON.parse(readFileSync(SCHEMA_PATH, "utf8"));
      const ajv = new Ajv2020({ allErrors: true, strict: false, validateFormats: false, code: { source: true, esm: true } });
      // The one runtime helper ajv needs counts characters by code point. Inline it so the module
      // stays plain ESM.
      return standaloneCode(ajv, ajv.compile(schema)).replaceAll(
        'require("ajv/dist/runtime/ucs2length").default',
        "((text) => [...text].length)",
      );
    },
  };
}
