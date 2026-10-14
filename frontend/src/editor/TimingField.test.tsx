import Form from "@rjsf/core";
import type { RJSFSchema } from "@rjsf/utils";
import validator from "@rjsf/validator-ajv8";
import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import type { S } from "../api/client";
import type { EditorContext } from "./SectionTemplate";
import { TimingField, ordered, parseWarnings, shares, tidy, type Timing } from "./TimingField";

const SCHEMA: RJSFSchema = { type: "object", properties: { timing: { type: "object" } } };

const DEFAULTS: S["TimingDefaultsOut"] = {
  phases: [
    { id: "opening", label: "Opening", hint: "Formal.", instruction: "OPENING PHASE: be formal.", allow_injects: true },
    { id: "exploration", label: "Exploration", hint: "Talk.", instruction: "EXPLORATION PHASE: talk.", allow_injects: true },
    { id: "closing", label: "Closing", hint: "Wrap up.", instruction: "CLOSING PHASE: close.", allow_injects: true },
  ],
  warnings: [5, 1],
  silence_after_seconds: 90,
};

const CONTEXT: EditorContext = {
  section: "basics",
  flags: [],
  isOther: () => false,
  confirm: () => {},
  moves: [],
  issues: [],
  timingDefaults: DEFAULTS,
};

/** The field inside a real rjsf form, keeping its own value like the editor does; `seen` records every change. */
function renderTiming(initial: Timing | undefined, seen: (Timing | undefined)[] = []) {
  function Harness() {
    const [value, setValue] = useState<any>(initial);
    return (
      <Form
        schema={SCHEMA}
        formData={{ timing: value } as any}
        validator={validator}
        noValidate
        fields={{ timing: TimingField } as any}
        uiSchema={{ timing: { "ui:field": "timing" }, "ui:submitButtonOptions": { norender: true } }}
        formContext={CONTEXT}
        onChange={(event) => {
          seen.push(event.formData?.timing);
          setValue(event.formData?.timing);
        }}
      />
    );
  }
  render(<Harness />);
  return seen;
}

const last = (seen: (Timing | undefined)[]) => seen[seen.length - 1];

describe("timing helpers", () => {
  it("tidy leaves out everything empty, and everything when nothing is set", () => {
    expect(tidy({})).toBeUndefined();
    expect(tidy({ phases: [], warnings: [], on_timeout: "guide", silence: {} })).toBeUndefined();
    expect(tidy({ on_timeout: "trainer", silence: { line: "", after_seconds: 45 } })).toEqual({
      on_timeout: "trainer",
      silence: { after_seconds: 45 },
    });
  });

  it("ordered gives every stage but the last a rising end turn, and the last none", () => {
    expect(ordered([{ id: "a", instruction: "x" }, { id: "b", instruction: "y", until_turn: 2 }, { id: "c", instruction: "z", until_turn: 9 }])).toEqual([
      { id: "a", instruction: "x", until_turn: 3 },
      { id: "b", instruction: "y", until_turn: 6 }, // 2 was not later than 3
      { id: "c", instruction: "z" },
    ]);
  });

  it("parses warning minutes, dropping what is not a positive whole number", () => {
    expect(parseWarnings("1, 5; 5 abc 0 -2")).toEqual([5, 1]);
    expect(parseWarnings("")).toEqual([]);
  });

  it("sizes the bar by each stage's turns, the last as long as the others on average", () => {
    expect(shares([{ id: "a", instruction: "", until_turn: 2 }, { id: "b", instruction: "", until_turn: 8 }, { id: "c", instruction: "" }])).toEqual([2, 6, 4]);
  });
});

