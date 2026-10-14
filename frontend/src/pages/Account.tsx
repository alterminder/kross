import { useState, type FormEvent } from "react";
import { api, appUrl, nav } from "../api/client";
import { useMe } from "../me";
import { Problem } from "../ui";

export function Account() {
  const me = useMe();
  const [problem, setProblem] = useState<string>();
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);

  async function createOrg(event: FormEvent) {
    event.preventDefault();
    setCreating(true);
    setProblem(undefined);
    try {
      await api("orgs", { method: "POST", body: { name } });
      nav.to(appUrl("org")); // a full reload: /api/me now shows the new active org
    } catch (failure) {
      setProblem((failure as Error).message);
      setCreating(false);
    }
  }

  async function remove() {
    if (!confirm("Delete your account? Your sessions, debriefs and private scenarios are deleted for good. Organisations where you are the only member are deleted too.")) return;
    try {
      await api("me", { method: "DELETE" });
      nav.to(appUrl("signin"));
    } catch (failure) {
      setProblem((failure as Error).message);
    }
  }
  return (
    <>
      <h1>Account</h1>
      <dl>
        <dt>Name</dt>
        <dd>{me.display_name}</dd>
        <dt>Email</dt>
        <dd>{me.email ?? "—"}</dd>
      </dl>
      <Problem text={problem} />
      <section>
        <h2>Start an organisation</h2>
        <form onSubmit={createOrg}>
          <label>
            Organisation name
            <input value={name} required maxLength={200} onChange={(event) => setName(event.target.value)} />
          </label>
          <div className="actions">
            <button type="submit" disabled={creating}>
              Create organisation
            </button>
          </div>
        </form>
        <p className="muted">You become its admin: you invite trainees and can follow their sessions.</p>
      </section>
      <div className="actions">
        <button className="danger" onClick={remove}>
          Delete my account
        </button>
      </div>
    </>
  );
}
