import { useRef, useState, type FormEvent } from "react";
import { Link } from "react-router";
import { api, type S } from "../api/client";
import { useLoad } from "../hooks";
import { useMe } from "../me";
import { Problem } from "../ui";

export function OrgPage() {
  const me = useMe();
  const members = useLoad<S["MemberOut"][]>("org/members");
  const invites = useLoad<S["InviteOut"][]>("org/invites");
  const sessions = useLoad<S["SessionCard"][]>("sessions?scope=org");
  const [days, setDays] = useState(7);
  const [uses, setUses] = useState(10);
  const [created, setCreated] = useState<string>();
  const [problem, setProblem] = useState<string>();
  const busy = useRef(false);
  const [pending, setPending] = useState(false);

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

  function createInvite(event: FormEvent) {
    event.preventDefault();
    void act(async () => {
      const invite = await api<S["InviteOut"]>("org/invites", { method: "POST", body: { days, max_uses: uses } });
      setCreated(invite.url ?? undefined);
      await invites.reload();
    });
  }

  return (
    <>
      <h1>{me.active_org.name}</h1>
      <Problem text={problem ?? members.error} />

      <h2>Members</h2>
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Email</th>
            <th>Role</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {members.data?.map((member) => (
            <tr key={member.user_id}>
              <td>{member.display_name}</td>
              <td>{member.email ?? "—"}</td>
              <td>
                <select
                  aria-label={`Role of ${member.display_name}`}
                  value={member.role}
                  onChange={(event) =>
                    act(async () => {
                      await api(`org/members/${member.user_id}`, { method: "PATCH", body: { role: event.target.value } });
                      await members.reload();
                    })
                  }
                >
                  <option value="member">Member</option>
                  <option value="admin">Admin</option>
                </select>
              </td>
              <td>
                <button
                  className="danger"
                  onClick={() =>
                    confirm(`Remove ${member.display_name} from ${me.active_org.name}?`) &&
                    act(async () => {
                      await api(`org/members/${member.user_id}`, { method: "DELETE" });
                      await members.reload();
                    })
                  }
                >
                  Remove
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>Invite links</h2>
      <form className="row" onSubmit={createInvite}>
        <label>
          Valid for (days) <input type="number" min={1} max={30} value={days} onChange={(event) => setDays(Number(event.target.value))} />
        </label>
        <label>
          Uses <input type="number" min={1} max={100} value={uses} onChange={(event) => setUses(Number(event.target.value))} />
        </label>
        <button disabled={pending}>Create a link</button>
      </form>
      {created && (
        <p>
          Copy this link now; it is shown only once: <code>{created}</code>{" "}
          <button type="button" className="secondary" onClick={() => navigator.clipboard?.writeText(created)}>
            Copy
          </button>
        </p>
      )}
      <table>
        <thead>
          <tr>
            <th>Role</th>
            <th>Expires</th>
            <th>Used</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {invites.data?.map((invite) => (
            <tr key={invite.id}>
              <td>{invite.role}</td>
              <td>{new Date(invite.expires_at).toLocaleString()}</td>
              <td>
                {invite.uses} of {invite.max_uses}
              </td>
              <td>
                <button
                  className="danger"
                  onClick={() =>
                    act(async () => {
                      await api(`org/invites/${invite.id}`, { method: "DELETE" });
                      await invites.reload();
                    })
                  }
                >
                  Revoke
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>Sessions</h2>
      <table>
        <thead>
          <tr>
            <th>Player</th>
            <th>Scenario</th>
            <th>Status</th>
            <th>Turn</th>
            <th>Result</th>
            <th>Started</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {sessions.data?.map((session) => (
            <tr key={session.id}>
              <td>{session.player}</td>
              <td>{session.title}</td>
              <td>{session.status}</td>
              <td>{session.turn}</td>
              <td>{session.result ?? "—"}</td>
              <td>{new Date(session.created_at).toLocaleString()}</td>
              <td>
                {session.player_id === me.id ? (
                  // your own session: progress is hidden from you while it runs (the server enforces it too)
                  session.status === "active" ? (
                    <Link to={`/play/${session.id}`}>Continue</Link>
                  ) : (
                    <Link to={`/sessions/${session.id}/debrief`}>Debrief</Link>
                  )
                ) : (
                  <>
                    <Link to={`/sessions/${session.id}/watch`}>Watch</Link>
                    {session.status === "ended" && (
                      <>
                        {" · "}
                        <Link to={`/sessions/${session.id}/debrief`}>Debrief</Link>
                      </>
                    )}
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
