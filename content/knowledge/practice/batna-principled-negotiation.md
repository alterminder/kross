---
id: practice-principled-negotiation
title: "Principled Negotiation and BATNA (Fisher & Ury)"
framework: "Fisher & Ury, Getting to Yes (1981)"
citation: "Roger Fisher and William Ury, Getting to Yes: Negotiating Agreement Without Giving In (1981; later editions with Bruce Patton)"
tags: [batna, principled_negotiation, interests, positions, options, objective_criteria, alternatives, getting_to_yes]
mapped_moves: [identifies_interest, positional_demand, offers_options]
mapped_dials: [rigidity]
summary: "Getting to Yes teaches negotiating on interests rather than positions, inventing options for mutual gain, using objective criteria, and judging any deal against your BATNA. This is not CCHN doctrine. CCHN covers the interest analysis more deeply with the iceberg, and replaces BATNA with bottom lines and red lines."
---

# Principled Negotiation and BATNA (Fisher & Ury)

## What it is for

*Getting to Yes*, from the Harvard Negotiation Project, proposes "principled negotiation" (negotiation on the merits) instead of hard or soft haggling over positions. It is widely taught, so trainees often know its vocabulary. This note shows where it fits with CCHN and where it does not.

## The method

The book's four principles:

1. **Separate the people from the problem.** Deal with perceptions, emotions and communication directly. Be soft on the people and firm on the problem.
2. **Focus on interests, not positions.** A position is what someone says they want. Interests are why they want it. Ask "why?" and "why not?". Look for basic human needs such as security, economic well-being, belonging, recognition and control over one's life.
3. **Invent options for mutual gain.** Generate options before deciding. Look for ways to dovetail different interests. Make it easy for the other side to say yes.
4. **Insist on objective criteria.** Settle differences by fair standards (market value, precedent, expert opinion) or fair procedures, not by a contest of will.

**BATNA (Best Alternative To a Negotiated Agreement).**
- Your BATNA is what you will do if no agreement is reached. It is the yardstick for any proposal.
- It protects you from accepting a deal worse than your alternative, and from rejecting one that is better.
- Fisher and Ury prefer it to a fixed "bottom line", which they see as too rigid.
- They advise improving your BATNA and estimating the other side's.

## At the table

In a humanitarian setting, the useful parts look like this:
- **Ask about interests, not just positions.** "What would need to be in place for you to be comfortable with the convoy passing?"
- **Bring options, not one solution.** "We could go by road in the morning, by river, or start with a smaller convoy. Which would work best for your side?"
- **Use shared, checkable standards.** "Could we agree on how to decide who is most in need, for example by using the health centre's records?"

## What to avoid

- **Treating access as a market deal.** CCHN calls interest-based bargaining "transactional" and humanitarian negotiation "relational" (see below).
- **Using your alternative as a threat.** Lines like "If you refuse, we go to the governor" or "…to the press" are threats. They raise hostility and close the relationship.
- **Assuming you have a strong BATNA.** In access negotiations the alternative is often no access, and the population bears that cost. The counterpart's alternative, simply refusing, can be much stronger than yours.
- **Treating international law as an "objective criterion" the counterpart must accept.** Norms persuade only if they are in force and the counterpart recognises them.
- **Confusing the two meanings of "bottom line".** Fisher and Ury's rigid bottom line is not CCHN's bottom line (see below).

## How this relates to CCHN

**Where it agrees**
- **Positions vs. interests.** CCHN's iceberg (Tool 9) separates the counterpart's position (WHAT) from its tactical reasoning (HOW) and its values and motives (WHY). The Common Shared Space (Tool 11) looks for overlap at all three levels.
- **Options.** CCHN asks for options rather than solutions (Tool 6, FM p. 162) and builds scenarios with the team (Tool 14).
- **Shared standards.** These are close to CCHN's agreed facts and convergent norms (Tool 2) and to its quality-of-information test (Tool 1).

**Where CCHN goes further or differs**
- **Interests vs. values.** CCHN's lower layers are not only "interests". Values and motives are more emotional than logical (FM p. 205), and value issues are often not negotiable: keep them in mind but put them aside at first (Tier 3, FM p. 305).
- **People and problem.** Fisher and Ury separate them. CCHN treats the relationship itself as the asset: agreements are "only derivative products of the relationship" (FM p. 110), and legitimacy is partly personal (Tool 3).
- **Transactional vs. relational.** CCHN describes transactional negotiation as "Also called interest-based negotiations" (FM p. 107). It notes that most negotiation training emphasises the transactional over the relational, while humanitarian negotiation with conflict actors is essentially relational (FM p. 108). A deal drifts into transactional mode when a commander seeks personal advantage (FM p. 110).
- **No BATNA in CCHN.** The Field Manual does not use the concept. Your limits come from:
  - the **bottom line**, the negotiator's tactical pause point where diminishing returns cross rising risks (FM p. 285). Citing it lets you pause "without breaking the relationship" (FM p. 288);
  - the **red line**, the outer limit set by the mandator, which only the mandator can change (FM pp. 279, 363).
- **A refusal is not a walk-away moment.** For CCHN, a rejection of your terms is "only a moment in a relationship" (FM p. 88).

**Use instead:** Tool 9 (iceberg) for interests and motives; Tool 11 (Common Shared Space) for mutual gain; Tools 13–14 for bottom lines and scenarios; Tool 17 for red lines.

**Still useful as preparation (practice, not CCHN):** list real alternatives before you go in. These might be another route, another counterpart reached through your network (Tool 12), or another organisation better placed to deliver. Do not brandish them at the table.

## Try instead

* *Instead of:* "If you don't let us through, we will take this to the governor."
* *Try:* "What would make it possible for you to let the convoy through on Thursday?"

* *Instead of:* "Our bottom line is that we will never accept escorts."
* *Try (once the dialogue is established):* "Armed escorts are something I'm not able to agree to. Could we look at other ways to give you confidence about the route, for example sharing our schedule with your officers in advance?"

## How KROSS uses it

- **Rewarded moves.** `identifies_interest` (naming or testing the reasoning or motive behind a position) and `offers_options` lower the counterpart's `rigidity`.
- **Penalised moves.** `positional_demand` (repeating a demand without exploring the objection) raises it. Using an alternative as leverage ("we'll go over your head") counts as `threatens`.
- **Where the interests are.** They sit in `counterparts[].iceberg` and `hidden_interests`, which are revealed in iceberg order as trust grows.
- **Where your limits are.** They come from `issues` (ideal, bottom line, red line) and `trainee_brief.red_lines`, not from a BATNA.

## Related tools

- Tool 4, Typology: transactional vs. relational negotiation.
- Tool 9, Iceberg: position, reasoning, values and motives.
- Tool 11, Common Shared Space: searching for overlap.
- Tools 13–14, Shared benefit and scenarios: bottom lines.
- Tool 17, Red lines: the mandator's limits.
