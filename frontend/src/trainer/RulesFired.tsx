/** What the rules did on one turn: moves with their quote and dial changes, rule flags, cues sent to the
 * counterpart, reveals, injections and trainer overrides. Events are the engine's Event rows. */
import type { EngineEvent, TrainerView } from "./progress";

const signed = (value: number) => (value > 0 ? `+${value}` : String(value));

function reasonOf(event: EngineEvent): string {
  if (event.cue) return event.cue.text || event.cue.label;
  return event.reason || event.ref || "";
}

export function RulesFired({ state, turn }: { state: TrainerView["state"]; turn: number }) {
  const log = state.log.filter((item) => item.turn === turn);
  const moves = state.moves.filter((item) => item.turn === turn);
  const flags = state.flags.filter((item) => item.turn === turn);
  const deltas = (items: EngineEvent[]) =>
    items
      .filter((item) => item.dial)
      .map((item) => `${item.dial} ${signed((item.after ?? 0) - (item.before ?? 0))}`)
      .join(", ");
  const other = log.filter((item) => item.source !== "move");
  if (!moves.length && !flags.length && !other.length) return <p className="hint">No rule fired on turn {turn}.</p>;
  return (
    <div className="fired">
      {flags.map((item, i) => (
        <p className="flag" key={`f${i}`}>
          ⚑ {item.id.replaceAll("_", " ")}: “{item.quote}”
        </p>
      ))}
      {moves.map((item, i) => {
        const moveEntries = log.filter((entry) => entry.source === "move" && entry.ref === item.id);
        const changes = deltas(moveEntries);
        const isOverride = moveEntries.some((entry) => entry.reason === "scenario override");
        return (
          <div className="fired-row" key={`m${i}`}>
            <b>{item.id.replaceAll("_", " ")}</b>
            <span className="fired-delta">
              {changes || "no dial change"}
              {isOverride && (
                <span className="override-tag" title="Custom dial reaction for this scenario">
                  {" "}(scenario override)
                </span>
              )}
            </span>
            <blockquote>“{item.quote}”</blockquote>
          </div>
        );
      })}
      {other.map((item, i) => (
        <div className={`fired-row fired-${item.source}`} key={`o${i}`}>
          <b>{item.source === "cue" ? "told the counterpart" : item.source}</b>
          {item.dial && (
            <span className="fired-delta">
              {item.dial} {item.before} → {item.after}
            </span>
          )}
          <p>{reasonOf(item)}</p>
        </div>
      ))}
    </div>
  );
}
