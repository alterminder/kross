---
id: cchn-naivasha-grid
title: "Planning a Negotiation Process: the Naivasha Grid"
framework: "CCHN Field Manual on Frontline Humanitarian Negotiation"
citation: "CCHN Field Manual (2019), Introduction pp. 28-33, Part 2 introduction pp. 193-197, Part 3 introduction pp. 313-318; CCHN Negotiator Handbook, p. 4; CCHN Facilitator Handbook (2020), Session 2, pp. 15-18"
tags: [naivasha, planning, preparation, roles, mandator, support_team, relational, transactional, process]
mapped_moves: [refers_to_mandator, unauthorized_commitment]
mapped_dials: [trust]
summary: "The Naivasha Grid maps a humanitarian negotiation as three role pathways: the frontline negotiator (context analysis, tactical plan, transaction), the support team (analysis and scenarios) and the mandator (objectives and red lines). Use it to plan before a negotiation and to find what is blocking one; never as a rigid checklist."
---

# CCHN: Planning a Negotiation Process (the Naivasha Grid)

## What it is for

The Naivasha Grid is CCHN's map of a negotiation process, first drawn by 24 ICRC frontline negotiators in Naivasha, Kenya, in 2014 and later adapted by CCHN for all agencies (FM p. 29). It serves two purposes (FM pp. 29–30; FH p. 17):

- **Planning tool:** organise the work ahead of your negotiation and decide who does what.
- **Analytical tool:** when a process stalls, find which task or role is missing.

## The method

**Three pathways (Figure 3, FM p. 30; NH p. 4)**

- **Green: the frontline negotiator** has the leading role: *Analyze context → Develop tactical plan → Engage in transaction* (Tools 1–8).
- **Yellow: the negotiation support team** works intermittently with the negotiator (FM p. 31). It covers:
  - *Analyze interests & motives of counterpart* (Tool 9);
  - *Identify own priorities & objectives* (Tools 10–11);
  - *Analyze network of influence* (Tool 12);
  - *Design scenario & bottom line* (Tools 13–14).
  The Grid groups these under two labels, "Identifying shared objectives" and "Leveraging influence".
- **Red: the mandator** frames the whole process with *Mission and strategic objectives* (Tools 15–16) and *Institutional policies and red lines* (Tool 17).

**Two stages**

- **Relational stage** (context analysis to tactical plan): building and maintaining rapport with counterparts and stakeholders (FM p. 47).
- **Transactional stage** (tactical plan to transaction): the final step, where the parties agree the actual terms as a series of reciprocal commitments (FM p. 152).
- Humanitarian negotiation is essentially relational, so most of the effort belongs to the first stage (FM p. 110).

**Why the roles are split**

- Negotiations are team-based. Without a critical process around them they can turn into private dealings, and a negotiator who is too close may chase an agreement at any cost (FM pp. 194–195).
- The team keeps a critical space for reviewing objectives and assures the mandator that tactical choices were deliberate (FM pp. 196–197).
- The mandator gives the negotiator authority and keeps agreements within institutional policies such as the humanitarian principles and "do no harm" (FM p. 317).
- A negotiator is not a representative. Representatives deliver validated messages with little room to manoeuvre; a negotiator is mandated to explore options and compromises (FM pp. 315–316).
- One person can hold different roles in different processes at the same time, and all three roles count equally (FM pp. 32, 318).

**Out of scope (FM p. 31):** needs assessment, programme design, internal deliberations, negotiation with your own mandator, and implementation of the final agreement.

**How CCHN teaches it (FH Session 2, pp. 16–17).** Participants order their own planning tasks, then build their own grid from puzzle pieces. The Grid answers four questions: How do we sort information about a context? What methods and tactics do we use? Why do we negotiate? What are our objectives and red lines?

## At the table

- **Know which stage you are in.** With no relationship yet, do not jump to trucks and dates; start from agreed facts and shared concerns.
- **Stay in your role.** When a request goes beyond what you can decide, pause and refer back. Do not invent a new red line or drop one on the spot. Strong prohibiting messages belong to the mandator, not to you (FM p. 240).
- **Use the Grid to diagnose.** If stuck, ask which box is empty: facts, counterpart analysis, network, bottom line or mandate.

Example lines:
- "Before we get to the practical arrangements, how do you see the situation for the families in the district?"
- "That goes beyond what I can decide here. I will consult my hierarchy and come back to you tomorrow."

## What to avoid

- Treating the Grid as rigid or complete (FH p. 17).
- Negotiating solo with no team or mandator behind you (FM pp. 194–195).
- Setting or revising red lines yourself. That is the mandator's job (FM pp. 279, 340).
- Acting like a representative who only repeats positions, or a mandator who denounces (FM pp. 240, 315–316).
- Rushing to the transaction before the relationship can carry it (FM p. 110).

## Key lines from the manual

> "Humanitarian negotiations can easily turn into private dealings if the process is not integrated into a professional and critical endeavour" (p. 194)

> "This distribution of roles reduces the risk of the negotiator who lacks sufficient distance from the situation wanting to reach an agreement at all costs." (p. 195)

> "humanitarian negotiators devote more resources and time at the relational stage of the process than at the transactional stage" (p. 110)

> "the mandate is not designed to dictate specific tasks, methods, or outcomes of the negotiation but to set a genuine space of dialogue with the counterpart" (p. 314)

> "There is not one exhaustive grid, but it is important to present it to generate and frame the conversation." (Facilitator Handbook, p. 17)

## Try instead

* *Instead of:* "Yes, I can agree to that now." (for something outside your mandate)
* *Try:* "That goes beyond what I can decide on my own. I will take it to my hierarchy and come back to you. Meanwhile, can we confirm the points we already agree on?"

* *Instead of:* "We need to send twenty trucks through your checkpoint on Monday."
* *Try:* "Before we look at the convoy itself, could you tell me what concerns you most about the situation on the road?"

## How KROSS uses it

- **You play the green pathway**, the frontline negotiator.
- **The brief stands in for the red pathway:** `trainee_brief.mandate` (`can_decide`, `must_refer`), `trainee_brief.red_lines` (with `source` and `flexible_by_mandator_only`) and `trainee_brief.objective`.
- **The scenario data stands in for the support team:** `counterparts[].iceberg` and `hidden_interests` (Tool 9), `stakeholders` (Tool 12), and `issues` with ideal, bottom line, red line and tier (Tools 13–14).
- **Moves.** `refers_to_mandator` uses the red pathway well. `unauthorized_commitment` skips it and raises `mandate_breach` or `red_line_crossed`.
- **Dials.** The relational stage shows up mainly in `trust`.
- **No preparation step yet.** Use the Grid as a checklist while reading the brief, and in the debrief to find where the process got stuck.

## Related tools

- Tool 2, Island of Agreements: opening the relationship on agreed facts and convergent norms.
- Tool 4, Typology: relational vs transactional negotiation.
- Tool 9, Iceberg: the support team's analysis of the counterpart.
- Tools 13–14, Scenarios: bottom lines and when to pause.
- Tools 15 and 17, Mandate and Red lines: the mandator's framing.
