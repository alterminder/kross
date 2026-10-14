# Configuration

All runtime settings are environment variables read once at process start (restart to apply). Where a value is
set decides: backend runtime for `NLAB_*`/`LLM_*`/`GEMINI_*`/`IMAGE_MODEL`, the frontend build for `VITE_*`,
and Docker Compose for database wiring. Nothing in this table is read from the database.

Start from a template: [`.env.app.example`](../.env.app.example) (production runtime),
[`.env.example`](../.env.example) (Compose admin file) or [`backend/.env.example`](../backend/.env.example)
(local development).

## Feature switches

The ones operators turn on or off. Everything else is tuning below.

| Feature | Enabled by | Default | Disable / enable semantics |
| --- | --- | --- | --- |
| Guest play (anonymous, no sign-in) | `NLAB_GUEST_PLAY=true` | off | Off: visitors must sign in. On: guests start immediately, may only play curated scenarios alone, and have their own daily caps on top of the general ones |
| Strategic prep controls (Naivasha Grid) | frontend **build** with `VITE_HIDE_PREP=0` | hidden | Build-time only. Any other value or unset hides authoring and play controls. A runtime `.env.app` value does nothing. Saved prep data and its debrief section are kept and still shown either way |
| Multiple counterpart generation | `NLAB_ALLOW_MULTIPLE_COUNTERPARTS=true` | off | Off: generation creates one speaking counterpart. On: multiple actors from the brief. Generation only; existing scenarios keep their actors |
| Google sign-in | `NLAB_GOOGLE_CLIENT_ID` **and** `NLAB_GOOGLE_CLIENT_SECRET` | off | A provider appears only when all its fields are set; leave any empty to disable it |
| Organisation sign-in (OIDC) | `NLAB_OIDC_METADATA_URL`, `NLAB_OIDC_CLIENT_ID` and `NLAB_OIDC_CLIENT_SECRET` | off | Same all-or-nothing rule. `NLAB_OIDC_NAME`/`NLAB_OIDC_LABEL` only name the provider/button (defaults `sso` / `Organisation sign-in`) |
| Image generation (scenario covers) | `GEMINI_API_KEY` set | off | Without the key the painter is unavailable and cover generation degrades to no image |
| Per-role model thinking | on by default for every role | on | `<PREFIX>_THINKING=off\|disabled\|false\|0` (case-insensitive) turns thinking off for that role; then no reasoning effort is sent. Any other value or unset keeps it on |

## Core settings (`NLAB_*`)

| Variable | Default | Effect / type |
| --- | --- | --- |
| `NLAB_SECRET_KEY` | **required** | Signs the short-lived cookie carrying OIDC state. Production: random, ≥ 32 chars, no "change-me" |
| `NLAB_PRODUCTION` | `false` in code; Docker `ENV` default `true` | Enables the production gates below. Invalid security settings prevent startup. Compose forces `true`; the image env default can be overridden outside Compose |
| `NLAB_DATABASE_URL` | unset | Full SQLAlchemy URL (`postgresql+asyncpg://…`). **Wins over all `NLAB_DB_*` fields when set**; otherwise the URL is built from them (a password with URL characters then never needs encoding) |
| `NLAB_DB_HOST` / `NLAB_DB_PORT` / `NLAB_DB_USER` / `NLAB_DB_PASSWORD` / `NLAB_DB_NAME` | `localhost` / `5432` / `nlab` / unset / `nlab` | DB pieces used only when `NLAB_DATABASE_URL` is unset. `NLAB_DB_PASSWORD` is the runtime login (`nlab_app` under Compose) |
| `NLAB_CONTENT_DIR` | repository `content/` (`/app/content` in the image) | Path to the curated content |
| `NLAB_STATIC_DIR` | unset | The built frontend. Unset in development, where Vite serves it; the image sets `/app/static` |
| `NLAB_ROOT_PATH` | empty | Sub-path hosting is **not** supported: the container refuses to start when this is set |
| `NLAB_ALLOW_MULTIPLE_COUNTERPARTS` | `false` | See feature switches |

