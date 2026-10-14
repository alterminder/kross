import Form from "@rjsf/core";
import type { RJSFSchema } from "@rjsf/utils";
import validator from "@rjsf/validator-ajv8";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ButtonTemplates } from "./buttons";

const SCHEMA: RJSFSchema = {
  type: "object",
  properties: { names: { type: "array", items: { type: "string" } } },
};

const NESTED: RJSFSchema = {
  type: "object",
  properties: {
    counterparts: {
      type: "array",
      items: {
        type: "object",
        properties: { hidden_interests: { type: "array", items: { type: "object", properties: { text: { type: "string" } } } } },
      },
    },
  },
};

describe("ButtonTemplates", () => {
  it("renders array buttons with visible text and accessible names, and no glyphicons", () => {
    const { container } = render(<Form schema={SCHEMA} formData={{ names: ["a", "b"] }} validator={validator} templates={{ ButtonTemplates }} />);
    const up = screen.getByRole("button", { name: "Move name 1 up" });
    expect(up).toHaveTextContent("↑");
    expect(up).toBeDisabled(); // the first item cannot move up
    expect(screen.getByRole("button", { name: "Move name 1 down" })).toHaveTextContent("↓");
    expect(screen.getByRole("button", { name: "Move name 2 down" })).toHaveTextContent("↓");
    expect(screen.getByRole("button", { name: "Remove name 1" })).toHaveTextContent("×");
    const add = screen.getByRole("button", { name: "+ Add name" });
    expect(add).toHaveTextContent("+ Add name");
    expect(add).toBeEnabled();
    expect(container.querySelector(".glyphicon")).toBeNull();
  });

  it("names nested lists in the button, not just the item number", () => {
    render(
      <Form
        schema={NESTED}
        formData={{ counterparts: [{ hidden_interests: [{ text: "a" }, { text: "b" }] }] }}
        validator={validator}
        templates={{ ButtonTemplates }}
      />,
    );
    expect(screen.getByRole("button", { name: "Remove hidden interest 2" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Move hidden interest 2 down" })).toBeInTheDocument();
  });
});
