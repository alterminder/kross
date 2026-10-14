import { useRef, useState, type TextareaHTMLAttributes } from "react";
import { Link, useNavigate } from "react-router";
import { api, apiUrl, type S } from "../api/client";
import { Problem } from "../ui";

type Turn = { question: string; answer: string };

const MAX_STEPS = 5; // step 1 is the brief, steps 2-5 are up to four follow-up questions

/** A text area with the animated gradient border. */
function GlowTextarea({ label, ...props }: { label: string } & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <div className="glow-border">
      <textarea aria-label={label} rows={8} {...props} />
    </div>
  );
}

/** The painted picture of the scene so far: picture 1 reveals itself, the final painting crossfades over it. */
function Picture({ first, final, pending }: { first: string | null; final: string | null; pending: boolean }) {
  return (
    <div className="builder-picture">
      {first && <img className="painting" src={first} alt="" />}
      {final && <img className="painting painting-final" src={final} alt="Painted scene of your scenario" />}
      {pending && <p className="painting-label">Painting…</p>}
    </div>
  );
}

export function Builder() {
  const navigate = useNavigate();
  const [phase, setPhase] = useState<"intro" | "building" | "finishing" | "done" | "failed">("intro");
  const [brief, setBrief] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState<string | null>(null);
  const [answer, setAnswer] = useState("");
  const [picture, setPicture] = useState<string | null>(null);
  const [finalPicture, setFinalPicture] = useState<string | null>(null);
  const [painting, setPainting] = useState(0);
  const [created, setCreated] = useState<{ id: string; title: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string>();
  const firstPicture = useRef<Promise<string | null>>(Promise.resolve(null));
  const locked = useRef(false);

  /** One user operation at a time: a synchronous lock, released when the whole operation (including finish) settles. */
  function acquire(): boolean {
    if (locked.current) return false;
    locked.current = true;
    return true;
  }

  function composed(details: Turn[]): string {
    const extras = details.map((turn) => `Q: ${turn.question}\nA: ${turn.answer}`).join("\n");
    return extras ? `${brief}\n\nAdditional details:\n${extras}` : brief;
  }

  /** The painted picture of `text`. Decoration: a failed or cancelled call is a silent no-picture. */
  async function paint(
    text: string,
    final: boolean,
    previous: string | null,
    signal?: AbortSignal,
  ): Promise<string | null> {
    try {
      const out = await api<S["PictureOut"]>("scenarios/builder/picture", {
        method: "POST",
        body: { text, previous_image: previous?.split(",")[1] ?? null, final },
        signal,
      });
      return out.image;
    } catch {
      return null;
    }
  }

  /** Bounded decoration: resolves null at the deadline; the timer is cleared when the work settles first. */
  function within<T>(ms: number, work: Promise<T>): Promise<T | null> {
    return new Promise((resolve) => {
      const timer = setTimeout(() => resolve(null), ms);
      work.then(
        (value) => {
          clearTimeout(timer);
          resolve(value);
        },
        () => {
          clearTimeout(timer);
          resolve(null);
        },
      );
    });
  }

  /** The final painting in the background under one 120 s deadline: once it expires no new request is started and an
      in-flight one is cancelled. Leaving the page early loses only the cover. */
  async function coverArtwork(scenarioId: string, text: string): Promise<void> {
    setPainting((n) => n + 1);
    try {
      const deadline = Date.now() + 120_000;
      const previous = await within(deadline - Date.now(), firstPicture.current);
      if (Date.now() >= deadline) return; // out of time: never start the final paid request
      const controller = new AbortController();
      const cancel = setTimeout(() => controller.abort(), deadline - Date.now());
      try {
        const painted = await paint(text, true, previous, controller.signal);
        if (!painted) return;
        setFinalPicture(painted);
        await putCover(scenarioId, painted);
      } finally {
        clearTimeout(cancel);
      }
    } finally {
      setPainting((n) => n - 1);
    }
  }

  /** The painting as WebP for the library card: at most 1600x900, quality 0.8, like the theme covers. */
  async function toWebp(dataUrl: string): Promise<Blob> {
    const image = new Image();
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve();
      image.onerror = () => reject(new Error("The picture could not be read"));
      image.src = dataUrl;
    });
    const scale = Math.min(1, 1600 / image.width, 900 / image.height);
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(image.width * scale);
    canvas.height = Math.round(image.height * scale);
    canvas.getContext("2d")!.drawImage(image, 0, 0, canvas.width, canvas.height);
    return new Promise<Blob>((resolve) => canvas.toBlob((blob) => resolve(blob as Blob), "image/webp", 0.8));
  }

  /** The final painting becomes the scenario's cover. A failure saves without one: the card keeps its theme cover. */
  async function putCover(scenarioId: string, image: string): Promise<void> {
    try {
      const blob = await toWebp(image);
      await fetch(apiUrl(`scenarios/${scenarioId}/cover-image`), {
        method: "PUT",
        credentials: "same-origin",
        headers: { "X-Requested-With": "nlab", "Content-Type": "image/webp" },
        body: blob,
      });
    } catch {
      // the cover is decoration: save without it
    }
  }

  async function finish(details: Turn[]): Promise<void> {
    if (!acquire()) return;
    try {
      setPhase("finishing");
      setProblem(undefined);
      const text = composed(details);
      const draft = await api<S["ConversionOut"]>("scenarios/convert", { method: "POST", body: { text, filename: "" } });
      if (!draft.scenario) throw new Error(draft.errors.join("; ") || "The brief could not be turned into a scenario.");
      const saved = await api<S["ScenarioDetail"]>("scenarios", { method: "POST", body: { content: draft.scenario } });
      setCreated({ id: saved.id, title: saved.title });
      setPhase("done"); // the scenario is safe now; the cover is decoration and follows in the background
      void coverArtwork(saved.id, text);
    } catch (failure) {
      setProblem((failure as Error).message);
      setPhase("failed");
    } finally {
      setBusy(false);
      locked.current = false;
    }
  }

  async function step(body: S["BuilderIn"]): Promise<void> {
    if (!acquire()) return; // two clicks in one batch make one request
    let ended: Turn[] | null = null;
    try {
      setBusy(true);
      setProblem(undefined);
      const out = await api<S["BuilderOut"]>("scenarios/builder", { method: "POST", body });
      if (body.question === null) {
        // picture 1 paints the brief; the question never waits for it
        setPainting((n) => n + 1);
        firstPicture.current = paint(brief, false, null).then((image) => {
          if (image) setPicture(image);
          setPainting((n) => n - 1);
          return image;
        });
      }
      if (body.question !== null) {
        // the new turn comes from the request snapshot, so a second click cannot overwrite it
        const details = [...(body.turns ?? []), { question: body.question ?? "", answer: out.answer ?? "" }];
        setTurns(details);
        setAnswer("");
        if (out.done) ended = details;
      } else if (out.done) {
        ended = [...(body.turns ?? [])];
      }
      if (ended === null) {
        setPhase("building");
        setQuestion(out.question);
      }
    } catch (failure) {
      setProblem((failure as Error).message); // the text area keeps what the user wrote
    } finally {
      setBusy(false);
      locked.current = false;
    }
    if (ended !== null) await finish(ended); // finish takes the lock synchronously at its entry
  }

  async function playNow() {
    if (!created || !acquire()) return;
    try {
      setBusy(true);
      setProblem(undefined);
      const session = await api<S["SessionOut"]>("sessions", { method: "POST", body: { scenario_id: created.id, mode: "playtest" } });
      navigate(`/play/${session.id}?onboard=1`);
    } catch (failure) {
      setProblem((failure as Error).message);
    } finally {
      setBusy(false);
      locked.current = false;
    }
  }

  if (phase === "intro") {
    return (
      <article className="builder-intro">
        <h1>Describe your scenario</h1>
        <p className="subtitle">Paste a short brief: the story, the place, the people involved, what is at stake.</p>
        <GlowTextarea label="Your brief" value={brief} onChange={(event) => setBrief(event.target.value)} />
        <Problem text={problem} />
        <div className="actions">
          <button
            disabled={busy || !brief.trim()}
            onClick={() => step({ brief, turns: [], question: null, answer: null, improvise: false })}
          >
            {busy ? "Thinking…" : "Submit and continue"}
          </button>
        </div>
      </article>
    );
  }

  return (
    <div className="builder">
      <section className="builder-panel">
        {phase === "done" && created ? (
          <>
            <h1>Your scenario is ready</h1>
            <p className="subtitle">{created.title}</p>
            <Problem text={problem} />
            <div className="actions">
              <button onClick={playNow} disabled={busy}>
                Play it now
              </button>
              <Link className="button secondary" to={`/scenarios/${created.id}/edit`}>
                Fine-tune in the editor
              </Link>
            </div>
            <p>
              <Link to="/">Back to the scenario list</Link>
            </p>
          </>
        ) : phase === "finishing" ? (
          <>
            <h1>Building your scenario…</h1>
            <p className="subtitle">This can take up to a minute.</p>
          </>
        ) : (
          <>
            <p className="builder-step">Step {turns.length + 2} of {MAX_STEPS}</p>
            <div className="builder-known">
              <h2>What we know so far</h2>
              <dl>
                <dt>Brief</dt>
                <dd>{brief.length > 200 ? `${brief.slice(0, 200)}…` : brief}</dd>
                {turns.map((turn, i) => (
                  <div key={i}>
                    <dt>{turn.question}</dt>
                    <dd>{turn.answer}</dd>
                  </div>
                ))}
              </dl>
            </div>
            {phase === "failed" ? (
              <>
                <Problem text={problem} />
                <div className="actions">
                  <button onClick={() => finish(turns)}>Try again</button>
                </div>
              </>
            ) : (
              <>
                <h2 aria-live="polite" className="builder-question">
                  {question}
                </h2>
                <GlowTextarea
                  label="Your answer"
                  rows={5}
                  value={answer}
                  onChange={(event) => setAnswer(event.target.value)}
                />
                <Problem text={problem} />
                <div className="actions">
                  <button
                    disabled={busy || !answer.trim()}
                    onClick={() => step({ brief, turns, question, answer, improvise: false })}
                  >
                    {busy ? "Thinking…" : "Submit"}
                  </button>
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() => step({ brief, turns, question, answer: null, improvise: true })}
                  >
                    Improvise
                  </button>
                </div>
              </>
            )}
          </>
        )}
      </section>
      <Picture first={picture} final={finalPicture} pending={painting > 0} />
    </div>
  );
}
