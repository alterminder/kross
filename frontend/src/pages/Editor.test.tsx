import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { parse } from "yaml";
import { json, renderAt, stubApi } from "../test-utils";
import { ScenarioEditor } from "./Editor";

const EDIT_PATH = "/scenarios/s1/edit";

/** The detail the editor loads: `content` as an existing scenario the caller may edit. */
function detail(content: unknown, extra: Record<string, unknown> = {}) {
  return {
    id: "s1",
    title: "Water",
    cover: "field",
    content,
    can_edit: true,
    difficulty: null,
    minutes: null,
    skills: [],
    submitted: false,
    version: 1,
    visibility: "org",
    brief: {},
    ...extra,
  };
}

const SCHEMA = {
  $schema: "https://json-schema.org/draft/2020-12/schema",
  type: "object",
  properties: { title: { type: "string", title: "Title" } },
};

describe("ScenarioEditor", () => {
  it("lists the server's issues with their paths when a save is refused", async () => {
    stubApi({
      "GET scenarios/s1": detail(parse("title: Water point")),
      "GET scenarios/schema": SCHEMA,
      "GET scenarios/covers": ["field"],
      "PUT scenarios/s1": () => json({ detail: [{ path: "outcomes", message: "is required" }] }, 422),
      "POST scenarios/validate": [{ path: "outcomes", message: "is required" }],
    });
    renderAt(EDIT_PATH, <ScenarioEditor />, "/scenarios/:id/edit");
    await screen.findByDisplayValue("Water point");
    await userEvent.click(await screen.findByRole("button", { name: "Save" }));
    expect(await screen.findByText("outcomes")).toBeInTheDocument();
  });
});

const CONDITION_SCHEMA = {
  type: "object",
  properties: {
    title: { type: "string", title: "Title" },
    when: { $ref: "#/$defs/condition" },
  },
  $defs: {
    condition: {
      type: "object",
      description: "Machine-evaluable condition",
      properties: { trust_gte: { type: "integer" }, turn_gte: { type: "integer" } },
    },
  },
};

const BLOCK_MESSAGE = "Fix the condition marked in red before checking or saving";

