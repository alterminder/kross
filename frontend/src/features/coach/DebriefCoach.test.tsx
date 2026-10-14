import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { events, stubApi } from "../../test-utils";
import { DebriefCoach } from "./DebriefCoach";

describe("DebriefCoach", () => {
  it("renders suggestions, asks question, streams reply with CCHN citations, and opens modal", async () => {
    let coachCalled = false;
    stubApi({
      "GET sessions/s1/coach/suggestions": {
        suggestions: ["Why did the counterpart resist?"],
        citations: [],
      },
      "POST sessions/s1/coach": () => {
        coachCalled = true;
        return events(
          [
            "citations",
            [
              {
                id: "cchn-tool-09",
                title: "Analyzing the Position of the Counterpart (the Iceberg)",
                framework: "CCHN Field Manual",
                citation: "CCHN Field Manual (2019), Tool 9, pp. 199-217",
                summary: "WHAT, HOW and WHY of the position.",
              },
            ],
          ],
          [
            "reply",
            {
              text: "Under CCHN Tool 9, the counterpart kept to his stated position.",
            },
          ],
          ["done", { citations: [] }],
        );
      },
      "GET knowledge/cchn-tool-09": {
        id: "cchn-tool-09",
        title: "Analyzing the Position of the Counterpart (the Iceberg)",
        framework: "CCHN Field Manual",
        citation: "CCHN Field Manual (2019), Tool 9, pp. 199-217",
        tags: ["counterpart", "iceberg"],
        summary: "WHAT, HOW and WHY of the position.",
        body_markdown: "Full CCHN Tool 9 doctrine text and guidance.",
      },
    });

    render(<DebriefCoach sessionId="s1" />);
    await act(async () => {});

    // Suggestions chip visible
    const chip = screen.getByText(/Why did the counterpart resist\?/);
    expect(chip).toBeInTheDocument();

    // Click suggestion chip
    await act(async () => {
      fireEvent.click(chip);
    });

    expect(coachCalled).toBe(true);

    // Reply text should be rendered
    expect(
      screen.getByText(/Under CCHN Tool 9, the counterpart kept to his stated position/),
    ).toBeInTheDocument();

    // CCHN citation badge should be rendered
    const badge = screen.getByText(/Analyzing the Position of the Counterpart \(the Iceberg\)/);
    expect(badge).toBeInTheDocument();

    // Click citation badge to open KnowledgeModal
    await act(async () => {
      fireEvent.click(badge);
    });

    // Knowledge modal dialog opens
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText(/CCHN Doctrine Framework/)).toBeInTheDocument();
    expect(screen.getByText("Full CCHN Tool 9 doctrine text and guidance.")).toBeInTheDocument();

    // Close modal
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
