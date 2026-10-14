import type { UiSchema } from "@rjsf/utils";

type Node = Record<string, any>;

/** What the editor calls one field: plain title, a one-line hint, array row wording, and audience for cards. */
export type FieldLabel = {
  label: string;
  hint?: string;
  /** The singular for array rows: "Skill" gives rows "Skill 1", "Skill 2" and buttons like "Remove Skill 2". */
  item?: string;
  /** The add-button text: "Add skill". */
  add?: string;
  /** The badge on the card: who of the two audiences reads this. */
  audience?: "trainee" | "hidden";
  /** Short string lists render as chips with an add button instead of rows. */
  chips?: boolean;
  /** Sentence-length text renders as a textarea, full width. */
  long?: boolean;
  /** Root-level simple fields sharing a group render in one card headed with it; an object joins that card when it is in the same tab. */
  group?: string;
  /** Plain display labels for enum options; the stored values stay as they are. */
  options?: Record<string, string>;
  /** Audience wording override, e.g. revealable facts are "Hidden at the start", not "never". */
  audienceAs?: string;
  /** Whether array items can be moved up/down. False removes reorder buttons. */
  orderable?: boolean;
  /** Whether the array is read-only metadata (no add, no reorder, no delete). */
  readOnly?: boolean;
  /** Takes the full width of the section (column-span: all). */
  wide?: boolean;
};

/**
 * Plain names and hints for every field the scenario schema defines, keyed by schema path (dots, `[]` for array
 * items). CCHN tool names stay where they are the trainer's vocabulary. Anything unmapped falls back to the
 * humanised key in the templates — a raw key never reaches the screen.
 */
