import { describe, expect, it } from "vitest";
import { conditionUiSchema } from "./conditions";
import scenarioSchema from "./fixtures/scenario-schema.json";

const CONDITION = { $ref: "#/$defs/condition" };

const SCHEMA = {
  $defs: {
    condition: {
      type: "object",
      properties: {
        trust_gte: { type: "integer" },
        any: { type: "array", items: { $ref: "#/$defs/condition" } },
        all: { type: "array", items: { $ref: "#/$defs/condition" } },
      },
    },
  },
  type: "object",
  properties: {
    when: CONDITION,
    list: {
      type: "array",
      items: {
        type: "object",
        properties: { reveal_when: CONDITION, note: { type: "string" } },
      },
    },
    auto: { type: "object", properties: { when: CONDITION, label: { type: "string" } } },
    plain: { type: "string" },
  },
};

describe("conditionUiSchema", () => {
  it("marks every condition site and terminates on the recursive def", () => {
    expect(conditionUiSchema(SCHEMA)).toEqual({
      when: { "ui:field": "condition" },
      list: { items: { reveal_when: { "ui:field": "condition" } } },
      auto: { when: { "ui:field": "condition" } },
    });
  });

  it("finds the same sites when the condition def is stubbed for rendering, as Editor.tsx's formSchema does", () => {
    const stubbed = { ...scenarioSchema, $defs: { ...scenarioSchema.$defs, condition: { type: "object" } } };
    expect(conditionUiSchema(stubbed)).toEqual(conditionUiSchema(scenarioSchema));
  });

  it("finds the four condition sites of the real scenario schema", () => {
    expect(conditionUiSchema(scenarioSchema)).toEqual({
      counterparts: { items: { hidden_interests: { items: { reveal_when: { "ui:field": "condition" } } } } },
      triggers: { items: { when: { "ui:field": "condition" } } },
      injections: { items: { auto: { when: { "ui:field": "condition" } } } },
      outcomes: { items: { when: { "ui:field": "condition" } } },
    });
  });
});
