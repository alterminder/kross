# Self-hosting

KROSS runs as two containers from [`compose.yml`](../compose.yml): the app (API plus the built frontend) and Postgres.
You put your own reverse proxy with TLS in front. Every setting is described in [configuration.md](configuration.md).

## Requirements

- A server with Docker Engine and the Compose plugin. **4 GB RAM / 2 vCPU** is a sensible minimum: the containers are
  limited to 1 GB each, plus the proxy and the OS.
- A domain pointing at the server, and a reverse proxy with TLS. [`deploy/nginx.conf.example`](../deploy/nginx.conf.example)
  is a tested Nginx config; Caddy or Traefik work too.
- An API key for an OpenAI-compatible model endpoint.
- A sign-in provider: a Google OAuth client, or your organisation's OIDC provider. The redirect URI is
  `<NLAB_PUBLIC_URL>/api/auth/google/callback`, or `/api/auth/<NLAB_OIDC_NAME>/callback` for OIDC.

All commands run from the repository root, for example `/opt/kross`.

## 1. Configure

Two files, split so the app container never sees the database owner password:

```sh
cp .env.example .env           # Compose only: database owner and runtime passwords
cp .env.app.example .env.app   # the app's runtime settings
chmod 600 .env .env.app
openssl rand -hex 32           # run three times: POSTGRES_PASSWORD, POSTGRES_APP_PASSWORD (must differ), NLAB_SECRET_KEY
```

In `.env.app`, set at least `NLAB_PUBLIC_URL`, one sign-in provider and the model settings. While
`NLAB_DAILY_SPEND_CEILING_USD` is above 0, `NLAB_MODEL_PRICES` must price **every** model you configure. With
`NLAB_PRODUCTION=true` (forced by `compose.yml`) the app refuses to start with placeholder secrets, an `http://` URL,
insecure cookies or an unpriced model, and says which setting is wrong.

## 2. Start, migrate, seed

```sh
docker compose build
docker compose up -d --wait db
docker compose run --rm migrate                            # database migrations, owner login, one-shot
docker compose run --rm migrate python -m nlab.api.seed    # the curated scenarios; safe to repeat
deploy/db/provision-roles.sh                               # lock down the runtime login
docker compose up -d --wait app
curl -fsS http://127.0.0.1:8000/api/health
```

The app connects as `nlab_app`, a login that can read and write rows but cannot create or change tables, cannot write
the migration version and has no superuser rights. On a fresh volume `deploy/db/init/01-roles.sh` creates it;
`provision-roles.sh` refreshes it and must run **after every migration**. Migrations never run on their own.

**Make yourself superadmin:** sign in once, then list identities and copy your stable subject into `.env.app`:

```sh
docker compose run --rm app python -m nlab.api.auth_admin identities
# NLAB_SUPERADMIN_IDENTITIES={"google": ["<your subject>"]}
docker compose up -d app
```

## 3. Reverse proxy and TLS

The app is published on host loopback only (`127.0.0.1:${NLAB_HTTP_PORT:-8000}`). With the Nginx example (needs
Nginx 1.25.1 or newer for `http2 on`; Debian 12 and Ubuntu 24.04 ship older versions, so use the nginx.org packages):

```sh
certbot certonly --nginx -d <your.domain>          # get the certificate first: the config below needs it
sed 's/negotiation.example.org/<your.domain>/g' deploy/nginx.conf.example > /etc/nginx/conf.d/kross.conf
nginx -t && systemctl reload nginx
printf '#!/bin/sh\nnginx -t && systemctl reload nginx\n' > /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
chmod 755 /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
```

Remove the distribution's default site if it also claims `default_server`. Raise the HSTS `max-age` in the config only
after `certbot renew --dry-run` passes.

It serves one hostname and rejects others, redirects HTTP to HTTPS, replaces forwarded headers, rate-limits sign-in,
guest and paid model routes (including the streamed replies), sends security headers and logs without query strings
or cookies. If you use another proxy, keep server-sent event responses unbuffered and do not log query strings (OAuth
callbacks carry codes in them).

**Trusted proxy address.** Set `NLAB_FORWARDED_ALLOW_IPS` in `.env.app` to the one address the app container sees your
proxy connect from, usually the Compose network's gateway:

```sh
docker network inspect "$(basename "$PWD")_default" --format '{{(index .IPAM.Config 0).Gateway}}'
```

Never use `*` or a whole private range: anything that can reach the app port could then forge client IP addresses,
which per-IP limits rely on. Sub-path hosting is not supported; keep `NLAB_ROOT_PATH` empty.

## 4. Daily purge

The purge deletes play sessions older than `NLAB_SESSION_RETENTION_DAYS` (production requires a positive value; the
privacy notice template promises about 12 months, so 365), old guest accounts and expired sign-ins. Run it daily,
for example from cron:

```cron
15 3 * * *  cd /opt/kross && docker compose run --rm app python -m nlab.api.purge
```

## 5. Backups

Dump the database daily, encrypt the dump and keep it off the server:

```sh
docker compose exec -T db pg_dump -U nlab -Fc nlab > kross-$(date +%F).dump
```

Rehearse a restore into a new, throwaway database before you rely on it (`createdb` + `pg_restore`), and never restore
over the live `nlab` database by accident.

## Before going public

1. **Privacy notice.** `frontend/src/pages/privacy.md` is a template: replace every `[BRACKETED]` value and make it match
   your deployment (operator, model provider, hosting, retention). It is built into the frontend, so rebuild afterwards.
2. **Branding.** The social preview tags (`og:*`, `twitter:*`) in `frontend/index.html` point at the reference
   instance; change them to your domain.
3. **Checks.** `https://<domain>/api/health` returns 200; `http://` redirects; a wrong `Host` gets no answer; API
   responses carry `Cache-Control: no-store`, CSP with `frame-ancestors 'none'` and `X-Frame-Options`; and
   `docker compose exec -T db psql -U nlab_app -d nlab -c 'CREATE TABLE x(a int)'` fails with a permission error.
4. **Monitoring.** Alert on database disk use (the write and storage limits are allowances, not measured disk),
   container memory, error rates and model spend (`/api/admin/usage` as a superadmin).
5. **Your model provider.** Transcripts go to the provider you configure: check its data-handling terms against your
   privacy notice.

## Upgrades

```sh
git pull
docker compose build --pull
# take a backup first
docker compose run --rm migrate
deploy/db/provision-roles.sh
docker compose up -d --wait
```

The `db` volume survives upgrades. The database image is `postgres:16-alpine` with its `gosu` binary replaced by
Alpine's `su-exec` (see [`deploy/db/Dockerfile`](../deploy/db/Dockerfile)). Never change the Postgres major version in
place: that needs a dump and restore.

## Operations notes

- **Guest play** is off by default (`NLAB_GUEST_PLAY`). Set the trusted proxy address first, so per-IP signup limits
  see real visitor addresses.
- **Connection bounds:** Uvicorn runs with `--limit-concurrency 32 --timeout-keep-alive 5`, plus the proxy's per-IP
  limits. Lower them only after measuring real training traffic.
- **Preparation controls** (Naivasha Grid) are hidden unless the frontend is built with `VITE_HIDE_PREP=0`; the
  Docker build passes no `VITE_*` arguments.
- **Ask the Coach** refuses off-topic questions before they reach the coach model; `NLAB_COACH_QUESTIONS_PER_SESSION`
  caps questions per session.
