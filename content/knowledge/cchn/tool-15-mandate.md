---
id: cchn-tool-15
title: "Design of the Mandate"
framework: "CCHN Field Manual on Frontline Humanitarian Negotiation"
citation: "CCHN Field Manual (2019), Tool 15, pp. 319-331 (with Part 3 introduction, pp. 314-318); CCHN Negotiator Handbook, Tool 15, pp. 72-76"
tags: [mandate, mandator, delegation_of_authority, confidentiality, reporting, refer_back, specific_terms]
mapped_moves: [refers_to_mandator, unauthorized_commitment, discloses_confidential, threatens_publicity]
mapped_dials: [trust]
summary: "The mandator gives the negotiator a mandate made of general terms, confidential specific terms (including red lines) and a delegation of authority. A clear mandate is leverage. A vague 'don't ask, don't tell' mandate is a risk. Reporting points tell the negotiator when to go back to the mandator."
---

# CCHN Tool 15: Design of the Mandate

## What it is for
Tool 15 helps the mandator turn the organisation's mission and strategic objectives into a negotiator's mandate. The mandate should be broad enough to adapt to the field but detailed enough to stay aligned with core values (p. 319). The mandate does not dictate tasks or outcomes. It sets "a genuine space of dialogue" with the counterpart while stipulating "clear red lines" (p. 314).

## The method

**Three meanings of "mandate" (pp. 314-316)**
- **Mandate of an organisation**: its overall mission, granted by an external authority such as a treaty, the UN General Assembly or an NGO's governing assembly.
- **Mandate of a negotiator**: granted internally by the hierarchy. It delegates the power to engage the organisation in a specific negotiation. Its limits are set by the mandator and can be adapted by the mandator.
- **Representatives and agents** (director, spokesperson): their lines are prepared and validated in advance. They have "little room to maneuver" and are not mandated to explore alternatives or find compromises (pp. 315-316).

**Three roles (pp. 316-318)**
- **Mandator**: gives authority, governs the process, and keeps agreements within institutional policy (humanitarian principles, "do no harm"). The mandate can be explicit, or implicit in a job description.
- **Negotiator**: represents the organisation and may reach agreements.
- **Support team**: analysis, tactics and a "critical space" for planning (p. 317).
One person can hold different roles in different processes (p. 318).

**Three components of a negotiator's mandate (p. 319)**
1. **General terms**: a well-defined understanding of the mission and strategic objectives.
2. **Specific terms**: operational objectives in this context, plus the policies and red lines that bound the mandate. These are "generally considered to be confidential between the mandator and the negotiator". They frame the conversation, not the final terms, and identify areas of possible compromise (p. 321).
3. **Delegation of authority**: the power to engage the authorities and to agree on terms. The FM separates instructions to *represent* (advocacy) from a mandate to *negotiate*, which means the ability to make compromises (p. 322).

**Against "don't ask, don't tell" (pp. 322-323).** Some organisations ask agents to find "practical solutions" without stating red lines. This gives flexibility but carries reputational risk, blocks organisational learning and breeds misperception. Internal transparency on allowed compromises gives "greater cohesion" in the long run (p. 323).

**Application, three steps (HfA case, pp. 324-330; NH p. 72)**
1. **Location, object and time frame.** The NH template rows are Context, Object, Time period, Counterparts, Designation of the negotiator and Reporting line (NH p. 74). In the HfA case these include "6 months renewable" and a reporting line to the Country Director (p. 326). Negotiators need clear instructions on the "format, timing, and content" of reporting. Instructions should also cover the bottom lines, "moments where the negotiator will need to go back to the mandator" (p. 326).
2. **Person in charge.** Appoint a lead negotiator, free them from other duties, and give them a small team, peer reviewers and logistical support (p. 327).
3. **General and specific terms.** General terms follow from mission and values (p. 328). Specific terms depend on whether the issue is factual (needs experts and evidence) or normative (needs professional and political support) (p. 329). The specific terms table is marked "STRICTLY CONFIDENTIAL" (p. 330).

## At the table
- Know what you can decide before you sit down. If a request falls outside it, refer it: "That goes beyond what I'm mandated to agree here. I'll take it to our Country Director and come back to you by Thursday."
- Use the general terms openly. They answer WHO you are and WHY you are here (NH p. 75): "We are here to make sure surgical care reaches those who need it, without taking sides."
- Keep the specific terms private. When the counterpart asks "What is the most your headquarters will accept?", answer: "That's a discussion I have with my hierarchy. Let's look at what would work for both of us."
- Report back at the agreed points, and tell the counterpart when you will return.

## What to avoid
- Going in with a vague mission: it is then hard to build trust or explain why the counterpart should compromise (p. 320).
- Accepting a "don't ask, don't tell" mandate: "What happens in the deep field rarely stays there very long" (p. 322).
- Acting like a representative who only repeats positions, or like a negotiator with no limits.
- Revealing the specific terms or red lines of your mandate to the counterpart.

## Key lines from the manual
> "The clearer the mandate of the negotiator, the more able the negotiator will be to build a relationship based on trust with the counterparts" (p. 320)

> "The specific terms of the mandate are generally considered to be confidential between the mandator and the negotiator" (p. 321)

> "The policy of 'don't ask, don't tell' offers the largest flexibility to trusted negotiators in the field." (p. 322)

> "the specific terms of the negotiation, including the redlines are likely to remain confidential between the mandator and the negotiator." (NH p. 72)

## Try instead
* *Instead of:* "Don't worry, I'll make sure we pay the guards' compensation."
* *Try:* "Compensation is outside what I can decide here. I'll put your request to our Country Director and report back to you."
* *Instead of:* "Between us, my instructions let me accept an escort as long as it stays outside the camp."
* *Try:* "Let's look at a few ways the escort question could work. I'll see which of them I can take forward."

## How KROSS uses it
- **trainee_brief.mandate**: `can_decide` is the delegation of authority, and `must_refer` lists what goes back to the mandator. Both are confidential specific terms. **trainee_brief.objective** reflects the general terms, and **trainee_brief.red_lines** the bounding policies.
- **Moves**: `refers_to_mandator` (referring at a reporting point); `unauthorized_commitment` (agreeing outside `can_decide`, which raises the `mandate_breach` flag); `discloses_confidential` (revealing specific terms or red lines, which raises the `confidentiality` flag and lowers `trust`).
- **Dials**: the FM links a clear mandate to building `trust` (p. 320).

## Related tools
- Tool 10 Own Priorities and Objectives: specific terms frame the negotiator's objectives.
- Tool 13/14 Shared Benefit and Cost-Benefit: bottom lines are the refer-back points.
- Tool 16 External Communication: the mandator controls messaging around the process.
- Tool 17 Red Lines: the limits written into the specific terms.
