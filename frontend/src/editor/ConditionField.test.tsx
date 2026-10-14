import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { ConditionField, type BuilderContext } from "./ConditionField";
import { conditionDrafts } from "./drafts";

const PATH = ["when"];
const MOVES = [
  { id: "identifies_interest", description: "Names an interest of the counterpart" },
  { id: "asks_goal", description: "Asks what the trainee wants" },
];

/** Renders the field with rjsf's echo: onChange is recorded and comes back as the new form data. */
function mount(formData: unknown, ctx: Partial<BuilderContext> = {}) {
  const onChange = vi.fn();
  function Harness() {
    const [value, setValue] = useState(formData);
    return (
      <ConditionField
        schema={{ type: "object", title: "Reveal when" }}
        formData={value}
        onChange={(next, path) => {
          onChange(next, path);
          setValue(next as Record<string, unknown>);
        }}
        fieldPathId={{ $id: "root_when", path: PATH }}
        formContext={{ moves: MOVES, issues: ["access"], ...ctx }}
      />
    );
  }
  render(<Harness />);
  return { onChange };
}

describe("ConditionField rows", () => {
  it("shows an any group's members as labelled rows", () => {
    mount({ any: [{ move: "identifies_interest" }, { trust_gte: 55 }] });
    const group = screen.getByRole("group", { name: "Any of these" });
    expect(within(group).getByText("Move made: Identifies interest")).toBeInTheDocument();
    expect(within(group).getByText("Trust at least 55")).toBeInTheDocument();
  });

  it("commits a changed threshold with the whole condition, keeping the siblings", async () => {
    const { onChange } = mount({ any: [{ move: "identifies_interest" }, { trust_gte: 55 }] });
    const number = screen.getByRole("spinbutton");
    await userEvent.clear(number);
    await userEvent.type(number, "60");
    expect(onChange).toHaveBeenLastCalledWith({ any: [{ move: "identifies_interest" }, { trust_gte: 60 }] }, PATH);
  });

  it("shows goal_requested false as No and round-trips it", async () => {
    const { onChange } = mount({ goal_requested: false });
    expect(screen.getByText("Asked for the goal: No")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByRole("combobox"), "yes");
    await userEvent.selectOptions(screen.getByRole("combobox"), "no");
    expect(onChange).toHaveBeenLastCalledWith({ goal_requested: false }, PATH);
  });

  it("keeps an unknown move id and round-trips it", async () => {
    const { onChange } = mount({ move: "made_up" });
    expect(screen.getByText("Move made: made_up (unknown move)")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByRole("combobox"), "identifies_interest");
    await userEvent.selectOptions(screen.getByRole("combobox"), "made_up");
    expect(onChange).toHaveBeenLastCalledWith({ move: "made_up" }, PATH);
  });

  it("shows an unsupported key as a row and keeps it while another row changes", async () => {
    const { onChange } = mount({ mystery: 1, trust_gte: 55 });
    expect(screen.getByText("Unsupported test mystery = 1")).toBeInTheDocument();
    await userEvent.clear(screen.getByRole("spinbutton"));
    await userEvent.type(screen.getByRole("spinbutton"), "60");
    expect(onChange).toHaveBeenLastCalledWith({ mystery: 1, trust_gte: 60 }, PATH);
  });

  it("shows the object's rows under an All of these heading, keeping the key order", () => {
    mount({ trust_gte: 40, turn_lte: 5 });
    const group = screen.getByRole("group", { name: "All of these" });
    expect(within(group).getByRole("group", { name: "Trust at least 40" })).toBeInTheDocument();
    expect(within(group).getByRole("group", { name: "Turn at most 5" })).toBeInTheDocument();
    const trust = screen.getByText("Trust at least 40");
    const turn = screen.getByText("Turn at most 5");
    expect(trust.compareDocumentPosition(turn) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("shows proposal_reaches as three selects", () => {
    mount({ proposal_reaches: { issue: "access", side: "own", line: "red_line" } });
    expect(screen.getAllByRole("combobox")).toHaveLength(3);
  });
});

describe("ConditionField adding, removing and drafts", () => {
  const addMenu = () => screen.getByRole("button", { name: "Add test" }).parentElement!;

  it("offers only the test kinds the object does not already have", async () => {
    mount({ move: "identifies_interest" });
    await userEvent.click(screen.getByRole("button", { name: "Add test" }));
    expect(within(addMenu()).queryByRole("button", { name: "Move made" })).toBeNull();
    expect(within(addMenu()).getByRole("button", { name: "Trust at least" })).toBeInTheDocument();
    expect(within(addMenu()).getByRole("button", { name: "Proposal reaches" })).toBeInTheDocument();
  });

  it("adds a blank row as an invalid draft and commits it once filled", async () => {
    const { onChange } = mount({});
    await userEvent.click(screen.getByRole("button", { name: "Add test" }));
    await userEvent.click(within(addMenu()).getByRole("button", { name: "Trust at least" }));
    expect(onChange).not.toHaveBeenCalled();
    expect(conditionDrafts.get("root_when")?.valid).toBe(false);
    await userEvent.type(screen.getByRole("spinbutton"), "55");
    expect(onChange).toHaveBeenLastCalledWith({ trust_gte: 55 }, PATH);
    expect(conditionDrafts.get("root_when")?.valid).toBe(true);
  });

  it("keeps a cleared number as an invalid draft and never commits 0", async () => {
    const { onChange } = mount({ trust_gte: 55 });
    await userEvent.clear(screen.getByRole("spinbutton"));
    expect(onChange).not.toHaveBeenCalled();
    expect(conditionDrafts.get("root_when")?.valid).toBe(false);
    expect(screen.getByRole("spinbutton")).toHaveValue(null);
  });

  it("adds an any group only after its first member is complete", async () => {
    const { onChange } = mount({});
    await userEvent.click(screen.getByRole("button", { name: "Add 'any of' group" }));
    expect(onChange).not.toHaveBeenCalled();
    expect(conditionDrafts.get("root_when")?.valid).toBe(false);
    const group = screen.getByRole("group", { name: "Any of these" });
    await userEvent.click(within(group).getByRole("button", { name: "Add test" }));
    await userEvent.click(within(group).getByRole("button", { name: "Trust at least" }));
    expect(onChange).not.toHaveBeenCalled();
    await userEvent.type(screen.getByRole("spinbutton"), "55");
    expect(onChange).toHaveBeenLastCalledWith({ any: [{ trust_gte: 55 }] }, PATH);
    expect(conditionDrafts.get("root_when")?.valid).toBe(true);
  });

  it("removes exactly the named key and moves focus to the next row", async () => {
    const { onChange } = mount({ trust_gte: 55, turn_lte: 5 });
    await userEvent.click(screen.getByRole("button", { name: "Remove 'Trust at least 55'" }));
    expect(onChange).toHaveBeenLastCalledWith({ turn_lte: 5 }, PATH);
    expect(screen.getByRole("spinbutton")).toHaveFocus();
  });

  it("moves focus to the Add button when the removed row was the last", async () => {
    const { onChange } = mount({ trust_gte: 55 });
    await userEvent.click(screen.getByRole("button", { name: "Remove 'Trust at least 55'" }));
    expect(onChange).toHaveBeenLastCalledWith(undefined, PATH);
    expect(screen.getByText("No condition (never fires)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add test" })).toHaveFocus();
  });

  it("keeps the value through Edit as JSON and back", async () => {
    mount({ trust_gte: 55, mystery: 1 });
    await userEvent.click(screen.getByRole("button", { name: "Edit as JSON" }));
    expect(screen.getByRole("textbox")).toHaveValue('{\n  "trust_gte": 55,\n  "mystery": 1\n}');
    await userEvent.click(screen.getByRole("button", { name: "Back to the rows" }));
    expect(screen.getByText("Trust at least 55")).toBeInTheDocument();
    expect(screen.getByText("Unsupported test mystery = 1")).toBeInTheDocument();
  });

  it("keeps invalid JSON as an incomplete draft", async () => {
    const { onChange } = mount({ trust_gte: 55 });
    await userEvent.click(screen.getByRole("button", { name: "Edit as JSON" }));
    const box = screen.getByRole("textbox");
    await userEvent.clear(box);
    const sent = onChange.mock.calls.length;
    await userEvent.paste("{");
    expect(screen.getByText(/Not valid JSON/)).toBeInTheDocument();
    expect(onChange.mock.calls.length).toBe(sent);
    expect(conditionDrafts.get("root_when")?.valid).toBe(false);
  });

  it("keeps an unknown move id while another test is added", async () => {
    const { onChange } = mount({ move: "made_up" });
    await userEvent.click(screen.getByRole("button", { name: "Add test" }));
    await userEvent.click(within(addMenu()).getByRole("button", { name: "Trust at least" }));
    await userEvent.type(screen.getByRole("spinbutton"), "55");
    expect(onChange).toHaveBeenLastCalledWith({ move: "made_up", trust_gte: 55 }, PATH);
  });
});

describe("ConditionField removal writes absence, never {}", () => {
  it("removing the only move of the only group member drops the whole condition", async () => {
    const { onChange } = mount({ any: [{ move: "identifies_interest" }] });
    await userEvent.click(screen.getByRole("button", { name: "Remove 'Move made: Identifies interest'" }));
    expect(onChange).toHaveBeenLastCalledWith(undefined, PATH);
    expect(conditionDrafts.get("root_when")?.valid).toBe(true);
  });

  it("removing the inner move of a nested all leaves the sibling member intact", async () => {
    const { onChange } = mount({ any: [{ all: [{ move: "identifies_interest" }] }, { move: "asks_goal" }] });
    await userEvent.click(screen.getByRole("button", { name: "Remove 'Move made: Identifies interest'" }));
    expect(onChange).toHaveBeenLastCalledWith({ any: [{ move: "asks_goal" }] }, PATH);
    expect(conditionDrafts.get("root_when")?.valid).toBe(true);
  });
});

describe("ConditionField JSON mode and drafts", () => {
  it("refuses 'Back to the rows' while the JSON box holds an invalid draft, then switches once it parses", async () => {
    const { onChange } = mount({ trust_gte: 55 });
    await userEvent.click(screen.getByRole("button", { name: "Edit as JSON" }));
    const box = screen.getByRole("textbox");
    await userEvent.clear(box);
    await userEvent.paste('{"trust_gte": 60, "move": ');
    const sent = onChange.mock.calls.length;
    await userEvent.click(screen.getByRole("button", { name: "Back to the rows" }));
    expect(await screen.findByText("Fix the condition marked in red before checking or saving")).toBeInTheDocument();
    expect(screen.getByRole("textbox")).toBe(box); // the box is still open: the draft is not thrown away
    expect(box).toHaveFocus();
    expect(onChange.mock.calls.length).toBe(sent);
    await userEvent.clear(box);
    await userEvent.paste('{"trust_gte": 60}');
    await userEvent.click(screen.getByRole("button", { name: "Back to the rows" }));
    expect(screen.getByText("Trust at least 60")).toBeInTheDocument();
  });
});

describe("ConditionField row errors", () => {
  it("links a message to an invalid number", async () => {
    mount({ trust_gte: 55 });
    await userEvent.clear(screen.getByRole("spinbutton"));
    expect(screen.getByText("Enter a number from 0 to 100")).toBeInTheDocument();
    expect(screen.getByRole("spinbutton")).toHaveAccessibleDescription("Enter a number from 0 to 100");
  });

  it("links a message to a blank select", async () => {
    mount({});
    await userEvent.click(screen.getByRole("button", { name: "Add test" }));
    await userEvent.click(screen.getByRole("button", { name: "Move made" }));
    expect(screen.getByText("Choose a move")).toBeInTheDocument();
    expect(screen.getByRole("combobox")).toHaveAccessibleDescription("Choose a move");
  });
});

describe("ConditionField focus after removal", () => {
  it("moves focus to the next member when the removed test was a member's only one", async () => {
    mount({ any: [{ move: "identifies_interest" }, { trust_gte: 5 }] });
    await userEvent.click(screen.getByRole("button", { name: "Remove 'Move made: Identifies interest'" }));
    expect(screen.getByRole("combobox", { name: "Trust at least 5: dial" })).toHaveFocus(); // the next member's first control
  });

  it("focuses the Remove button when the next row is an unsupported test", async () => {
    mount({ trust_gte: 5, mystery: 1 });
    await userEvent.click(screen.getByRole("button", { name: "Remove 'Trust at least 5'" }));
    expect(screen.getByRole("button", { name: "Remove 'Unsupported test mystery = 1'" })).toHaveFocus();
  });

  it("falls back to the Add button when the removal empties the whole condition", async () => {
    mount({ any: [{ move: "identifies_interest" }] });
    await userEvent.click(screen.getByRole("button", { name: "Remove 'Move made: Identifies interest'" }));
    expect(screen.getByRole("button", { name: "Add test" })).toHaveFocus();
  });
});

describe("ConditionField legends", () => {
  function mountAt(name: string, path: (string | number)[]) {
    render(
      <ConditionField
        schema={{ type: "object" }}
        formData={{ trust_gte: 3 }}
        onChange={() => {}}
        fieldPathId={{ $id: `root_${path.join("_")}`, path }}
        name={name}
        formContext={{ moves: MOVES, issues: [] }}
      />,
    );
  }

  it("humanises the field name into the legend, with the auto site spelled out", () => {
    mountAt("reveal_when", ["counterparts", 0, "hidden_interests", 0, "reveal_when"]);
    expect(screen.getByRole("group", { name: "Reveal when" })).toBeInTheDocument();
    mountAt("when", ["triggers", 0, "when"]);
    expect(screen.getByRole("group", { name: "When" })).toBeInTheDocument();
    mountAt("when", ["injections", 0, "auto", "when"]);
    expect(screen.getByRole("group", { name: "Auto-fire when" })).toBeInTheDocument();
  });

  it("keeps a plain hint below the legend", () => {
    mountAt("when", ["triggers", 0, "when"]);
    expect(screen.getByText("Every test here must hold for this to apply.")).toBeInTheDocument();
  });
});

describe("ConditionField empty texts", () => {
  function mountAt(value: unknown, path: (string | number)[], name: string) {
    render(
      <ConditionField
        schema={{ type: "object" }}
        formData={value}
        onChange={() => {}}
        fieldPathId={{ $id: `root_${path.join("_")}`, path }}
        name={name}
        formContext={{ moves: MOVES, issues: [] }}
      />,
    );
  }

  it("reads the engine's meaning per site when the condition is absent or empty", () => {
    const reveal = ["counterparts", 0, "hidden_interests", 0, "reveal_when"];
    const auto = ["injections", 0, "auto", "when"];
    mountAt(undefined, reveal, "reveal_when");
    expect(screen.getByText("Default reveal rule")).toBeInTheDocument();
    mountAt({}, reveal, "reveal_when");
    expect(screen.getAllByText("Default reveal rule")).toHaveLength(2); // absent and {} both read the same
    mountAt(undefined, auto, "when");
    expect(screen.getByText("Only at the turn above, if set")).toBeInTheDocument();
    mountAt({}, auto, "when");
    expect(screen.getAllByText("Only at the turn above, if set")).toHaveLength(2);
    mountAt(undefined, ["triggers", 0, "when"], "when");
    expect(screen.getAllByText("Missing: add a test").length).toBeGreaterThanOrEqual(1);
    mountAt({}, ["triggers", 0, "when"], "when");
    expect(screen.getAllByText("Always").length).toBeGreaterThanOrEqual(1); // a trigger with no tests fires always
    mountAt(undefined, ["outcomes", 0, "when"], "when");
    expect(screen.getAllByText("Missing: add a test").length).toBeGreaterThanOrEqual(1);
    mountAt(undefined, ["when"], "when");
    expect(screen.getByText("No condition (never fires)")).toBeInTheDocument();
  });
});

describe("ConditionField round trips the mutation run missed", () => {
  it("round-trips a 0 threshold", async () => {
    const { onChange } = mount({ trust_gte: 0, turn_lte: 5 });
    expect(screen.getByText("Trust at least 0")).toBeInTheDocument();
    await userEvent.clear(screen.getByRole("spinbutton", { name: /Turn at most/ }));
    await userEvent.type(screen.getByRole("spinbutton", { name: /Turn at most/ }), "9");
    expect(onChange).toHaveBeenLastCalledWith({ trust_gte: 0, turn_lte: 9 }, PATH);
  });

  it("treats a blank move, level or proposal select as an incomplete draft that blocks", async () => {
    const { onChange } = mount({});
    await userEvent.click(screen.getByRole("button", { name: "Add test" }));
    await userEvent.click(screen.getByRole("button", { name: "Move made" }));
    expect(conditionDrafts.get("root_when")?.valid).toBe(false);
    await userEvent.selectOptions(screen.getByRole("combobox", { name: /Move made/ }), "asks_goal");
    expect(onChange).toHaveBeenLastCalledWith({ move: "asks_goal" }, PATH);
    expect(conditionDrafts.get("root_when")?.valid).toBe(true);

    await userEvent.click(screen.getByRole("button", { name: "Add test" }));
    await userEvent.click(screen.getByRole("button", { name: "Conversation level is" }));
    expect(conditionDrafts.get("root_when")?.valid).toBe(false);
    await userEvent.selectOptions(screen.getByRole("combobox", { name: /Conversation level is/ }), "technical");
    expect(onChange).toHaveBeenLastCalledWith({ move: "asks_goal", level: "technical" }, PATH);
    expect(conditionDrafts.get("root_when")?.valid).toBe(true);

    await userEvent.click(screen.getByRole("button", { name: "Add test" }));
    await userEvent.click(screen.getByRole("button", { name: "Proposal reaches" }));
    expect(conditionDrafts.get("root_when")?.valid).toBe(false);
    await userEvent.selectOptions(screen.getByRole("combobox", { name: /: issue/ }), "access");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: /: side/ }), "own");
    expect(conditionDrafts.get("root_when")?.valid).toBe(false);
    await userEvent.selectOptions(screen.getByRole("combobox", { name: /: line/ }), "red_line");
    expect(onChange).toHaveBeenLastCalledWith(
      { move: "asks_goal", level: "technical", proposal_reaches: { issue: "access", side: "own", line: "red_line" } },
      PATH,
    );
    expect(conditionDrafts.get("root_when")?.valid).toBe(true);
  });

  it("refuses Edit as JSON while a row draft is open", async () => {
    mount({});
    await userEvent.click(screen.getByRole("button", { name: "Add test" }));
    await userEvent.click(screen.getByRole("button", { name: "Trust at least" }));
    await userEvent.click(screen.getByRole("button", { name: "Edit as JSON" }));
    expect(screen.getByText("Fix the condition marked in red before checking or saving")).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).toBeNull(); // the rows still show
  });

  it("keeps a complete proposal_reaches while a sibling row changes", async () => {
    const { onChange } = mount({ proposal_reaches: { issue: "access", side: "own", line: "red_line" }, trust_gte: 50 });
    await userEvent.clear(screen.getByRole("spinbutton"));
    await userEvent.type(screen.getByRole("spinbutton"), "51");
    expect(onChange).toHaveBeenLastCalledWith({ proposal_reaches: { issue: "access", side: "own", line: "red_line" }, trust_gte: 51 }, PATH);
  });

  it("keeps extra keys inside proposal_reaches while it is edited", async () => {
    const { onChange } = mount({ proposal_reaches: { issue: "access", side: "own", line: "red_line", extra: 1 } });
    await userEvent.selectOptions(screen.getByRole("combobox", { name: /: side/ }), "counterpart");
    expect(onChange).toHaveBeenLastCalledWith({ proposal_reaches: { issue: "access", side: "counterpart", line: "red_line", extra: 1 } }, PATH);
  });
});

