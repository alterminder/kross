import { hidePrep } from "../prep";

type Node = Record<string, any>;

export type Content = Record<string, unknown>;

export type SectionId = "basics" | "brief" | "cchn_prep" | "counterpart" | "rules" | "scoring" | "unused" | "other";

export type Section = { id: SectionId; label: string; paths: string[] };

/** Which schema paths each section shows. `[]` marks an array item's fields. */
export const SECTIONS: Section[] = [
  {
    id: "basics",
    label: "Basics",
    paths: ["title", "id", "difficulty", "estimated_minutes", "skills_tested", "negotiation.start_level", "timing", "preparation", "review", "sources", "generated"],
  },
  {
    id: "brief",
    label: "Trainee brief",
    paths: ["trainee_brief.situation", "trainee_brief.objective", "trainee_brief.facts", "trainee_brief.mandate", "trainee_brief.red_lines", "trainee_brief.decision_options"],
  },
  {
    id: "cchn_prep",
    label: "Strategic prep (Naivasha Grid)",
    paths: ["island_of_agreements", "claims", "own_iceberg", "css"],
  },
  {
    id: "counterpart",
    label: "Counterpart",
    paths: [
      "counterparts[].id",
      "counterparts[].role",
      "counterparts[].persona",
      "counterparts[].cultural_profile",
      "counterparts[].opening",
      "counterparts[].fallback",
      "counterparts[].preferred_level",
      "counterparts[].legitimacy_weights",
      "counterparts[].iceberg.position.stated",
      "counterparts[].iceberg.position.implicit",
      "counterparts[].iceberg.tactical_reasoning",
      "counterparts[].iceberg.motives_values",
      "counterparts[].state_initial",
      "counterparts[].hidden_interests",
      "counterparts[].authority",
      "counterparts[].constraints_from_constituency",
      "counterparts[].challenges",
      "stakeholders",
    ],
  },
  {
    id: "rules",
    label: "Rules & twists",
    paths: ["triggers", "injections", "outcomes", "overrides", "issues", "implementation_checklist", "multiparty"],
  },
  {
    id: "scoring",
    label: "Scoring & debrief",
    paths: ["rubric", "debrief", "reflection"],
  },
  {
    id: "unused",
    label: "Extras (not used yet)",
    paths: [
      "negotiation.nature",
      "negotiation.type",
      "phases",
      "counterparts[].behaviours",
      "counterparts[].motive_candidates",
      "avatar",
      "degradation_cues",
    ],
  },
  { id: "other", label: "Other", paths: [] },
];

export function section(id: SectionId): Section {
  return SECTIONS.find((item) => item.id === id) ?? SECTIONS.at(-1)!;
}

/** A field path with array indices folded away: ["counterparts", 0, "persona"], counterparts.0.persona and counterparts[militia_rep].persona all become counterparts[].persona. */
export function normalisePath(path: (string | number)[] | string): string {
  const parts: (string | number)[] = Array.isArray(path)
    ? path
    : String(path)
        .replace(/\[[^\]]*\]/g, "[]")
        .split(".")
        .map((part) => (/^\d+$/.test(part) ? Number(part) : part));
  return parts.reduce<string>(
    (acc, part) => (typeof part === "number" || /^\d+$/.test(String(part)) ? `${acc}[]` : acc ? `${acc}.${part}` : String(part)),
    "",
  );
}

const claimed = (paths: string[], path: string) => paths.some((claim) => path === claim || path.startsWith(`${claim}.`) || path.startsWith(`${claim}[`));
const parentOf = (paths: string[], path: string) => paths.some((claim) => claim.startsWith(`${path}.`) || claim.startsWith(`${path}[`));

/** The structured strategic-prep fields, hidden as controls by the VITE_HIDE_PREP build flag (src/prep.ts). */
const PREP = ["preparation", "island_of_agreements", "claims", "own_iceberg", "css"];

/** The flag hides the prep controls in every section; the saved content stays in the scenario untouched. */
function prepHidden(path: string): boolean {
  return hidePrep() && PREP.some((claim) => claimed([claim], path));
}

