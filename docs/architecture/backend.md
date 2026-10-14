# Backend (`nlab.api` and `nlab.db`)

A FastAPI app (`nlab.api.main:app`) on Postgres through async SQLAlchemy. `nlab.api` owns HTTP, cookies, sign-in and
CSRF; `nlab.db` owns the data rules and knows nothing about HTTP.

## API layout

All routes live under `/api`; every other path serves the built frontend (`nlab.api.spa`), so deep links work.

| Module | Routes |
| --- | --- |
| `auth`, `identity` | `/api/auth/*`: providers, OIDC login and callback, guest sign-in, sign-out |
| `account` | `/api/me`: the caller, their orgs, the active org, the daily allowance, account deletion |
| `org`, `invites` | Members, roles and invite links of the active org; opening and accepting an invite |
| `scenarios` | The library: cards, details, create and edit with validation, publishing, covers, brief conversion, the guided builder |
| `rules` | The active org's behaviour rules |
| `play` | Start a session, send turns (streamed), end, debrief, preparation and reflection notes, coach questions |
| `steer` | Trainer actions on a live session: dials, free-text twists, comments |
| `knowledge` | The knowledge library |
| `admin` | Creating orgs and the usage report (superadmins) |
| `health` | `/api/health` |

The OpenAPI schema (`python -m nlab.api.openapi`) is the contract with the frontend, whose TypeScript types are
generated from it.

## Sign-in and sessions

- **OIDC only.** Google and one generic OIDC provider (an organisation's own SSO) share one Authlib code path. A
  provider is enabled only when all its settings are present. Optional guest play creates an anonymous account with
  its own caps.
- **Identity = provider + subject.** A new identity becomes its own user even when a verified email matches an
  existing account, so a recycled mailbox can never hand one person another person's account.
- **Server-side sessions.** The `nlab_session` cookie (httpOnly, `Secure` in production, `SameSite=Lax`) carries a
  random token; the database stores only its SHA-256 hash. Sign-out, member removal and account deletion revoke
  access at once. Sessions have an idle timeout and an absolute lifetime.
- **CSRF.** `SameSite=Lax` plus a required `X-Requested-With: nlab` header on every state-changing request.
- **Authorisation** is checked on every request against the membership in the active org, never cached in the cookie.
- **Superadmins** are pinned to provider + subject (`NLAB_SUPERADMIN_IDENTITIES`), checked against the identity that
  authenticated the session.
- **Invite links** carry their token in the URL fragment (`/invite#<token>`) and request bodies, never in a path or
  query string, so it stays out of access logs and `Referer` headers. Tokens are stored hashed.

## Data layer (`nlab.db`)

| Area | Tables |
| --- | --- |
| Accounts | `users`, `identities`, `auth_sessions` |
| Tenancy | `orgs`, `memberships`, `invites` |
| Library | `scenarios`, `scenario_versions`, `scenario_cover_images`, `rule_versions` |
| Play | `play_sessions`, `turns`, `turn_comments` |
| Usage and limits | `llm_calls` (the ledger), `budget_reservations`, `daily_admissions`, `storage_buckets` |

- **Tenancy.** Functions that read or change an org's data take an `OrgContext` and filter by it. Scenario reads go
  through `visible_to`, the one place that decides who sees what: `private` (the creator), `org` (the org library) or
  `public` (curated, managed by superadmins). Tests try cross-org reads and must fail.
- **Versions.** Every save of a scenario or of an org's rules is a new immutable version; play sessions pin both.
- **Turn claims.** A conditional update on the session row claims a turn, so two messages can never race; no
  transaction stays open across a model call (`tests/api/test_play_transactions.py` probes `pg_stat_activity` to prove it).
- **Migrations** (Alembic, `backend/migrations/`) run only when an operator runs them, never on start.
- **Database roles.** In production the app connects as `nlab_app` (DML only, no DDL, no superuser); the owner login
  is used only by the one-shot `migrate` container. See [deployment.md](../deployment.md#2-start-migrate-seed).

## Cost control

Model calls cost money, so every billed call is admitted before it reaches the provider:

1. `nlab.api.budget.Budgeted` wraps the provider. Before each call it checks, in one short transaction, the caller's
   remaining user, org and guest token caps and the deployment's daily spend ceiling against the call's worst case,
   then opens a reservation.
2. After the call, one atomic update settles that exact reservation with the real usage. An open reservation counts
   at its full size, so work in flight is never free and nothing is counted twice.
3. A refused call raises before any charge exists and answers `429`.

Separately, `nlab.api.storage` admits every authenticated write against per-user, per-org and deployment write and
storage allowances. These counters survive deletion, so deleting content never restores an allowance.

Limits are configured with `NLAB_LIMIT_*`, `NLAB_GUEST_*` and `NLAB_DAILY_SPEND_CEILING_USD`; see
[configuration.md](../configuration.md#limits-concurrency-and-storage). Superadmins see usage and estimated cost at
`/api/admin/usage`.

## Background work

Turn scoring and debriefs run as bounded in-process tasks (`nlab.api.background`, `nlab.api.scoring`), each in its own
database session. A restart loses running tasks; the session end scores whatever is missing before writing the
debrief.

## Operations commands

| Command | Does |
| --- | --- |
| `python -m nlab.api.seed` | Loads `content/scenarios/*.yaml` into the curated library (safe to repeat) |
| `python -m nlab.api.purge` | Deletes old play sessions (`NLAB_SESSION_RETENTION_DAYS`), old guests, expired sign-in sessions and obsolete daily counters; run daily |
| `python -m nlab.api.auth_admin identities` | Lists sign-in identities with their stable subjects (what `NLAB_SUPERADMIN_IDENTITIES` needs) |
| `python -m nlab.api.auth_admin revoke-sessions --user-id <uuid>` | Ends every session of one user |
| `python -m nlab.api.openapi` | Prints the OpenAPI schema |

## HTTP policy

`nlab.api.http_policy` bounds request bodies and upload time, requires the CSRF header, and sends security headers
(CSP with `frame-ancestors 'none'`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`) and
`Cache-Control: no-store` on API responses. With `NLAB_PRODUCTION=true`, startup refuses insecure settings; see
[configuration.md](../configuration.md#production-hardening-nlab_productiontrue).
