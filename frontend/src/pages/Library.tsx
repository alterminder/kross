import { Link } from "react-router";
import { api, type S } from "../api/client";
import { useLoad } from "../hooks";
import { IconTrash } from "../icons";
import { useMe } from "../me";
import { Problem, cardCover } from "../ui";

const BADGE: Record<string, string> = { private: "Private", org: "Organisation" };
export const LEVELS: Record<string, number> = { beginner: 1, intermediate: 2, advanced: 3, expert: 4 };

export function DifficultyDots({ level }: { level: string }) {
  const filled = LEVELS[level];
  return (
    <span className="diff-dots" role="img" aria-label={`Difficulty: ${level}, ${filled} of 4`}>
      {[1, 2, 3, 4].map((i) => (
        <span key={i} className="diff-dot" data-filled={i <= filled || undefined} />
      ))}
    </span>
  );
}

export function ScenarioCard({ card }: { card: S["ScenarioCard"] }) {
  const level = card.difficulty && LEVELS[card.difficulty] ? card.difficulty : null;
  return (
    <Link to={`/scenarios/${card.id}`} className="cover-card" style={{ backgroundImage: `url("${cardCover(card)}")` }}>
      {card.visibility !== "public" && <span className="cover-badge">{card.submitted ? "Submitted" : BADGE[card.visibility]}</span>}
      <div className="card-body">
        <h3>{card.title}</h3>
        {(level || card.minutes) && (
          <p className="facts">
            {level && (
              <>
                <span className="diff-label">{level[0].toUpperCase() + level.slice(1)}</span> <DifficultyDots level={level} />
              </>
            )}
            {card.minutes ? `${level ? " · " : ""}${card.minutes} min` : null}
          </p>
        )}
        <ul className="chips">
          {card.skills.slice(0, 3).map((skill) => (
            <li key={skill}>{skill}</li>
          ))}
        </ul>
      </div>
    </Link>
  );
}

export function Library() {
  const scenarios = useLoad<S["ScenarioCard"][]>("scenarios");
  const sessions = useLoad<S["SessionCard"][]>("sessions");
  const guest = useMe().is_guest;

  const remove = async (id: string) => {
    if (!confirm("Delete this session and its debrief?")) return;
    try {
      await api(`sessions/${id}`, { method: "DELETE" });
      await sessions.reload();
    } catch (failure) {
      window.alert((failure as Error).message);
    }
  };

  return (
    <>
      <Problem text={scenarios.error} />
      <div className="cards">
        {scenarios.data?.map((card) => (
          <ScenarioCard key={card.id} card={card} />
        ))}
        {!guest && (
          <Link to="/scenarios/new" className="add-card">
            <span aria-hidden="true">+ </span>Add scenario
          </Link>
        )}
      </div>
      {sessions.data && sessions.data.length > 0 && (
        <>
          <h2>Your sessions</h2>
          <ul className="sessions">
            {sessions.data.map((session) => (
              <li key={session.id}>
                <img
                  src={cardCover({ id: session.scenario_id, cover: session.cover, cover_image_version: session.cover_image_version })}
                  alt=""
                />
                <span className="grow">
                  {session.title}
                  {session.mode === "playtest" && " (playtest)"}
                </span>
                <span className="muted">{session.status === "active" ? `turn ${session.turn}` : (session.result ?? "ended")}</span>
                {session.status === "active" ? (
                  <Link to={`/play/${session.id}`}>Continue</Link>
                ) : (
                  <Link to={`/sessions/${session.id}/debrief`}>Debrief</Link>
                )}
                <button
                  type="button"
                  className="delete-session"
                  onClick={() => void remove(session.id)}
                  aria-label={`Delete session: ${session.title}`}
                >
                  <IconTrash size={15} />
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}
