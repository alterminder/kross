# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Report them privately through GitHub:
[Report a vulnerability](https://github.com/alterminder/kross/security/advisories/new) (Security → Advisories).

Include what you found, how to reproduce it and what an attacker could do with it. We aim to answer within a
week. Please give us a reasonable time to fix the problem before you disclose it.

## Supported versions

Only the latest commit on `main` receives security fixes.

## Scope

In scope: this repository's code, the Docker image it builds, `compose.yml` and `deploy/`.
Out of scope: your own deployment's configuration, the model providers you connect, and social engineering.

## How KROSS is built to be safe

- **Sign-in:** OIDC only, server-side sessions with hashed tokens, `SameSite=Lax` cookies plus a required custom
  header on every state-changing request, authorisation checked on every request.
- **Tenancy:** every org-owned query is filtered through one data layer; tests try cross-org reads and must fail.
- **Model calls:** every billed call is admitted against user, org, guest and deployment limits before it reaches the
  provider; transcripts are sent to the model provider you configure, never elsewhere.
- **Production gates:** with `NLAB_PRODUCTION=true` the app refuses to start with weak secrets, plain-HTTP URLs,
  insecure cookies or an unpriced spend ceiling ([configuration](docs/configuration.md#production-hardening-nlab_productiontrue)).
- **Deployment:** non-root container, read-only filesystems, dropped capabilities, a runtime database login that
  cannot change tables, and an Nginx example with rate limits and security headers ([self-hosting](docs/deployment.md)).

Operators: keep real sensitive information out of sessions (the privacy notice template says so to users), and read
your model provider's data-handling terms.
