# Model layer (`nlab.llm`)

Every model call goes through `nlab.llm`. The package never reads the environment or files (except its own bundled
`prompts.toml`); the app builds the configuration and the provider and passes them in
(`tests/llm/test_boundary.py`).

## Roles

Each role is a separate, configurable call. Defaults come from `LLM_*`; any role can use its own model, key, endpoint,
reasoning effort and thinking switch through its prefix (see [configuration.md](../configuration.md#models-any-openai-compatible-endpoint)).

| Role | Env prefix | Does | Output |
| --- | --- | --- | --- |
| classifier | `CLASSIFIER` | Labels the latest trainee message: moves, goal requests, red lines, proposals, operational details, mandate breaches | Structured, quote-checked |
| counterpart | `AVATAR` | Speaks as the counterpart, from a prompt built by code from the scenario, revealed interests and engine cues | Streamed text |
| grant | `GRANT` | Did the counterpart's reply grant the offered outcome? | The granting quote, or nothing |
| evaluator | `EVALUATOR` | Scores a turn against the rubric (1–5 per dimension) | Structured, quote-checked |
| debrief | `DEBRIEF` | Summary, strengths, missed chances with "try instead", one focus for next time | Structured, quote-checked |
| coach | `COACH` | "Ask the Coach" after a session, grounded in the knowledge notes | Streamed text |
| scope | `SCOPE` | Is a coach question on topic? Off-topic questions get a fixed refusal | Structured |
| converter | `CONVERTER` | Brief → draft scenario; quoted lines must appear verbatim in the brief | Structured |
| builder | `BUILDER` | The guided scenario builder's interview | Structured |
| director | `DIRECTOR` | Rewrites a trainer's free-text twist in character | Structured |
| bias | `BIAS` | Checks a rewritten twist for bias | Structured |
| illustrator | `ILLUSTRATOR` | Writes the scene description for a scenario cover | Structured |

Cover pictures themselves are painted by a separate image model (`GEMINI_API_KEY`, `IMAGE_MODEL`) through
`nlab.api.pictures`; the usage ledger records them under the `painter` role.

## Evidence or nothing

`nlab.llm.quotes` makes every judgement provider-independent: a label, score, flag or debrief point needs a quote that
code finds in the source text, or it is dropped. The number of dropped quotes is recorded per call, so a model that
invents evidence shows up in the usage data.

## Structured output

`nlab.llm.structured` asks for JSON matching a Pydantic model, validates it, retries once, and fails loudly. A reply in
the wrong shape never validates as "nothing observed". Models that do not support `json_schema` response formats
(`deepseek*` models, and any model that rejects it once) fall back to JSON mode, then to plain text, with the expected
shape described in the prompt.

## Provider

`nlab.llm.provider.Provider` is the single interface: `complete` for a whole answer and `stream` for text chunks, both
reporting token usage. `nlab.llm.openai_compat` implements it for any OpenAI-compatible chat API (OpenAI, DeepSeek,
Swisscom, Ollama, …). The app wraps the provider in budget admission (`nlab.api.budget.Budgeted`), so
the model layer never has to know about limits.

## Prompts

All prompts live in [`prompts.toml`](../../backend/src/nlab/llm/prompts.toml), loaded once. They started as verbatim
copies of the hackathon prototype; deliberate changes are pinned by `tests/llm/test_prompts.py`. Field descriptions in
`nlab.llm.answers` are part of the prompt too.

## Call records

Every role returns its result together with a `CallRecord`: role, model, input and output tokens, latency, outcome and
quote rejections. The app writes one ledger row per call (never the message text), which feeds daily limits, the
spend ceiling and the superadmin usage report.

## Bounds

Fixed in code, not configurable: 2048 output tokens by default (coach answers 2000, converter 24000), an input bound
of 131072 tokens, no SDK retries, a 60 s call timeout (converter 300 s), a 300 s total deadline and a 20 s bound on
the counterpart's first word (a silent stream is retried once).
