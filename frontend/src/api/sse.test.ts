// @vitest-environment node
import { describe, expect, it } from "vitest";
import { readSse, type SseEvent } from "./sse";

function streamOf(...chunks: Uint8Array[]): Response {
  return new Response(
    new ReadableStream({
      start(controller) {
        for (const chunk of chunks) controller.enqueue(chunk);
        controller.close();
      },
    }),
  );
}

describe("readSse", () => {
  it("yields events split across chunks, even inside a multi-byte character", async () => {
    const bytes = new TextEncoder().encode(
      'event: reply\ndata: {"text": "Déjà"}\n\nevent: done\ndata: {"turn": 1, "ended": false, "outcome": null}\n\n',
    );
    const cut = bytes.indexOf(0xc3) + 1; // between the two bytes of "é"
    const seen: SseEvent[] = [];
    for await (const event of readSse(streamOf(bytes.slice(0, cut), bytes.slice(cut)))) seen.push(event);
    expect(seen).toEqual([
      { event: "reply", data: { text: "Déjà" } },
      { event: "done", data: { turn: 1, ended: false, outcome: null } },
    ]);
  });
});
