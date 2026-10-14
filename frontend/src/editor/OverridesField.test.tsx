import Form from "@rjsf/core";
import type { RJSFSchema } from "@rjsf/utils";
import validator from "@rjsf/validator-ajv8";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { S } from "../api/client";
import { conditionDrafts } from "./drafts";
import { OverridesField } from "./OverridesField";
import type { EditorContext } from "./SectionTemplate";

const SCHEMA: RJSFSchema = {
  type: "object",
  properties: {
    overrides: { type: "object" },
  },
};

const RULES_DATA: S["RulesOut"] = {
  can_edit: true,
  dials: ["trust", "hostility"],
  moves: [
    {
      id: "clarifies_operational_detail",
      description: "Clarifies operational detail",
      default: { trust: 2 },
      deltas: { trust: 2 },
      changed: false,
      ends_session: false,
      source: "",
    },
    {
      id: "argues_principles_only",
      description: "Argues principles only",
      default: { trust: -3, hostility: 2 },
      deltas: { trust: -3, hostility: 2 },
      changed: false,
      ends_session: false,
      source: "",
    },
  ],
};

function renderOverrides(formData: any = {}, onChange = vi.fn()) {
  const context: EditorContext = {
    section: "rules",
    flags: [],
    isOther: () => false,
    confirm: () => {},
    moves: RULES_DATA.moves.map((m) => ({ id: m.id, description: m.description })),
    issues: [],
    rulesData: RULES_DATA,
  };

  return render(
    <Form
      schema={SCHEMA}
      formData={{ overrides: formData }}
      validator={validator}
      noValidate
      fields={{ overrides: OverridesField }}
      uiSchema={{ overrides: { "ui:field": "overrides" } }}
      formContext={context}
      onChange={(e) => onChange(e.formData?.overrides)}
    />,
  );
}

describe("OverridesField", () => {
  it("renders behaviour table with inherited values and descriptions", () => {
    renderOverrides();
    expect(screen.getByText("Behaviour for this scenario")).toBeInTheDocument();
    expect(screen.getByText("Clarifies operational detail")).toBeInTheDocument();
    expect(screen.getByText("Argues principles only")).toBeInTheDocument();

    const input = screen.getByRole("spinbutton", { name: "clarifies_operational_detail trust" }) as HTMLInputElement;
    expect(input.value).toBe("2");
  });

  it("changing a dial calls onChange with scenario override structure", () => {
    const onChange = vi.fn();
    renderOverrides({}, onChange);

    const input = screen.getByRole("spinbutton", { name: "clarifies_operational_detail trust" });
    fireEvent.change(input, { target: { value: "8" } });

    expect(onChange).toHaveBeenCalledWith({
      moves: {
        clarifies_operational_detail: {
          deltas: { trust: 8 },
        },
      },
    });
  });

  it("renders reset button when move is overridden and clicking resets it", () => {
    const onChange = vi.fn();
    const initialData = {
      moves: {
        clarifies_operational_detail: {
          deltas: { trust: 8 },
        },
      },
    };
    renderOverrides(initialData, onChange);

    const resetBtn = screen.getByRole("button", { name: "Reset clarifies_operational_detail to standard rules" });
    expect(resetBtn).toBeInTheDocument();

    fireEvent.click(resetBtn);
    expect(onChange).toHaveBeenCalledWith(undefined);
  });

  it("supports toggle to raw JSON and back", () => {
    renderOverrides();
    const toggleBtn = screen.getByRole("button", { name: "Edit as JSON" });
    fireEvent.click(toggleBtn);
    expect(screen.getByRole("textbox", { name: "Overrides JSON" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Back to table" })).toBeInTheDocument();
  });

  it("commits valid JSON edits live without clicking Back to table", () => {
    const onChange = vi.fn();
    renderOverrides({}, onChange);

    fireEvent.click(screen.getByRole("button", { name: "Edit as JSON" }));
    const textarea = screen.getByRole("textbox", { name: "Overrides JSON" });

    fireEvent.change(textarea, {
      target: { value: JSON.stringify({ moves: { argues_principles_only: { deltas: { trust: -8 } } } }) },
    });

    expect(onChange).toHaveBeenCalledWith({
      moves: {
        argues_principles_only: {
          deltas: { trust: -8 },
        },
      },
    });
  });

  it("blocks saving invalid JSON by registering in conditionDrafts", () => {
    const onChange = vi.fn();
    renderOverrides({}, onChange);

    fireEvent.click(screen.getByRole("button", { name: "Edit as JSON" }));
    const textarea = screen.getByRole("textbox", { name: "Overrides JSON" });

    fireEvent.change(textarea, { target: { value: "invalid json {" } });
    expect(screen.getByRole("alert")).toBeInTheDocument();

    const draft = conditionDrafts.get("root_overrides");
    expect(draft?.valid).toBe(false);

    // Clicking "Back to table" while invalid keeps JSON view
    fireEvent.click(screen.getByRole("button", { name: "Back to table" }));
    expect(screen.getByRole("textbox", { name: "Overrides JSON" })).toBeInTheDocument();

    // Fixing JSON restores valid draft
    fireEvent.change(textarea, { target: { value: "{}" } });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(conditionDrafts.get("root_overrides")).toBeUndefined();
  });

  it("changing one dial only overrides that dial and keeps other inherited dials displayed", () => {
    const onChange = vi.fn();
    // argues_principles_only has default trust: -3, hostility: 2
    renderOverrides({}, onChange);

    const trustInput = screen.getByRole("spinbutton", { name: "argues_principles_only trust" });
    const hostilityInput = screen.getByRole("spinbutton", { name: "argues_principles_only hostility" }) as HTMLInputElement;
    expect(hostilityInput.value).toBe("2");

    fireEvent.change(trustInput, { target: { value: "-8" } });
    expect(onChange).toHaveBeenCalledWith({
      moves: {
        argues_principles_only: {
          deltas: { trust: -8 },
        },
      },
    });

    // When rendered with this override, hostility remains displayed as inherited 2
    renderOverrides(
      {
        moves: {
          argues_principles_only: {
            deltas: { trust: -8 },
          },
        },
      },
      onChange,
    );
    const hostilityAfter = screen.getAllByRole("spinbutton", { name: "argues_principles_only hostility" })[0] as HTMLInputElement;
    expect(hostilityAfter.value).toBe("2");
  });
});

