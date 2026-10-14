import { useRef, useState, type FormEvent } from "react";
import { api, type S } from "../api/client";
import { useLoad } from "../hooks";
import { Problem, Table } from "../ui";

export function UsagePage() {
  const { data, error } = useLoad<S["UsageOut"]>("admin/usage?days=7");
  const [name, setName] = useState("");
  const [created, setCreated] = useState<S["NewOrgOut"]>();
  const [problem, setProblem] = useState<string>();
  const pending = useRef(false);

  async function createOrg(event: FormEvent) {
    event.preventDefault();
    if (pending.current) return;
    pending.current = true;
    setProblem(undefined);
    try {
      setCreated(await api<S["NewOrgOut"]>("admin/orgs", { method: "POST", body: { name } }));
      setName("");
    } catch (failure) {
      setProblem((failure as Error).message);
    } finally {
      pending.current = false;
    }
  }

  return (
    <>
      <h1>Usage</h1>
      <Problem text={error} />
      {data && (
        <>
          <p>
            Today: {data.spent_today_usd.toFixed(2)} USD
            {data.ceiling_usd > 0 ? ` of the ${data.ceiling_usd.toFixed(2)} USD daily ceiling` : " (no daily ceiling)"}.
          </p>
          <h2>Per day (UTC)</h2>
          <Table rows={data.days} />
          <h2>Per model</h2>
          <Table rows={data.models} />
          <h2>Per organisation today</h2>
          <Table rows={data.orgs_today} />
        </>
      )}
      <h2>New organisation</h2>
      <form className="row" onSubmit={createOrg}>
        <label>
          Name <input value={name} required maxLength={200} onChange={(event) => setName(event.target.value)} />
        </label>
        <button>Create</button>
      </form>
      <Problem text={problem} />
      {created && (
        <p>
          {created.name} exists. Send this link to its first admin; it is shown only once: <code>{created.admin_invite_url}</code>
        </p>
      )}
    </>
  );
}
