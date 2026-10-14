import type { FieldProps } from "@rjsf/utils";
import { useState } from "react";
import type { EditorContext } from "./SectionTemplate";

type Stage = { id: string; label?: string; hint?: string; instruction: string; until_turn?: number; allow_injects?: boolean };
type Silence = { after_seconds?: number; line?: string; penalty?: number };
export type Timing = { phases?: Stage[]; warnings?: number[]; on_timeout?: string; silence?: Silence };

const ON_TIMEOUT: { value: string; label: string; says: string }[] = [
  { value: "guide", label: "Nothing ends", says: "The trainee is told time is up and may carry on." },
  { value: "end", label: "The meeting ends", says: "It ends without a result, as when the trainee stops." },
  { value: "fail", label: "It ends as a failure", says: "The meeting ends without an agreement." },
  { value: "trainer", label: "The trainer decides", says: "The trainer watching the session is asked. Without a trainer nothing ends." },
];

const STEP = 3; // turns between the stages a new stage is given

/** The value to store: every empty part left out, and nothing at all (undefined) when nothing is set, so a scenario
 * that sets no pacing keeps the built-in behaviour. */
export function tidy(timing: Timing): Timing | undefined {
  const out: Timing = {};
  if (timing.phases?.length) out.phases = timing.phases;
  if (timing.warnings?.length) out.warnings = timing.warnings;
  if (timing.on_timeout && timing.on_timeout !== "guide") out.on_timeout = timing.on_timeout;
  const silence: Silence = {};
  if (timing.silence?.after_seconds !== undefined) silence.after_seconds = timing.silence.after_seconds;
  if (timing.silence?.line) silence.line = timing.silence.line;
  if (timing.silence?.penalty !== undefined) silence.penalty = timing.silence.penalty;
  if (Object.keys(silence).length) out.silence = silence;
  return Object.keys(out).length ? out : undefined;
}

/** The stages ordered the way the server demands: every one but the last ends on a later turn, the last runs to the end. */
export function ordered(stages: Stage[]): Stage[] {
  let previous = 0;
  return stages.map((stage, index) => {
    const { until_turn, ...rest } = stage;
    if (index === stages.length - 1) return rest;
    const until = until_turn !== undefined && until_turn > previous ? until_turn : previous + STEP;
    previous = until;
    return { ...rest, until_turn: until };
  });
}

export function parseWarnings(text: string): number[] {
  const found = text
    .split(/[\\s,;]+/)
    .map((part) => Number.parseInt(part, 10))
    .filter((minutes) => Number.isInteger(minutes) && minutes >= 1);
  return [...new Set(found)].sort((a, b) => b - a);
}

/** Each stage's share of the bar: its length in turns; the last, which runs to the end, as long as the others on average. */
export function shares(stages: Stage[]): number[] {
  const lengths: number[] = [];
  let previous = 0;
  for (const stage of stages.slice(0, -1)) {
    const until = stage.until_turn ?? previous + STEP;
    lengths.push(Math.max(1, until - previous));
    previous = until;
  }
  const average = lengths.length ? lengths.reduce((a, b) => a + b, 0) / lengths.length : STEP;
  return [...lengths, Math.max(2, Math.round(average))].slice(0, stages.length);
}

const number = (text: string): number | undefined => (text.trim() === "" ? undefined : Number(text));

