import { fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderAt, stubApi } from "../test-utils";
import { KnowledgeLibrary } from "./KnowledgeLibrary";

const MOCK_DOCS = [
  {
    id: "cchn-tool-02",
    title: "Tool 2: Island of Agreements",
    framework: "CCHN Field Manual",
    citation: "Module 3, Section 2",
    tags: ["facts", "norms", "preparation"],
    summary: "Identify shared facts and shared norms as solid ground before tackling divergent issues.",
    body_markdown: "# Tool 2: Island of Agreements\n\nContent details here.",
  },
  {
    id: "cchn-tool-08",
    title: "Tool 8: De-escalation & Emotion",
    framework: "CCHN Field Manual",
    citation: "Module 4, Section 8",
    tags: ["de-escalation", "hostility", "empathy"],
    summary: "Managing tension spikes and interpersonal hostility through 6 structured communication steps.",
    body_markdown: "# Tool 8: De-escalation\n\nContent details here.",
  },
  {
    id: "practice-batna",
    title: "Principled Negotiation & BATNA",
    framework: "Practice Notes",
    citation: "Harvard / Frontline Synthesis",
    tags: ["batna", "alternatives", "leverage"],
    summary: "Assessing best alternative to a negotiated agreement in humanitarian access constraints.",
    body_markdown: "# BATNA\n\nContent details here.",
  },
];