/** Opens the form with one condition (when: {trust_gte: 5}), its JSON box open, and reports what reaches fetch. */
async function openEditor() {
  sessionStorage.clear(); // the section is remembered per scenario
  const sent: { content: Record<string, unknown> }[] = [];
  const fetchMock = stubApi({
    "GET scenarios/s1": detail(parse("title: Water\nwhen: {trust_gte: 5}")),
    "GET scenarios/schema": CONDITION_SCHEMA,
    "GET scenarios/covers": ["field"],
    "GET rules": { can_edit: true, dials: ["trust"], moves: [{ id: "identifies_interest", description: "Names an interest", source: "", deltas: {}, default: {}, changed: false, ends_session: false }] },
    "POST scenarios/validate": (init?: RequestInit) => {
      sent.push(JSON.parse(String(init?.body)));
      return json([]);
    },
  });
  const calls = () => fetchMock.mock.calls.map(([input]) => String(input).replace(/^\/api\//, ""));
  renderAt(EDIT_PATH, <ScenarioEditor />, "/scenarios/:id/edit");
  await screen.findByDisplayValue("Water");
  await userEvent.click(screen.getByRole("tab", { name: "Other" })); // the test schema's root-level `when` lives there
  await userEvent.click(screen.getByRole("button", { name: "Edit as JSON" }));
  return { calls, sent, box: screen.getByRole("textbox", { name: "Condition JSON" }) };
}

describe("ScenarioEditor condition drafts", () => {
  it("refuses Check while a condition draft is invalid, then checks with the parsed condition", async () => {
    const { calls, sent, box } = await openEditor();
    await userEvent.click(box);
    await userEvent.clear(box);
    await userEvent.paste("{");
    await userEvent.click(screen.getByRole("button", { name: "Check" }));
    expect(await screen.findByText(BLOCK_MESSAGE)).toBeInTheDocument();
    expect(calls().filter((call) => call.includes("scenarios/validate"))).toHaveLength(0);
    expect(sent).toHaveLength(0);

    await userEvent.clear(box);
    await userEvent.paste('{"turn_gte": 3}');
    await userEvent.click(screen.getByRole("button", { name: "Check" }));
    expect(await screen.findByText("No problems found.")).toBeInTheDocument();
    expect(sent).toHaveLength(1);
    expect(sent[0].content.when).toEqual({ turn_gte: 3 });
  });

  it("refuses Save while a blank condition row is an unfinished draft", async () => {
    const { calls } = await openEditor();
    await userEvent.click(screen.getByRole("button", { name: "Back to the rows" }));
    await userEvent.click(screen.getByRole("button", { name: "Add test" }));
    await userEvent.click(screen.getByRole("button", { name: "Turn at least" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText(BLOCK_MESSAGE)).toBeInTheDocument();
    expect(calls().filter((call) => call === "scenarios")).toHaveLength(0);
  });

  it("refuses the YAML switch while a condition draft is invalid", async () => {
    const { box } = await openEditor();
    await userEvent.click(box);
    await userEvent.clear(box);
    await userEvent.paste("{");
    await userEvent.click(screen.getByRole("button", { name: "Edit as YAML" }));
    expect(await screen.findByText(BLOCK_MESSAGE)).toBeInTheDocument();
    expect(screen.queryByLabelText("Scenario YAML")).toBeNull();
  });
});


const SECTIONS_SCHEMA = {
  type: "object",
  properties: {
    title: { type: "string" },
    counterparts: {
      type: "array",
      items: {
        type: "object",
        properties: {
          id: { type: "string" },
          persona: { type: "string" },
          state_initial: { type: "object", properties: { trust: { type: "integer" } } },
        },
      },
    },
    triggers: { type: "array", items: { type: "object", properties: { when: { $ref: "#/$defs/condition" }, say: { type: "string" } } } },
    injections: { type: "array", items: { type: "object", properties: { id: { type: "string" }, label: { type: "string" } } } },
    outcomes: { type: "array", items: { type: "object", properties: { id: { type: "string" }, label: { type: "string" } } } },
    issues: { type: "array", items: { type: "object", properties: { id: { type: "string" } } } },
    implementation_checklist: { type: "array", items: { type: "object", properties: { id: { type: "string" } } } },
    skills_tested: { type: "array", items: { type: "string" } },
    review: { type: "object", properties: { needs_icrc_confirmation: { type: "array", items: { type: "string" } } } },
    mystery_extra: { type: "string" },
  },
  $defs: { condition: { type: "object", properties: { trust_gte: { type: "integer" } } } },
};

const SECTIONS_YAML = `title: Water
counterparts:
  - id: militia_rep
    persona: Firm
    state_initial: {trust: 55}
triggers:
  - say: "No."
    when: {trust_gte: 55}
injections: []
outcomes:
  - id: win
    label: Win
issues:
  - id: access
implementation_checklist: []
mystery_extra: kept
`;

/** Opens the form on `yaml` and reports the captured save payloads and the rendered container. */
async function openSections(yaml = SECTIONS_YAML, saved: Record<string, unknown>[] = [], extra: Record<string, unknown> = {}, schema: unknown = SECTIONS_SCHEMA) {
  sessionStorage.clear(); // the section is remembered per scenario
  stubApi({
    "GET scenarios/s1": detail(parse(yaml)),
    "GET scenarios/schema": schema,
    "GET scenarios/covers": ["field"],
    "GET rules": { can_edit: true, dials: ["trust"], moves: [] },
    "PUT scenarios/s1": (init?: RequestInit) => {
      saved.push(JSON.parse(String(init?.body)).content);
      return json(detail(parse(yaml)));
    },
    ...extra,
  });
  const view = renderAt(EDIT_PATH, <ScenarioEditor />, "/scenarios/:id/edit");
  await screen.findByDisplayValue("Water");
  return { ...view, saved };
}

describe("ScenarioEditor sections", () => {
  it.each([undefined, "", "   ", "SCENARIO 01"])("folds source material into Advanced, shows populated bank references, and preserves sources (%s)", async (bank) => {
    const sources: Record<string, unknown> = { file: "case-study.md", cchn_tools: [3, 9] };
    if (bank !== undefined) sources.bank = bank;
    const { saved, container } = await openSections(SECTIONS_YAML + `sources: ${JSON.stringify(sources)}\n`, [], {}, {
      ...SECTIONS_SCHEMA,
      properties: {
        ...SECTIONS_SCHEMA.properties,
        sources: {
          type: "object",
          properties: { bank: { type: "string" }, cchn_tools: { type: "array", items: { type: "integer" } } },
        },
      },
    });
    expect(screen.getByText("Source material")).not.toBeVisible();
    await userEvent.click(screen.getByText("Advanced"));
    expect(screen.getByText("Source material")).toBeVisible();
    const references = screen.getByRole("list", { name: "CCHN references" });
    expect(within(references).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      "Tool 3: Fostering Legitimacy and Building Trust",
      "Tool 9: Analyzing the Position of the Counterpart (the Iceberg)",
    ]);
    const field = container.querySelector('[data-path="sources.cchn_tools"]') as HTMLElement;
    expect(within(field).queryAllByRole("button")).toHaveLength(0);
    expect(within(field).queryAllByRole("spinbutton")).toHaveLength(0);
    const reference = screen.queryByRole("textbox", { name: "Scenario bank" });
    if (bank?.trim()) expect(reference).toHaveValue(bank);
    else expect(reference).toBeNull();
    const title = screen.getByDisplayValue("Water");
    await userEvent.clear(title);
    await userEvent.type(title, "Water point");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(saved).toHaveLength(1));
    expect(saved[0].sources).toEqual(sources);
  });

  it("mounts only the selected section's fields", async () => {
    const { container } = await openSections();
    await userEvent.click(screen.getByRole("tab", { name: /Rules & twists/ }));
    expect(container.querySelector("#root_triggers_0_say")).toBeTruthy();
    expect(container.querySelector("#root_injections")).toBeTruthy();
    expect(container.querySelector("#root_outcomes_0_label")).toBeTruthy();
    expect(container.querySelector("#root_issues_0_id")).toBeTruthy();
    expect(container.querySelector("#root_implementation_checklist")).toBeTruthy();
    expect(container.querySelector("#root_counterparts_0_persona")).toBeNull();
    expect(container.querySelector("#root_title")).toBeNull();
  });

  it("keeps every value across a section switch", async () => {
    const { saved } = await openSections();
    for (const name of [/Rules & twists/, /Counterpart/, /Scoring/, /Other/, /Basics/]) {
      await userEvent.click(screen.getByRole("tab", { name }));
    }
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(saved).toHaveLength(1));
    expect(saved[0]).toEqual(parse(SECTIONS_YAML));
  });

  it("shows a property no section claims under Other", async () => {
    const { container } = await openSections();
    await userEvent.click(screen.getByRole("tab", { name: "Other" }));
    expect(container.querySelector("#root_mystery_extra")).toBeTruthy();
    expect(container.querySelector("#root_title")).toBeNull();
  });

  it("shows ICRC flags with a count and removes an entry on Confirm", async () => {
    const { saved } = await openSections(SECTIONS_YAML.replace("mystery_extra: kept", "mystery_extra: kept\nreview:\n  needs_icrc_confirmation: [\"counterparts[militia_rep].persona\"]\n"));
    const button = screen.getByRole("tab", { name: /Counterpart/ });
    expect(button).toHaveTextContent("⚑ 1");
    await userEvent.click(button);
    expect(screen.getByText("⚑ ICRC to confirm")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(screen.getByRole("tab", { name: /Counterpart/ })).not.toHaveTextContent("⚑");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(saved).toHaveLength(1));
    expect((saved[0].review as { needs_icrc_confirmation: string[] }).needs_icrc_confirmation).toEqual([]);
  });

  it("flags an inferred skills_tested on Basics with a working Confirm", async () => {
    const yaml = SECTIONS_YAML.replace(
      "mystery_extra: kept\n",
      'mystery_extra: kept\nskills_tested: ["Island of agreements"]\nreview:\n  needs_icrc_confirmation: ["skills_tested"]\n',
    );
    const { saved } = await openSections(yaml);
    const basics = screen.getByRole("tab", { name: /Basics/ });
    expect(basics).toHaveTextContent("⚑ 1");
    await userEvent.click(basics);
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(screen.getByRole("tab", { name: /Basics/ })).not.toHaveTextContent("⚑");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(saved).toHaveLength(1));
    expect((saved[0].review as { needs_icrc_confirmation: string[] }).needs_icrc_confirmation).toEqual([]);
  });

  it("refuses a section switch while a condition draft is invalid", async () => {
    const { container } = await openSections();
    await userEvent.click(screen.getByRole("tab", { name: /Rules & twists/ }));
    await userEvent.click(screen.getByRole("button", { name: "Add test" }));
    await userEvent.click(screen.getByRole("button", { name: "Turn at least" }));
    await userEvent.click(screen.getByRole("tab", { name: "Basics" }));
    expect(await screen.findByText(BLOCK_MESSAGE)).toBeInTheDocument();
    expect(container.querySelector("#root_triggers_0_say")).toBeTruthy();
    expect(container.querySelector("#root_title")).toBeNull();
  });
});

