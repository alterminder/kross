---
id: practice-authority-constraints
title: "When the Counterpart Cites Orders, Competence or Paperwork"
framework: "KROSS practice note (not CCHN doctrine)"
citation: "KROSS practice heuristic; CCHN-grounded parts cite the CCHN Field Manual (2019), Tools 4, 6, 8, 9, 12 and 14"
tags: [authority, orders, paperwork, permits, competence, blame, refer_back, mandator, constituency, channel, procedure]
mapped_moves: [asks_good_question, identifies_interest, shows_respect_curiosity, positional_demand]
mapped_dials: [rigidity, trust]
summary: "When a counterpart says 'I have no orders', 'this is not my decision' or 'your papers are not in order', it may be a real limit on their authority, fear of blame, or a tactic. This KROSS heuristic tells you to test the message, find who can decide, ask what constrains them, match their channel and format, and protect their standing. Each step is marked as CCHN-grounded or heuristic."
---

# When the Counterpart Cites Orders, Competence or Paperwork

## What it is for

Common blocking lines at a checkpoint or an office: "I have no orders." "This is not my decision." "That is the ministry's competence." "Your permit is not valid here."

Earlier KROSS material called this a "procedural wall", which is not a CCHN term and invites you to push through. This **KROSS practice heuristic** asks you to read the line as information about the counterpart's authority and risks first.

The same line can mean three things:
- **A real authority limit.** The counterpart has their own mandator and cannot decide this.
- **Fear of blame.** They could decide, but saying yes exposes them personally.
- **A tactic.** Hiding in technicalities to avoid a harder conversation, or keeping things ambiguous on purpose.

## The method

Each step says whether it is **CCHN** (with the Field Manual source) or **heuristic** (KROSS's own advice).

1. **Test the message (CCHN, Tool 9).** Before acting on what you hear, apply the three-pronged test (FM pp. 209–210):
   - How much authority does this person have?
   - How clear is the position?
   - Did it come through a predictable channel, at a predictable time, in the usual format?
   
   Ambiguity can be a deliberate tactic (FM p. 209), and less authoritative messages should not be dismissed, since they may carry a position informally (FM p. 210).

2. **Find who decides, and offer them a refer-back (CCHN, Tools 6 and 14).**
   - Tool 6's checklist asks who is in charge on the other side, who they report to and how much flexibility they have (FM p. 165).
   - Tool 14: the counterpart has its own bottom line and red line, and a proposal beyond its bottom line requires the counterpart to "refer back to his/her mandator" (FM pp. 291–294).
   - Pushing for an on-the-spot yes in that zone can make them politicise the negotiation (FM p. 294). Give them time and something to take upward.

3. **Ask what constrains them (CCHN, Tool 12).**
   - Counterparts weigh a move by its cost within their own constituency (FM p. 252).
   - They have "only a limited space in which to move within the acceptable margins of all the stakeholders" (FM p. 276).
   - Other actors' red lines can limit them (FM p. 295).

4. **Match their channel and format (CCHN, Tool 9).** A position gains authority when it comes in the expected form. You are expected to "use the same form and timing" when you reply (FM p. 210). If they work by written request through a given office, send one.

5. **Watch for a level shift (CCHN, Tool 4).**
   - Government representatives may stick to technical issues, "e.g., the allocation of travel permits", to avoid the more principled ones (FM p. 124). Humanitarians can get lost in technicalities too (FM p. 124).
   - Decide deliberately: solve the paperwork at the technical level, or name the real issue and take it to the right person.

6. **Protect their standing (heuristic, supported by CCHN).**
   - Make it safe to say yes: put requests in writing, involve their superior, give them credit.
   - The word "face" is not in the Field Manual. Tool 8 says assertiveness "aims to build on the authority and responsibility of the counterparts" and respects their social position (FM p. 180).
   - Tool 6 asks you to understand the counterpart's personal and institutional liabilities (FM p. 160).

7. **End with a next step (CCHN, Tool 6).** Agree who will do what and when, even if today's answer is no (FM p. 163).

## At the table

- "Who would be the right person to take this decision? Could you help us reach them?"
- "What would you need from us in writing to pass this on to your commander?"
- "I don't want to put you in a difficult position. What would make it easier for you to support this?"
- "So the next step is that we send the letter today, and you let us know by Thursday. Is that right?"

## What to avoid

- **Treating the line as a wall to break.** Threatening, or going loudly over their head ("I'll call your minister"), raises hostility and puts the blame risk squarely on them.
- **Acting on an informal "go ahead" without checking its authority and channel.** CCHN's checkpoint example shows how dangerous this can be (FM pp. 211–213).
- **Repeating your demand louder.** That is positional, not exploratory.
- **Arguing law to override procedure** ("international law gives us the right…"). CCHN advises against legal arguments the counterpart does not recognise (FM p. 349).
- **Assuming it is always a tactic, or always genuine.**

## How this relates to CCHN

- **Grounded in CCHN:**
  - the authority, clarity and predictability test (Tool 9);
  - asking who the counterpart reports to, and the counterpart's own bottom and red lines (Tools 6 and 14);
  - constituency constraints (Tool 12);
  - replying in the same form and timing (Tool 9);
  - level-shifting into technicalities (Tool 4);
  - building on the counterpart's authority and responsibility (Tool 8);
  - always agreeing next steps (Tool 6).
- **KROSS heuristic, not CCHN:**
  - the three readings (authority limit, fear of blame, tactic) as a diagnostic;
  - the idea of "protecting face";
  - the specific example lines.

CCHN does not have a named technique for this situation.

## Try instead

* *Instead of:* "This is ridiculous. We have every right to pass, and I will call your minister."
* *Try:* "I hear you, you don't have the order yet. Who would be able to give it, and how can we help get the request to them today?"

* *Instead of:* "Our papers are perfectly valid."
* *Try:* "Which document would you need to see, and from which office? We will make sure it comes through the usual channel."

## How KROSS uses it

- **Scenario data.**
  - `counterparts[].authority` describes what the counterpart can decide.
  - `hidden_interests` may include fear of blame or pressure from superiors, revealed as trust grows.
  - `stakeholders` lists who constrains the counterpart.
- **Rewarded moves.** `asks_good_question`, `identifies_interest` and `shows_respect_curiosity` (acknowledging the counterpart's role and building on their authority) lower `rigidity` and build `trust`.
- **Penalised moves.** `positional_demand`, `threatens` and `overclaims_norm` raise `rigidity`.

## Related tools

- Tool 9, Iceberg: the three-pronged test of authority, clarity and predictability.
- Tool 14, Cost-benefit of options: the counterpart's bottom line, red line and refer-back.
- Tool 12, Network mapping: constituency and spoilers.
- Tool 4, Typology: politicising and depoliticising, and technicalities.
- Tool 8, Human elements: assertive, not aggressive.
