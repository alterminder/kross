# Backend

The Python package `nlab`: the rules engine, the model layer, the data layer and the FastAPI app.

| Package | What | Docs |
| --- | --- | --- |
| `nlab.engine` | Pure rules engine: dials, reveals, twists, outcomes, validation | [engine.md](../docs/architecture/engine.md) |
| `nlab.llm` | Every model call, with quote checks | [llm.md](../docs/architecture/llm.md) |
| `nlab.db` | Tables, tenancy filter, usage ledger | [backend.md](../docs/architecture/backend.md#data-layer-nlabdb) |
| `nlab.api` | FastAPI app: sign-in, orgs, scenarios, play, limits | [backend.md](../docs/architecture/backend.md) |

```sh
uv sync
uv run pytest                                   # engine, model layer, API (needs the dev Postgres) and golden replays
uv run ruff check && uv run ruff format --check && uv run mypy
```

Running the app locally: [docs/development.md](../docs/development.md).
