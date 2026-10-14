import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { S } from "../../api/client";
import { PreparationView } from "./PreparationView";

const MOCK_SESSION: S["SessionOut"] = {
  id: "s1",
  scenario_id: "c1",
  title: "Access to IDP Camp",
  cover: "camp",
  mode: "solo",
  status: "active",
  turn: 0,
  turn_running: false,
  brief: { situation: "Test brief situation" },
  transcript: [],
  outcome: null,
  debrief_status: null,
  preparation: null,
  preparation_modules: ["island_of_agreements", "level_and_narrative", "lines_and_options"],
  preparation_minutes: 5,
  phases: [],
  warning_minutes: [5, 1],
  on_timeout: "guide",
  silence_seconds: 90,
  counterparts: [],
  stakeholders: [],
};

describe("PreparationView", () => {
  it("renders module navigation tabs and timer", () => {
    render(<PreparationView session={MOCK_SESSION} onSave={vi.fn()} onSkip={vi.fn()} />);

    expect(screen.getByText("STRATEGIC PREPARATION (NAIVASHA GRID)")).toBeInTheDocument();
    expect(screen.getByText("Access to IDP Camp")).toBeInTheDocument();
    expect(screen.getByText(/5:00/)).toBeInTheDocument();

    expect(screen.getByRole("button", { name: /Island of Agreements/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Level & Narrative/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Lines & Options/i })).toBeInTheDocument();
  });

  it("switches tabs to show Level & Narrative fields", () => {
    render(<PreparationView session={MOCK_SESSION} onSave={vi.fn()} onSkip={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: /Level & Narrative/i }));

    expect(screen.getByLabelText(/WHY \(Identity & Core Humanitarian Principles\)/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/HOW \(Mandate, Policies & Modalities\)/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/WHAT \(Specific Operational Transaction\)/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Expected Negotiation Level/i)).toBeInTheDocument();
  });

  it("calls onSave with filled data when clicking Save & Enter Negotiation", async () => {
    const onSave = vi.fn();
    render(<PreparationView session={MOCK_SESSION} onSave={onSave} onSkip={vi.fn()} />);

    // In Island of agreements (default active)
    const agreedInput = screen.getByLabelText(/Agreed Facts/i);
    fireEvent.change(agreedInput, { target: { value: "Convoy is ready\nPassage route clear" } });

    // Switch to Level & narrative
    fireEvent.click(screen.getByRole("button", { name: /Level & Narrative/i }));
    const whyInput = screen.getByLabelText(/WHY/i);
    fireEvent.change(whyInput, { target: { value: "Humanitarian imperative" } });

    // Click Save
    const saveBtn = screen.getByRole("button", { name: /Save & Enter Negotiation/i });
    fireEvent.click(saveBtn);

    expect(onSave).toHaveBeenCalledTimes(1);
    const savedData = onSave.mock.calls[0][0];
    expect(savedData.skipped).toBe(false);
    expect(savedData.island_of_agreements.agreed_facts).toEqual(["Convoy is ready", "Passage route clear"]);
    expect(savedData.level_and_narrative.why).toBe("Humanitarian imperative");
  });

  it("calls onSkip when clicking Skip Preparation", () => {
    const onSkip = vi.fn();
    render(<PreparationView session={MOCK_SESSION} onSave={vi.fn()} onSkip={onSkip} />);

    const skipBtn = screen.getByRole("button", { name: /Skip Preparation/i });
    fireEvent.click(skipBtn);

    expect(onSkip).toHaveBeenCalledTimes(1);
  });

  it("renders in drawer mode and calls onClose when clicking close", () => {
    const onClose = vi.fn();
    render(<PreparationView session={MOCK_SESSION} onSave={vi.fn()} onClose={onClose} isDrawer />);

    expect(screen.getByTestId("preparation-view")).toHaveClass("prep-drawer");
    const closeBtn = screen.getByRole("button", { name: /Close preparation sheet/i });
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: /Save Changes/i })).toBeInTheDocument();
  });

  it("renders error alert if onSave fails", async () => {
    const onSave = vi.fn().mockRejectedValue(new Error("Failed to save preparation"));
    render(<PreparationView session={MOCK_SESSION} onSave={onSave} onSkip={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: /Save & Enter Negotiation/i }));

    expect(await screen.findByText("Failed to save preparation")).toBeInTheDocument();
  });

  it("renders error alert if onSkip fails", async () => {
    const onSkip = vi.fn().mockRejectedValue(new Error("Failed to skip preparation"));
    render(<PreparationView session={MOCK_SESSION} onSave={vi.fn()} onSkip={onSkip} />);

    fireEvent.click(screen.getByRole("button", { name: /Skip Preparation/i }));

    expect(await screen.findByText("Failed to skip preparation")).toBeInTheDocument();
  });
});
