# Contributing

Thanks for helping. KROSS is used to train people for difficult, real negotiations, so changes are judged on two
things: does it make practice more realistic or feedback more trustworthy, and does it keep the simulation
explainable?

## Ways to help

- **Trainers and negotiators:** review the draft dial values and scenarios, report a counterpart that behaves
  unrealistically (with the session transcript), or contribute a scenario. Scenarios are YAML files and need no code:
  see [content/scenarios/README.md](content/scenarios/README.md).
- **Developers:** pick an [issue](https://github.com/alterminder/kross/issues) or an item from the
  [roadmap](ROADMAP.md). For anything larger than a bug fix, open an issue first so we can agree on the approach.

## Development

Setup, the dev server and all checks are in [docs/development.md](docs/development.md); how the pieces fit is in
[docs/architecture/](docs/architecture/README.md). Before you open a pull request, run:

```sh
cd backend && uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest
cd frontend && npm run typecheck && npm test
```

## Ground rules

- **The model describes, code decides.** Dials, reveals and outcomes change only in `nlab.engine`, from classified
  evidence. Do not let a model's free text decide game state.
- **Keep the boundaries.** `nlab.engine` stays pure; `nlab.llm` never reads the environment; `nlab.db` never imports
  HTTP. Tests enforce this.
- **Every judgement needs a quote.** New model outputs that judge the trainee must go through the quote checks.
- **Behaviour changes are explicit.** If a change alters how a session plays out, say so in the pull request and
  update the tests (including the golden replays) on purpose.
- **API changes regenerate the types**: `frontend/openapi.json` and `frontend/src/api/schema.d.ts` (see
  development.md). CI fails otherwise.
- **No secrets, no real people.** Never commit `.env` files, keys or real transcripts. Scenario names and places must
  be fictional, and generated images must not show protected emblems (see `frontend/public/covers/README.md`).

## Pull requests

Keep them small and focused, describe what changed and why, and link the issue. By contributing you agree that your
contribution is licensed under the [Apache License 2.0](LICENSE).