describe("KnowledgeLibrary", () => {
  it("renders page header, search controls, and all doctrine cards", async () => {
    stubApi({ "GET knowledge": MOCK_DOCS });
    renderAt("/knowledge", <KnowledgeLibrary />);

    expect(await screen.findByRole("heading", { name: "Knowledge Library" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Search doctrine/i)).toBeInTheDocument();

    expect(screen.getByText("Tool 2: Island of Agreements")).toBeInTheDocument();
    expect(screen.getByText("Tool 8: De-escalation & Emotion")).toBeInTheDocument();
    expect(screen.getByText("Principled Negotiation & BATNA")).toBeInTheDocument();
  });

  it("filters doctrine cards by search query", async () => {
    stubApi({ "GET knowledge": MOCK_DOCS });
    renderAt("/knowledge", <KnowledgeLibrary />);

    await screen.findByText("Tool 2: Island of Agreements");

    const searchInput = screen.getByPlaceholderText(/Search doctrine/i);
    fireEvent.change(searchInput, { target: { value: "de-escalation" } });

    expect(screen.getByText("Tool 8: De-escalation & Emotion")).toBeInTheDocument();
    expect(screen.queryByText("Tool 2: Island of Agreements")).toBeNull();
    expect(screen.queryByText("Principled Negotiation & BATNA")).toBeNull();
  });

  it("filters doctrine cards via the Frameworks dropdown, all selected by default", async () => {
    stubApi({ "GET knowledge": MOCK_DOCS });
    renderAt("/knowledge", <KnowledgeLibrary />);

    await screen.findByText("Tool 2: Island of Agreements");
    expect(screen.getByText("Principled Negotiation & BATNA")).toBeInTheDocument();

    // Uncheck a framework in the dropdown
    fireEvent.click(screen.getByRole("button", { name: /Frameworks/ }));
    const menu = screen.getByRole("group", { name: "Filter by framework" });
    fireEvent.click(within(menu).getByRole("checkbox", { name: /CCHN Field Manual/ }));

    expect(screen.getByText("Principled Negotiation & BATNA")).toBeInTheDocument();
    expect(screen.queryByText("Tool 2: Island of Agreements")).toBeNull();
    expect(screen.queryByText("Tool 8: De-escalation & Emotion")).toBeNull();

    // Check it back: the cards return
    fireEvent.click(within(menu).getByRole("checkbox", { name: /CCHN Field Manual/ }));
    expect(screen.getByText("Tool 2: Island of Agreements")).toBeInTheDocument();
    expect(screen.getByText("Tool 8: De-escalation & Emotion")).toBeInTheDocument();
  });

  it("closes the Frameworks dropdown on a click outside", async () => {
    stubApi({ "GET knowledge": MOCK_DOCS });
    renderAt("/knowledge", <KnowledgeLibrary />);

    await screen.findByText("Tool 2: Island of Agreements");

    fireEvent.click(screen.getByRole("button", { name: /Frameworks/ }));
    expect(screen.getByRole("group", { name: "Filter by framework" })).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByPlaceholderText(/Search doctrine/i));
    expect(screen.queryByRole("group", { name: "Filter by framework" })).toBeNull();
  });

  it("filters doctrine cards by clicking topic tags", async () => {
    stubApi({ "GET knowledge": MOCK_DOCS });
    renderAt("/knowledge", <KnowledgeLibrary />);

    await screen.findByText("Tool 2: Island of Agreements");

    // Click #facts tag pill
    const factsTag = screen.getByRole("button", { name: "#facts" });
    fireEvent.click(factsTag);

    expect(screen.getByText("Tool 2: Island of Agreements")).toBeInTheDocument();
    expect(screen.queryByText("Tool 8: De-escalation & Emotion")).toBeNull();
    expect(screen.queryByText("Principled Negotiation & BATNA")).toBeNull();

    // Clear tag filter
    const clearBtn = screen.getByRole("button", { name: "Clear tag filter" });
    fireEvent.click(clearBtn);

    expect(screen.getByText("Tool 2: Island of Agreements")).toBeInTheDocument();
    expect(screen.getByText("Tool 8: De-escalation & Emotion")).toBeInTheDocument();
  });

  it("opens KnowledgeModal when a doctrine card is clicked", async () => {
    stubApi({
      "GET knowledge": MOCK_DOCS,
      "GET knowledge/cchn-tool-02": MOCK_DOCS[0],
    });
    renderAt("/knowledge", <KnowledgeLibrary />);

    const card = await screen.findByRole("button", { name: /Open doctrine: Tool 2: Island of Agreements/i });
    fireEvent.click(card);

    // Modal dialog should be displayed
    const modal = await screen.findByRole("dialog");
    expect(within(modal).getByRole("heading", { name: "Tool 2: Island of Agreements" })).toBeInTheDocument();
  });

  it("renders markdown formatting (headings, bold, lists) inside KnowledgeModal", async () => {
    stubApi({
      "GET knowledge": MOCK_DOCS,
      "GET knowledge/cchn-tool-02": {
        ...MOCK_DOCS[0],
        body_markdown: "## The method\n\nEach step says whether it is **CCHN** or **heuristic**.\n\n1. **Test the message.** Details here.",
      },
    });
    renderAt("/knowledge", <KnowledgeLibrary />);

    const card = await screen.findByRole("button", { name: /Open doctrine: Tool 2: Island of Agreements/i });
    fireEvent.click(card);

    const modal = await screen.findByRole("dialog");
    expect(within(modal).getByRole("heading", { name: "The method" })).toBeInTheDocument();
    expect(within(modal).getByText("CCHN")).toBeInTheDocument();
    expect(within(modal).getByText("Test the message.")).toBeInTheDocument();
  });

  it("hides the internal 'How KROSS uses it' section from the reader", async () => {
    stubApi({
      "GET knowledge": MOCK_DOCS,
      "GET knowledge/cchn-tool-02": {
        ...MOCK_DOCS[0],
        body_markdown:
          "## Public part\n\nVisible text.\n\n## How KROSS uses it\n\nInternal engine note.\n\n## Related tools\n\nAlso visible.",
      },
    });
    renderAt("/knowledge", <KnowledgeLibrary />);

    const card = await screen.findByRole("button", { name: /Open doctrine: Tool 2: Island of Agreements/i });
    fireEvent.click(card);

    const modal = await screen.findByRole("dialog");
    expect(within(modal).getByText("Visible text.")).toBeInTheDocument();
    expect(within(modal).getByText("Also visible.")).toBeInTheDocument();
    expect(within(modal).queryByText(/Internal engine note/)).toBeNull();
    expect(within(modal).queryByRole("heading", { name: "How KROSS uses it" })).toBeNull();
  });
});