## Authentication and sessions

| Variable | Default | Effect / type |
| --- | --- | --- |
| `NLAB_PUBLIC_URL` | `http://localhost:8000` | Public address; sign-in redirects return here. Production must be an `https://` URL with a real (non-wildcard, non-loopback) hostname, no credentials/query/fragment |
| `NLAB_COOKIE_SECURE` | `true` | `Secure` flag and HTTPS-only cookies. Production requires `true` |
| `NLAB_SESSION_IDLE_HOURS` | `8` | Idle timeout (float, must be > 0) |
| `NLAB_SESSION_MAX_DAYS` | `7` | Absolute session lifetime (float, must be > 0) |
| `NLAB_SUPERADMIN_IDENTITIES` | `{}` | JSON `{"provider": ["stable subject", …]}`. Platform admins are pinned to provider + subject at every sign-in |
| `NLAB_SUPERADMIN_EMAILS` | empty | **Deprecated: grants nobody** (never consulted, fails closed). Production startup refuses when set; use `NLAB_SUPERADMIN_IDENTITIES` |
| `NLAB_GOOGLE_CLIENT_ID` / `NLAB_GOOGLE_CLIENT_SECRET` | unset | Google sign-in; both required to enable (see feature switches) |
| `NLAB_OIDC_NAME` / `NLAB_OIDC_LABEL` | `sso` / `Organisation sign-in` | Display names for the OIDC provider only |
| `NLAB_OIDC_METADATA_URL` / `NLAB_OIDC_CLIENT_ID` / `NLAB_OIDC_CLIENT_SECRET` | unset | OIDC sign-in; all three required to enable |

## Limits, concurrency and storage

**`0` disables a cap** where marked; limits marked *positive-only* cannot be zero (startup validation enforces ≥ 1).
Guest caps sit on top of the general ones. Daily windows are UTC days.

| Variable | Default | 0 semantics / bounds |
| --- | --- | --- |
| `NLAB_LIMIT_USER_SESSIONS_PER_DAY` | `30` | `0` = uncapped |
| `NLAB_LIMIT_USER_TOKENS_PER_DAY` | `1000000` | `0` = uncapped |
| `NLAB_LIMIT_ORG_TOKENS_PER_DAY` | `10000000` | `0` = uncapped |
| `NLAB_DAILY_SPEND_CEILING_USD` | `25.0` | `0` = uncapped (and the price checks below are skipped) |
| `NLAB_MODEL_PRICES` | `{}` | JSON `model: [USD per 1M input tokens, USD per 1M output tokens]`. With a non-zero ceiling, **production refuses to start unless every configured model (including the image model) is priced**; unpriced models count as 0 outside production (with a warning) |
| `NLAB_GUEST_LIMIT_SESSIONS_PER_DAY` | `3` | `0` = uncapped, per guest |
| `NLAB_GUEST_LIMIT_TOKENS_PER_DAY` | `150000` | `0` = uncapped, per guest |
| `NLAB_GUEST_LIMIT_TOTAL_TOKENS_PER_DAY` | `2000000` | `0` = uncapped, all guests together |
| `NLAB_GUEST_LIMIT_SIGNUPS_PER_DAY` | `200` | `0` = uncapped, new guests per day |
| `NLAB_GUEST_LIMIT_SIGNUPS_PER_IP_PER_DAY` | `20` | *Positive-only* (≥ 1) |
| `NLAB_GUEST_SESSION_HOURS` | `24` | Guest session lifetime; > 0 and ≤ 24 (purge assumes at most one day) |
| `NLAB_COACH_QUESTIONS_PER_SESSION` | `10` | `0` = uncapped |
| `NLAB_SESSION_RETENTION_DAYS` | `0` | `0` keeps play sessions forever (development); production requires > 0 matching the privacy notice (365 matches the privacy notice template) |
| `NLAB_LIMIT_USER_WRITES_PER_DAY` / `NLAB_LIMIT_ORG_WRITES_PER_DAY` / `NLAB_LIMIT_TOTAL_WRITES_PER_DAY` | `500` / `5000` / `20000` | *Positive-only* (≥ 1) |
| `NLAB_LIMIT_USER_STORAGE_BYTES` / `NLAB_LIMIT_ORG_STORAGE_BYTES` / `NLAB_LIMIT_TOTAL_STORAGE_BYTES` | `1e9` / `5e9` / `2e10` | *Positive-only* (≥ 1); cumulative allowances, not physical disk |
| `NLAB_MAX_CONCURRENT_MODEL_CALLS` / `NLAB_MAX_CONCURRENT_PAID_PER_USER` | `16` / `4` | *Positive-only* (≥ 1) |
| `NLAB_BACKGROUND_MAX_CONCURRENT` / `NLAB_BACKGROUND_MAX_PENDING` | `8` / `64` | *Positive-only* (≥ 1) |

