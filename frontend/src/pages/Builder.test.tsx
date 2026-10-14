import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { deferred, json, renderAt, stubApi } from "../test-utils";
import { Builder } from "./Builder";

const BRIEF = "A two-truck food convoy is stopped at a checkpoint outside Al-Masirah.";
const QUESTION = "Who commands the checkpoint, and what does he want?";
const NEXT = "What is at stake if the trucks are delayed?";
const INVENTED = "Major Deng commands the checkpoint; he wants a written request from the NGO headquarters.";
const PICTURE = "data:image/png;base64,AAAA";
const FINAL = "data:image/png;base64,BBBB";

/** jsdom decodes no images and has no canvas: enough of both for the WebP conversion. */
function stubCanvas() {
  vi.stubGlobal(
    "Image",
    class {
      width = 1600;
      height = 900;
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      set src(_value: string) {
        queueMicrotask(() => this.onload?.());
      }
    },
  );
  HTMLCanvasElement.prototype.getContext = (() => ({
    drawImage() {},
  })) as unknown as typeof HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.toBlob = ((callback: BlobCallback) => {
    callback(new Blob([new Uint8Array([82, 73, 70, 70, 87, 69, 66, 80])], { type: "image/webp" }));
  }) as typeof HTMLCanvasElement.prototype.toBlob;
}

/** The scripted builder endpoint plus an immediate no-picture; extra routes override the picture step. */
function stubBuilder(extra: Record<string, unknown> = {}) {
  return stubApi({
    "POST scenarios/builder": (init?: RequestInit) => {
      const body = JSON.parse(String(init?.body));
      if (body.improvise) return json({ answer: INVENTED, question: NEXT, done: false });
      if (body.question) return json({ answer: body.answer, question: null, done: true });
      return json({ answer: null, question: QUESTION, done: false });
    },
    "POST scenarios/builder/picture": () => json({ image: null }),
    ...extra,
  });
}