const TWO_COUNTERPARTS = SECTIONS_YAML.replace(
  "  - id: militia_rep\n    persona: Firm\n    state_initial: {trust: 55}\n",
  "  - id: militia_rep\n    persona: Firm\n    state_initial: {trust: 55}\n  - id: second\n    persona: Soft\n    state_initial: {trust: 10}\n",
);

describe("ScenarioEditor issue links", () => {
  it("focuses the exact item the issue names and maps sub-paths to their condition site", async () => {
    const { container } = await openSections(TWO_COUNTERPARTS, [], {
      "POST scenarios/validate": [
        { path: "counterparts.1.persona", message: "too vague" },
        { path: "triggers.0.when.turn_gte", message: "unknown condition key" },
        { path: "made.up.path", message: "nonsense" },
      ],
    });
    await userEvent.click(screen.getByRole("button", { name: "Check" }));

    // the second counterpart's persona, not the first
    await userEvent.click(await screen.findByRole("button", { name: "counterparts.1.persona" }));
    await waitFor(() => expect(container.querySelector("#root_counterparts_1_persona")).toBe(document.activeElement));

    // a sub-path under a condition site opens that site (Rules & twists) and focuses its field
    await userEvent.click(await screen.findByRole("button", { name: "triggers.0.when.turn_gte" }));
    await waitFor(() => expect(document.activeElement?.closest("[data-index-path='triggers.0.when']")).toBeTruthy());

    // a path that maps to no field stays a plain item
    expect(screen.queryByRole("button", { name: "made.up.path" })).toBeNull();
    expect(screen.getByText("made.up.path")).toBeInTheDocument();
  });

  it("does nothing when the section switch is refused", async () => {
    const { container } = await openSections(SECTIONS_YAML, [], {
      "POST scenarios/validate": [{ path: "counterparts.0.persona", message: "too vague" }],
    });
    await userEvent.click(screen.getByRole("button", { name: "Check" }));
    await userEvent.click(screen.getByRole("tab", { name: /Rules & twists/ }));
    await userEvent.click(screen.getByRole("button", { name: "Add test" }));
    await userEvent.click(screen.getByRole("button", { name: "Turn at least" }));
    await userEvent.click(await screen.findByRole("button", { name: "counterparts.0.persona" }));
    expect(await screen.findByText(BLOCK_MESSAGE)).toBeInTheDocument();
    expect(container.querySelector("#root_counterparts_0_persona")).toBeNull(); // still in Rules & twists
    expect(screen.getByRole("spinbutton", { name: /Turn at least/ })).toHaveFocus(); // focus stays on the invalid draft
  });
});

describe("ScenarioEditor confirmation", () => {
  it("Confirm removes exactly one entry of two", async () => {
    const yaml = SECTIONS_YAML.replace(
      "mystery_extra: kept\n",
      'mystery_extra: kept\nreview:\n  needs_icrc_confirmation: ["counterparts[militia_rep].persona", "counterparts[militia_rep].state_initial"]\n',
    );
    const { container, saved } = await openSections(yaml);
    await userEvent.click(screen.getByRole("tab", { name: /Counterpart/ }));
    const persona = container.querySelector<HTMLElement>('[data-path="counterparts[].persona"]')!;
    await userEvent.click(within(persona).getByRole("button", { name: "Confirm" }));
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument(); // a confirmation is an edit until saved
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(saved).toHaveLength(1));
    expect((saved[0].review as { needs_icrc_confirmation: string[] }).needs_icrc_confirmation).toEqual([
      "counterparts[militia_rep].state_initial",
    ]);
  });
});

