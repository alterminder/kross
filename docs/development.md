# Development

You need Docker (for Postgres), [uv](https://docs.astral.sh/uv/) and Node 22.

## Run it locally

```sh
docker compose -f compose.dev.yml up -d --wait db      # Postgres on 127.0.0.1:5433
cd frontend && npm install && npm run build && cd ..   # the web app, served by the dev server
cd backend && uv sync
uv run python -m tests.dev_server                      # http://127.0.0.1:8765, scripted model
```

Run the last command from `backend/`. Sign in without a password at
`http://127.0.0.1:8765/api/auth/dev/login?as=alice`; `as=admin` is a superadmin. The dev server answers with a
scripted model. It lets anyone sign in as anyone, so it exists only on your machine: it lives under `backend/tests/`,
which the Docker image never contains (CI checks this).

- **A real model:** put `LLM_API_KEY` (and optionally `LLM_BASE_URL`, `LLM_MODEL` or per-role settings; see
  [configuration.md](configuration.md)) in `backend/.env`, then add `--real-llm`. Drafting scenarios from a brief
  needs a real model.
- **Hot reload of the frontend:** run `uv run python -m tests.dev_server --public-url http://localhost:5173` and, in
  `frontend/`, `npm run dev`.
- **Sign in with Google locally:** put `NLAB_GOOGLE_CLIENT_ID` and `NLAB_GOOGLE_CLIENT_SECRET` in `backend/.env` and
  register the redirect URI `<public URL>/api/auth/google/callback` in Google Cloud:
  `http://127.0.0.1:8765/api/auth/google/callback` by default, or `http://localhost:5173/api/auth/google/callback`
  with `--public-url http://localhost:5173`. The dev server prints it at startup.

## Run the API without the dev server

```sh
cd backend
cp .env.example .env              # set NLAB_SECRET_KEY and a sign-in provider
uv run --env-file .env alembic upgrade head
uv run --env-file .env python -m nlab.api.seed    # load the curated scenarios (safe to repeat)
uv run uvicorn nlab.api.main:app --reload
```

Migrations run only when you run `alembic upgrade head`, never on start. They read the same settings as the app, so
`NLAB_SECRET_KEY` and the `NLAB_DB_*` (or `NLAB_DATABASE_URL`) variables must be set. Without `LLM_API_KEY` the server
runs and answers 503 for model features.

The files win over API edits of curated scenarios: the seed makes each curated scenario match
`content/scenarios/*.yaml`, adding a new version over any API edit, and a curated scenario deleted in the app stays
deleted (the seed reports it as `retired`).

## Checks

| What | Command |
| --- | --- |
| Backend lint, format, types | `cd backend && uv run ruff check && uv run ruff format --check && uv run mypy` |
| Backend tests | `cd backend && uv run pytest` |
| Frontend types and unit tests | `cd frontend && npm run typecheck && npm test` |
| End-to-end (Playwright) | `cd frontend && npx playwright install chromium && npm run e2e` |

The API tests create and migrate a database called `nlab_test` on the dev Postgres server (override with
`NLAB_TEST_DATABASE_URL`). `npm run e2e` builds the frontend and starts the dev server on :8765 with a fresh `nlab_e2e`
database. CI runs the same checks on every pull request (`.github/workflows/`).

`backend/tests/golden/fixtures/` replays 26 recorded sessions from the hackathon prototype through the engine; the
expected values came from the prototype itself, so they pin the engine's behaviour.

## After changing the API

The frontend's TypeScript types are generated from the backend's OpenAPI schema:

```sh
cd backend && uv run python -m nlab.api.openapi > ../frontend/openapi.json && cd ../frontend && npm run gen
```

CI fails when `frontend/openapi.json` or `frontend/src/api/schema.d.ts` is out of date.

## Scenario covers

The card images in `frontend/public/covers/` were generated once with `scripts/generate_covers.py` (needs
`GEMINI_API_KEY`); see [its README](../frontend/public/covers/README.md) for the rules every image must follow.
