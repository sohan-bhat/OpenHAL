declare module "virtual:device-schema-validator" {
  import type { ValidateFunction } from "ajv";

  const validate: ValidateFunction;
  export default validate;
}
