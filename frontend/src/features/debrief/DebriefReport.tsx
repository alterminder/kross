import type { S } from "../../api/client";
import { label } from "../../ui";
import { IconCheck, IconX } from "../../icons";

type Debrief = S["DebriefOut"];
type Moment = { turn: number; note: string; quote?: string | null; try_instead?: string };
/** What the debrief model wrote. A debrief saved before the turn notes existed has only the first three fields. */
type Body = {
  summary?: string;
  strengths?: string[];
  improvements?: string[];
  did_well?: Moment[];
  missed?: Moment[];
  one_focus?: { title: string; advice: string } | null;
  score_check?: { id: string; first: number | null; second: number | null; uncertain: boolean }[];
};
type Scores = { scores?: { id: string; score: number | null; quote?: string | null }[] };

const SCALE = 5;

export function bodyOf(data: Debrief): Body {
  return (data.debrief ?? {}) as Body;
}

export function OutcomeBanner({ outcome, reached }: Pick<Debrief, "outcome" | "reached">) {
  if (!outcome) return null;
  const result = String(outcome.result ?? "");
  const tone = result === "success" ? "" : result === "fail" ? " fail" : " partial"; // "ended" and partial agreements read as neutral
  return (
    <div className={`outcome debrief-outcome${tone}`}>
      <div>
        <div className="eyebrow">Outcome</div>
        <h2>{String(outcome.label ?? result)}</h2>
        <p className="muted">Decided by the exercise's own rules, never by the model's opinion.</p>
      </div>
      {reached.length > 0 && (
        <ul className="debrief-milestones" aria-label="Milestones reached">
          {reached.map((item, index) => (
            <li key={index}>✓ {String(item.label ?? item.id)}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** What the second scoring pass said about a dimension the two passes disagree on. */
function disagreement(first: number | null, second: number | null): string {
  if (first === null || second === null) return "One scoring pass saw no evidence for this skill and the other did.";
  return `Two scoring passes gave ${first} and ${second} (${Math.abs(first - second)} apart).`;
}

export function Skills({
  scores,
  dimensions,
  checks,
  scale,
}: {
  scores: Debrief["scores"];
  dimensions: Debrief["dimensions"];
  checks?: Body["score_check"];
  scale?: { min?: number; max?: number; labels?: Record<string, string> } | null;
}) {
  const items = ((scores ?? {}) as Scores).scores ?? [];
  if (items.length === 0) return null;
  const minScale = scale?.min ?? 0;
  const maxScale = scale?.max ?? SCALE;
  const unsure = new Map((checks ?? []).filter((check) => check.uncertain).map((check) => [check.id, check]));
  return (
    <section className="card debrief-skills">
      <div className="eyebrow">Your skills this run</div>
      <ul>
        {items.map((item) => (
          <li key={item.id}>
            <div className="skill-row">
              <span>{dimensions?.[item.id] ?? label(item.id)}</span>
              {item.score === null ? (
                <span className="muted">Not observed</span>
              ) : (
                <>
                  <span
                    className="skill-bar"
                    role="meter"
                    aria-label={dimensions?.[item.id] ?? label(item.id)}
                    aria-valuemin={minScale}
                    aria-valuemax={maxScale}
                    aria-valuenow={item.score}
                  >
                    <span
                      style={{
                        width: `${Math.max(0, Math.min(100, ((item.score - minScale) / (maxScale - minScale || 1)) * 100))}%`,
                      }}
                    />
                  </span>
                  <b>
                    {item.score}/{maxScale}
                    {scale?.labels?.[String(item.score)] ? ` (${scale.labels[String(item.score)]})` : ""}
                  </b>
                </>
              )}
            </div>
            {item.quote && <blockquote>“{item.quote}”</blockquote>}
            {unsure.has(item.id) && (
              <p className="uncertain">
                <b>Uncertain.</b> {disagreement(unsure.get(item.id)!.first, unsure.get(item.id)!.second)} Read it as a
                range, not a firm figure.
              </p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function HiddenFacts({ facts }: { facts: Debrief["hidden_facts"] }) {
  if (!facts || facts.length === 0) return null;
  const found = facts.filter((fact) => fact.found).length;
  return (
    <section className="card debrief-facts">
      <div className="eyebrow">
        Hidden facts · {found} of {facts.length} found
      </div>
      <ul>
        {facts.map((fact) => (
          <li key={fact.id} className={fact.found ? "found" : "missed"}>
            <span aria-hidden="true">{fact.found ? <IconCheck size={14} /> : <IconX size={14} />}</span>
            <div>
              <p>{fact.text}</p>
              {!fact.found && fact.unlock && <p className="muted">It would have come out when: {fact.unlock}.</p>}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function MomentCard({ moment, kind }: { moment: Moment; kind: "good" | "missed" }) {
  return (
    <div className={`card debrief-moment ${kind}`}>
      <p>
        <span className="turn-tag">Turn {moment.turn}</span> <b>{moment.note}</b>
      </p>
      {moment.quote && <blockquote>“{moment.quote}”</blockquote>}
      {kind === "missed" && moment.try_instead && (
        <div className="try-instead">
          <div className="eyebrow">Try instead</div>
          <p>“{moment.try_instead}”</p>
        </div>
      )}
    </div>
  );
}

export function Moments({ body }: { body: Body }) {
  const good = body.did_well ?? [];
  const missed = body.missed ?? [];
  if (good.length + missed.length === 0) {
    // an older debrief, or one whose notes were all dropped for quoting words nobody said
    const strengths = body.strengths ?? [];
    const improvements = body.improvements ?? [];
    if (strengths.length + improvements.length === 0) return null;
    return (
      <div className="debrief-columns">
        <section>
          <h2>What you did well</h2>
          <ul>
            {strengths.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
        </section>
        <section>
          <h2>What to improve</h2>
          <ul>
            {improvements.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
        </section>
      </div>
    );
  }
  return (
    <div className="debrief-moments">
      {good.length > 0 && (
        <section>
          <h2>What you did well</h2>
          {good.map((moment, index) => (
            <MomentCard key={index} moment={moment} kind="good" />
          ))}
        </section>
      )}
      {missed.length > 0 && (
        <section>
          <h2>Missed opportunity</h2>
          {missed.map((moment, index) => (
            <MomentCard key={index} moment={moment} kind="missed" />
          ))}
        </section>
      )}
    </div>
  );
}

const signed = (value: number) => (value > 0 ? `+${value}` : `−${Math.abs(value)}`);

/** Why the dials moved: the trainee's own words next to what each did to the counterpart. */
export function DialCauses({ causes }: { causes: Debrief["dial_causes"] }) {
  if (!causes || causes.length === 0) return null;
  return (
    <section className="card debrief-causes">
      <div className="eyebrow">Why the dials moved</div>
      <ul>
        {causes.map((cause, index) => (
          <li key={index}>
            <span className="turn-tag">Turn {cause.turn}</span>
            <span className="cause-changes">
              {Object.entries(cause.changes).map(([dial, change]) => (
                <span key={dial} className="cause-change">
                  {change > 0 ? "▲" : "▼"} {label(dial)} {signed(change)}
                </span>
              ))}
            </span>
            <span className="cause-why">
              {cause.label}
              {cause.quote ? <> · “{cause.quote}”</> : null}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function OneFocus({ focus }: { focus: Body["one_focus"] }) {
  if (!focus) return null;
  return (
    <section className="card debrief-focus">
      <div className="eyebrow">One focus for next run</div>
      <h2>{focus.title}</h2>
      <p>{focus.advice}</p>
    </section>
  );
}

export function RuleFlags({ flags }: { flags: Debrief["flags"] }) {
  if (flags.length === 0) return null;
  return (
    <section>
      <h2>Rule flags</h2>
      <ul>
        {flags.map((flag, index) => (
          <li key={index}>
            <b>Turn {String(flag.turn)}</b> · {label(String(flag.id))}
            {flag.quote ? <>: “{String(flag.quote)}”</> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function FinalDials({
  dials,
  counterpartDials,
}: {
  dials: Debrief["dials"];
  counterpartDials?: Debrief["counterpart_dials"];
}) {
  const entries = Object.entries(dials);
  const parties = counterpartDials ?? [];
  if (entries.length === 0 && parties.length === 0) return null;
  return (
    <section>
      <h2>Final dials</h2>
      {parties.length > 1 ? (
        parties.map((party) => (
          <div key={party.id}>
            <h3>{party.role}</h3>
            <ul className="debrief-dials">
              {Object.entries(party.dials ?? {}).map(([name, value]) => (
                <li key={name}>
                  <span>{label(name)}</span> <b>{value}</b>
                </li>
              ))}
            </ul>
          </div>
        ))
      ) : (
        <ul className="debrief-dials">
          {entries.map(([name, value]) => (
            <li key={name}>
              <span>{label(name)}</span> <b>{value}</b>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
