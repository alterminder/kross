-- Role setup for the KROSS database. Idempotent: safe to run again.
--
-- Run through the wrapper scripts only:
--   deploy/db/provision-roles.sh  (existing volume, run on the host)
--   deploy/db/init/01-roles.sh    (fresh volume, runs inside the db container)
-- They validate identifiers against ^[a-z_][a-z0-9_]*$ and deliver the password
-- through the NLAB_APP_PASSWORD environment variable or stdin, never argv.
--
-- psql variables (identifiers, validated by the wrappers):
--   db_name    : application database (prod: nlab)
--   app_role   : runtime login the web app uses (prod: nlab_app)
--   owner_role : schema owner / migration login (prod: nlab)
-- Password: environment variable NLAB_APP_PASSWORD, quoted via %L.

\set ON_ERROR_STOP on

\if :{?app_role}
\else
DO $$ BEGIN RAISE EXCEPTION 'roles.sql: --set=app_role is required'; END $$;
\endif
\if :{?db_name}
\else
DO $$ BEGIN RAISE EXCEPTION 'roles.sql: --set=db_name is required'; END $$;
\endif
\if :{?owner_role}
\else
DO $$ BEGIN RAISE EXCEPTION 'roles.sql: --set=owner_role is required'; END $$;
\endif

\getenv app_password NLAB_APP_PASSWORD
SELECT :'app_password' = '' AS no_password \gset
\if :no_password
DO $$ BEGIN RAISE EXCEPTION 'roles.sql: NLAB_APP_PASSWORD is not set in the environment'; END $$;
\endif

-- Runtime login: no superuser, no role/database creation, no replication, no RLS bypass.
SELECT format(
    'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L',
    :'app_role', :'app_password'
) WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_role') \gexec

-- Re-running refreshes the password and drops any capability drift.
SELECT format(
    'ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L',
    :'app_role', :'app_password'
) \gexec

-- Strip EVERY inherited role membership: NOSUPERUSER does not remove grants
-- like pg_execute_server_program or the owner role itself. No membership of
-- the runtime login is intended, so all of them are revoked.
SELECT format('REVOKE %I FROM %I', r.rolname, :'app_role')
FROM pg_auth_members AS m
JOIN pg_roles AS r ON r.oid = m.roleid
WHERE m.member = (SELECT oid FROM pg_roles WHERE rolname = :'app_role')
\gexec

\connect :db_name

-- No DDL for anyone but the owner: the runtime login must not create objects.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE TEMPORARY ON DATABASE :db_name FROM PUBLIC;

GRANT CONNECT ON DATABASE :db_name TO :app_role;
GRANT USAGE ON SCHEMA public TO :app_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO :app_role;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO :app_role;

-- Future objects: migrations create tables as owner_role, so default
-- privileges on that role cover every later migration too.
ALTER DEFAULT PRIVILEGES FOR ROLE :owner_role IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :app_role;
ALTER DEFAULT PRIVILEGES FOR ROLE :owner_role IN SCHEMA public
    GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO :app_role;

-- Schema bookkeeping is owner-only work: the runtime login keeps SELECT (some
-- tooling checks the installed revision) but must never write alembic_version.
-- Run provision-roles.sh again after each migration so a recreated table is
-- re-restricted (default privileges cannot exclude a single table).
SELECT format('REVOKE INSERT, UPDATE, DELETE ON TABLE %I.%I FROM %I', 'public', 'alembic_version', :'app_role')
WHERE to_regclass('public.alembic_version') IS NOT NULL
\gexec
