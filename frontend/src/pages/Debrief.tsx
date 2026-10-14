import { useEffect } from "react";
import { useParams } from "react-router";
import { spent, type S } from "../api/client";
import { DebriefCoach } from "../features/coach/DebriefCoach";
import { CchnDebriefSection } from "../features/debrief/CchnDebriefSection";
import { useLoad } from "../hooks";
import { DialCauses, FinalDials, HiddenFacts, Moments, OneFocus, OutcomeBanner, RuleFlags, Skills, bodyOf } from "../features/debrief/DebriefReport";
import { Problem } from "../ui";

const TERMINAL = new Set([401, 403, 404, 410]); // signing in again or a gone session: polling will not fix these

export function Debrief() {
  const { id } = useParams() as { id: string };
  const { data, error, status, settled, reload } = useLoad<S["DebriefOut"]>(`sessions/${id}/debrief`);
  useEffect(() => {
    if (data?.status === "ready" || data?.status === "failed") spent(); // the background work settled: refresh the header's allowance
  }, [data?.status, id]);
  useEffect(() => {
    if (status !== undefined && TERMINAL.has(status)) return; // 401/403/404/410: retrying will not fix these
    const waiting = data === undefined ? status !== undefined : data.status === "pending";
    if (!waiting) return; // ready, failed or unavailable: done; a first request still in flight: wait for it
    const timer = setTimeout(reload, 3000); // the debrief is written in the background; poll while pending, retry a transient failure
    return () => clearTimeout(timer);
  }, [data, status, settled, reload]);
  if (error) return <Problem text={error} />;
  if (!data) return <p className="loading">Loading…</p>;
  const summary = bodyOf(data).summary;
  return (
    <article className="debrief-page">
      <h1>Debrief</h1>
      <OutcomeBanner outcome={data.outcome} reached={data.reached ?? []} />
      {data.status === "pending" && <p>Writing your debrief… this page updates by itself.</p>}
      {data.status === "failed" && <p>The debrief could not be written; the scores below still apply.</p>}
      {data.status === "unavailable" && <p>No language model is configured, so there is no written debrief.</p>}
      {summary && <p className="debrief-summary">{summary}</p>}
      <div className="debrief-report">
        <div className="debrief-side">
          <Skills scores={data.scores} dimensions={data.dimensions} checks={bodyOf(data).score_check} scale={data.score_scale} />
          <HiddenFacts facts={data.hidden_facts} />
        </div>
        <div className="debrief-main">
          <Moments body={bodyOf(data)} />
          <DialCauses causes={data.dial_causes} />
          <OneFocus focus={bodyOf(data).one_focus} />
        </div>
      </div>
      <RuleFlags flags={data.flags ?? []} />
      <FinalDials dials={data.dials ?? {}} counterpartDials={data.counterpart_dials} />

      {/* CCHN Doctrine Debrief & Reflection Modules */}
      {data.status !== "pending" && data.cchn_debrief && (
        <CchnDebriefSection
          sessionId={id}
          cchnDebrief={data.cchn_debrief}
          initialReflection={(data.reflection as Record<string, string>) || null}
          onReflectionSaved={reload}
        />
      )}

      {/* Interactive AI Debrief Coach grounded in CCHN Doctrine */}
      {data.status !== "pending" && <DebriefCoach sessionId={id} />}
    </article>
  );
}