describe("ScenarioEditor flags nits", () => {
  it("Confirm removes exactly one duplicate entry", async () => {
    const yaml = SECTIONS_YAML.replace(
      "mystery_extra: kept\n",
      'mystery_extra: kept\nreview:\n  needs_icrc_confirmation: ["counterparts[militia_rep].persona", "counterparts[militia_rep].persona"]\n',
    );
    const { container, saved } = await openSections(yaml);
    await userEvent.click(screen.getByRole("tab", { name: /Counterpart/ }));
    const persona = container.querySelector<HTMLElement>('[data-path="counterparts[].persona"]')!;
    await userEvent.click(within(persona).getAllByRole("button", { name: "Confirm" })[0]);
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(saved).toHaveLength(1));
    expect((saved[0].review as { needs_icrc_confirmation: string[] }).needs_icrc_confirmation).toEqual(["counterparts[militia_rep].persona"]);
  });

  it("counts a container flag in one section only and says the count in words", async () => {
    const yaml = SECTIONS_YAML.replace("mystery_extra: kept\n", 'mystery_extra: kept\nreview:\n  needs_icrc_confirmation: ["counterparts"]\n');
    await openSections(yaml);
    const counterpart = screen.getByRole("tab", { name: /Counterpart/ });
    expect(counterpart).toHaveTextContent("⚑ 1");
    expect(counterpart).toHaveTextContent("1 to confirm");
    expect(screen.getByRole("tab", { name: /Extras/ })).not.toHaveTextContent("⚑");
  });
});

const LABELS_SCHEMA = {
  type: "object",
  properties: {
    id: { type: "string", pattern: "^[a-z0-9_]+$" },
    title: { type: "string", description: "One scenario file. Shared rules live in config/…" },
    skills_tested: { type: "array", items: { type: "string" }, description: "ids checked by validate.py" },
    generated: { type: "object", properties: { tool: { type: "string" }, source_sha256: { type: "string" } } },
    review: { type: "object", properties: { needs_icrc_confirmation: { type: "array", items: { type: "string" } } } },
    mystery_extra: { type: "string", description: "engine internals" },
  },
};

const LABELS_YAML = `id: water_point
title: Water point
skills_tested: ["Island of agreements", "Reframing"]
generated:
  tool: convert.py
review:
  needs_icrc_confirmation: ["title"]
mystery_extra: kept
`;

/** Opens the form with a mapped field, a mapped list and an unmapped one. */
async function openLabels(saved: Record<string, unknown>[] = []) {
  sessionStorage.clear();
  stubApi({
    "GET scenarios/s1": detail(parse(LABELS_YAML)),
    "GET scenarios/schema": LABELS_SCHEMA,
    "GET scenarios/covers": ["field"],
    "GET rules": { can_edit: true, dials: ["trust"], moves: [] },
    "PUT scenarios/s1": (init?: RequestInit) => {
      saved.push(JSON.parse(String(init?.body)).content);
      return json(detail(parse(LABELS_YAML)));
    },
  });
  const view = renderAt(EDIT_PATH, <ScenarioEditor />, "/scenarios/:id/edit");
  await screen.findByDisplayValue("Water point");
  return { ...view, saved };
}

