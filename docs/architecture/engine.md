# Rules engine (`nlab.engine`)

The engine decides everything that matters in a session: how the counterpart's hidden state moves, what they reveal,
when a twist fires and how the negotiation ends. It is a pure library: typed inputs in, a new state and a list of
events out. It never reads files or the environment, never touches the network or the database and never calls a
model (`tests/engine/test_boundary.py` fails if it imports any of that). The same inputs always give the same result.

## State

| Part | What | Defined in |
| --- | --- | --- |
| Dials | `trust`, `rigidity`, `hostility` (0–100, initial values per scenario) and `consistency` (starts at 100 in every session) | `content/behaviour_rules.yaml` → `state_variables` |
| Negotiation level | `political`, `professional` or `technical` (CCHN Tool 4); triggers may shift it | `state_categories` |
| Revealed | Hidden interests the trainee has uncovered, in iceberg order (CCHN Tool 9): tactical reasoning first, motives and values later | scenario `hidden_interests`, rules `hidden_interest_reveal_defaults` |
| Flags | `mandate_breach`, `red_line_crossed`, `confidentiality`, `escalation` | `content/rubric.yaml` → `flags` |
| Offer, reached, outcome | An outcome offered to the counterpart, partial milestones reached, the final result | scenario `outcomes` |
| Moves, proposals, covered details | What the trainee did, with quotes | the classifier's output |

`State` serialises to JSON and is stored after every turn.

## Moves and dials

[`behaviour_rules.yaml`](../../content/behaviour_rules.yaml) defines about 70 **moves** (`asks_good_question`,
`acknowledges_emotion`, `threatens`, `premature_red_line`, `politicizes`, …) and how much each one changes each dial.
Every move names its `source`: the ICRC scenario bank, a CCHN Field Manual tool, or `design` (an engineering choice).

> The numbers are drafts. Neither the bank nor the CCHN manual gives numeric values. The *direction* of each change is
> grounded in its source; the *size* is a placeholder for trainers to confirm.

- A scenario may override any move's dial changes (`overrides`).
- An org admin may edit the dial changes for their org (`nlab.engine.rules.effective_rules` merges the shipped
  defaults with the org's saved edits). Each save is a new rules version; a session pins the version it started with.
- **Consistency** is a shared dial: `nonsense`, `story_contradiction`, `crude_language` and `insults_counterpart`
  lower it, every other turn recovers 5 points, and at 0 the global outcome `conversation_broke_down` ends the session.

## Conditions

Outcomes, triggers, hidden-interest reveals and automatic twists all use one condition language
(`nlab.engine.conditions`), parsed once when content loads:

```yaml
when:
  all:
    - trust_gte: 60
    - any: [{ move: identifies_interest }, { move: shows_respect_curiosity }]
```

Keys: `<dial>_gte`, `<dial>_lte`, `turn_gte`, `turn_lte`, `move`, `level`, `goal_requested`, `proposal_reaches`, and
nested `all` / `any`. An unknown key is a validation error, never silently false.

## Operations

Each operation takes typed inputs and returns `Step(state, events)`; inputs are never mutated.

| Function | Does |
| --- | --- |
| `start(scenario, rules)` | Initial state and the counterpart's opening line |
| `step(scenario, rules, state, text, classification)` | One trainee turn: dial changes, reveals, flags, triggers, automatic twists, then a `fail` outcome or an outcome offered to the counterpart |
| `grantable(state)` / `grant(scenario, state, quote)` | The counterpart said yes to an outcome offered on an earlier turn; the dials are re-checked first |
| `inject(scenario, state, id)` / `inject_text(...)` | A preset twist, or a trainer's free-text twist (rewritten in character and bias-checked by the model layer) |
| `set_dial(state, dial, value)` | Trainer override from the live console |
| `nudge(...)`, `time_up(...)`, `end(state)` | Pacing nudges, the session clock running out, the player ending the session |
| `validate(content, rules, rubric)` | JSON schema, then cross-checks against the rules and rubric; every issue has a field path |

## Outcomes

- `fail` outcomes are checked after every trainee turn and end the session at once. Twists and trainer overrides never
  end a session; the outcome is decided on the trainee's next message.
- `success` and `partial` need the counterpart to say yes: when their dial conditions hold, the counterpart is told to
  *offer* the outcome; on a later turn, the counterpart's own reply must *grant* it (checked by the grant-check model
  role), and the engine re-checks the dials. A `success` ends the session; a `partial` is a milestone and play continues.
- The player can end the session at any time (result `ended`).

## Events

Every change is an `Event` with a kind (`dial`, `reveal`, `detail`, `injection`, `grant`, `flag`, `level`, `cue`,
`outcome`, `ended`) and a structured cause: the move and its quote, a rule, a twist, or the trainer. The trainer view
and the debrief are built from these events, which is how "why did trust drop on turn 4?" always has an answer.

Cues (`hint`, `offer`, `agree_now`, `reached`) are typed; their wording lives in the counterpart prompt, not in the
engine.

## CCHN debrief

`nlab.engine.cchn_debrief` computes the method-specific debrief sections from the stored session: the negotiation
level over time, how deep into the counterpart's iceberg the trainee got, de-escalation steps completed, preparation
versus what actually happened, and competence indicators. Like the rest of the engine, it is pure.

## Tests

- `tests/engine/`: behaviour tests for every operation, the shipped scenarios and the rules file.
- `tests/golden/`: 26 sessions recorded with the hackathon prototype, replayed action by action; the engine must
  reproduce the prototype's state after every step.
