---
id: cchn-tool-17
title: "Identification of Red Lines"
framework: "CCHN Field Manual on Frontline Humanitarian Negotiation"
citation: "CCHN Field Manual (2019), Tool 17, pp. 342-374 (with Module B introduction, pp. 340-341); CCHN Negotiator Handbook, Tool 17, pp. 81-87"
tags: [red_lines, mandator, legal_norms, humanitarian_principles, professional_standards, ethics, warning_signs]
mapped_moves: [overclaims_norm, unpacks_principle, refers_to_mandator, unauthorized_commitment, negotiates_own_red_line, debates_red_line_policy, notes_degradation_signal, transparent_red_line]
mapped_dials: [trust, hostility]
summary: "Red lines are the hard limits of the mandate. They come from legal, institutional, professional and moral-ethical sources, and they are set and changed only by the mandator, never by the negotiator. Used well, they are tools that protect the negotiator, not rules to wave at the counterpart."
---

# CCHN Tool 17: Identification of Red Lines

## What it is for
"There cannot be a mandate to negotiate an arrangement without some minimal limits" (p. 340). Tool 17 helps the mandator, negotiator and team trace where red lines come from and turn them into the limits of a specific mandate (NH p. 81). Red lines are "the hard limits of the mandate", beyond the negotiator's tactical bottom lines (p. 341).

## The method

**Who owns red lines (pp. 340, 363-364, 372-373)**
- Red lines belong to the mandator. Once a negotiator starts to steer them, "the construct of the mandate falls apart". The negotiator is then directly exposed to political and social pressure (p. 340).
- Red lines may be adapted in exceptional circumstances, on a cost/benefit basis, but only by the mandator at the right level of the hierarchy (e.g. limited armed escorts on specific segments where needs are extreme) (pp. 363-364).
- Red lines are "enablers rather than actual limits" (p. 340). They also keep the negotiator neutral between the counterpart and their own organisation, so they can "intercede between the two icebergs" (p. 373).

**Four sources (p. 342)**
1. **Legal** (pp. 342-350): community norms (customary, often oral, enforced "without much due process"), national laws (of the host state, of incorporation, of donors, of transit states and states hosting banks), and international law. International law does not apply directly unless the government is a party to the treaty or has otherwise agreed to it (p. 345). In the FM example, a lawyer-counterpart rebuts an NGO's claimed "right of access" and tax immunity point by point: treaty not ratified, ICRC study not binding, host-state consent required, immunities belong to others (pp. 346-347). Your own legal obligations can also frame red lines against undue demands, such as an informal "security fee" (pp. 348-349).
   Guidance (p. 349): (a) know which restrictions are actively enforced and which are "more rhetorical"; (b) spot norms used to extract undue advantages and seek clearance higher up; (c) avoid legal arguments unless the laws are in force, recognised by the counterpart *and* give an incontestable advantage; (d) get legal advice.
2. **Institutional** (pp. 350-359). Unlike legal red lines, these are "under the control of the organization", and the mandator may delegate some flexibility (p. 351). They fall into two groups:
   - *Humanitarian principles*, whose interpretations "vary from one organization to the next" (p. 351). **Humanity**: some organisations limit themselves to lifesaving aid, others include life-enhancing and rights-promoting work. **Neutrality**: do not take sides on the core of the conflict, yet "take the side of vulnerable groups" (p. 352). **Impartiality**: aid by need without discrimination, which raises hard questions about access (pp. 353-354). The mandator sets its terms. **Independence**: "remain skeptical" about your own claim (p. 354); it is judged in the eyes of the counterpart (p. 357).
   - *Other policies*: financial accountability, security protocols, rules against sexual harassment and abuse, "do no harm", duty of care, professional procedures (p. 357).
3. **Professional** (pp. 359-361): expected methods of assessment and delivery, of dealing with beneficiaries, and of conduct. Local customs apply "as long as these rules do not undermine the capacity and dignity of the negotiators" (p. 360).
4. **Moral or ethical** (pp. 361-363): personal and hard to judge objectively. "Growing discomfort is a signal" (pp. 361-362). In the FM case, children are detained with adults. The negotiator discusses it with the team and the mandator, and the mandator makes the call (p. 363).

**Application (pp. 366-372; NH pp. 82-87).** Step 1: per source, the policy and the red line it creates. Step 2: a summary by issue and stakeholder, a "starting point of conversation" "regularly revisited and reapproved by the mandator" (p. 372).

## At the table
- Present a limit as your organisation's, without closing the door: "That decision sits with my headquarters, not with me. I can put your proposal to them."
- Explain a principle in the counterpart's terms: "We decide who receives food by assessing needs ourselves. I'm happy to show you how."
- Make legal points only if they pass test (c); otherwise talk about shared interests.
- Watch for signs that the situation is degrading: unexplained cancellation, long waits, weapons in the room, unexplained silence, no eye contact, refusal to shake hands, an aggressive tone, people being moved around the table (pp. 360-361). Keep your own conduct professional and discuss the signs with your team.

## What to avoid
- Bending or renegotiating a red line yourself. If you are seen to control it, the pressure lands on you (p. 373).
- Claiming rights that are not in force or not recognised (pp. 346-349).
- Copying another organisation's concessions: their compliance "is not a motive to violate one's own rules" (p. 350).

## Key lines from the manual
> "The determination of the red lines should always stay within the domain of the mandator and never be under the control of the negotiator." (p. 340)

> "the point of the negotiation is to seek the consent of the counterpart to operate and not force its compliance" (p. 349)

> "a sudden lack of respect of the counterpart for the professional standing of the negotiation team may be a sign of a significant degradation of the situation." (p. 360)

> "Red lines are more 'tools' than 'rules' of humanitarian negotiation." (p. 372)

## Try instead
* *Instead of:* "Under international law, we have the right to access this camp."
* *Try:* "People in the camp need food. How can we organise distribution in a way that also meets your security concerns?"
* *Instead of:* "All right, I'll make an exception on escorts this time."
* *Try:* "Escorts are a policy question my headquarters decides. I'll put your proposal to them. Meanwhile, can we look at how to make the route safer?"
* *Instead of:* "Fine, we'll pay the security fee like the others."
* *Try:* "We are bound by the laws on fees and documentation that apply to us. Is there an official permit process we can follow?"

## How KROSS uses it
- **trainee_brief.red_lines**: each red line has a `source` (legal, institutional, professional or ethical, matching the four sources) and `flexible_by_mandator_only`, since only the mandator can adapt it. Crossing one raises the `red_line_crossed` flag.
- **Moves**: `overclaims_norm` (asserting rights that are not in force or not recognised, rebutted as in pp. 346-347); `unpacks_principle` (principles explained in the counterpart's terms); `refers_to_mandator` (sending a request to change a red line upward); `unauthorized_commitment` (agreeing past a red line).
- **Dials**: warning signs of degradation map onto rising `hostility`; overclaiming costs `trust`.

## Related tools
- Tool 13 Shared Benefit: red line (C) vs bottom line (B).
- Tool 15 Design of the Mandate: red lines sit in the confidential specific terms.
- Tool 11 Common Shared Space: discussing limits without door-closing language.
