import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { S } from "../../api/client";
import { OnboardingCarousel } from "./OnboardingCarousel";

const MOCK_SESSION: S["SessionOut"] = {
  id: "session-123",
  scenario_id: "scen-456",
  title: "Detained before nightfall",
  cover: "prison",
  mode: "solo",
  status: "active",
  turn: 0,
  turn_running: false,
  phases: [],
  warning_minutes: [5, 1],
  on_timeout: "guide",
  silence_seconds: 90,
  preparation_modules: [],
  counterparts: [],
  stakeholders: [],
  brief: {
    situation:
      "A police station in a tense rural district. You are meeting Captain Idris Mansour, head of the district police station. What you know: he was arrested this morning at the main crossroads; he was moved to a rural police post; a rumour says he stole seeds.",
    objective: "Obtain the release of the detained day labourer before nightfall.",
    mandate: {
      can_decide: [
        "Propose that he is brought back to this station tonight and registered",
        "Agree the time and conditions of an ICRC visit",
      ],
      must_refer: [
        "Any commitment about his legal case",
        "Any public statement about the police",
      ],
    },
    red_lines: [
      { text: "Never identify the family or community sources", source: "ethical" },
      { text: "No payment or goods in exchange for release", source: "institutional" },
    ],
    counterpart_role: "Captain Idris Mansour, district police chief",
    estimated_minutes: 20,
  },
  transcript: [{ role: "character", text: "There is no one here. This is a police matter.", turn: 0 }],
  outcome: null,
  debrief_status: null,
};

describe("OnboardingCarousel", () => {
  it("shows Mission by default with the exercise metadata and mandate", () => {
    render(<OnboardingCarousel session={MOCK_SESSION} userName="Lola" onComplete={vi.fn()} />);

    expect(screen.getByRole("button", { name: "Mission" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "What we know" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Objective" })).toBeInTheDocument();

    expect(screen.getByText("YOUR MISSION")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Detained before nightfall" })).toBeInTheDocument();
    expect(screen.getByText("20:00")).toBeInTheDocument();
    expect(screen.getByText("Written exchange")).toBeInTheDocument();
    expect(screen.getByText(/Authorized within your mandate/i)).toBeInTheDocument();
    expect(
      screen.getByText("Propose that he is brought back to this station tonight and registered"),
    ).toBeInTheDocument();
    expect(screen.getByText(/Requires headquarters referral/i)).toBeInTheDocument();
  });

  it("jumps straight to any section and back", () => {
    render(<OnboardingCarousel session={MOCK_SESSION} onComplete={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "What we know" }));
    expect(screen.getByText("WHAT YOU KNOW")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "The facts you start with" })).toBeInTheDocument();
    expect(screen.getByText("he was arrested this morning at the main crossroads")).toBeInTheDocument();
    expect(screen.getByText("RED LINES (NON-NEGOTIABLE)")).toBeInTheDocument();
    expect(screen.getByText(/Never identify the family or community sources/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Objective" }));
    expect(screen.getByText("YOUR OBJECTIVE")).toBeInTheDocument();
    expect(
      screen.getByText("Obtain the release of the detained day labourer before nightfall."),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Mission" }));
    expect(screen.getByText("YOUR MISSION")).toBeInTheDocument();
  });

  it("moves through the tabs with Next and enters from the last tab", () => {
    const onComplete = vi.fn();
    render(<OnboardingCarousel session={MOCK_SESSION} onComplete={onComplete} />);

    fireEvent.click(screen.getByRole("button", { name: "Next →" }));
    expect(screen.getByText("WHAT YOU KNOW")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Next →" }));
    expect(screen.getByText("YOUR OBJECTIVE")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "← Back" }));
    expect(screen.getByText("WHAT YOU KNOW")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Next →" }));
    fireEvent.click(screen.getByRole("button", { name: "Enter Negotiation →" }));
    expect(onComplete).toHaveBeenCalled();
  });

  it("calls onClose when skip is clicked", () => {
    const onClose = vi.fn();
    render(<OnboardingCarousel session={MOCK_SESSION} onComplete={vi.fn()} onClose={onClose} />);

    fireEvent.click(screen.getByRole("button", { name: "Skip to negotiation" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("closes from the X button", () => {
    const onClose = vi.fn();
    render(<OnboardingCarousel session={MOCK_SESSION} onComplete={vi.fn()} onClose={onClose} />);

    fireEvent.click(screen.getByRole("button", { name: "Close brief" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("offers Close instead of Enter Negotiation once the dialogue is under way", () => {
    const onComplete = vi.fn();
    const onClose = vi.fn();
    render(
      <OnboardingCarousel
        session={{ ...MOCK_SESSION, turn: 3 }}
        onComplete={onComplete}
        onClose={onClose}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Objective" }));
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalled();
    expect(onComplete).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /Enter Negotiation/ })).toBeNull();
  });

  it("offers Prepare Strategy when preparation modules exist", () => {
    const onPrepare = vi.fn();
    render(
      <OnboardingCarousel
        session={{ ...MOCK_SESSION, preparation_modules: [{ id: "p1", kind: "naivasha" }] as never }}
        onComplete={vi.fn()}
        onPrepare={onPrepare}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Objective" }));
    fireEvent.click(screen.getByRole("button", { name: "Prepare Strategy (Naivasha Grid) →" }));
    expect(onPrepare).toHaveBeenCalled();
  });
});
