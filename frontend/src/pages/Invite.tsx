import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router";
import { api, appUrl, nav, type S } from "../api/client";
import { Problem } from "../ui";

const PROBLEM: Record<string, string> = { revoked: "was revoked", expired: "has expired", used_up: "has been used up" };

export function Invite() {
  const token = useLocation().hash.slice(1); // the token travels in the fragment, never in a request URL
  const [preview, setPreview] = useState<S["InvitePreview"]>();
  const [read, setRead] = useState(false);
  const [problem, setProblem] = useState<string>();
  useEffect(() => {
    if (!token) return;
    api<S["InvitePreview"]>("invites/preview", { method: "POST", body: { token } }).then(setPreview, (failure: Error) =>
      setProblem(failure.message),
    );
  }, [token]);

  if (!token) return <p>This invite link is incomplete. Ask for a new one.</p>;
  if (problem && !preview) return <Problem text={problem} />;
  if (!preview) return <p className="loading">Loading…</p>;
  if (preview.already_member) {
    return (
      <p>
        You are already a member of {preview.org_name}. <Link to="/">Go to the library</Link>
      </p>
    );
  }
  if (preview.problem) return <p>This invite link {PROBLEM[preview.problem]}. Ask {preview.org_name} for a new one.</p>;

  async function join() {
    try {
      const joined = await api<S["AcceptOut"]>("invites/accept", { method: "POST", body: { token, acknowledged: true } });
      await api("orgs/active", { method: "POST", body: { org_id: joined.org_id } });
      nav.to(appUrl()); // a full reload: everything now runs in the new org
    } catch (failure) {
      setProblem((failure as Error).message);
    }
  }

  return (
    <article>
      <h1>Join {preview.org_name}</h1>
      <p>{preview.notice}</p>
      <label>
        <input type="checkbox" checked={read} onChange={(event) => setRead(event.target.checked)} /> I have read this
      </label>
      <Problem text={problem} />
      <div className="actions">
        <button disabled={!read} onClick={join}>
          Join as {preview.role}
        </button>
      </div>
    </article>
  );
}
