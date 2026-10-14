import { apiUrl, failure, request, spent } from "./client";

// each event's data has its own shape: reply {text}, notice and error {detail}, done {turn, ended, outcome}
export type SseEvent = { event: string; data: any };

/** Server-sent events from a fetch response (EventSource cannot POST). */
export async function* readSse(response: Response): AsyncGenerator<SseEvent> {
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    buffer += decoder.decode(value, { stream: true });
    let end: number;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      let event = "message";
      const data: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7);
        else if (line.startsWith("data: ")) data.push(line.slice(6));
      }
      yield { event, data: data.length ? JSON.parse(data.join("\n")) : null };
    }
  }
}

/** Sends the trainee's message and yields the turn's events: reply, notice, error, done. */
export async function* sendTurn(sessionId: string, text: string, interlocutor?: string): AsyncGenerator<SseEvent> {
  const body = interlocutor ? { text, interlocutor } : { text };
  const response = await fetch(apiUrl(`sessions/${sessionId}/turns`), request("POST", body));
  if (!response.ok) throw await failure(response);
  try {
    yield* readSse(response);
  } finally {
    spent(); // the turn ended: one usage refresh for the whole stream, not per chunk
  }
}

/** Triggers an in-character silence nudge when the trainee is silent or idle. */
export async function* sendNudge(sessionId: string): AsyncGenerator<SseEvent> {
  const response = await fetch(apiUrl(`sessions/${sessionId}/nudge`), request("POST", {}));
  if (!response.ok) throw await failure(response);
  try {
    yield* readSse(response);
  } finally {
    spent();
  }
}

/** Sends a question to the CCHN-grounded debrief Coach and streams citations, reply chunks, and done event. */
export async function* sendCoachQuestion(
  sessionId: string,
  question: string,
  history: Array<{ role: string; content: string }> = [],
): AsyncGenerator<SseEvent> {
  const response = await fetch(apiUrl(`sessions/${sessionId}/coach`), request("POST", { question, history }));
  if (!response.ok) throw await failure(response);
  try {
    yield* readSse(response);
  } finally {
    spent();
  }
}
