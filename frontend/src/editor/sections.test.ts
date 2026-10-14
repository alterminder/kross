import { describe, expect, it, vi } from "vitest";
import scenarioSchema from "./fixtures/scenario-schema.json";
import { SECTIONS, flagsOf, inSection, normalisePath, otherPaths, schemaPaths, sectionOf } from "./sections";

describe("sections", () => {
  it("folds ids and indices into schema paths and routes flags, keeping bare counterpart fields", () => {
    expect(normalisePath(["counterparts", 0, "persona"])).toBe("counterparts[].persona");
    expect(normalisePath("counterparts[militia_rep].persona")).toBe("counterparts[].persona");
    const top = new Set(["title", "counterparts"]);
    const flags = flagsOf(
      {
        review: { needs_icrc_confirmation: ["counterparts[militia_rep].persona", "state_initial"] },
        generated: { warnings: ["Check the indicators"] },
      },
      top,
    );
    expect(flags.map((flag) => flag.path)).toEqual(["counterparts[].persona", "counterparts[].state_initial", "rubric.indicators"]);
    expect(flags[0].raw).toBe("counterparts[militia_rep].persona");
  });

  it("keeps a new unclaimed field visible under Other, nested or not", () => {
    const schema = {
      type: "object",
      properties: {
        title: { type: "string" },
        counterparts: { type: "array", items: { type: "object", properties: { persona: { type: "string" }, fresh_field: { type: "string" } } } },
        mystery_extra: { type: "string" },
      },
    };
    const isOther = otherPaths(schema);
    expect(isOther("mystery_extra")).toBe(true);
    expect(isOther("counterparts")).toBe(true); // the container of an unclaimed field
    expect(isOther("counterparts[].fresh_field")).toBe(true);
    expect(isOther("counterparts[].persona")).toBe(false);
    expect(isOther("title")).toBe(false);
  });

  it("routes a path to the section that claims it", () => {
    expect(sectionOf("counterparts[].persona")).toBe("counterpart");
    expect(sectionOf("triggers")).toBe("rules");
    expect(sectionOf("negotiation")).toBe("basics"); // it holds negotiation.start_level
    expect(sectionOf("mystery")).toBeUndefined();
  });
});

describe("section map", () => {
  const leaves = [...schemaPaths(scenarioSchema)].filter(
    (path) => ![...schemaPaths(scenarioSchema)].some((other) => other.startsWith(`${path}.`) || other.startsWith(`${path}[`)),
  );
  const hiddenLeaves = () => {
    const isOther = otherPaths(scenarioSchema);
    return leaves.filter((path) => !SECTIONS.some((item) => inSection(path, item.id, isOther)));
  };

  it("hides exactly the strategic preparation fields by default; the rest stays in its one section", () => {
    const prep = ["preparation", "island_of_agreements", "claims", "own_iceberg", "css"];
    const under = (path: string) => prep.some((root) => path === root || path.startsWith(`${root}.`) || path.startsWith(`${root}[`));
    const hidden = hiddenLeaves();
    expect(hidden.length).toBeGreaterThan(0);
    expect(hidden).toEqual(leaves.filter(under));
    const isOther = otherPaths(scenarioSchema);
    const multi = leaves.filter((path) => !under(path) && SECTIONS.filter((item) => inSection(path, item.id, isOther)).length > 1);
    expect(multi).toEqual([]);
    expect(leaves.length).toBeGreaterThan(100);
  });

  it("restores the preparation controls when the build sets VITE_HIDE_PREP=0: nothing hidden, nothing twice", () => {
    vi.stubEnv("VITE_HIDE_PREP", "0");
    const isOther = otherPaths(scenarioSchema);
    expect(hiddenLeaves()).toEqual([]);
    const multi = leaves.filter((path) => SECTIONS.filter((item) => inSection(path, item.id, isOther)).length > 1);
    expect(multi).toEqual([]);
  });

  it("routes trainee_brief.decision_options to the Trainee brief: the trainee reads it in play", () => {
    expect(sectionOf("trainee_brief.decision_options")).toBe("brief");
  });

  it("routes trainee_brief.facts to the Trainee brief: verified facts the trainee holds at the start", () => {
    expect(sectionOf("trainee_brief.facts")).toBe("brief");
  });
});