## Models (any OpenAI-compatible endpoint)

Global settings and per-role overrides are read from the same environment (or `backend/.env` in development,
see "Where values are read" below). Without `LLM_API_KEY` the app runs but every model feature answers 503 and
sessions record debriefs as unavailable.

| Variable | Default | Effect |
| --- | --- | --- |
| `LLM_API_KEY` | **required for model features** | The main key; also the fallback key for every role |
| `LLM_MODEL` | `gpt-4o-mini` | Default model for every role |
| `LLM_BASE_URL` | unset (OpenAI) | Any OpenAI-compatible endpoint |
| `OPENAI_ORG_ID` / `OPENAI_PROJECT_ID` | unset | Read **indirectly by the OpenAI SDK itself**, not by the app. Deployment-wide scope: they annotate every call the SDK makes; they are not `NLAB_*` settings and not per-role configuration |

**Role override families.** Each role accepts the same suffixes with its prefix — one row per suffix, not 144:

| Prefix | Role | Extra suffixes |
| --- | --- | --- |
| `CLASSIFIER` | classifier | — |
| `AVATAR` | counterpart | `AVATAR_CLOSING_EFFORT` (effort for the one closing line, with thinking on), `AVATAR_FIRST_WORD_SECONDS` (float; a silent stream is retried once) |
| `GRANT` | grant check | — |
| `EVALUATOR` | evaluator | — |
| `DEBRIEF` | debrief | — |
| `CONVERTER` | brief-to-scenario conversion | — |
| `DIRECTOR` | free-text twist rewrite | — |
| `BIAS` | bias check | — |
| `COACH` | "Ask the Coach" | — |
| `SCOPE` | scope check | — |
| `BUILDER` | guided builder | — |
| `ILLUSTRATOR` | image scene description | — |

| Suffix (per prefix above) | Effect |
| --- | --- |
| `<PREFIX>_MODEL` | Model override for that role |
| `<PREFIX>_API_KEY` | Key override for that role. **Required for `<PREFIX>_BASE_URL` to apply**, so the main key never leaves for a third-party host |
| `<PREFIX>_BASE_URL` | Per-role endpoint; only read together with `<PREFIX>_API_KEY` |
| `<PREFIX>_REASONING_EFFORT` | Reasoning effort for that role (suppressed when thinking is off) |
| `<PREFIX>_THINKING` | `off\|disabled\|false\|0` turns that role's thinking off (see feature switches) |

