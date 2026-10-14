import { useState } from "react";
import { api, type S } from "../api/client";
import { useLoad } from "../hooks";
import { Problem, label } from "../ui";

type Deltas = Record<string, number>;

export function RulesPage() {
  const { data, error, reload } = useLoad<S["RulesOut"]>("rules");
  const [edits, setEdits] = useState<Record<string, Deltas>>({});
  const [problem, setProblem] = useState<string>();
  const [saved, setSaved] = useState(false);
  if (error) return <Problem text={error} />;
  if (!data) return <p className="loading">Loading…</p>;
  const rules = data;

  const deltas = (move: S["MoveOut"]): Deltas => edits[move.id] ?? move.deltas;
  function change(move: S["MoveOut"], dial: string, value: number) {
    setSaved(false);
    setEdits((all) => ({ ...all, [move.id]: { ...deltas(move), [dial]: value } }));
  }

  async function save() {
    setProblem(undefined);
    try {
      await api("rules", { method: "PUT", body: { moves: edits } });
      setEdits({});
      setSaved(true);
      await reload();
    } catch (failure) {
      setProblem((failure as Error).message);
    }
  }

  return (
    <>
      <h1>Behaviour rules</h1>
      <p>How much each move by the trainee changes the counterpart's dials. Sessions already started keep the rules they began with.</p>
      <Problem text={problem} />
      {saved && <p>Saved. New sessions use these rules.</p>}
      <table className="rules">
        <thead>
          <tr>
            <th>Move</th>
            {rules.dials.map((dial) => (
              <th key={dial}>{label(dial)}</th>
            ))}
            <th />
          </tr>
        </thead>
        <tbody>
          {rules.moves.map((move) => (
            <tr key={move.id} className={move.changed || edits[move.id] ? "changed" : undefined}>
              <th scope="row" title={move.id}>
                {move.description}
                {move.ends_session && " (ends the session)"}
              </th>
              {rules.dials.map((dial) => (
                <td key={dial}>
                  {rules.can_edit ? (
                    <input
                      type="number"
                      step={1}
                      aria-label={`${move.id} ${dial}`}
                      value={deltas(move)[dial] ?? 0}
                      onChange={(event) => change(move, dial, Number(event.target.value))}
                    />
                  ) : (
                    (deltas(move)[dial] ?? 0)
                  )}
                </td>
              ))}
              <td>
                {rules.can_edit && (move.changed || edits[move.id]) && (
                  <button className="secondary" onClick={() => setEdits((all) => ({ ...all, [move.id]: move.default }))}>
                    Default
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {rules.can_edit && (
        <button onClick={save} disabled={Object.keys(edits).length === 0}>
          Save the rules
        </button>
      )}
    </>
  );
}