describe("ConditionField nits", () => {
  it("turns out-of-range and non-integer numbers into drafts", async () => {
    const { onChange } = mount({ turn_gte: 3, trust_lte: 50 });
    const [turn, trust] = screen.getAllByRole("spinbutton");

    await userEvent.clear(turn);
    await userEvent.type(turn, "0");
    expect(screen.getByText("Enter a whole number of 1 or more")).toBeInTheDocument();
    expect(conditionDrafts.get("root_when")?.valid).toBe(false);
    expect(onChange).not.toHaveBeenCalled(); // below the schema's minimum of 1

    await userEvent.clear(trust);
    await userEvent.type(trust, "150");
    expect(screen.getByText("Enter a number from 0 to 100")).toBeInTheDocument();
    expect(conditionDrafts.get("root_when")?.valid).toBe(false);
    expect(onChange).not.toHaveBeenCalledWith({ turn_gte: 3, trust_lte: 150 }, PATH);

    await userEvent.clear(trust);
    await userEvent.type(trust, "25");
    expect(onChange).toHaveBeenLastCalledWith({ turn_gte: 3, trust_lte: 25 }, PATH);
  });

  it("explains when the chosen dial is already taken instead of snapping back silently", async () => {
    const { onChange } = mount({ trust_gte: 3, rigidity_gte: 50 });
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Trust at least 3: dial" }), "rigidity");
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByText("Rigidity at least is already in this list")).toBeInTheDocument();
  });

  it("keeps a key named ? as data, not as the scalar sentinel", async () => {
    const { onChange } = mount({ "?": 1, trust_gte: 3 });
    await userEvent.clear(screen.getByRole("spinbutton"));
    await userEvent.type(screen.getByRole("spinbutton"), "4");
    expect(onChange).toHaveBeenLastCalledWith({ "?": 1, trust_gte: 4 }, PATH);
  });
});