describe("TimingField", () => {
  it("offers the built-in stages as a starting point when the scenario has none", () => {
    const seen = renderTiming(undefined);
    expect(screen.getByText(/No stages of its own/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Start from the built-in stages" }));
    const stages = last(seen)?.phases ?? [];
    expect(stages.map((s) => [s.id, s.until_turn])).toEqual([["opening", 2], ["exploration", 7], ["closing", undefined]]);
    expect(stages[0].instruction).toBe("OPENING PHASE: be formal.");
    expect(screen.getByRole("list", { name: "Stages on a timeline" })).toHaveTextContent("Exploration");
  });

  it("keeps the stages ordered when one is added or removed", () => {
    const seen = renderTiming({ phases: [{ id: "a", instruction: "x", until_turn: 2 }, { id: "b", instruction: "y" }] });
    fireEvent.click(screen.getByRole("button", { name: "+ Add stage" }));
    expect(last(seen)?.phases).toEqual([
      { id: "a", instruction: "x", until_turn: 2 },
      { id: "b", instruction: "y", until_turn: 5 }, // no longer the last: it needs an end
      { id: "stage_3", instruction: "" },
    ]);
    fireEvent.click(screen.getByRole("button", { name: "Remove stage 3" }));
    expect(last(seen)?.phases).toEqual([{ id: "a", instruction: "x", until_turn: 2 }, { id: "b", instruction: "y" }]); // b is last again
    fireEvent.click(screen.getByRole("button", { name: "Back to the built-in stages" }));
    expect(last(seen)).toBeUndefined();
  });

  it("edits a stage's words, end turn and whether twists are allowed", () => {
    const seen = renderTiming({ phases: [{ id: "a", instruction: "x", until_turn: 2 }, { id: "b", instruction: "y" }] });
    fireEvent.change(screen.getByLabelText("Stage 1 label"), { target: { value: "Cold start" } });
    fireEvent.change(screen.getByLabelText("Stage 1 instruction"), { target: { value: "Say little." } });
    fireEvent.change(screen.getByLabelText("Stage 1 ends after turn"), { target: { value: "4" } });
    fireEvent.click(screen.getByLabelText("Stage 1 allows twists"));
    expect(last(seen)?.phases?.[0]).toEqual({ id: "a", label: "Cold start", instruction: "Say little.", until_turn: 4, allow_injects: false });
    expect(screen.getByLabelText("Stage 2 ends after turn")).toBeDisabled(); // the last stage runs to the end
    fireEvent.click(screen.getByLabelText("Stage 1 allows twists"));
    expect(last(seen)?.phases?.[0].allow_injects).toBeUndefined(); // allowed is the default and is not stored
  });

  it("sets the warning times, and removes them when cleared", () => {
    const seen = renderTiming(undefined);
    fireEvent.change(screen.getByLabelText("Warning minutes"), { target: { value: "2, 10" } });
    expect(last(seen)).toEqual({ warnings: [10, 2] });
    fireEvent.change(screen.getByLabelText("Warning minutes"), { target: { value: "" } });
    expect(last(seen)).toBeUndefined();
  });

  it("chooses what happens when time runs out; the default is not stored", () => {
    const seen = renderTiming(undefined);
    expect(screen.getByRole("radio", { name: "Nothing ends" })).toBeChecked();
    fireEvent.click(screen.getByRole("radio", { name: "The trainer decides" }));
    expect(last(seen)).toEqual({ on_timeout: "trainer" });
    expect(screen.getByRole("radio", { name: "The trainer decides" })).toBeChecked();
    fireEvent.click(screen.getByRole("radio", { name: "Nothing ends" }));
    expect(last(seen)).toBeUndefined();
  });

  it("sets the silence rules and stores only what is filled in", () => {
    const seen = renderTiming(undefined);
    fireEvent.change(screen.getByLabelText("Silence after seconds"), { target: { value: "45" } });
    fireEvent.change(screen.getByLabelText("Silence line"), { target: { value: "Was there anything else?" } });
    fireEvent.change(screen.getByLabelText("Silence penalty"), { target: { value: "12" } });
    expect(last(seen)).toEqual({ silence: { after_seconds: 45, line: "Was there anything else?", penalty: 12 } });
    fireEvent.change(screen.getByLabelText("Silence after seconds"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Silence line"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Silence penalty"), { target: { value: "" } });
    expect(last(seen)).toBeUndefined();
  });
});
