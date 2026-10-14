---
id: practice-incremental-pressure
title: "Incremental Pressure (Salami Tactics)"
framework: "General negotiation practice (salami tactics)"
citation: "The term 'salami tactics' is commonly attributed to the Hungarian communist leader Mátyás Rákosi (late 1940s); it is widely used in negotiation and political literature"
tags: [salami, incremental, nibbling, creeping_demands, cumulative_risk, bottom_line, red_line, precedent, pressure]
mapped_moves: [unauthorized_commitment, refers_to_mandator]
mapped_dials: [rigidity]
summary: "Salami tactics win a large concession through a series of small demands, each reasonable on its own. This is not CCHN doctrine. CCHN's rising-risk curve, the bottom line as a pause point, the warning not to buckle to other organisations' risk tolerance, and the rule that only the mandator adapts red lines are the CCHN answers."
---

# Incremental Pressure (Salami Tactics)

## What it is for

"Salami tactics" means taking something slice by slice: getting a large concession through small steps, none of which seems worth refusing. The term is commonly attributed to Mátyás Rákosi, the Hungarian communist leader of the late 1940s. It now names any creeping-demand pattern in negotiation, including "nibbling", where small extras are added after a deal is almost closed.

In access negotiations it sounds like: "Just one officer will ride with the first truck." "We only need the list of names for security." "Just this once, deliver at our post."

## The method

**How the pattern works (practice knowledge, not CCHN):**
- **The anchor moves.** Each step is compared with the previous position, not with where you started.
- **Consistency pressure.** Having said yes to the last slice, refusing the next one feels inconsistent.
- **Fatigue and relationship pressure.** After hours of talks, one more small yes seems cheaper than a no.
- **Precedent.** Each slice becomes the new normal for the next negotiation, and for other organisations.

**Practical counters (practice, not CCHN):**
- **Keep the whole picture.** Track the cumulative effect against your original plan and your limits, not against the last offer.
- **Ask for the full list.** "Is there anything else you will need for the convoy?" Then evaluate the package, not each piece.
- **Name the pattern neutrally**, without accusing anyone.
- **Decide pause points before you go in**, and use them.

## At the table

- **Summarise and ask for everything.** "Let me check what we have agreed so far: the route, the timing and the checkpoint procedure. Is there anything else you will need, so I can look at the whole arrangement with my team?"
- **Pause at your bottom line.** "Adding a list of recipients' names goes beyond what I can agree today. I'll need to consult before going further."

## What to avoid

- **Agreeing piece by piece until you have crossed a red line without noticing.**
- **Accusing the counterpart of manipulation.** Summarise and pause instead.
- **Over-reacting with absolutes such as "never" or "non-negotiable".** CCHN lists these among the phrases to avoid (FM p. 240).
- **Salami-slicing the counterpart yourself.** CCHN notes that a counterpart's political cost rises with each compromise they make (FM p. 276). Pushing them slice by slice can corner them.

## How this relates to CCHN

The Field Manual does not use the terms "salami" or "incremental pressure", but it describes the same danger and gives the tools to deal with it.

- **Rising risks of compromises (Tool 13, FM pp. 282–285, Fig. 14).**
  - CCHN's worked example is a ladder of compromises for access to an IDP camp: full access with no military presence → a limited, non-visible military presence → the military actively monitoring the distribution → limited access with a military escort, plus a list of beneficiaries for the camp authorities (FM pp. 282–283). Each rung costs more in neutrality and independence, and by the third the benefit of the negotiation starts to decrease (FM p. 283). Figure 14 shows the risk curve rising across these compromises (FM p. 284).
  - The risks include respect of humanitarian principles, staff security, protection of the population, professional standards, reputation and other legal norms (FM p. 284).
  - The manual warns of a negotiator "pressured into an increasingly compromising and risky posture while the shared benefits and ownership of the negotiation keep shrinking" (FM p. 285).
- **The bottom line as a pause point.**
  - The bottom line sits where the diminishing return crosses the rising risk, which calls for a pause in the dialogue (FM p. 285).
  - Citing it lets you pause "without breaking the relationship" and consult your team and, if needed, the mandator (FM p. 288).
  - The bottom line is under your control (FM p. 279). Set it before the meeting so the slices have a stopping point.
- **Do not buckle to other organisations' tolerance.**
  - A counterpart may press the more restrictive organisation using another organisation's risk tolerance. The negotiator "should not buckle". The policy is the mandator's, and the negotiator has no permission to engage on it (FM p. 287).
  - Another organisation's compliance is no reason to break your own rules (FM p. 350).
- **Only the mandator adapts red lines.**
  - Red lines "cannot be changed or revised without the agreement of the mandator" (FM p. 363).
  - Exceptional adaptations are made at the appropriate level because they set "expectations for future negotiations and operations" (FM p. 364). This is CCHN's version of the precedent problem.
- **Clear terms close the gaps.** Vague terms become a liability at implementation (FM p. 159). Tool 7's criteria (FM p. 172) make later "small additions" visible as changes to the agreement.

**Use instead:** Tools 13–14 for the compromise ladder and bottom lines; Tool 17 for red lines and the mandator's role; Tool 7 for precise terms.

## Try instead

* *Instead of:* "OK, one soldier on the first truck is fine."
* *Try:* "Armed personnel on our trucks is something I can't agree to here. I'll raise it with my hierarchy. Meanwhile, could we share the route and timing with your officers in advance?"

* *Instead of:* "Yes, and we can also give you the names."
* *Try:* "Before we add anything, let me summarise what we have agreed so far, so I can review the whole arrangement with my team."

## How KROSS uses it

- **The ladder.** Each entry in `issues` carries an ideal outcome, a bottom line, a red line and a tier, which is the ladder the counterpart may try to walk you down.
- **Your limits.** `trainee_brief.red_lines` (often `flexible_by_mandator_only`) and `trainee_brief.mandate.must_refer` mark where a slice stops being yours to give.
- **Moves.**
  - `refers_to_mandator` rewards pausing without breaking the relationship.
  - `unauthorized_commitment` marks the slice that went too far and raises `mandate_breach` or `red_line_crossed`.
  - `premature_red_line` catches answering creeping demands with door-closing absolutes too early.
- **Dials.** A counterpart with high `rigidity` is more likely to keep adding demands.

## Related tools

- Tool 13, Shared benefit: the rising-risk curve (Fig. 14) and the natural bottom line.
- Tool 14, Cost-benefit of options: citing the bottom line, and tiers.
- Tool 17, Red lines: only the mandator adapts them, and adaptations set precedents.
- Tool 7, Clarifying the terms: precise terms resist later nibbling.
- Tool 12, Network mapping: the counterpart's own rising political cost.