describe("Builder", () => {
  it("shows the question before the picture resolves, then paints it in", async () => {
    const painting = deferred();
    stubBuilder({ "POST scenarios/builder/picture": () => painting.promise });
    const { container } = renderAt("/scenarios/new", <Builder />);
    await userEvent.type(await screen.findByLabelText("Your brief"), BRIEF);
    await userEvent.click(screen.getByRole("button", { name: "Submit and continue" }));
    await screen.findByText(QUESTION); // the question does not wait for the picture
    expect(screen.getByText("Painting…")).toBeInTheDocument();
    expect(container.querySelectorAll("img")).toHaveLength(0);
    painting.resolve(json({ image: PICTURE }));
    await waitFor(() => expect(container.querySelectorAll("img.painting")).toHaveLength(1));
    expect(screen.queryByText("Painting…")).toBeNull();
  });

  it("improvise shows the invented answer among the known details", async () => {
    stubBuilder();
    renderAt("/scenarios/new", <Builder />);
    await userEvent.type(await screen.findByLabelText("Your brief"), BRIEF);
    await userEvent.click(screen.getByRole("button", { name: "Submit and continue" }));
    await userEvent.click(await screen.findByRole("button", { name: "Improvise" }));
    expect(await screen.findByText(INVENTED)).toBeInTheDocument();
    expect(await screen.findByText(NEXT)).toBeInTheDocument();
  });

  it("finishes by converting the brief and putting the final painting as the cover", async () => {
    stubCanvas();
    const texts: string[] = [];
    const paints: { text: string; previous_image: string | null; final: boolean }[] = [];
    const covers: unknown[] = [];
    stubBuilder({
      "POST scenarios/builder/picture": (init?: RequestInit) => {
        const body = JSON.parse(String(init?.body));
        paints.push(body);
        return json({ image: body.final ? FINAL : PICTURE });
      },
      "POST scenarios/convert": (init?: RequestInit) => {
        texts.push(JSON.parse(String(init?.body)).text);
        return json({ scenario: { title: "Hostile checkpoint" }, errors: [], warnings: [] });
      },
      "POST scenarios": () => json({ id: "s1", title: "Hostile checkpoint" }),
      "PUT scenarios/s1/cover-image": (init?: RequestInit) => {
        covers.push(init?.body);
        return json(null, 204);
      },
    });
    const { container } = renderAt("/scenarios/new", <Builder />);
    await userEvent.type(await screen.findByLabelText("Your brief"), BRIEF);
    await userEvent.click(screen.getByRole("button", { name: "Submit and continue" }));
    await userEvent.type(await screen.findByLabelText("Your answer"), "The food must reach the town before dark.");
    await userEvent.click(screen.getByRole("button", { name: "Submit" }));
    expect(await screen.findByText("Your scenario is ready")).toBeInTheDocument();
    expect(screen.getByText("Hostile checkpoint")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Fine-tune in the editor" })).toHaveAttribute("href", "/scenarios/s1/edit");
    expect(texts[0]).toContain(BRIEF);
    expect(texts[0]).toContain("Additional details:");
    expect(texts[0]).toContain(QUESTION);
    const final = paints.find((paint) => paint.final);
    expect(final?.previous_image).toBe("AAAA"); // the edit builds on picture 1
    expect(final?.text).toContain("Additional details:");
    await waitFor(() => expect(covers).toHaveLength(1)); // the final painting becomes the scenario's cover
    await waitFor(() => expect(container.querySelector("img.painting-final")).toHaveAttribute("src", FINAL));
  });

  it("saves the scenario before the final picture resolves, then uploads it as the cover", async () => {
    stubCanvas();
    const artwork = deferred();
    const saves: unknown[] = [];
    const covers: unknown[] = [];
    stubBuilder({
      "POST scenarios/builder/picture": (init?: RequestInit) =>
        JSON.parse(String(init?.body)).final ? artwork.promise : json({ image: PICTURE }),
      "POST scenarios/convert": () => json({ scenario: { title: "Hostile checkpoint" }, errors: [], warnings: [] }),
      "POST scenarios": (init?: RequestInit) => {
        saves.push(init?.body);
        return json({ id: "s1", title: "Hostile checkpoint" });
      },
      "PUT scenarios/s1/cover-image": (init?: RequestInit) => {
        covers.push(init?.body);
        return json(null, 204);
      },
    });
    const { container } = renderAt("/scenarios/new", <Builder />);
    await userEvent.type(await screen.findByLabelText("Your brief"), BRIEF);
    await userEvent.click(screen.getByRole("button", { name: "Submit and continue" }));
    await userEvent.type(await screen.findByLabelText("Your answer"), "The food must reach the town before dark.");
    await userEvent.click(screen.getByRole("button", { name: "Submit" }));
    expect(await screen.findByText("Your scenario is ready")).toBeInTheDocument(); // saved before the picture lands
    expect(saves).toHaveLength(1);
    expect(covers).toHaveLength(0);
    artwork.resolve(json({ image: FINAL }));
    await waitFor(() => expect(covers).toHaveLength(1)); // the cover follows once the painting arrives
    await waitFor(() => expect(container.querySelector("img.painting-final")).toHaveAttribute("src", FINAL));
  });

  it("two clicks in one batch make one request and keep the answer", async () => {
    const gate = deferred();
    const builders: { question: string | null; answer: string | null }[] = [];
    const texts: string[] = [];
    const saves: unknown[] = [];
    stubApi({
      "POST scenarios/builder": (init?: RequestInit) => {
        const body = JSON.parse(String(init?.body));
        builders.push(body);
        return body.question ? gate.promise : json({ answer: null, question: QUESTION, done: false });
      },
      "POST scenarios/builder/picture": () => json({ image: null }),
      "POST scenarios/convert": (init?: RequestInit) => {
        texts.push(JSON.parse(String(init?.body)).text);
        return json({ scenario: { title: "Hostile checkpoint" }, errors: [], warnings: [] });
      },
      "POST scenarios": (init?: RequestInit) => {
        saves.push(init?.body);
        return json({ id: "s1", title: "Hostile checkpoint" });
      },
    });
    renderAt("/scenarios/new", <Builder />);
    await userEvent.type(await screen.findByLabelText("Your brief"), BRIEF);
    await userEvent.click(screen.getByRole("button", { name: "Submit and continue" }));
    await screen.findByText(QUESTION);
    await userEvent.type(screen.getByLabelText("Your answer"), "The food must reach the town before dark.");
    const submit = screen.getByRole("button", { name: "Submit" });
    act(() => {
      fireEvent.click(submit); // both clicks run before React commits: only the lock keeps the second out
      fireEvent.click(submit);
    });
    gate.resolve(json({ answer: "The food must reach the town before dark.", question: null, done: true }));
    expect(await screen.findByText("Your scenario is ready")).toBeInTheDocument();
    expect(builders).toHaveLength(2); // the brief plus one accepted answer, not two
    expect(saves).toHaveLength(1);
    expect(texts[0]).toContain("The food must reach the town before dark."); // the answer was not lost
    expect(texts[0]).toContain(QUESTION);
  });

  it("never starts the final picture request after the deadline", async () => {
    stubCanvas();
    const first = deferred();
    const paints: { final: boolean }[] = [];
    stubApi({
      "POST scenarios/builder": (init?: RequestInit) => {
        const body = JSON.parse(String(init?.body));
        return body.question
          ? json({ answer: body.answer, question: null, done: true })
          : json({ answer: null, question: QUESTION, done: false });
      },
      "POST scenarios/builder/picture": (init?: RequestInit) => {
        const body = JSON.parse(String(init?.body));
        paints.push(body);
        return body.final ? json({ image: FINAL }) : first.promise;
      },
      "POST scenarios/convert": () => json({ scenario: { title: "Hostile checkpoint" }, errors: [], warnings: [] }),
      "POST scenarios": () => json({ id: "s1", title: "Hostile checkpoint" }),
    });
    renderAt("/scenarios/new", <Builder />);
    await userEvent.type(await screen.findByLabelText("Your brief"), BRIEF);
    await userEvent.click(screen.getByRole("button", { name: "Submit and continue" }));
    await screen.findByText(QUESTION);
    await userEvent.type(screen.getByLabelText("Your answer"), "The food must reach the town before dark.");
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] }); // the deadline becomes fireable
    fireEvent.click(screen.getByRole("button", { name: "Submit" }));
    await act(async () => {}); // convert and save settle: the success screen appears with picture 1 still pending
    expect(screen.getByText("Your scenario is ready")).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(120_000); // the deadline expires while picture 1 is still pending
    });
    await act(async () => {});
    first.resolve(json({ image: PICTURE })); // picture 1 arrives late
    await act(async () => {});
    expect(paints.filter((paint) => paint.final)).toHaveLength(0); // no final paid request after the deadline
    vi.useRealTimers();
  });

  it("a conversion error shows the problem and Try again re-runs the finish", async () => {
    stubCanvas();
    const texts: string[] = [];
    let conversions = 0;
    stubBuilder({
      "POST scenarios/convert": (init?: RequestInit) => {
        conversions += 1;
        texts.push(JSON.parse(String(init?.body)).text);
        return conversions === 1
          ? json({ scenario: null, errors: ["title is required"], warnings: [] })
          : json({ scenario: { title: "Hostile checkpoint" }, errors: [], warnings: [] });
      },
      "POST scenarios": () => json({ id: "s1", title: "Hostile checkpoint" }),
    });
    renderAt("/scenarios/new", <Builder />);
    await userEvent.type(await screen.findByLabelText("Your brief"), BRIEF);
    await userEvent.click(screen.getByRole("button", { name: "Submit and continue" }));
    await userEvent.type(await screen.findByLabelText("Your answer"), "The food must reach the town before dark.");
    await userEvent.click(screen.getByRole("button", { name: "Submit" }));
    expect(await screen.findByText("title is required")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Your scenario is ready")).toBeInTheDocument();
    expect(conversions).toBe(2); // the same brief and answers, converted again
    expect(texts[1]).toContain(BRIEF);
    expect(texts[1]).toContain(QUESTION);
    expect(texts[1]).toContain("The food must reach the town before dark."); // nothing typed is lost
  });
});
