import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { useDraft } from "./drafts";

export type MoveInfo = { id: string; description: string };
export type BuilderContext = { moves: MoveInfo[]; issues: string[] };

const DIALS: Record<string, string> = { trust: "Trust", rigidity: "Rigidity", hostility: "Hostility" };
const OPS: Record<string, string> = { gte: "at least", lte: "at most" };
const SIDES: Record<string, string> = { own: "Own", counterpart: "Counterpart" };
const LINES: Record<string, string> = { bottom_line: "Bottom line", red_line: "Red line" };
const LEVELS: Record<string, string> = { political: "Political", professional: "Professional", technical: "Technical" };

/** The kinds the "Add test" menu offers: its labels come from the table here, not from the schema. */
export const KINDS = [
  "move",
  "goal_requested",
  "trust_gte",
  "trust_lte",
  "rigidity_gte",
  "rigidity_lte",
  "hostility_gte",
  "hostility_lte",
  "turn_gte",
  "turn_lte",
  "level",
  "proposal_reaches",
];

export function titleCase(id: string): string {
  const words = id.replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function isGroup(key: string): boolean {
  return key === "any" || key === "all";
}

function thresholdOf(key: string): { base: string; op: string } | null {
  const found = /^(.+)_(gte|lte)$/.exec(key);
  return found && (found[1] === "turn" || found[1] in DIALS) ? { base: found[1], op: found[2] } : null;
}

/** The row a key renders as; undefined when the builder does not know the key. */
export function rowLabel(key: string): string | undefined {
  if (key === "move") return "Move made";
  if (key === "goal_requested") return "Asked for the goal";
  if (key === "level") return "Conversation level is";
  if (key === "proposal_reaches") return "Proposal reaches";
  const threshold = thresholdOf(key);
  return threshold ? `${threshold.base === "turn" ? "Turn" : DIALS[threshold.base]} ${OPS[threshold.op]}` : undefined;
}

/** The row's one-line summary: its label and current value, also the name of its Remove button. */
export function rowSummary(key: string, value: unknown, ctx: BuilderContext): string {
  if (key === "") return `Unsupported value = ${JSON.stringify(value)}`;
  const label = rowLabel(key);
  if (!label) return `Unsupported test ${key} = ${JSON.stringify(value)}`;
  if (value === undefined || value === "") return `${label} (not set)`;
  if (key === "move") {
    const id = String(value);
    return `Move made: ${ctx.moves.some((move) => move.id === id) ? titleCase(id) : `${id} (unknown move)`}`;
  }
  if (key === "goal_requested") return `Asked for the goal: ${value ? "Yes" : "No"}`;
  if (key === "level") return `Conversation level is: ${LEVELS[String(value)] ?? String(value)}`;
  if (key === "proposal_reaches") {
    const { issue, side, line } = (value ?? {}) as Record<string, string>;
    return `Proposal reaches: ${issue && side && line ? `${titleCase(issue)} / ${SIDES[side] ?? side} / ${LINES[line] ?? line}` : "(not set)"}`;
  }
  return `${label} ${String(value)}`;
}

/** A row with no value yet (a draft) is complete once every part is filled in. */
export function rowComplete(key: string, value: unknown): boolean {
  if (value === undefined) return false;
  if (key === "proposal_reaches") {
    const part = (value ?? {}) as Record<string, unknown>;
    return Boolean(part.issue && part.side && part.line);
  }
  return true;
}

/** A number box that keeps its text until it parses: blank, out of range or not a whole number is an incomplete draft. */
function NumberBox({ draftId, name, value, onValue, min, max, message }: { draftId: string; name: string; value: unknown; onValue: (next: number) => void; min: number; max?: number; message: string }) {
  const box = useRef<HTMLInputElement>(null);
  const describedBy = useId();
  const [text, setText] = useState(value === undefined || value === null ? "" : String(value));
  useEffect(() => {
    setText(value === undefined || value === null ? "" : String(value));
  }, [value]);
  const valid = (candidate: string) => {
    const parsed = Number(candidate);
    return candidate.trim() !== "" && Number.isInteger(parsed) && parsed >= min && (max === undefined || parsed <= max);
  };
  const invalid = !valid(text);
  useDraft(`${draftId}:number`, invalid, () => box.current?.focus());
  return (
    <>
      <input
        ref={box}
        type="number"
        aria-label={name}
        aria-invalid={invalid}
        aria-describedby={invalid ? describedBy : undefined}
        value={text}
        min={min}
        max={max}
        step={1}
        onChange={(event) => {
          setText(event.target.value);
          if (valid(event.target.value)) onValue(Number(event.target.value));
        }}
      />
      {invalid && (
        <small id={describedBy} className="problem">
          {message}
        </small>
      )}
    </>
  );
}

/** A select that keeps a stored value even when it is not one of the offered options. */
function Select({
  draftId,
  name,
  value,
  onValue,
  options,
  placeholder,
  unknown,
  message,
}: {
  draftId: string;
  name: string;
  value: unknown;
  onValue: (next: string) => void;
  options: Record<string, string>;
  placeholder: string;
  unknown: string;
  message: string;
}) {
  const box = useRef<HTMLSelectElement>(null);
  const describedBy = useId();
  const current = value === undefined ? "" : String(value);
  const [unknownValue] = useState(current !== "" && !(current in options) ? current : ""); // a stored value the options list lost is kept
  const invalid = current === "";
  useDraft(`${draftId}:${name}`, invalid, () => box.current?.focus());
  return (
    <>
      <select
        ref={box}
        aria-label={name}
        aria-invalid={invalid}
        aria-describedby={invalid ? describedBy : undefined}
        value={current}
        onChange={(event) => {
          if (event.target.value !== "") onValue(event.target.value);
        }}
      >
        {current === "" && <option value="">{placeholder}</option>}
        {unknownValue !== "" && !(unknownValue in options) && <option value={unknownValue}>{`${unknownValue} (${unknown})`}</option>}
        {Object.entries(options).map(([option, text]) => (
          <option key={option} value={option}>
            {text}
          </option>
        ))}
      </select>
      {invalid && (
        <small id={describedBy} className="problem">
          {message}
        </small>
      )}
    </>
  );
}

type RowProps = {
  draftId: string;
  name: string;
  value: unknown;
  ctx: BuilderContext;
  taken: Set<string>;
  onValue: (next: unknown) => void;
  onRename: (nextKey: string) => void;
  onRemove?: () => void;
};

/** One labelled row: its summary legend, the controls for its test and its Remove button. */
export function ConditionRow({ draftId, name, value, ctx, taken, onValue, onRename, onRemove }: RowProps) {
  const summary = rowSummary(name, value, ctx);
  const threshold = thresholdOf(name);
  const [takenNote, setTakenNote] = useState<string>();
  let controls: ReactNode = null;

  if (name === "move") {
    controls = (
      <Select
        draftId={draftId}
        name={`${summary}: move`}
        value={value}
        onValue={onValue}
        unknown="unknown move"
        placeholder="(choose a move)"
        message="Choose a move"
        options={Object.fromEntries(ctx.moves.map((move) => [move.id, `${titleCase(move.id)} — ${move.description}`]))}
      />
    );
  } else if (name === "goal_requested") {
    controls = (
      <Select draftId={draftId} name={`${summary}: answer`} value={value === undefined ? "" : value ? "yes" : "no"} onValue={(next) => onValue(next === "yes")} options={{ yes: "Yes", no: "No" }} placeholder="(choose)" unknown="unknown" message="Choose yes or no" />
    );
  } else if (name === "level") {
    controls = <Select draftId={draftId} name={`${summary}: level`} value={value} onValue={onValue} options={LEVELS} placeholder="(choose a level)" unknown="unknown" message="Choose a level" />;
  } else if (name === "proposal_reaches") {
    const part = (key: string, options: Record<string, string>, text: string) => {
      const current = (value ?? {}) as Record<string, unknown>;
      return (
        <Select
          draftId={draftId}
          name={`${summary}: ${text}`}
          value={current[key]}
          unknown={`unknown ${text}`}
          placeholder={`(choose ${text === "issue" ? "an" : "a"} ${text})`}
          message={`Choose ${text === "issue" ? "an issue" : `a ${text}`}`}
          options={options}
          onValue={(next) => onValue({ ...current, [key]: next })}
        />
      );
    };
    controls = (
      <>
        {part("issue", Object.fromEntries(ctx.issues.map((issue) => [issue, titleCase(issue)])), "issue")}
        {part("side", SIDES, "side")}
        {part("line", LINES, "line")}
      </>
    );
  } else if (threshold) {
    const rename = (base: string, op: string) => {
      const nextKey = `${base}_${op}`;
      if (!taken.has(nextKey) || nextKey === name) {
        setTakenNote(undefined);
        onRename(nextKey);
      } else setTakenNote(`${rowLabel(nextKey)} is already in this list`);
    };
    controls = (
      <>
        {threshold.base !== "turn" && (
          <>
            <Select
              draftId={draftId}
              name={`${summary}: dial`}
              value={threshold.base}
              unknown="unknown"
              placeholder="(choose)"
              message="Choose a dial"
              options={DIALS}
              onValue={(next) => rename(next, threshold.op)}
            />
            <Select
              draftId={draftId}
              name={`${summary}: comparison`}
              value={threshold.op}
              unknown="unknown"
              placeholder="(choose)"
              message="Choose a comparison"
              options={OPS}
              onValue={(next) => rename(threshold.base, next)}
            />
          </>
        )}
        <NumberBox
          draftId={draftId}
          name={`${summary}: threshold`}
          value={value}
          onValue={onValue}
          min={threshold.base === "turn" ? 1 : 0}
          max={threshold.base === "turn" ? undefined : 100}
          message={threshold.base === "turn" ? "Enter a whole number of 1 or more" : "Enter a number from 0 to 100"}
        />
      </>
    );
  }

  return (
    <fieldset className="condition-row">
      <legend>{summary}</legend>
      {controls}
      {takenNote && <small className="problem">{takenNote}</small>}
      {onRemove && (
        <button type="button" className="small danger" onClick={onRemove}>
          {`Remove '${summary}'`}
        </button>
      )}
    </fieldset>
  );
}

/** An All/Any group: its members render as rows or nested groups. */
export function ConditionGroup({ groupKey, children, onRemove }: { groupKey: string; children: ReactNode; onRemove?: () => void }) {
  const label = groupKey === "any" ? "Any of these" : "All of these";
  return (
    <fieldset className="condition-group">
      <legend>{label}</legend>
      {children}
      {onRemove && (
        <button type="button" className="small danger" onClick={onRemove}>
          {`Remove '${label}'`}
        </button>
      )}
    </fieldset>
  );
}
