import type { RJSFSchema, ValidatorType } from "@rjsf/utils";
import validator, { createPrecompiledValidator, type ValidatorFunctions } from "@rjsf/validator-ajv8";
import validators from "./validators.gen";

/** The served schema's notes are written for developers (files, YAML, ids, engine internals): the labels map's hints replace them on screen.
 *  Property-name dictionaries (`properties`, `$defs`, …) may legitimately contain a key called "description": only schema-node metadata is dropped. */
function stripNotes(node: unknown): unknown {
  if (Array.isArray(node)) return node.map(stripNotes);
  if (node && typeof node === "object") {
    const DICTS = new Set(["properties", "$defs", "definitions", "patternProperties"]);
    const out: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(node)) {
      if (DICTS.has(key)) {
        const dict: Record<string, unknown> = {};
        for (const [name, sub] of Object.entries((value ?? {}) as Record<string, unknown>)) dict[name] = stripNotes(sub);
        out[key] = dict;
      } else if (key !== "description") out[key] = stripNotes(value);
    }
    return out;
  }
  return node;
}

/** The schema the form renders, from the served one. */
export function formSchemaOf(served: object): RJSFSchema {
  const copy = stripNotes(served) as RJSFSchema;
  delete copy.$schema; // rjsf's validator speaks draft-07; the server validates every save
  delete copy["x-skills-vocabulary"]; // content-dependent; the Editor reads it from the served schema
  // The builder owns conditions: stub the recursive def so rjsf never re-expands it (that was 80% of the nested edit cost).
  // The condition sites are still found through their $refs; the server validates saves with the real schema.
  copy.$defs = { ...copy.$defs, condition: { type: "object" } };
  return copy;
}

/** rjsf asks the validator which oneOf/anyOf branch some data matches. The CSP forbids ajv's runtime compiling, so the
 *  validators are compiled ahead from the backend's schema (`npm run validators`). A schema this build does not know (a
 *  dev backend ahead of the frontend) gets the runtime validator, which works where no CSP applies. */
export function validatorFor(schema: RJSFSchema): ValidatorType {
  try {
    return createPrecompiledValidator(validators as ValidatorFunctions, schema);
  } catch {
    return validator;
  }
}
