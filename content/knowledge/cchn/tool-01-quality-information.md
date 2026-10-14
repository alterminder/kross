---
id: cchn-tool-01
title: "Gathering Quality Information About the Context"
framework: "CCHN Field Manual on Frontline Humanitarian Negotiation"
citation: "CCHN Field Manual (2019), Tool 1, pp. 48-63; CCHN Negotiator Handbook, Tool 1, pp. 8-10"
tags: [information, evidence, sources, chain-of-custody, corroboration, credibility, factual-negotiation]
mapped_moves: [asks_good_question, discloses_confidential, presents_sourced_information, presents_vague_claim, bundles_weak_claims, discloses_protected_source]
mapped_dials: [trust, consistency]
summary: "Score each piece of information 0-3 on source, chain of custody, clarity and third-party corroboration (max 12). Open with the strong, well-sourced elements and leave the weak ones out. Vague or bundled claims give the counterpart room to deny."
---

# CCHN Tool 1: Gathering Quality Information About the Context

## What it is for
A humanitarian negotiation usually starts with two competing narratives. The organization describes serious needs. The authority questions the accuracy of that information, the priority of the response or the organization's mandate (p. 48). How much traction your offer gets depends more on the quality of the information behind it than on how serious or urgent your concerns are. The more alarming the claim, the more closely the counterpart will check where it came from.

The tool helps you pick the information that will be credible *in the eyes of the counterpart*. Your own view of its credibility is not the test. Moral authority alone "is not enough to leverage influence on the counterpart" (p. 54).

## The method
**1. List the elements of your narrative** (p. 50). Cover the political, social, cultural, economic and legal context, the humanitarian issues, the people and processes that create needs and those that respond to them, past and current negotiations, and security issues.

**2. Score each element 0-3 on four criteria** (pp. 51, 54):
- **Source**: how well the counterpart knows and trusts the source (e.g. data from the local clinic).
- **Chain of custody**: whether every intermediary is trusted and holds the same standards.
- **Clarity**: as little ambiguity and vagueness as possible.
- **Corroboration**: whether an independent third party has confirmed it.

The scale runs 0 = poor, 1 = limited, 2 = good, 3 = highest quality (the Handbook says "excellent"), so the maximum is 12 per element (p. 54). The criteria tend to go together: clear information usually comes from a trusted source through an intact chain and is easy to corroborate (p. 51).

**3. Sort the elements.** In the manual's worked examples, a camp population estimate of "20,000-30,000" from community leaders via a local NGO scores 3/12 (pp. 54-55). A nutrition assessment from a recognized INGO, confirmed by other observers, scores 10/12 (pp. 56-57). The Handbook separates the most relevant information (> 6 points) from the least relevant (< 6) (NH p. 9).

**4. Act on the scores** (pp. 61-62):
- seek more information before the meeting;
- skip the weakest elements;
- admit what you do not know, but stress the strong elements;
- strengthen key elements by narrowing the statement, verifying the source, testing the chain of custody, or finding a third party to corroborate.

## At the table
- **Lead with your best-scoring facts.** In the manual's detention case (pp. 58-61), the strongest element (11/12) is that community members saw the police transfer the detained day laborer to a remote location at 12:30. Rumors that he was accused of theft score only 4/12.
- **Be specific, not dramatic.** Numbers, dates, places and a credible source carry weight.
- **Expect the counterpart to probe.** Counterparts assess their "information advantage" early. They may "bundle, hide, or contradict information" to create confusion (p. 51). Answer with precise, sourced detail, and do not invent anything to fill a gap.
- **Protect sources.** Sometimes you cannot reveal a source because it would put that person at risk. By default, gather information from several sources so that no single person can be identified (p. 52).

Example lines:
- "Community members saw a police car leave the village with our day laborer at 12:30 today. We would like to work this out with you before nightfall."
- "There is a lot we do not know yet. What we know clearly is when and where he was moved."
- "I cannot share who told us this, but several people described the same thing."

## What to avoid
- **Bundling.** Mixing strong and weak claims into one story weakens your starting position (p. 60). Weak elements can derail the process and make it easier for the counterpart to deny (p. 61).
- **Rough assessments.** They help mobilize resources quickly, but they become liabilities at the table (p. 49).
- **Relying on one source.** Single-source assessments are easy to instrumentalize (p. 51).
- **Trying to be the expert.** You do not need deep subject expertise. Experts may destabilize the counterpart and make them withdraw from the discussion (p. 62). Call on specialist support when you need it.
- **Exposing a source** who could face reprisal (p. 52).

## Key lines from the manual
> "Rough assessments, while of value for rapid mobilization of resources, can turn into major liabilities at the negotiation table." (p. 49)

> "Bundling the five statements as the overarching story weakens the starting position of this negotiation." (p. 60)

> "The negotiator should avoid introducing weak elements which will likely derail the process" (p. 61)

> "the negotiator should not aim to become a substantive expert on the object of the negotiation." (p. 62)

## Try instead
* *Instead of:* "We have information that dozens of families are starving in the areas under your control."
* *Try:* "A local church told us last week that 125 people suffer from severe malnutrition, 35 of them children. Twelve children are on therapeutic feeding at the local clinic." (example adapted from p. 49)

* *Instead of:* "Your men arrested our worker, they're holding him at the station, they say he stole seeds, and everyone knows how detainees get treated."
* *Try:* "Our day laborer was taken this morning, and a police car was seen leaving the village with him at 12:30. Can we look together at where he is now?"

## How KROSS uses it
- **Factual negotiations.** When `negotiation.type` is `factual`, the dispute is over facts. The Negotiator Handbook sends factual cases back to this tool (NH p. 24). `island_of_agreements.contested_facts` lists the points to clarify with evidence.
- **Trust and consistency.** Specific, sourced statements support `trust`. A trainee who changes a fact they stated earlier triggers `story_contradiction`, which lowers `trust` and `consistency`. Leading with weak claims makes that more likely.
- **Asking questions.** Questions that narrow an estimate or check a claim (`asks_good_question`) can unlock `counterparts[].hidden_interests` once their trust thresholds are reached.
- **Protecting sources.** Revealing a protected source counts as `discloses_confidential` and raises the `confidentiality` flag.

## Related tools
- Tool 2, Island of Agreements: sorts the facts you have scored into agreed and contested.
- Tool 3, Legitimacy and Trust: clear, verifiable messages are the "clarity" pillar of trust.
- Tool 5, Pathway of a Normative Negotiation: if the dispute is about norms rather than facts, better data alone will not settle it.