/** Is this path claimed by (or inside) one of the real sections? */
export function covered(path: string): boolean {
  return SECTIONS.some((item) => item.id !== "other" && claimed(item.paths, path));
}

/** Show this path in this section: its own fields, fields inside one it claims, and the containers down to them. */
export function inSection(path: string, which: SectionId, isOther: (path: string) => boolean = (p) => !covered(p)): boolean {
  if (prepHidden(path)) return false;
  if (which === "other") return isOther(path);
  const target = section(which);
  return claimed(target.paths, path) || parentOf(target.paths, path);
}

/** The section that holds this path (for issue links); undefined when only "Other" claims it (or prep hides it). */
export function sectionOf(path: string): SectionId | undefined {
  if (prepHidden(path)) return undefined;
  return SECTIONS.find((item) => item.id !== "other" && (claimed(item.paths, path) || parentOf(item.paths, path)))?.id;
}

/** Every property path the served schema declares, folded as normalisePath does. */
export function schemaPaths(schema: unknown): Set<string> {
  const root = (schema ?? {}) as Node;
  const defs = (root.$defs ?? {}) as Record<string, Node>;
  const found = new Set<string>();
  function walk(node: Node, base: string, seen: Set<string>) {
    let spec = node ?? {};
    if (typeof spec.$ref === "string") {
      const name = spec.$ref.replace("#/$defs/", "");
      if (seen.has(name) || name === "condition") return; // the condition builder owns its keys; they are not fields
      spec = defs[name] ?? {};
      seen = new Set([...seen, name]);
    }
    for (const [key, child] of Object.entries((spec.properties ?? {}) as Record<string, Node>)) {
      const path = base === "" ? key : `${base}.${key}`;
      found.add(path);
      walk(child, path, seen);
    }
    if (spec.items) walk(spec.items as Node, `${base}[]`, seen);
  }
  walk(root, "", new Set());
  return found;
}

/**
 * "Other" visibility from the served schema: a path shows when it (or something below it) is a property no section
 * claims, so an unclaimed field nested in a claimed container still appears and a fully claimed container does not.
 */
export function otherPaths(schema: unknown): (path: string) => boolean {
  const claims = SECTIONS.flatMap((item) => item.paths);
  const holdsClaims = (path: string) => claims.some((claim) => claim.startsWith(`${path}.`) || claim.startsWith(`${path}[`));
  const free = [...schemaPaths(schema)].filter((path) => !covered(path) && !holdsClaims(path));
  return (path: string) =>
    free.some((found) => found === path || found.startsWith(`${path}.`) || found.startsWith(`${path}[`) || path.startsWith(`${found}.`) || path.startsWith(`${found}[`));
}

export type Flag = { path: string; reason: string; raw?: string };

// ponytail: the converter's warnings are matched by keyword; give warnings a "path: text" prefix in convert.py if more are added.
const WARNING_PATHS: [RegExp, string][] = [
  [/indicator/i, "rubric.indicators"],
  [/opening/i, "counterparts[].opening"],
];

/**
 * Fields marked for a human check, as schema paths: review.needs_icrc_confirmation plus the converter's warnings
 * (the scenario's own generated.warnings and a fresh conversion's). A bare counterpart field gets a counterparts[]. prefix.
 */
export function flagsOf(content: Content, top: Set<string>, extraWarnings: string[] = []): Flag[] {
  const toPath = (raw: string) => {
    const path = normalisePath(raw);
    return top.has(path.split(/[.[]/)[0]) ? path : `counterparts[].${path}`;
  };
  const review = ((content.review as Content | undefined)?.needs_icrc_confirmation as string[] | undefined) ?? [];
  const warnings = [...(((content.generated as Content | undefined)?.warnings as string[] | undefined) ?? []), ...extraWarnings];
  return [
    ...review.map((raw) => ({ path: toPath(raw), reason: "ICRC to confirm", raw })),
    ...warnings.flatMap((text) => WARNING_PATHS.filter(([pattern]) => pattern.test(text)).map(([, path]) => ({ path, reason: text }))),
  ];
}