export const LABELS: Record<string, FieldLabel> = {
  // ---- Basics
  schema: { label: "File format", hint: "Fixed — marks the scenario format version." },
  id: { label: "Scenario file id", hint: "The id scenario files and conditions refer to." },
  title: { label: "Scenario title", group: "The scenario" },
  difficulty: {
    label: "Difficulty",
    group: "The scenario",
    options: { beginner: "Beginner", intermediate: "Intermediate", advanced: "Advanced", expert: "Expert" },
  },
  estimated_minutes: { label: "Time limit (minutes)", group: "The scenario" },
  skills_tested: {
    label: "Skills tested",
    hint: "The negotiation skills this scenario exercises.",
    item: "Skill",
    add: "Add skill",
    chips: true,
  },
  negotiation: { label: "Negotiation style", hint: "CCHN typology: what kind of negotiation this is and where it starts.", group: "The scenario" },
  "negotiation.nature": {
    label: "Nature of the relationship",
    hint: "Relational, transactional or adversarial.",
    options: { relational: "Relational", transactional: "Transactional", adversarial: "Adversarial" },
  },
  "negotiation.type": { label: "Factual or normative", hint: "Whether the parties argue facts or norms.", options: { factual: "Factual", normative: "Normative" } },
  "negotiation.start_level": {
    label: "Negotiation style",
    options: { political: "Political", professional: "Professional", technical: "Technical" },
  },
  timing: { label: "Pacing", hint: "How the session is timed and what happens when things stall." },
  "timing.phases": { label: "Stages", hint: "The meeting's stages, in order.", item: "Stage", add: "Add stage" },
  "timing.phases[].id": { label: "Stage id", hint: "What rules and conditions refer to." },
  "timing.phases[].label": { label: "Stage name", hint: "What the trainee sees as the stage's name." },
  "timing.phases[].hint": { label: "Stage note", hint: "What the trainee sees about the stage." },
  "timing.phases[].instruction": { label: "How the counterpart behaves", hint: "In this stage. The trainee never sees it." , long: true },
  "timing.phases[].until_turn": { label: "Runs until turn", hint: "The stage lasts up to this trainee turn." },
  "timing.phases[].allow_injects": { label: "Twists allowed", hint: "Off: the trainer cannot fire a twist during this stage." },
  "timing.warnings": { label: "Time warnings", hint: "Minutes left when the trainee sees a soft banner.", item: "Minute mark", add: "Add warning" },
  "timing.on_timeout": { label: "When time runs out", hint: "What happens when the scenario's minutes are over." },
  "timing.silence": { label: "When the trainee goes quiet", hint: "How the counterpart reacts to silence." },
  "timing.silence.after_seconds": { label: "After (seconds)", hint: "Seconds of silence before the counterpart speaks up." },
  "timing.silence.line": { label: "What they say", hint: "Their line, word for word. Left out: the model improvises one." , long: true },
  "timing.silence.penalty": { label: "Hostility cost", hint: "How much a silence raises hostility." },
  preparation: { label: "Preparation stage", hint: "The Naivasha Grid groundwork before the meeting." },
  "preparation.time_limit_minutes": { label: "Preparation time (minutes)", hint: "How long the trainee has to prepare." },
  "preparation.modules": {
    label: "Preparation tools",
    hint: "Which preparation tools the trainee works through.",
    item: "Tool",
    add: "Add tool",
    options: {
      island_of_agreements: "Island of Agreements",
      information_quality: "Information quality",
      legitimacy_profile: "Legitimacy profile",
      level_and_narrative: "Level and narrative",
      counterpart_iceberg: "Counterpart iceberg",
      common_shared_space: "Common Shared Space",
      network: "Network",
      lines_and_options: "Lines and options",
      meeting_checklist: "Meeting checklist",
    },
  },
  review: { label: "Review status", hint: "Where this scenario stands in the review process." },
  "review.status": { label: "Status", hint: "Draft until an ICRC reviewer has looked it over.", options: { draft: "Draft", reviewed: "Reviewed" } },
  "review.needs_icrc_confirmation": {
    label: "Fields waiting for an ICRC check",
    hint: "Confirming a field in the editor clears its entry here.",
    item: "Field",
    readOnly: true,
  },
  sources: { label: "Source material", hint: "Where the scenario came from." },
  "sources.bank": { label: "Scenario bank", hint: "The bank entry it was built from." },
  "sources.cchn_tools": { label: "CCHN references", hint: "Field Manual tools cited as source material." },
  generated: { label: "Conversion notes", hint: "Filled in when a scenario was converted by the tool. Safe to ignore." },
  "generated.tool": { label: "Conversion tool", hint: "What did the conversion." },
  "generated.model": { label: "Model used", hint: "The model behind the conversion." },
  "generated.prompt_version": { label: "Prompt version", hint: "The conversion prompt's version." },
  "generated.source_sha256": { label: "Source checksum", hint: "Fingerprint of the source text." },
  "generated.notes": { label: "Conversion notes", hint: "What the converter noted.", item: "Note", readOnly: true },
  "generated.warnings": { label: "Conversion warnings", hint: "What the converter flagged for a human.", item: "Warning", readOnly: true },

  // ---- Trainee brief
  trainee_brief: { label: "Trainee brief", hint: "What the trainee reads before and during the session.", audience: "trainee" },
  "trainee_brief.situation": { label: "Situation", hint: "What is going on, as the trainee learns it." , long: true },
  "trainee_brief.objective": { label: "Objective", hint: "What the trainee must achieve." , long: true },
  "trainee_brief.decision_options": { label: "Choices to weigh", hint: "Open decisions the trainee must think through.", item: "Choice", add: "Add choice", orderable: false },
  "trainee_brief.facts": { label: "What you know", hint: "Verified facts the trainee holds at the start.", item: "Fact", add: "Add fact", orderable: false },
  "trainee_brief.mandate": { label: "Mandate", hint: "What the trainee may decide alone and what must go back to the mandator.", audience: "trainee" },
  "trainee_brief.mandate.can_decide": { label: "May decide alone", hint: "From the ideal outcome down to the bottom line.", item: "Point you may agree", add: "Add point", orderable: false },
  "trainee_brief.mandate.must_refer": { label: "Must refer back", hint: "Between the bottom line and the red line; the mandator decides.", item: "Point to refer", add: "Add point", orderable: false },
  "trainee_brief.red_lines": { label: "Red lines", hint: "What can never be agreed.", item: "Red line", add: "Add red line", orderable: false },
  "trainee_brief.red_lines[].text": { label: "The red line", hint: "In one sentence." , long: true },
  "trainee_brief.red_lines[].source": {
    label: "Where it comes from",
    hint: "Legal, institutional, professional, ethical or moral.",
    options: { legal: "Legal", institutional: "Institutional", professional: "Professional", ethical: "Ethical", moral: "Moral" },
  },
  "trainee_brief.red_lines[].flexible_by_mandator_only": { label: "Only the mandator may move this", hint: "The negotiator can never trade it away." },

  // ---- Strategic prep (Naivasha Grid)
  island_of_agreements: { label: "Island of Agreements", hint: "CCHN Tool 2: what the two sides already agree on.", audience: "trainee" },
  "island_of_agreements.agreed_facts": { label: "Agreed facts", hint: "Facts both sides already accept.", item: "Fact", add: "Add agreed fact", chips: true },
  "island_of_agreements.contested_facts": { label: "Contested facts", hint: "Facts the two sides read differently.", item: "Fact", add: "Add contested fact", chips: true },
  "island_of_agreements.convergent_norms": { label: "Shared norms", hint: "Principles both sides stand on.", item: "Norm", add: "Add shared norm", chips: true },
  "island_of_agreements.divergent_norms": { label: "Conflicting norms", hint: "Principles the sides weigh differently.", item: "Norm", add: "Add conflicting norm", chips: true },
  claims: { label: "Information claims", hint: "CCHN Tool 1: pieces of information and how solid they are.", item: "Claim", add: "Add claim" },
  "claims[].id": { label: "Claim id", hint: "What the debrief refers to." },
  "claims[].text": { label: "The claim", hint: "What the information says." , long: true },
  "claims[].criteria": { label: "Assessment", hint: "How solid the claim looks on the CCHN assessment key (0–3 each)." },
  "claims[].criteria.source": { label: "Source quality", hint: "How reliable the source is (0–3)." },
  "claims[].criteria.method": { label: "Method", hint: "How the information was gathered (0–3)." },
  "claims[].criteria.fact_checking": { label: "Fact checking", hint: "How well it was cross-checked (0–3)." },
  "claims[].criteria.relevance": { label: "Relevance", hint: "How much it matters here (0–3)." },
  own_iceberg: { label: "The trainee's iceberg", hint: "CCHN Tools 4 & 10: the trainee's own why, how and what.", audience: "trainee" },
  "own_iceberg.why": { label: "Why — purpose", hint: "What the trainee is really after." , long: true },
  "own_iceberg.how": { label: "How — approach", hint: "How they mean to get there." , long: true },
  "own_iceberg.what": { label: "What — position", hint: "What they put on the table." , long: true },
  css: { label: "Common Shared Space", hint: "CCHN Tool 11: where the two sides' interests overlap.", audience: "trainee" },
  "css.convergent": { label: "Converging interests", hint: "Where the sides want the same thing.", item: "Interest", add: "Add interest", chips: true },
  "css.divergent": { label: "Diverging interests", hint: "Where the sides pull apart.", item: "Interest", add: "Add interest", chips: true },
  "css.potential_synergies": { label: "Possible trade-offs", hint: "Gains one side can offer the other cheaply.", item: "Idea", add: "Add idea", chips: true },

  // ---- Counterpart
  counterparts: { label: "Counterparts", hint: "Who sits on the other side. Only the first counterpart is played.", item: "Counterpart", add: "Add counterpart" },
  "counterparts[].id": { label: "Internal id", hint: "What conditions and rules refer to." },
  "counterparts[].role": { label: "Role", hint: "Their job in the story, e.g. Deputy head of the colony." },
  "counterparts[].persona": { label: "Persona", hint: "How they come across, in a line or two." , long: true },
  "counterparts[].cultural_profile": { label: "Cultural and communication profile", hint: "Written by a trainer: how someone from this context talks and listens." , long: true },
  "counterparts[].authority": { label: "Authority", hint: "CCHN Tool 9: what they may decide and what must go up.", audience: "hidden" },
  "counterparts[].authority.decides": { label: "May decide", hint: "What is theirs to settle.", item: "Point they may decide", add: "Add point", orderable: false },
  "counterparts[].authority.must_consult": { label: "Must consult others", hint: "What needs someone else's word.", item: "Point to consult", add: "Add point", orderable: false },
  "counterparts[].opening": { label: "Opening line", hint: "The first thing they say when the session starts." , long: true },
  "counterparts[].fallback": { label: "Fallback line", hint: "What they say when no answer comes, so they never break character." },
  "counterparts[].preferred_level": {
    label: "Preferred level",
    hint: "The level they are most comfortable on.",
    options: { political: "Political", professional: "Professional", technical: "Technical" },
  },
  "counterparts[].legitimacy_weights": { label: "Legitimacy", hint: "CCHN Tool 3: what gives the other side the right to ask, in their eyes.", audience: "hidden" },
  "counterparts[].legitimacy_weights.legal": { label: "Legal basis", hint: "How much weight the law carries for them." },
  "counterparts[].legitimacy_weights.institutional": { label: "Institutional mandate", hint: "How much weight an institution's word carries." },
  "counterparts[].legitimacy_weights.professional": { label: "Professional standing", hint: "How much weight expertise carries." },
  "counterparts[].legitimacy_weights.moral": { label: "Moral authority", hint: "How much weight a moral claim carries." },
  "counterparts[].motive_candidates": {
    label: "Possible motives",
    hint: "Authoring notes on the possible motives the brief lists. Stored in the file; the simulation does not read them.",
    item: "Motive",
    add: "Add motive",
  },
  "counterparts[].iceberg": { label: "Iceberg", hint: "CCHN Tool 9: stated position, reasoning, and what sits underneath.", audience: "hidden" },
  "counterparts[].iceberg.position": { label: "Position", hint: "The visible tip: what they say they want.", audience: "hidden" },
  "counterparts[].iceberg.position.stated": { label: "Stated position", hint: "Their demand, in their own words." , long: true },
  "counterparts[].iceberg.position.implicit": { label: "Unsaid positions", hint: "What they also want but do not say.", item: "Position", add: "Add position", orderable: false },
  "counterparts[].iceberg.tactical_reasoning": { label: "Tactical reasoning", hint: "How they justify the position to themselves.", audience: "hidden" },
  "counterparts[].iceberg.tactical_reasoning.type": {
    label: "Kind of reasoning",
    hint: "Legal, professional, logical, and so on.",
    options: {
      legal: "Legal",
      professional: "Professional",
      logical: "Logical",
      military: "Military",
      political: "Political",
      necessity: "Necessity",
      alternative_norm: "Alternative norm",
      ignorance: "Lack of information",
    },
  },
  "counterparts[].iceberg.tactical_reasoning.text": { label: "The reasoning", hint: "Why the position makes sense to them." , long: true },
  "counterparts[].iceberg.motives_values": { label: "Motives and values", hint: "What sits at the bottom of the iceberg.", audience: "hidden" },
  "counterparts[].iceberg.motives_values.values": { label: "Values", hint: "What they stand on.", item: "Value", add: "Add value", chips: true },
  "counterparts[].iceberg.motives_values.emotions": { label: "Emotions", hint: "What they feel about it.", item: "Emotion", add: "Add emotion", chips: true },
  "counterparts[].iceberg.motives_values.deep_needs": { label: "Deep needs", hint: "What they need out of this.", item: "Need", add: "Add need", chips: true },
  "counterparts[].hidden_interests": {
    label: "Hidden facts",
    hint: "What the trainee must earn to hear.",
    item: "Hidden fact",
    add: "Add hidden fact",
    audience: "hidden",
    audienceAs: "Hidden at the start",
    orderable: false,
  },
  "counterparts[].hidden_interests[].id": { label: "Fact id", hint: "What conditions refer to." },
  "counterparts[].hidden_interests[].layer": {
    label: "Depth",
    hint: "How deep it sits: their reasoning or their motives.",
    options: { tactical_reasoning: "Tactical reasoning", motive_value: "Motive and value" },
  },
  "counterparts[].hidden_interests[].text": { label: "What they are hiding", hint: "The fact itself." , long: true },
  "counterparts[].hidden_interests[].reveal_when": { label: "Reveal when", hint: "The moment the trainee has earned it." },
  "counterparts[].challenges": { label: "Difficulties they face", hint: "Their own problems away from the table.", item: "Difficulty", add: "Add difficulty", orderable: false },
  "counterparts[].constraints_from_constituency": {
    label: "What their people will accept",
    hint: "The people they answer to set these limits.",
    item: "Limit",
    add: "Add limit",
    audience: "hidden",
    orderable: false,
  },
  "counterparts[].state_initial": { label: "Where they start", hint: "The dials the run opens with.", audience: "hidden" },
  "counterparts[].state_initial.trust": { label: "Trust", hint: "How much they trust the trainee at the start (0–100)." },
  "counterparts[].state_initial.rigidity": { label: "Rigidity", hint: "How stuck on their position they start (0–100)." },
  "counterparts[].state_initial.hostility": { label: "Hostility", hint: "How hostile they start (0–100)." },
  degradation_cues: {
    label: "Early warning signs",
    hint: "CCHN Tool 8: signs the situation or the counterpart is hardening.",
    item: "Warning sign",
    chips: true,
  },
  stakeholders: { label: "People around the counterpart", hint: "CCHN Tool 12: who they answer to and who answers to them.", item: "Person", add: "Add person" },
  "stakeholders[].id": { label: "Id", hint: "What conditions and rules refer to." },
  "stakeholders[].role": { label: "Role", hint: "Their job and where they sit." },
  "stakeholders[].stance": {
    label: "Stance",
    hint: "Transformative or conservative.",
    options: { transformative: "Transformative", conservative: "Conservative" },
  },
  "stakeholders[].scope": { label: "Reach", hint: "Global or local.", options: { global: "Global", local: "Local" } },
  "stakeholders[].influence": { label: "Influence", hint: "How much pull they have.", options: { high: "High", medium: "Medium", low: "Low" } },
  "stakeholders[].degrees_to_counterpart": { label: "Distance to the counterpart", hint: "How many steps away from the counterpart (1 = direct)." },
  "stakeholders[].red_line_on_counterpart": { label: "Their limit for the counterpart", hint: "What they will not let the counterpart do." , long: true },
  "stakeholders[].tactic": {
    label: "How to work with them",
    hint: "Alliance, cooperation, coalition or mitigation.",
    options: { alliance: "Alliance", cooperation: "Cooperation", coalition: "Coalition", mitigation: "Mitigation" },
  },
  avatar: { label: "Portrait and voice", hint: "How the first counterpart looks and sounds (not used yet)." },
  "avatar.look": { label: "Look", hint: "What they look like." },
  "avatar.look.skin": { label: "Skin", hint: "In a few words." },
  "avatar.look.hair": { label: "Hair", hint: "In a few words." },
  "avatar.look.outfit": { label: "Outfit", hint: "What they wear." },
  "avatar.look.hat": { label: "Headwear", hint: "None, a cap or a beret.", options: { none: "None", cap: "Cap", beret: "Beret" } },
  "avatar.look.moustache": { label: "Has a moustache" },
  "avatar.look.long_hair": { label: "Long hair" },
  "avatar.mood": { label: "Expressions", hint: "Which dial drives each expression." },
  "avatar.mood.warmth": { label: "Warmth", hint: "The dial that drives it; a leading minus inverts it." },
  "avatar.mood.anger": { label: "Anger", hint: "The dial that drives it; a leading minus inverts it." },
  "avatar.mood.attention": { label: "Attention", hint: "The dial that drives it; a leading minus inverts it." },
  "avatar.mood.worry": { label: "Worry", hint: "The dial that drives it; a leading minus inverts it." },
  "avatar.mood.daylight": { label: "Daylight", hint: "The dial that drives it; a leading minus inverts it." },
  "avatar.mood.confusion": { label: "Confusion", hint: "The dial that drives it; a leading minus inverts it." },
  "avatar.voice": { label: "Voice", hint: "The voice they speak with." },
  "avatar.voice.id": { label: "Voice id", hint: "The voice service's id." },
  "avatar.voice.name": { label: "Voice name", hint: "A name for the voice." },
  "avatar.voice.description": { label: "Voice description", hint: "How the voice sounds." },
  "avatar.voice.sample": { label: "Voice sample", hint: "A sample to listen to." },

  // ---- Rules & twists
  triggers: { label: "Automatic reactions", hint: "What fires by itself when the moment comes.", item: "Reaction", add: "Add reaction", orderable: false },
  "triggers[].when": { label: "When", hint: "The moment this fires." },
  "triggers[].say": { label: "They say", hint: "A line the counterpart says then." , long: true },
  "triggers[].effect": { label: "Effect", hint: "What it changes behind the scenes." , long: true },
  "triggers[].shift_level": {
    label: "Shift the level to",
    hint: "Moves the conversation to another level.",
    options: { political: "Political", professional: "Professional", technical: "Technical" },
  },
  injections: { label: "Trainer twists", hint: "Buttons on the trainer console, fired mid-session.", item: "Twist", add: "Add twist" },
  "injections[].id": { label: "Twist id", hint: "What rules and conditions refer to." },
  "injections[].label": { label: "Button label", hint: "What the trainer sees on the button." },
  "injections[].instruction": { label: "What happens", hint: "What the twist does to the counterpart." , long: true },
  "injections[].auto": { label: "Fire automatically", hint: "By turn number or when a condition holds." },
  "injections[].auto.at_turn": { label: "At turn", hint: "Fires on this trainee turn." },
  "injections[].auto.when": { label: "When", hint: "Fires when this holds." },
  "injections[].dials": { label: "Dial changes", hint: "How much each dial moves (−100 to 100)." },
  outcomes: { label: "Outcomes", hint: "How the session can end, and what counts as success.", item: "Outcome", add: "Add outcome", orderable: false },
  "outcomes[].id": { label: "Outcome id", hint: "What rules and the debrief refer to." },
  "outcomes[].label": { label: "Outcome name", hint: "What the debrief calls it." },
  "outcomes[].result": { label: "Result", hint: "Success, partial or failure." },
  "outcomes[].when": { label: "When", hint: "The ending this belongs to." },
  issues: { label: "Issues", hint: "CCHN Tools 13/14: what is on the table and where each side's lines sit.", item: "Issue", add: "Add issue", orderable: false },
  "issues[].id": { label: "Issue id", hint: "What conditions and rules refer to." },
  "issues[].label": { label: "Issue name", hint: "What everyone calls it." },
  "issues[].tier": { label: "How hard it is", hint: "1 quick win, 2 demanding, 3 needs the mandator." },
  "issues[].own": { label: "Our lines", hint: "Ideal, bottom line and red line, from the mandate.", audience: "trainee" },
  "issues[].own.ideal": { label: "Ideal outcome", hint: "What we dream of." , long: true },
  "issues[].own.bottom_line": { label: "Bottom line", hint: "Where we stop saying yes." , long: true },
  "issues[].own.red_line": { label: "Red line", hint: "Where we walk." , long: true },
  "issues[].own.hidden": { label: "Keep hidden for now", hint: "Do not open with this line." },
  "issues[].counterpart": { label: "Their lines", hint: "Hidden until a trainee proposal reaches them.", audience: "hidden" },
  "issues[].counterpart.ideal": { label: "What they dream of", hint: "Their best outcome." , long: true },
  "issues[].counterpart.bottom_line": { label: "Where they fold", hint: "Where they still say yes." , long: true },
  "issues[].counterpart.red_line": { label: "Where they walk", hint: "Where they refuse and end it." , long: true },
  "issues[].counterpart.hidden": { label: "Hidden from the trainee", hint: "Surfaces only when a proposal reaches this line." },
  implementation_checklist: {
    label: "Implementation checklist",
    hint: "CCHN Tool 7: the five things a workable agreement covers.",
    item: "Check",
    add: "Add check",
    orderable: false,
  },
  "implementation_checklist[].id": { label: "Id", hint: "What rules and the debrief refer to." },
  "implementation_checklist[].criterion": { label: "Criterion", hint: "Commitments, roles and tasks, sequence, divergence, or responsibility." },
  overrides: { label: "Rule changes", hint: "Any shared rule this scenario replaces.", wide: true },
  multiparty: { label: "Parallel talks", hint: "CCHN Tool 14: other tables running at the same time." },
  "multiparty.confidential_between": { label: "Confidential deals", hint: "Terms kept between some of the parties.", item: "Deal", add: "Add deal" },
  "multiparty.confidential_between[].term": { label: "The term", hint: "What was agreed quietly." , long: true },
  "multiparty.confidential_between[].between": { label: "Between", hint: "Who it is kept between.", item: "Party", add: "Add party" },

  // ---- Scoring & debrief
  rubric: { label: "Scoring", hint: "What a good negotiation scores here." },
  "rubric.dimensions": { label: "Scoring dimensions", hint: "As the shared rules name them.", item: "Dimension", add: "Add dimension", orderable: false },
  "rubric.indicators": { label: "Watch for", hint: "Signs of a good negotiation to look out for.", item: "Indicator", add: "Add indicator", orderable: false },
  "rubric.score_scale": { label: "Score scale", hint: "Overrides the shared scale for this scenario." },
  "rubric.score_scale.min": { label: "Lowest score", hint: "The bottom of the scale." },
  "rubric.score_scale.max": { label: "Highest score", hint: "The top of the scale." },
  "rubric.score_scale.labels": { label: "Score labels", hint: "What each score is called." },
  debrief: { label: "Debrief", hint: "What the debrief shows and how it speaks." },
  "debrief.sections": {
    label: "Debrief sections",
    hint: "Which parts of the debrief report to show.",
    item: "Section",
    add: "Add section",
    orderable: false,
    options: {
      agreement_check: "Agreement check",
      zones: "Zones of agreement",
      level_timeline: "Level timeline",
      iceberg_depth: "Iceberg depth",
      deescalation_report: "De-escalation report",
      prep_vs_reality: "Prep vs reality",
      reflection: "Reflection",
      competences: "Competences",
    },
  },
  "debrief.feedback_style": {
    label: "Feedback style",
    hint: "How the debrief words its feedback.",
    options: { coaching: "Coaching", rigorous: "Rigorous", direct: "Direct", supportive: "Supportive" },
  },
  reflection: { label: "Reflection questions", hint: "CCHN Tool 6: what the trainee answers after the session.", wide: true },
  "reflection.questions": { label: "", item: "Question", add: "Add question", orderable: false },
  "reflection.questions[].id": { label: "Question id", hint: "What the debrief refers to." },
  "reflection.questions[].prompt": { label: "The question", hint: "What the trainee is asked." , long: true },
  "reflection.questions[].guidance": { label: "Guidance", hint: "A hint shown with the question." , long: true },

  // ---- Extras (not used by the simulation)
  phases: { label: "Story stages", hint: "Ordered stages of a long scenario, verbatim lines only.", item: "Stage", add: "Add stage" },
  "phases[].id": { label: "Stage id", hint: "What rules and conditions refer to." },
  "phases[].name": { label: "Stage name", hint: "What the stage is called." },
  "phases[].instruction": { label: "What happens", hint: "What the counterpart or the engine does in this stage." , long: true },
  "phases[].counterpart_says": { label: "What they say", hint: "Verbatim line from the brief." , long: true },
  "phases[].trainee_must": { label: "What the trainee must do", hint: "The step the trainee is expected to take." , long: true },
  "counterparts[].behaviours": { label: "Habits", hint: "Scenario-specific habits (CCHN Tools 6 and 7)." },
  "counterparts[].behaviours.vague_replies": { label: "Deliberately vague answers", hint: "Lines that dodge without refusing.", item: "Line", add: "Add line" },
  "counterparts[].behaviours.closing_test": { label: "How they test the close", hint: "What they say to check the deal is real." , long: true },
};