export function TimingField(props: FieldProps<Timing>) {
  const { formData, onChange, registry, fieldPathId } = props;
  const path = fieldPathId?.path ?? ["timing"];
  const ctx = registry.formContext as EditorContext | undefined;
  const timing = formData ?? {};
  const stages = timing.phases ?? [];
  const [warningsText, setWarningsText] = useState(() => (timing.warnings ?? []).join(", "));

  function set(next: Timing) {
    onChange(tidy(next), path);
  }
  function setStages(next: Stage[]) {
    set({ ...timing, phases: ordered(next) });
  }
  function change(index: number, changes: Partial<Stage>) {
    setStages(stages.map((stage, at) => (at === index ? { ...stage, ...changes } : stage)));
  }
  function addStage() {
    const taken = new Set(stages.map((stage) => stage.id));
    let n = stages.length + 1;
    while (taken.has(`stage_${n}`)) n += 1;
    setStages([...stages, { id: `stage_${n}`, instruction: "" }]);
  }
  function startFromBuiltIn() {
    const base = ctx?.timingDefaults?.phases ?? [];
    setStages(base.map((stage, at) => ({ id: stage.id, label: stage.label, hint: stage.hint, instruction: stage.instruction, until_turn: [2, 7][at] })));
  }
  const silence = timing.silence ?? {};
  const setSilence = (changes: Silence) => set({ ...timing, silence: { ...silence, ...changes } });
  const widths = shares(stages);
  const total = widths.reduce((a, b) => a + b, 0);

  return (
    <div className="field timing">
      <h3 className="card-title">Pacing</h3>
      <p className="hint">
        Stages, warnings, what happens when time runs out and how a silence is handled. Everything left empty keeps the built-in behaviour.
      </p>
      <div className="cards">
        <section className="card wide">
          <h4 className="card-title">Stages</h4>
      {stages.length === 0 ? (
        <div className="stages-empty">
          <p className="hint" style={{ marginBottom: "16px" }}>
            No stages of its own: the built-in opening, exploration and closing apply, timed by the scenario's length.
          </p>
          <button type="button" className="small secondary" onClick={startFromBuiltIn}>
            Start from the built-in stages
          </button>
        </div>
      ) : (
        <>
          <ol className="stage-bar" aria-label="Stages on a timeline">
            {stages.map((stage, index) => (
              <li key={index} className={`stage-${index % 4}`} style={{ flexGrow: widths[index] / total }}>
                <b>{stage.label || stage.id}</b>
                <small>{index === stages.length - 1 ? "to the end" : `to turn ${stage.until_turn}`}</small>
              </li>
            ))}
          </ol>
          <div className="stage-list">
            {stages.map((stage, index) => {
              const last = index === stages.length - 1;
              const n = index + 1;
              return (
                <fieldset key={index} className="stage">
                  <legend>Stage {n}</legend>
                  <label>
                    Name (id)
                    <input
                      aria-label={`Stage ${n} id`}
                      value={stage.id}
                      pattern="[a-z0-9_]+"
                      onChange={(event) => change(index, { id: event.target.value })}
                    />
                  </label>
                  <label>
                    Trainee sees
                    <input aria-label={`Stage ${n} label`} value={stage.label ?? ""} placeholder="Defaults to the id" onChange={(event) => change(index, { label: event.target.value || undefined })} />
                  </label>
                  <label className="wide">
                    About the stage (trainee sees)
                    <input aria-label={`Stage ${n} hint`} value={stage.hint ?? ""} onChange={(event) => change(index, { hint: event.target.value || undefined })} />
                  </label>
                  <label className="wide">
                    How the counterpart behaves (trainee never sees)
                    <textarea aria-label={`Stage ${n} instruction`} rows={3} value={stage.instruction} onChange={(event) => change(index, { instruction: event.target.value })} />
                  </label>
                  <label>
                    Lasts up to turn
                    {last ? (
                      <input aria-label={`Stage ${n} ends after turn`} value="the end" disabled />
                    ) : (
                      <input
                        aria-label={`Stage ${n} ends after turn`}
                        type="number"
                        min={1}
                        value={stage.until_turn ?? ""}
                        onChange={(event) => change(index, { until_turn: number(event.target.value) })}
                      />
                    )}
                  </label>
                  <label className="check wide">
                    <input
                      type="checkbox"
                      aria-label={`Stage ${n} allows twists`}
                      checked={stage.allow_injects !== false}
                      onChange={(event) => change(index, { allow_injects: event.target.checked ? undefined : false })}
                    />{" "}
                    A trainer may fire twists in this stage
                  </label>
                  <button type="button" className="small secondary remove" aria-label={`Remove stage ${n}`} onClick={() => setStages(stages.filter((_, at) => at !== index))}>
                    Remove
                  </button>
                </fieldset>
              );
            })}
          </div>
          <p>
            <button type="button" className="small" onClick={addStage}>
              + Add stage
            </button>{" "}
            <button type="button" className="small secondary" onClick={() => setStages([])}>
              Back to the built-in stages
            </button>
          </p>
        </>
      )}
        </section>
        <section className="card">
          <h4 className="card-title">Warnings</h4>
      <label>
        Minutes left at which the trainee sees a banner
        <input
          aria-label="Warning minutes"
          value={warningsText}
          placeholder={(ctx?.timingDefaults?.warnings ?? [5, 1]).join(", ")}
          onChange={(event) => {
            setWarningsText(event.target.value);
            set({ ...timing, warnings: parseWarnings(event.target.value) });
          }}
        />
      </label>
        </section>
        <section className="card">
          <h4 className="card-title">When time runs out</h4>
      <div role="radiogroup" aria-label="When time runs out" className="on-timeout">
        {ON_TIMEOUT.map((option) => (
          <label key={option.value} className="check">
            <input
              type="radio"
              name="timing-on-timeout"
              aria-label={option.label}
              checked={(timing.on_timeout ?? "guide") === option.value}
              onChange={() => set({ ...timing, on_timeout: option.value })}
            />
            <span className="on-timeout-text">
              <b>{option.label}.</b> {option.says}
            </span>
          </label>
        ))}
      </div>
        </section>
        <section className="card timing-silence">
          <h4 className="card-title">Silence</h4>
      <label>
        The counterpart speaks up after (seconds)
        <input
          aria-label="Silence after seconds"
          type="number"
          min={10}
          max={600}
          value={silence.after_seconds ?? ""}
          placeholder={String(ctx?.timingDefaults?.silence_after_seconds ?? 90)}
          onChange={(event) => setSilence({ after_seconds: number(event.target.value) })}
        />
      </label>
      <label>
        What they say (word for word; empty: the model improvises)
        <input aria-label="Silence line" value={silence.line ?? ""} onChange={(event) => setSilence({ line: event.target.value || undefined })} />
      </label>
      <label>
        How hard a silence hits (hostility rises by this much)
        <input
          aria-label="Silence penalty"
          type="number"
          min={1}
          max={50}
          value={silence.penalty ?? ""}
          placeholder="8 (5)"
          onChange={(event) => setSilence({ penalty: number(event.target.value) })}
        />
      </label>
        </section>
      </div>
    </div>
  );
}
