---
id: cchn-tool-02
title: "Drawing the Island of Agreements"
framework: "CCHN Field Manual on Frontline Humanitarian Negotiation"
citation: "CCHN Field Manual (2019), Tool 2, pp. 64-84; CCHN Negotiator Handbook, Tool 2, pp. 11-13"
tags: [island-of-agreements, facts, norms, factual-negotiation, normative-negotiation, relationship, starting-point]
mapped_moves: [proposes_shared_objective, shows_respect_curiosity, argues_principles_only, overclaims_norm, opens_on_agreed_ground, opens_on_contested_point, argues_to_prove_reality]
mapped_dials: [trust, rigidity]
summary: "Sort the situation into agreed and contested facts and convergent and divergent norms. Start the conversation from the agreed facts and convergent norms (the island of agreements), then decide whether the real negotiation is about facts or about norms."
---

# CCHN Tool 2: Drawing the Island of Agreements

## What it is for
Each party sees the conflict through its own lens, which the manual calls a "kaleidoscopic vision" (p. 64). Unlike operational or technical analysis, negotiation context analysis must include how the counterpart reads reality (p. 64). This tool helps you find the ground the two sides already share, the "island of agreements", so that you can build trust there before taking on what divides you (p. 68). It also tells you what kind of negotiation you face: factual or normative.

Agencies have two roles: guardian of norms (advocacy) and pragmatic problem-solver (negotiation). At the table you play the second (p. 67).

## The method
**Facts and norms** (p. 66). A fact is something observable that the observer considers true. A norm is a way of behaving considered normal in a culture, or a behavior a group believes in. In the Handbook's short form, facts are "things one can see, observe" (NH p. 11).

**The four-column matrix** (pp. 79-81; NH p. 13):

| Contested facts | Agreed facts | Convergent norms | Divergent norms |
|---|---|---|---|
| Points to be clarified with factual evidence | Points of agreement to start the dialogue | Points to be underlined as convergent values | Points of divergence on norms to be negotiated |

The two middle columns form the island. From there the negotiation moves outward in one of two directions:
- **Factual negotiation**: widen the parties' shared understanding of the facts, using evidence. Convergent norms are taken as given.
- **Normative negotiation**: widen their shared understanding of the norms by building a new consensus on which norms apply. Agreed facts are taken as given (pp. 69-70, 81).

Facts that can be negotiated include the number and profile of beneficiaries, their location, technical terms (time, date, mode) and nutrition or health status. Norms that can be negotiated include the right of access, the parties' obligations, the population's legal status and the priority of the operation (p. 71).

**Three steps** (pp. 75-80):
1. Sort the facts and norms from both narratives into the four columns.
2. Decide whether the negotiation is factual or normative. List the issues from most to least agreeable.
3. Agree with the counterpart on where the discussion starts, and keep your objectives in view.

The Handbook adds: write key messages linking agreed facts and convergent norms, and choose priority issues among the contested ones (NH p. 12).

**The paradox** (pp. 68-69). To dispute a fact, a party usually has to accept, at least implicitly, some norms. To dispute a norm, it usually has to accept some facts. A party that rejects every fact and every norm closes off the relationship. So there is always some shared ground.

**Small talk can be an island** (p. 70). Common ground unrelated to the issue counts too: sports, food, music, shared frustration with hierarchy, patience over tea. The aim is to make the negotiation "a co-owned process of discovery".

## At the table
- **Open on the island.** Start with an agreed fact or a convergent value, not with the point of conflict.
- **Normative case** (the manual's no man's land example, p. 82): start from agreed facts (where the people are, the food situation, their needs, logistics). Build rapport on shared values, then turn to the hard question of access.
- **Factual case** (p. 83): start from convergent norms, then move to the disputed facts.
- **Match the argument to the dispute.** Facts call for evidence (Tool 1). Data will not settle a conflict of norms (Tool 5).

Example lines:
- "We agree that people are stuck between the two borders, and that shelter and food there are short."
- "Nobody here wants anyone to die of hunger, and your country's security matters. Can we start from that?"
- "Where we see things differently is how many people are there. Could we look at that together?"

## What to avoid
- **Trying to win the argument about reality.** The goal is a working relationship, not proving your version (p. 67). Do not be dogmatic about your own perceptions (p. 84).
- **Treating differences as ignorance or a violation.** The counterpart may define who counts as a child, or who the leaders are, differently from you. Read beyond the apparent disagreement (p. 67).
- **Splitting the difference on a norm.** In the child-recruitment example, a "deal" around 16 years old "could be as inappropriate as 14 or 18" (p. 74).
- **Contesting everything at once.** It leaves no starting point.

## Key lines from the manual
> "Parties to the negotiation may agree in effect about the implementation of an international norm without ever agreeing about the international norm itself." (p. 66)

> "The point of a humanitarian negotiation is not to prove one vision is superior to the other but to build a trustful relationship conducive to reaching an operational agreement." (p. 67)

> "To assert contested facts, a party often needs to agree, even implicitly, on convergent norms." (p. 68)

> "Negotiators are not mandated to convince the other side about one version of reality or to ensure compliance of the institutional norms" (p. 84)

## Try instead
* *Instead of:* "Under international law, you are obliged to let us cross the border."
* *Try:* "We agree no one should be left to starve, and we respect that your country's security comes first. Could we start with where the people are and what they need?"

* *Instead of:* "Your figures are simply wrong. There is a famine in that camp."
* *Try:* "We both want the food to reach the people who need it most. Could we compare our figures for the camp with yours?"

## How KROSS uses it
- **The scenario's island.** `island_of_agreements` holds the author's matrix. `negotiation.type` (factual or normative) gives the direction of the main negotiation.
- **Opening well.** Opening on an agreed fact or shared value usually counts as `proposes_shared_objective` (lower `rigidity`, higher `trust`). Curiosity about the counterpart's view fits `shows_respect_curiosity`.
- **Opening badly.** Leading with a divergent norm stated as a right is `argues_principles_only`. Claiming a norm the counterpart does not recognize is `overclaims_norm`. Both raise `rigidity`.
- **The iceberg.** `counterparts[].iceberg.motives_values` often shows where the counterpart's norms lie.

## Related tools
- Tool 1, Quality Information: the evidence you need for a factual negotiation.
- Tool 3, Legitimacy and Trust: adaptability starts from the agreed facts and convergent norms.
- Tool 4, Typology: factual negotiations are mostly technical; normative ones are political or professional.
- Tool 5, Pathway of a Normative Negotiation: how to handle a real conflict of norms.