describe("ScenarioEditor labels", () => {
  it("shows the map's label and hint, skill tags, and no raw keys or asterisks", async () => {
    const { container } = await openLabels();
    // a mapped field: plain label and the map's hint, not the schema's developer note
    expect(screen.getByText("Scenario title")).toBeInTheDocument();
    expect(screen.getByText("The negotiation skills this scenario exercises.")).toBeInTheDocument();
    expect(screen.queryByText(/Shared rules live/)).toBeNull();
    expect(screen.getByText("Island of agreements")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove Reframing" })).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/skills_tested/);
    expect(container.textContent).not.toMatch(/-1/);
    // the required asterisk is gone (validation errors still show)
    expect(screen.queryByText("*")).toBeNull();
  });

  it("removes skill tags, adds suggested and custom skills, and saves without blanks or duplicates", async () => {
    const yaml = SECTIONS_YAML + 'skills_tested: ["Legacy custom skill", "Reframing"]\n';
    const { saved } = await openSections(yaml, [], {}, {
      ...SECTIONS_SCHEMA,
      "x-skills-vocabulary": ["Network Mapping", "Reframing"],
    });
    const input = await screen.findByRole("textbox", { name: "Skills tested" });
    expect(screen.queryByRole("button", { name: "Add skill" })).toBeNull();
    await userEvent.type(input, "ref");
    expect(screen.queryByRole("button", { name: "Reframing" })).toBeNull();
    await userEvent.clear(input);
    await userEvent.click(screen.getByRole("button", { name: "Remove Reframing" }));
    await userEvent.type(input, "net");
    await userEvent.click(screen.getByRole("button", { name: "Network Mapping" }));
    expect(input).toHaveFocus();
    expect(input).toHaveValue("");
    expect(screen.getByText("Network Mapping")).toBeInTheDocument();
    await userEvent.type(input, "Supply chain planning{Enter}");
    await userEvent.type(input, "NETWORK MAPPING{Enter}  {Enter}");
    expect(saved).toHaveLength(0); // Enter adds a tag; it never submits the scenario
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(saved).toHaveLength(1));
    expect(saved[0].skills_tested).toEqual(["Legacy custom skill", "Network Mapping", "Supply chain planning"]);
  });

  it("puts the negotiation level in The scenario card, and Save stays in the editor", async () => {
    sessionStorage.clear();
    const saved: Record<string, unknown>[] = [];
    const yaml = "title: Water point\nnegotiation:\n  start_level: technical\n";
    stubApi({
      "GET scenarios/s1": detail(parse(yaml)),
      "GET scenarios/schema": {
        type: "object",
        properties: {
          title: { type: "string" },
          negotiation: { type: "object", properties: { start_level: { type: "string", enum: ["political", "professional", "technical"] } } },
        },
      },
      "GET scenarios/covers": ["field"],
      "GET rules": { can_edit: true, dials: ["trust"], moves: [] },
      "PUT scenarios/s1": (init?: RequestInit) => {
        saved.push(JSON.parse(String(init?.body)).content);
        return json(detail(parse(yaml)));
      },
    });
    renderAt(EDIT_PATH, <ScenarioEditor />, "/scenarios/:id/edit");
    const title = await screen.findByDisplayValue("Water point");
    const card = screen.getByRole("heading", { name: "The scenario" }).closest("section") as HTMLElement;
    expect(within(card).getByLabelText("Negotiation style")).toHaveDisplayValue("Technical");
    await userEvent.type(title, "s");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(saved).toHaveLength(1));
    expect(await screen.findByText("All changes saved")).toBeInTheDocument(); // still editing, not the scenario page
  });

  it("humanises an unmapped key and keeps the plumbing editable behind Advanced", async () => {
    const { saved } = await openLabels();
    // the file id, the conversion provenance and the raw review paths are reachable only through Advanced
    await userEvent.click(screen.getByText("Advanced"));
    const id = screen.getByLabelText("Scenario file id");
    await userEvent.clear(id);
    await userEvent.type(id, "renamed");
    expect(screen.getByLabelText("Conversion tool")).toHaveValue("convert.py");
    // developer notes stay hidden everywhere
    expect(screen.queryByText(/Shared rules live/)).toBeNull();
    expect(screen.queryByText(/validate\.py/)).toBeNull();
    await userEvent.click(screen.getByRole("tab", { name: "Other" }));
    expect(screen.getByText("Mystery extra")).toBeInTheDocument();
    expect(screen.queryByText(/mystery_extra/)).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(saved).toHaveLength(1));
    expect(saved[0].id).toBe("renamed");
    expect((saved[0].generated as Record<string, unknown>).tool).toBe("convert.py");
  });

  it("renders early warning signs as pills without an add button, and simplifies authority and red line lists without move buttons", async () => {
    const yaml =
      SECTIONS_YAML +
      'degradation_cues: ["Hostile glare", "Armed escalation"]\n' +
      'trainee_brief:\n  red_lines:\n    - text: "Never yield safety"\n' +
      'rubric:\n  indicators:\n    - "Check credentials"\n';
    const saved: Record<string, unknown>[] = [];
    const schema = {
      ...SECTIONS_SCHEMA,
      properties: {
        ...SECTIONS_SCHEMA.properties,
        degradation_cues: { type: "array", items: { type: "string" } },
        rubric: {
          type: "object",
          properties: {
            indicators: { type: "array", items: { type: "string" } },
          },
        },
        trainee_brief: {
          type: "object",
          properties: {
            red_lines: {
              type: "array",
              items: {
                type: "object",
                properties: { text: { type: "string" } },
              },
            },
          },
        },
        overrides: { type: "object" },
        reflection: {
          type: "object",
          properties: {
            questions: {
              type: "array",
              items: {
                type: "object",
                properties: { id: { type: "string" }, prompt: { type: "string" } },
              },
            },
          },
        },
        counterparts: {
          type: "array",
          items: {
            type: "object",
            properties: {
              ...((SECTIONS_SCHEMA.properties.counterparts.items as Record<string, any>).properties),
              authority: {
                type: "object",
                properties: {
                  decides: { type: "array", items: { type: "string" } },
                },
              },
              hidden_interests: {
                type: "array",
                items: {
                  type: "object",
                  properties: { text: { type: "string" } },
                },
              },
              iceberg: {
                type: "object",
                properties: {
                  motives_values: {
                    type: "object",
                    properties: {
                      values: { type: "array", items: { type: "string" } },
                    },
                  },
                },
              },
            },
          },
        },
      },
    };
    const { container } = await openSections(
      yaml.replace(
        "state_initial: {trust: 55}",
        'state_initial: {trust: 55}\n    authority:\n      decides: ["School evacuation", "Relocation timeline"]\n    hidden_interests:\n      - text: "Quiet deal"\n    iceberg:\n      motives_values:\n        values: ["Quiet resolution"]',
      ).replace(
        "implementation_checklist: []",
        'implementation_checklist:\n  - id: timeline',
      ) + "\noverrides: {}\nreflection:\n  questions:\n    - id: q1\n      prompt: 'What went well?'\n",
      saved,
      {},
      schema,
    );
    await userEvent.click(screen.getByRole("tab", { name: /Extras/ }));
    expect(screen.getByText("Hostile glare")).toBeInTheDocument();
    expect(screen.getByText("Armed escalation")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Add warning sign/ })).toBeNull();
    const input = screen.getByRole("textbox", { name: "Early warning signs" });
    await userEvent.type(input, "Radio silence{Enter}");
    expect(screen.getByText("Radio silence")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Remove Hostile glare" }));
    expect(screen.queryByText("Hostile glare")).toBeNull();

    // Authority: decides has no Move up / Move down buttons
    await userEvent.click(screen.getByRole("tab", { name: /Counterpart/ }));
    const decidesSection = container.querySelector('[data-path="counterparts[].authority.decides"]') as HTMLElement;
    expect(within(decidesSection).queryByRole("button", { name: /Move .* up/ })).toBeNull();
    expect(within(decidesSection).queryByRole("button", { name: /Move .* down/ })).toBeNull();

    // Values render as pills without add button
    expect(screen.getByText("Quiet resolution")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Add value/ })).toBeNull();

    // Hidden facts: has no Move up / Move down buttons
    const hiddenFactsSection = container.querySelector('[data-path="counterparts[].hidden_interests"]') as HTMLElement;
    expect(within(hiddenFactsSection).queryByRole("button", { name: /Move .* up/ })).toBeNull();
    expect(within(hiddenFactsSection).queryByRole("button", { name: /Move .* down/ })).toBeNull();

    // Red lines: has no Move up / Move down buttons
    await userEvent.click(screen.getByRole("tab", { name: /Trainee brief/ }));
    const redLinesSection = container.querySelector('[data-path="trainee_brief.red_lines"]') as HTMLElement;
    expect(within(redLinesSection).queryByRole("button", { name: /Move .* up/ })).toBeNull();
    expect(within(redLinesSection).queryByRole("button", { name: /Move .* down/ })).toBeNull();

    // Scoring & debrief: rubric indicators has no Move up / Move down buttons
    await userEvent.click(screen.getByRole("tab", { name: /Scoring/ }));
    const indicatorsSection = container.querySelector('[data-path="rubric.indicators"]') as HTMLElement;
    expect(within(indicatorsSection).queryByRole("button", { name: /Move .* up/ })).toBeNull();
    expect(within(indicatorsSection).queryByRole("button", { name: /Move .* down/ })).toBeNull();
    const reflectionSection = container.querySelector('[data-path="reflection"]') as HTMLElement;
    expect(reflectionSection).toHaveClass("wide");
    expect(within(reflectionSection).getByText("Reflection questions")).toBeInTheDocument();
    expect(within(reflectionSection).queryByText("Questions")).toBeNull();
    expect(within(reflectionSection).queryByText("What the trainee is asked afterwards.")).toBeNull();
    const questionsSection = container.querySelector('[data-path="reflection.questions"]') as HTMLElement;
    expect(questionsSection).not.toHaveClass("card");

    // Rules & twists: triggers, issues, outcomes, and checklist have no Move up / Move down buttons
    await userEvent.click(screen.getByRole("tab", { name: /Rules & twists/ }));
    const triggersSection = container.querySelector('[data-path="triggers"]') as HTMLElement;
    expect(within(triggersSection).queryByRole("button", { name: /Move .* up/ })).toBeNull();
    expect(within(triggersSection).queryByRole("button", { name: /Move .* down/ })).toBeNull();
    const issuesSection = container.querySelector('[data-path="issues"]') as HTMLElement;
    expect(within(issuesSection).queryByRole("button", { name: /Move .* up/ })).toBeNull();
    expect(within(issuesSection).queryByRole("button", { name: /Move .* down/ })).toBeNull();
    const outcomesSection = container.querySelector('[data-path="outcomes"]') as HTMLElement;
    expect(within(outcomesSection).queryByRole("button", { name: /Move .* up/ })).toBeNull();
    expect(within(outcomesSection).queryByRole("button", { name: /Move .* down/ })).toBeNull();
    const checklistSection = container.querySelector('[data-path="implementation_checklist"]') as HTMLElement;
    expect(within(checklistSection).queryByRole("button", { name: /Move .* up/ })).toBeNull();
    expect(within(checklistSection).queryByRole("button", { name: /Move .* down/ })).toBeNull();
    const overridesSection = container.querySelector('[data-path="overrides"]') as HTMLElement;
    expect(overridesSection).toHaveClass("wide");
  });
});

