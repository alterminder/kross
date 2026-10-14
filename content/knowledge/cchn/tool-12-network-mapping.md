---
id: cchn-tool-12
title: "Network Mapping and Leveraging Influence Among Stakeholders"
framework: "CCHN Field Manual on Frontline Humanitarian Negotiation"
citation: "CCHN Field Manual (2019), Tool 12, pp. 250-276; CCHN Negotiator Handbook, Tool 12, pp. 57-62"
tags: [stakeholders, network, influence, constituency, spoilers, alliance, coalition]
mapped_moves: [identifies_interest, asks_good_question, asks_about_constituency, offers_cover_for_cost]
mapped_dials: [rigidity, trust]
summary: "A counterpart's position depends on the people around them as much as on their own reasoning. Map stakeholders as the counterpart sees them (transformative to conservative, global to local), then use alliance, cooperation, coalition and mitigation so that moving toward your request becomes politically affordable, within the red lines that other actors impose on the counterpart."
---

# CCHN Tool 12: Network Mapping and Leveraging Influence Among Stakeholders

## What it is for

The analysis of interests and motives (Tool 9) assumes the counterpart has some autonomy. Yet positions are also shaped by the counterpart's environment, and values are a community concern discussed within their social network (p. 251). Tool 12 maps the actors who influence the counterpart on one issue. It helps you plan how to mobilize positive influence and reduce negative influence. The goal is a setting in which the counterpart can move toward your request (p. 250).

It is for one counterpart on one issue, and is meant to drive a discussion with the team, especially national staff (NH p. 57).

## The method

**Premises (pp. 252-255)**
1. Many competing actors are involved in any humanitarian negotiation.
2. Humanitarian negotiation is therefore part of a political process of balancing influences.
3. Neutrality means taking no position on the conflict issue. Yet humanitarian organizations still matter on the counterpart's political map, because they bring visibility, resources and legitimacy.

Empathy and legal or moral arguments are rarely enough. Weigh the counterpart's cost and benefit within their constituency's power relationships (p. 252). Unlike mediators, humanitarian negotiators address the immediate consequences of conflict, not its causes, and must avoid being instrumentalized (p. 254).

**Step 1: Define the axes (pp. 259-262)**
* **Horizontal: transformative to conservative.** This is the stakeholder's view on the issue being negotiated. Transformative actors want to change the current policy, and conservative actors want to keep it. The farther from the centre, the more radical the view.
* **Vertical: global to local.** This is identity as the counterpart perceives it, not as the actor sees itself. An international NGO that wants to be local may still look global to the governor. Other identity axes (ideological, religious, personal) can be used instead.
* Leave out actors with little or no influence on the counterpart, even beneficiaries who matter greatly to you. The manual calls them "forgotten people" (p. 262). Include actors who influence the counterpart and have a visible, continued presence.

**Step 2: Place the counterpart at the centre and position everyone (pp. 263-266).** Place your own organization on the map too. Perceptions are relative: each actor is at the centre of its own map. The quadrants often compete with each other, which benefits the counterpart, whose aim is to stay at the point of equilibrium. Each move the counterpart makes brings a political gain to some quadrants and a cost to others. The counterpart tries to stay within the "acceptable" limits, the red lines, of all competing actors (p. 265). Their zone to manoeuvre is the aggregation of those red lines (figure, p. 266).

**Step 3: Engage the four quadrants (Figure 8, pp. 267-270).** The manual's example negotiator is a global, transformative actor:
1. **Alliance** with peers in your own quadrant: compare notes, agree common norms, coordinate targeting and timing.
2. **Cooperation** with transformative local actors: support local organizations, give training and funding, and do not co-opt them.
3. **Coalition** with other global actors on the conservative side: attend their events and talk about parallel issues. The aim is not to agree on the negotiated issue but to build relationships in the counterpart's view.
4. **Mitigation** of the "spoilers" in the opposite quadrant (local, conservative): understand their concerns, assess their red lines, support technical projects and personalize relationships.

The scheme inverts for actors in other quadrants (p. 270). Make these efforts visible to the counterpart, to show that the cost of moving is affordable (p. 267).

**Step 4: Prioritize (pp. 270-275).** Invest sparingly. Target actors who:
* are open to listening,
* can explain your proposal to others,
* can draw a benefit for their own position from it, and
* have a direct, trusted relationship that leads to the counterpart.

Build a chain of positive influence and count each actor's degrees to the counterpart. The priority table also records how each actor perceives you ("too global", "slightly too transformative") and your proposed measures (NH p. 62).

## At the table

* Ask about the counterpart's constituency: *"Who else has a say in this, and whose opinion matters most to you?"*
* Treat outside constraints as real: *"If you agreed to visits, who would find it hardest to accept? What would help you explain the decision to them?"*
* When a spoiler is named, explore their concern instead of dismissing it: *"You mentioned the elders. What would worry them most?"*

## What to avoid

* Treating the map as a forecast. It is a planning aid built on subjective judgements (p. 255).
* Mapping alone. Rely on colleagues and national staff (pp. 257, 276).
* Spreading your networking too thin, or spending too much effort on passive actors (pp. 270-271).
* Forgetting that a big humanitarian success can create problems for other stakeholders and restrict the counterpart (p. 266).
* Expecting full compliance with IHL. The political cost of each further move rises as the counterpart compromises (p. 276).

## Key lines from the manual

> "humanitarian negotiation is intrinsically part of a political process of balancing influences among stakeholders." (p. 252)

> "Mapping influencers is not a scientific exercise." (p. 255)

> "Humanitarian negotiators are 'small fishes in a very large pond.'" (p. 256)

> "Counterparts have only a limited space in which to move within the acceptable margins of all the stakeholders." (p. 276)

## Try instead

* *Instead of:* "The embassies and the UN are all watching what you do here."
* *Try:* "What would you need to be able to explain this decision to the people you answer to?"

* *Instead of:* (the counterpart says the militia will object) "That is not our concern. We need access today."
* *Try:* "What exactly would the militia object to? Perhaps there is a way to address that concern."

## How KROSS uses it

* `stakeholders` puts actors on the counterpart's map. Each has a `stance` (transformative or conservative), a `scope` (global or local, as the counterpart perceives it), `degrees_to_counterpart`, an optional `red_line_on_counterpart` and a `tactic` (alliance, cooperation, coalition or mitigation).
* Part of a counterpart's rigidity comes from outside. `counterparts[].authority` (what they must consult on) and `hidden_interests` can carry constituency pressure, revealed through `asks_good_question`, `identifies_interest` and trust.
* Leaning on superiors, ministries or donors to pressure the counterpart counts as `threatens`, which raises hostility and rigidity.
* Debrief question: *Which stakeholders could influence the negotiation?*

## Related tools

* Tool 3 Legitimacy and Trust: connection with networks of influence is one source of legitimacy.
* Tool 9 Analyzing the Position of the Counterpart: the network explains the parts of a position the counterpart's own reasoning does not.
* Tools 13 and 14 (scenarios and bottom lines): design them within the limits that other stakeholders' red lines place on the counterpart (p. 265).
