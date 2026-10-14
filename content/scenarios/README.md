# Scenario authoring

A scenario is one YAML file in this folder, in the format
[`negotiation-scenario.v2.schema.json`](../../backend/src/nlab/engine/schema/negotiation-scenario.v2.schema.json).
**A new scenario needs no code change.** Create one in the app (import a brief, use the guided builder, or open an
existing scenario and edit the form), or copy a file and edit it by hand. The server validates on load and on save,
and `python -m nlab.api.seed` loads this folder into the curated library.

| Group | Files | Source |
|---|---|---|
| ICRC scenario bank | `s01_idp_camp_access`, `s09_hostile_checkpoint` | [`../scenario_bank.md`](../scenario_bank.md) |
| CCHN worked cases | `s08_tripartite_siege`, `cacr_*`, `fwb_*`, `hfa_*`, `hfe_*`, `imn_*` | CCHN worked cases (named in each file's `sources`) |
| CCHN Field Manual cases | `detention_police_station`, `border_no_mans_land` | Cases in the CCHN Field Manual; places and names fictional |
| Skill drills | `drill_*` | Short, single-skill practice runs |
| Converted from a brief | `negotiating_safe_access_education_child` | Built with brief-to-scenario conversion |

All are drafts: `review.needs_icrc_confirmation` lists what ICRC must confirm.

## Generation examples

Case-study import and the guided builder use `s01_idp_camp_access.yaml` and `s09_hostile_checkpoint.yaml` as output
examples. The explicit selection lives in `nlab.api.content.CONVERSION_EXAMPLE_IDS`; adding a scenario to this
folder does not add it to the generation prompt. These examples remain drafts, not ICRC-approved scenarios.
The supplied brief or builder answers provide the new scenario's facts. `../scenario_bank.md` remains source
documentation and is not a runtime input. Bank-format briefs can still be uploaded individually.

Generation defaults to one speaking counterpart, with other actors described in the situation and counterpart
constraints. Set `NLAB_ALLOW_MULTIPLE_COUNTERPARTS=true` to allow additional counterparts and interactive
stakeholders from the brief. Restart the backend after changing this environment setting. Existing scenarios
keep their actors; the setting only controls newly generated drafts.

## Main sections

| Section | What it holds | Read by |
|---|---|---|
| `trainee_brief` | situation, objective, mandate (`can_decide`, `must_refer`), `red_lines` | Trainee screen, classifier |
| `counterparts[0]` | role (name first, then a comma), persona, cultural_profile, opening, `fallback` (a line in the counterpart's voice, said when the model gives no answer), iceberg, hidden_interests, `state_initial` (trust, rigidity, hostility) | Counterpart, rules |
| `issues`, `implementation_checklist` | Issue lines (ideal, bottom line, red line) and terms to pin down | Classifier, rules |
| `triggers` | `when` condition → `say` (a line for the counterpart) or `effect`, optional `shift_level` | Rules → cues |
| `injections` | Twists: `instruction`, optional `dials`, optional `auto` | Trainer buttons, rules |
| `outcomes` | `success` / `partial` / `fail` with `when` conditions | Rules |
| `rubric` | `dimensions` (ids from `content/rubric.yaml`) and `indicators` | Evaluator, debrief |
| `timing` | Optional pacing: `phases` (the stages in order, each with `id`, `label` and `hint` for the trainee, `instruction` for the counterpart, `until_turn` and `allow_injects`), `warnings` (minutes left for the clock's banners), `on_timeout` (`guide`, `end`, `fail` or `trainer`) and `silence` (`after_seconds`, `line`, `penalty`). The editor shows it with the basics, under Pacing | Counterpart, play page, trainer cockpit, session end |
| `avatar` | Portrait look, which dial drives each expression, voice id | Not used yet (kept for a future voice module) |
| `review` | `status`, `needs_icrc_confirmation` | Scenario editor (highlighted fields) |

The counterpart model also reads its own private brief, which it must never recite:
- `iceberg.position.implicit`, the reasoning style, and the feelings and needs from `iceberg.motives_values`;
- `iceberg.tactical_reasoning.text` once every `tactical_reasoning` hidden interest is revealed (or the scenario gates
  none), then `values` once every `motive_value` interest is revealed too;
- `constraints_from_constituency`, stakeholder limits, and hidden issue lines (ideal, bottom line, red line) only
  once every hidden interest is revealed: these fields can duplicate facts from either layer;
- `authority`, `challenges`, public issue lines (`hidden: false`), `island_of_agreements` as its view of the facts and
  norms, and `stakeholders` as the people it answers to.

Unrevealed hidden-interest text never reaches it. Fields still unread (`phases`, `multiparty`, `negotiation.nature`
and `type`, `behaviours`, `motive_candidates`) are listed under "Not used by the simulation" in the editor.

## Conditions

Used by `triggers`, `outcomes`, `auto`, `reveal_when`: `trust_gte`, `trust_lte`, and the same for `rigidity`,
`hostility`, `turn`; `move: <move id>`; `level: political|professional|technical`; `proposal_reaches`; nested
`any: [...]` or `all: [...]`. Move ids are in `content/behaviour_rules.yaml`. `consistency` is handled by the shared
rules, not by scenario conditions.

## Automatic injections

`auto: {at_turn: 4}` or `auto: {when: {trust_gte: 50}}` fires the injection once. If the trainer fires it first, the
automatic rule skips it. `dials: {hostility: 10}` changes the dials; `instruction` tells the counterpart what happened.

## Outcomes

`fail` outcomes are checked in order after every trainee turn and end the session at once. `success` and `partial`
need the counterpart itself to say yes: when their dial conditions hold, the counterpart is told to offer the outcome
(turn N); once the trainee accepts or asks (turn N+1 or later), the counterpart's own reply, checked by the grant
check, reaches it. A success ends the session. A `partial` outcome is a milestone, recorded in `reached`; the session
continues. `goal_requested` in a success or partial rule is ignored (asking is not agreeing).

```yaml
outcomes:
  - id: passage
    label: Convoy passage agreed
    result: success
    when: {trust_gte: 65, rigidity_lte: 50, hostility_lte: 50}
  - id: refused
    label: Refused
    result: fail
    when: {any: [{hostility_gte: 90}, {turn_gte: 12}]}
```

The trainee can also end the session at any time (result `ended`); that needs nothing in the scenario.

## Rules shared by every scenario

`content/behaviour_rules.yaml` adds a `consistency` dial (starts at 100) with the moves `nonsense`,
`story_contradiction`, `crude_language` and `insults_counterpart`, and a global outcome `conversation_broke_down`
(consistency reaches 0), checked before the scenario's own outcomes. The dial change of every move can be edited per
organisation on the Behaviour rules page; edits apply to all of that organisation's scenarios.

Trainer overrides and hand-fired injections change the dials immediately. Outcomes are only decided after the
trainee's next message.