describe("ScenarioEditor tabs", () => {
  it("is a tablist whose arrow keys move between tabs and keep roving focus", async () => {
    await openSections();
    const first = screen.getByRole("tab", { name: "Basics" });
    expect(screen.getByRole("tablist", { name: "Sections" })).toBeInTheDocument();
    expect(first).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveAccessibleName("Basics");
    first.focus();
    await userEvent.keyboard("{ArrowRight}");
    const brief = screen.getByRole("tab", { name: /Trainee brief/ });
    expect(brief).toHaveAttribute("aria-selected", "true");
    expect(brief).toHaveFocus();
    await userEvent.keyboard("{ArrowLeft}");
    expect(screen.getByRole("tab", { name: "Basics" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Basics" })).toHaveFocus();
  });

  it("walks the tabs with Previous and Next", async () => {
    await openSections();
    expect(screen.queryByRole("button", { name: "← Previous: Basics" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Next: Trainee brief →" }));
    expect(screen.getByRole("tab", { name: /Trainee brief/ })).toHaveAttribute("aria-selected", "true");
    await userEvent.click(screen.getByRole("button", { name: "← Previous: Basics" }));
    expect(screen.getByRole("tab", { name: "Basics" })).toHaveAttribute("aria-selected", "true");
  });

  it("hides the Other tab when no field is unclaimed", async () => {
    await openSections(SECTIONS_YAML.replace("mystery_extra: kept\n", ""), [], {}, { type: "object", properties: { title: { type: "string" } } });
    expect(screen.queryByRole("tab", { name: "Other" })).toBeNull();
    expect(screen.getByRole("tab", { name: "Extras (not used yet)" })).toBeInTheDocument();
  });
});

const PREVIEW_SCHEMA = {
  type: "object",
  properties: {
    title: { type: "string" },
    trainee_brief: {
      type: "object",
      properties: {
        situation: { type: "string" },
        objective: { type: "string" },
        facts: { type: "array", items: { type: "string" } },
        red_lines: {
          type: "array",
          items: {
            type: "object",
            properties: { text: { type: "string" }, source: { type: "string", enum: ["legal", "institutional"] }, flexible_by_mandator_only: { type: "boolean" } },
          },
        },
      },
    },
  },
};

const PREVIEW_YAML = `title: Water
trainee_brief:
  situation: A camp is cut off.
  objective: Get access agreed.
  facts: ["The bridge is out."]
  red_lines:
    - text: No armed escort.
      source: institutional
      flexible_by_mandator_only: true
`;

describe("ScenarioEditor trainee preview", () => {
  it("shows the brief as the trainee reads it and updates live as the trainer types", async () => {
    await openSections(PREVIEW_YAML, [], {}, PREVIEW_SCHEMA);
    await userEvent.click(screen.getByRole("tab", { name: /Trainee brief/ }));
    const preview = screen.getByRole("complementary", { name: "Preview as the trainee will see it" });
    expect(within(preview).getByText("Water")).toBeInTheDocument();
    expect(within(preview).getByText("A camp is cut off.")).toBeInTheDocument();
    expect(within(preview).getByText("Get access agreed.")).toBeInTheDocument();
    expect(within(preview).getByText("The bridge is out.")).toBeInTheDocument();
    expect(within(preview).getByText("No armed escort.")).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("Situation"), " The wells flooded.");
    expect(within(preview).getByText("A camp is cut off. The wells flooded.")).toBeInTheDocument();
  });
});

describe("ScenarioEditor cover picker", () => {
  it("offers the painted cover as the first tile and switches between it and the themes", async () => {
    sessionStorage.clear();
    stubApi({
      "GET scenarios/s1": detail(parse("title: Water"), { cover: "custom", cover_image_version: "v2" }),
      "GET scenarios/schema": SCHEMA,
      "GET scenarios/covers": ["field", "camp"],
      "GET rules": { can_edit: true, dials: ["trust"], moves: [] },
    });
    renderAt(EDIT_PATH, <ScenarioEditor />, "/scenarios/:id/edit");
    await screen.findByDisplayValue("Water");
    const painted = screen.getByRole("radio", { name: "Painted for this scenario" });
    expect(screen.getAllByRole("radio")[0]).toBe(painted); // first tile
    expect(screen.queryByText("Painted for this scenario")).toBeNull(); // named by its image, no visible caption
    expect(painted).toBeChecked();
    await userEvent.click(screen.getByRole("radio", { name: "camp" }));
    expect(screen.getByRole("radio", { name: "camp" })).toBeChecked();
    await userEvent.click(painted); // picking the painted tile again switches back; the painting stays
    expect(painted).toBeChecked();
  });
});

const AVATAR_SCHEMA = {
  type: "object",
  properties: {
    title: { type: "string" },
    avatar: {
      type: "object",
      description: "sim/avatar.py, sim/voice.py internals",
      properties: {
        voice: { type: "object", description: "ElevenLabs wiring", properties: { description: { type: "string", description: "engine reads this key" } } },
      },
    },
  },
};

const ENUM_SCHEMA = {
  type: "object",
  properties: {
    title: { type: "string" },
    preparation: { type: "object", properties: { modules: { type: "array", items: { type: "string", enum: ["island_of_agreements", "network"] } } } },
    counterparts: {
      type: "array",
      items: {
        type: "object",
        properties: {
          hidden_interests: {
            type: "array",
            items: { type: "object", properties: { text: { type: "string" }, layer: { type: "string", enum: ["tactical_reasoning", "motive_value"] } } },
          },
        },
      },
    },
  },
};

describe("ScenarioEditor review round 1", () => {
  it("keeps a field literally named description editable while the notes stay hidden", async () => {
    const saved: Record<string, unknown>[] = [];
    await openSections("title: Water\navatar:\n  voice:\n    description: A quiet voice\n", saved, {}, AVATAR_SCHEMA);
    await userEvent.click(screen.getByRole("tab", { name: /Extras/ }));
    const field = screen.getByLabelText("Voice description");
    expect(field).toHaveValue("A quiet voice");
    expect(screen.queryByText(/ElevenLabs wiring/)).toBeNull();
    expect(screen.queryByText(/engine reads this key/)).toBeNull();
    await userEvent.type(field, " indeed");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(saved).toHaveLength(1));
    expect(((saved[0].avatar as Record<string, Record<string, unknown>>).voice ?? {}).description).toBe("A quiet voice indeed");
  });

  it("survives malformed brief and reference shapes from YAML and keeps the form usable", async () => {
    await openSections(
      "title: Water\ntrainee_brief:\n  facts: not-a-list\n  red_lines:\n    -\n    - text: No armed escort.\n",
      [],
      {},
      {
        ...PREVIEW_SCHEMA,
        properties: {
          ...PREVIEW_SCHEMA.properties,
          sources: { type: "object", properties: { cchn_tools: { type: "array", items: { type: "integer" } } } },
        },
      },
    );
    await userEvent.click(screen.getByRole("tab", { name: /Trainee brief/ }));
    const preview = screen.getByRole("complementary", { name: "Preview as the trainee will see it" });
    expect(within(preview).getByText("No armed escort.")).toBeInTheDocument(); // the null line is skipped, the string list is ignored
    expect(within(preview).queryByText("not-a-list")).toBeNull();
    expect(screen.getByLabelText("Situation")).toBeInTheDocument(); // the fields stay available for correction

    // the actual YAML → form switch, with object-valued facts (one with a toString key) and an object-valued text
    await userEvent.click(screen.getByRole("button", { name: "Edit as YAML" }));
    const box = screen.getByLabelText("Scenario YAML");
    await userEvent.clear(box);
    await userEvent.paste(
      "title: Water\ntrainee_brief:\n  facts:\n    - toString: The bridge is out.\n    - A real fact.\n  red_lines:\n    - text:\n        toString: Not text\n      source: legal\n    - text: No armed escort.\nsources:\n  cchn_tools:\n    - 3\n    - toString: Not a tool\n",
    );
    await userEvent.click(screen.getByRole("button", { name: "Back to the form" }));
    await userEvent.click(screen.getByRole("tab", { name: /Trainee brief/ }));
    const again = screen.getByRole("complementary", { name: "Preview as the trainee will see it" });
    expect(within(again).getByText("A real fact.")).toBeInTheDocument();
    expect(within(again).getByText("No armed escort.")).toBeInTheDocument();
    expect(within(again).queryByText("The bridge is out.")).toBeNull(); // the object fact is skipped, never coerced
    expect(within(again).queryByText(/object/)).toBeNull();
    expect(screen.getByLabelText("Situation")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Basics" }));
    await userEvent.click(screen.getByText("Advanced"));
    const references = screen.getByRole("list", { name: "CCHN references" });
    expect(within(references).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      "Tool 3: Fostering Legitimacy and Building Trust",
      "Invalid CCHN reference",
    ]);
    await userEvent.click(screen.getByRole("button", { name: "Edit as YAML" }));
    const content = parse((screen.getByLabelText("Scenario YAML") as HTMLTextAreaElement).value);
    expect(content.sources.cchn_tools).toEqual([3, { toString: "Not a tool" }]);
  });

  it("shows the confirm badge on a checkbox that draws its own label", async () => {
    const { saved } = await openSections(
      PREVIEW_YAML.replace("flexible_by_mandator_only: true", 'flexible_by_mandator_only: true\nreview:\n  needs_icrc_confirmation: ["trainee_brief.red_lines[].flexible_by_mandator_only"]'),
      [],
      {},
      PREVIEW_SCHEMA,
    );
    await userEvent.click(screen.getByRole("tab", { name: /Trainee brief/ }));
    const flagged = document.querySelector<HTMLElement>('[data-path="trainee_brief.red_lines[].flexible_by_mandator_only"]')!;
    expect(within(flagged).getByText("⚑ ICRC to confirm")).toBeInTheDocument();
    const checkbox = within(flagged).getByRole("checkbox");
    await userEvent.click(checkbox);
    expect(checkbox).not.toBeChecked(); // the field itself still edits
    await userEvent.click(within(flagged).getByRole("button", { name: "Confirm" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(saved).toHaveLength(1));
    expect((saved[0].review as { needs_icrc_confirmation: string[] }).needs_icrc_confirmation).toEqual([]);
    expect((saved[0].trainee_brief as Record<string, unknown>).red_lines).toEqual([
      { text: "No armed escort.", source: "institutional", flexible_by_mandator_only: false },
    ]);
  });

  it("opens Advanced to reach a folded-away field from an issue link", async () => {
    const { container } = await openSections(
      LABELS_YAML.replace("title: Water point", "title: Water"),
      [],
      { "POST scenarios/validate": [{ path: "id", message: "pick a friendlier id" }] },
      LABELS_SCHEMA,
    );
    await userEvent.click(screen.getByRole("button", { name: "Check" }));
    await userEvent.click(await screen.findByRole("button", { name: "id" }));
    await waitFor(() => expect(screen.getByLabelText("Scenario file id")).toHaveFocus());
    expect((container.querySelector("details.advanced") as HTMLDetailsElement).open).toBe(true);
  });

  it("labels enum options in plain words and stores the same values", async () => {
    vi.stubEnv("VITE_HIDE_PREP", "0"); // the preparation modules enum is hidden by default
    const saved: Record<string, unknown>[] = [];
    await openSections(
      "title: Water\npreparation:\n  modules: [island_of_agreements]\ncounterparts:\n  - hidden_interests:\n      - text: Ashamed.\n        layer: motive_value\n",
      saved,
      {},
      ENUM_SCHEMA,
    );
    // enum-array: plain words, raw values gone
    expect(screen.getAllByText("Island of Agreements").length).toBeGreaterThan(0);
    expect(screen.queryByText("island_of_agreements")).toBeNull();
    // select: plain option labels over the stored values
    await userEvent.click(screen.getByRole("tab", { name: /Counterpart/ }));
    const depth = screen.getByLabelText("Depth") as HTMLSelectElement;
    expect([...depth.options].filter((option) => option.selected).map((option) => option.textContent)).toEqual(["Motive and value"]);
    expect([...depth.options].filter((option) => option.textContent).map((option) => option.textContent)).toEqual(["Tactical reasoning", "Motive and value"]);
    expect(screen.queryByText("motive_value")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(saved).toHaveLength(1));
    expect((saved[0].preparation as Record<string, unknown>).modules).toEqual(["island_of_agreements"]);
    expect((saved[0].counterparts as Record<string, unknown>[])[0].hidden_interests).toEqual([{ text: "Ashamed.", layer: "motive_value" }]);
  });
});
