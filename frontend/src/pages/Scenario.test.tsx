import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router";
import { MeContext } from "../me";
import { ME, deferred, json, renderAt, stubApi } from "../test-utils";
import { ScenarioPage } from "./Scenario";

const SCENARIO = {
  id: "c1",
  title: "Hostile checkpoint",
  cover: "checkpoint",
  visibility: "public",
  version: 1,
  submitted: false,
  brief: { situation: "A roadblock at dawn." },
  content: null,
  can_edit: false,
};

describe("ScenarioPage", () => {
  it("sends exactly one POST when Start is double-clicked while the request is pending", async () => {
    const fetchMock = stubApi({
      "GET scenarios/c1": SCENARIO,
      "POST sessions": () => new Promise<Response>(() => {}), // never settles: still pending at the second click
    });
    renderAt("/scenarios/c1", <ScenarioPage />, "/scenarios/:id");
    const start = await screen.findByRole("button", { name: "Start" });
    fireEvent.click(start);
    fireEvent.click(start);
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
    expect(start).toBeDisabled();
  });

  it("offers Duplicate only where the full scenario is readable, and opens the copy in the editor", async () => {
    const mine = { ...SCENARIO, visibility: "private", content: { id: "c1" }, can_edit: true };
    const fetchMock = stubApi({
      "GET scenarios/c1": mine,
      "POST scenarios/c1/duplicate": () => json({ ...mine, id: "c2", title: "Hostile checkpoint (copy)" }, 201),
    });
    render(
      <MeContext.Provider value={ME}>
        <MemoryRouter initialEntries={["/scenarios/c1"]}>
          <Routes>
            <Route path="/scenarios/:id" element={<ScenarioPage />} />
            <Route path="/scenarios/:id/edit" element={<p>Editing a copy</p>} />
          </Routes>
        </MemoryRouter>
      </MeContext.Provider>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Duplicate" }));
    expect(await screen.findByText("Editing a copy")).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
  });

  it("hides Duplicate from a player who sees only the brief", async () => {
    stubApi({ "GET scenarios/c1": SCENARIO });
    renderAt("/scenarios/c1", <ScenarioPage />, "/scenarios/:id");
    await screen.findByRole("button", { name: "Start" });
    expect(screen.queryByRole("button", { name: "Duplicate" })).not.toBeInTheDocument();
  });

  it("does not let a pending save's reload strand the next scenario in Loading", async () => {
    const save = deferred();
    const loadB = deferred();
    const a = { id: "a", title: "Scenario A", brief: {}, cover: "checkpoint", content: {}, can_edit: true, visibility: "private" };
    const b = { ...a, id: "b", title: "Scenario B" };
    stubApi({
      "GET scenarios/a": a,
      "GET scenarios/b": () => loadB.promise,
      "POST scenarios/a/visibility": () => save.promise, // a save that stays pending across the navigation
    });
    function Next() {
      const navigate = useNavigate();
      return <button onClick={() => navigate("/scenarios/b")}>Go B</button>;
    }
    render(
      <MeContext.Provider value={{ ...ME, active_org: { ...ME.active_org, personal: false } }}>
        <MemoryRouter initialEntries={["/scenarios/a"]}>
          <Next />
          <Routes>
            <Route path="/scenarios/:id" element={<ScenarioPage />} />
          </Routes>
        </MemoryRouter>
      </MeContext.Provider>,
    );
    await screen.findByRole("heading", { name: "Scenario A" });
    fireEvent.change(screen.getByLabelText("Visible to"), { target: { value: "org" } });
    fireEvent.click(screen.getByRole("button", { name: "Go B" }));
    await act(async () => save.resolve(json({})));
    await act(async () => loadB.resolve(json(b)));
    expect(screen.getByRole("heading", { name: "Scenario B" })).toBeInTheDocument();
  });

  it("renders difficulty, time, and tags pills, and sanitizes legacy situation", async () => {
    const detailed = {
      ...SCENARIO,
      difficulty: "intermediate",
      minutes: 15,
      skills: ["Quality of Information", "Active Questioning"],
      brief: {
        situation:
          "A roadblock at dawn. What you know (information quality, CCHN Tool 1, out of 12): soldiers are armed; road is closed.",
      },
    };
    stubApi({ "GET scenarios/c1": detailed });
    renderAt("/scenarios/c1", <ScenarioPage />, "/scenarios/:id");

    expect(await screen.findByText("Intermediate")).toBeInTheDocument();
    expect(screen.getByText(/15 min/)).toBeInTheDocument();
    expect(screen.getByText("Quality of Information")).toBeInTheDocument();
    expect(screen.getByText("Active Questioning")).toBeInTheDocument();

    // Verify sanitized situation is displayed without the "What you know" appendix
    expect(screen.getByText("A roadblock at dawn.")).toBeInTheDocument();
    expect(screen.queryByText(/soldiers are armed/)).not.toBeInTheDocument();
  });
});
