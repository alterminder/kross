import { useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { api, type S } from "../api/client";
import { useLoad } from "../hooks";
import { useMe } from "../me";
import { Problem, cardCover } from "../ui";
import { DifficultyDots, LEVELS } from "./Library";

const VISIBILITY: Record<string, string> = {
  private: "Only me",
  org: "Everyone in the organisation",
  public: "Everyone (curated)",
};

export function ScenarioPage() {
  const { id } = useParams() as { id: string };
  const me = useMe();
  const navigate = useNavigate();
  const { data: scenario, error, reload } = useLoad<S["ScenarioDetail"]>(`scenarios/${id}`);
  const [problem, setProblem] = useState<string>();
  const busy = useRef(false); // one action at a time, even between two clicks in the same render
  const [pending, setPending] = useState(false);
  if (error) return <Problem text={error} />;
  if (!scenario) return <p className="loading">Loading…</p>;

  async function act(work: () => Promise<unknown>) {
    if (busy.current) return;
    busy.current = true;
    setPending(true);
    setProblem(undefined);
    try {
      await work();
    } catch (failure) {
      setProblem((failure as Error).message);
    } finally {
      busy.current = false;
      setPending(false);
    }
  }
  const start = (mode: "solo" | "playtest") =>
    act(async () => {
      const session = await api<S["SessionOut"]>("sessions", { method: "POST", body: { scenario_id: id, mode } });
      navigate(`/play/${session.id}?onboard=1`);
    });
  const duplicate = () =>
    act(async () => {
      const copy = await api<S["ScenarioDetail"]>(`scenarios/${id}/duplicate`, { method: "POST" });
      navigate(`/scenarios/${copy.id}/edit`);
    });
  const post = (path: string, body?: unknown) =>
    act(async () => {
      await api(`scenarios/${id}/${path}`, { method: "POST", body });
      await reload();
    });
  const remove = () =>
    confirm("Delete this scenario? Sessions already played keep their copy.") &&
    act(async () => {
      await api(`scenarios/${id}`, { method: "DELETE" });
      navigate("/");
    });

  const org = me.active_org;
  const adminOfRealOrg = org.role === "admin" && !org.personal;
  const choices = [...(adminOfRealOrg ? ["private", "org"] : []), ...(me.is_superadmin ? ["public"] : [])];
  const level = scenario.difficulty && LEVELS[scenario.difficulty] ? scenario.difficulty : null;
  const rawSituation =
    typeof scenario.brief === "string"
      ? scenario.brief
      : typeof scenario.brief === "object" && scenario.brief !== null
        ? String(scenario.brief.situation || scenario.brief.description || scenario.brief.summary || "")
        : "";
  const situation = rawSituation.replace(/\s*What you know\s*\(?[^:]*\)?:\s*[\s\S]*$/i, "").trim();

  return (
    <article className="scenario-detail-page">
      <div className="scenario-stage" style={{ backgroundImage: `url("${cardCover(scenario)}")` }}>
        <div className="scenario-backdrop-container">
          <header className="scenario-header">
            <h1>{scenario.title}</h1>
            {(level || scenario.minutes) && (
              <p className="scenario-facts">
                {level && (
                  <>
                    <span className="diff-label">{level[0].toUpperCase() + level.slice(1)}</span>{" "}
                    <DifficultyDots level={level} />
                  </>
                )}
                {scenario.minutes ? `${level ? " · " : ""}${scenario.minutes} min` : null}
              </p>
            )}
            {scenario.skills && scenario.skills.length > 0 && (
              <ul className="scenario-tags">
                {scenario.skills.map((skill) => (
                  <li key={skill} className="scenario-tag-pill">
                    {skill}
                  </li>
                ))}
              </ul>
            )}
            {situation && <p className="scenario-situation">{situation}</p>}
          </header>

          <Problem text={problem} />

          <div className="scenario-actions">
            <button className="scenario-start-btn" onClick={() => start("solo")} disabled={pending}>
              Start
            </button>
          </div>

          {(scenario.content || scenario.can_edit || (adminOfRealOrg && scenario.submitted)) && (
            <div className="scenario-admin-actions">
              <hr className="scenario-actions-divider" />
            {scenario.content && (
              <button className="secondary" onClick={() => start("playtest")} disabled={pending}>
                Playtest
              </button>
            )}
            {scenario.can_edit && (
              <Link className="button secondary" to={`/scenarios/${id}/edit`}>
                Edit
              </Link>
            )}
            {scenario.content && (
              <button className="secondary" onClick={duplicate} disabled={pending}>
                Duplicate
              </button>
            )}
            {scenario.can_edit && !adminOfRealOrg && !org.personal && scenario.visibility === "private" && !scenario.submitted && (
              <button className="secondary" onClick={() => post("submit")} disabled={pending}>
                Submit to the organisation
              </button>
            )}
            {adminOfRealOrg && scenario.submitted && (
              <button className="secondary" onClick={() => post("return")} disabled={pending}>
                Return to the author
              </button>
            )}
            {choices.length > 0 && scenario.content && (
              <label className="scenario-visibility-label">
                Visible to{" "}
                <select value={scenario.visibility} disabled={pending} onChange={(event) => post("visibility", { visibility: event.target.value })}>
                  {[...new Set([scenario.visibility, ...choices])].map((choice) => (
                    <option key={choice} value={choice}>
                      {VISIBILITY[choice]}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {scenario.can_edit && (
              <button className="danger" onClick={remove} disabled={pending}>
                Delete
              </button>
            )}
            </div>
          )}
        </div>
      </div>
    </article>
  );
}
