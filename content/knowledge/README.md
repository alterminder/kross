# Knowledge doctrine files

Each `.md` file under `cchn/` and `practice/` is one doctrine document.

## Format

```markdown
---
id: cchn-tool-07
title: "Clarifying the Terms of the Transaction"
framework: "CCHN Field Manual on Frontline Humanitarian Negotiation"
citation: "CCHN Field Manual (2019), Tool 7, pp. 168-177"
tags: [terms, agreement]
mapped_moves: [clarifies_operational_detail]
mapped_dials: [trust]
summary: "One-line core principle shown in the card and modal."
---

# Title

## What it is for
…user-facing sections…

## How KROSS uses it
…internal section (see below)…

## Related tools
```

## `## How KROSS uses it` — internal, not shown to users

This section explains how the simulation engine, coach, and debrief use the
doctrine (moves, dials, classifier hints). It is **not rendered** to users:
the knowledge reader (`frontend/src/features/coach/KnowledgeModal.tsx`) strips
the section before display.

Keep writing it — the LLM (coach prompts, retrieval) still reads the full
`body_markdown`, and it is the only place documenting the engine mapping.
It can sit anywhere in the body; the reader removes it up to the next `##` heading.