/** The map entry for a path, with the humanised key as the fallback: a raw key never reaches the screen. */
export function labelFor(path: string): FieldLabel {
  return LABELS[path] ?? { label: humaniseKey(path.split(".").at(-1)?.replace(/\[\]/g, "") ?? path) };
}

/** "skills_tested" -> "Skills tested"; the fallback for any unmapped key. */
export function humaniseKey(key: string): string {
  const text = key.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** The row wording for an array's items ("Skill"), falling back to the singular of its label. */
export function itemFor(path: string): { item: string; add: string } {
  const entry = LABELS[path] ?? {};
  const one = entry.item ?? singular(entry.label ?? humaniseKey(path.split(".").at(-1) ?? path));
  return { item: one, add: entry.add ?? `Add ${one.toLowerCase()}` };
}

function singular(word: string): string {
  return word.replace(/ies$/i, "y").replace(/s$/i, "");
}

/** Deep merge for uiSchema trees: the extra's leaves win, nested marks (like condition fields) survive. */
export function mergeUi(base: Node, extra: Node): Node {
  const out: Node = { ...base };
  for (const [key, value] of Object.entries(extra)) {
    const prior = out[key];
    out[key] =
      prior && value && typeof prior === "object" && typeof value === "object" && !Array.isArray(prior) && !Array.isArray(value) ? mergeUi(prior, value) : value;
  }
  return out;
}

/**
 * The rjsf uiSchema built from the map: plain titles, the one-line hints (replacing the schema's developer notes),
 * array row titles and add-button text, and chips for short lists. Walks the served schema like conditionUiSchema
 * does, so a new field gets its fallback name from this walk alone.
 */
export function labelUiSchema(schema: unknown): UiSchema {
  const root = (schema ?? {}) as Node;
  const defs = (root.$defs ?? {}) as Record<string, Node>;

  function walk(node: Node, base: string, seen: Set<string>): Node {
    const out: Node = {};
    let spec = node ?? {};
    let next = seen;
    if (typeof spec.$ref === "string") {
      const name = spec.$ref.replace("#/$defs/", "");
      if (seen.has(name)) return out;
      spec = defs[name] ?? {};
      next = new Set([...seen, name]);
    }
    for (const [key, child] of Object.entries((spec.properties ?? {}) as Record<string, Node>)) {
      const path = base === "" ? key : `${base}.${key}`;
      const entry = labelFor(path);
      const mark: Node = { "ui:title": entry.label, "ui:description": entry.hint ?? "" };
      if (entry.label === "") {
        mark["ui:options"] = { ...(mark["ui:options"] || {}), label: false };
      }
      if (entry.long) mark["ui:widget"] = "textarea";
      if (entry.options) mark["ui:enumNames"] = entry.options; // plain option labels; the stored values stay
      // resolve the child's $ref first: arrays like $defs/strings hide behind one
      let sub = child;
      let subSeen = next;
      if (typeof child.$ref === "string") {
        const name = child.$ref.replace("#/$defs/", "");
        sub = defs[name] ?? {};
        subSeen = new Set([...next, name]);
      }
      if (sub.type === "array" || sub.items) {
        const { item, add } = itemFor(path);
        mark["ui:addButtonText"] = add;
        if (LABELS[path]?.chips) {
          mark["ui:chips"] = true;
          mark["ui:field"] = "pills";
        }
        if (LABELS[path]?.orderable === false) {
          mark["ui:orderable"] = false;
          mark["ui:options"] = { ...(mark["ui:options"] || {}), orderable: false };
        }
        if (LABELS[path]?.readOnly) {
          mark["ui:orderable"] = false;
          mark["ui:readonly"] = true;
          mark["ui:options"] = { ...(mark["ui:options"] || {}), addable: false, orderable: false, removable: false };
        }
        mark.items = { ...walk((sub.items as Node) ?? {}, `${path}[]`, subSeen), "ui:title": item };
        if (LABELS[path]?.chips) mark.items["ui:chips"] = true;
        const itemEntry = labelFor(`${path}[]`);
        if (itemEntry.options ?? entry.options) mark.items["ui:enumNames"] = (itemEntry.options ?? entry.options)!; // enum-arrays read labels from items
      } else {
        Object.assign(mark, walk(child, path, next));
      }
      // oneOf/anyOf branches (e.g. multiparty's deals) carry properties of their own
      for (const alt of ["oneOf", "anyOf"] as const) {
        for (const branch of (sub[alt] ?? []) as Node[]) Object.assign(mark, walk(branch, path, subSeen));
      }
      out[key] = mark;
    }
    for (const alt of ["oneOf", "anyOf"] as const) {
      for (const branch of (spec[alt] ?? []) as Node[]) Object.assign(out, walk(branch, base, next));
    }
    return out;
  }

  return walk(root, "", new Set()) as UiSchema;
}