Inheritance: `GRANT` and `SCOPE` follow the **classifier's** effective settings when a classifier is configured,
then the global ones; every other role starts from the global settings. Not environment-configurable (code-fixed):
per-call output bounds (8192 tokens default, room for reasoning models' thinking; coach answers 2000, converter 24000), input bound 131072, retries 0,
60 s call timeout (converter 300 s), 300 s total deadline, 20 s first-word bound.

## Images

| Variable | Default | Effect |
| --- | --- | --- |
| `GEMINI_API_KEY` | unset | Enables painting (scenario covers). Unset: painter unavailable, generation degrades to no image |
| `IMAGE_MODEL` | `gemini-3.1-flash-image` | Image model. **Production refuses any other value while image generation is enabled** (`GEMINI_API_KEY` set; needs reviewed token limits first) |

## Hosting and Compose

| Variable | Where set | Effect |
| --- | --- | --- |
| `POSTGRES_PASSWORD` | Compose `.env` (admin file) | Owner login: bootstraps the `nlab` owner role in the `db` service and is used by `docker compose run migrate` and admin scripts. The web app never sees it. Required |
| `POSTGRES_APP_PASSWORD` | Compose `.env` (admin file) | Restricted runtime login; must differ from `POSTGRES_PASSWORD`. Reaches the app **only** as `NLAB_DB_PASSWORD` |
| `NLAB_HTTP_PORT` | Compose `.env` (admin file) | Host loopback port the app is published on (default `8000`); the proxy connects here |
| `NLAB_DB_HOST` / `NLAB_DB_USER` / `NLAB_DB_NAME` / `NLAB_DB_PASSWORD` | `compose.yml` app service | Set to `db` / `nlab_app` / `nlab` / `POSTGRES_APP_PASSWORD`; overrides any `.env.app` value |
| `NLAB_PRODUCTION` | default `true` in the image; `compose.yml` forces `true` over `.env.app` | Enables the production gates. Under Compose they cannot be bypassed |
| `NLAB_FORWARDED_ALLOW_IPS` | `.env.app` (runtime) | `uvicorn --proxy-headers --forwarded-allow-ips` peer; default `127.0.0.1`. Must be the address the app sees the proxy connect from ([how to find it](deployment.md#3-reverse-proxy-and-tls)), never `*` |
| `VITE_HIDE_PREP` | **frontend build only** | See feature switches. The Dockerfile has no `VITE_HIDE_PREP` ARG/ENV and the release workflow passes no build args, so shipped images hide prep controls. Do not expect `.env.app` to change it |

Build-tool-only variables fixed in the `Dockerfile` (`UV_*`, `PYTHONDONTWRITEBYTECODE`, `PYTHONUNBUFFERED`,
`PATH`) and test/CI tooling variables are not application configuration and are out of scope here.

## Where values are read (precedence)

- **Runtime environment beats dotenv** everywhere: `NLAB_*` settings take environment variables over the `.env`
  file, and the model/image readers merge the same way (`os.environ` wins). The dotenv file is `.env` in the
  process's working directory — normally `backend/.env` for the documented development commands. The shipped
  container has no `.env` and gets everything from the environment (`.env.app` via Compose `env_file`).
- **`NLAB_DATABASE_URL` beats the `NLAB_DB_*` fields** when both are set.
- The Compose `.env` (admin file) is read by Docker Compose for interpolation only and is never given to the app
  container. `.env.app` must not contain any `POSTGRES_*` owner credential.

## Production hardening (`NLAB_PRODUCTION=true`)

Startup refuses: a `NLAB_SECRET_KEY` shorter than 32 chars or containing "change-me"; a `NLAB_PUBLIC_URL` that is
not an `https://` URL with a real hostname; `NLAB_COOKIE_SECURE=false`; non-positive
`NLAB_SESSION_RETENTION_DAYS`; a placeholder/short (< 20 chars) database password; any `NLAB_SUPERADMIN_EMAILS`
value; an unpriced configured model while `NLAB_DAILY_SPEND_CEILING_USD` is non-zero; and a non-default
`IMAGE_MODEL` while image generation is enabled (`GEMINI_API_KEY` set).
