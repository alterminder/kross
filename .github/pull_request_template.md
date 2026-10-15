## What and why

## Behaviour changes

<!-- Does this change how a session plays out (dials, reveals, outcomes, prompts)? Say so, or write "none". -->

## Checks

- [ ] Backend: `ruff check`, `ruff format --check`, `mypy`, `pytest`
- [ ] Frontend: `npm run typecheck`, `npm test`
- [ ] API changed → regenerated `openapi.json` and `schema.d.ts`
- [ ] Scenario schema changed → `npm run validators` in `frontend/`
