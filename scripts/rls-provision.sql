-- Provisionnement idempotent des rôles RLS Méridian.
--
-- À exécuter avec un rôle qui a CREATEROLE (et SUPERUSER pour créer le rôle
-- BYPASSRLS ci-dessous), typiquement l'administrateur de la base, puis à
-- rejouer sans risque. Les GRANT supposent que :owner_role possède les tables
-- (ou que l'exécution se fait avec un rôle suffisant pour accorder ces droits).
--
-- Usage :
--   psql "$JUMEAU_PG_DSN" \
--     -v app_password='...' \
--     -v worker_password='...' \
--     -v owner_role=meridian \
--     -f scripts/rls-provision.sql
--
-- -v owner_role est le rôle de déploiement/propriétaire des tables
--   (défaut : meridian). Il sert à poser les ALTER DEFAULT PRIVILEGES sur les
--   futurs objets, pas seulement sur ceux déjà créés.
-- - Les rôles existants ne voient PAS leur mot de passe réécrit : faire une
--   rotation explicite avec ALTER ROLE ... PASSWORD si nécessaire.
-- - Les attributs NOSUPERUSER/NOBYPASSRLS sont réaffirmés à chaque exécution.

\set ON_ERROR_STOP on

\if :{?app_password}
\else
    \echo 'ERREUR : fournir -v app_password=...'
    DO $$ BEGIN RAISE EXCEPTION 'app_password manquant'; END $$;
\endif

\if :{?worker_password}
\else
    \echo 'ERREUR : fournir -v worker_password=...'
    DO $$ BEGIN RAISE EXCEPTION 'worker_password manquant'; END $$;
\endif

\if :{?owner_role}
\else
    \set owner_role meridian
\endif

-- meridian_app : API et workers « une passe par tenant ».
-- Policies RLS appliquées : chaque transaction doit poser meridian.tenant_id.
SELECT format(
    'CREATE ROLE meridian_app LOGIN PASSWORD %L '
    'NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE',
    :'app_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'meridian_app');
\gexec

-- meridian_worker : workers qui balaient TOUS les tenants (source, outbox,
-- exécution). BYPASSRLS est volontaire : sans contexte tenant, un rôle
-- NOBYPASSRLS ne verrait aucune ligne et ne pourrait pas réclamer les runs des
-- autres tenants. Ce rôle annule donc la défense en profondeur pour ce
-- processus : jamais pour l'API, secret distinct, accès réseau restreint,
-- audits dédiés. Alternative sans BYPASSRLS : utiliser meridian_app avec
-- JUMEAU_WORKER_TENANTS (une passe par tenant, un processus par tenant pour
-- outbox/execution).
SELECT format(
    'CREATE ROLE meridian_worker LOGIN PASSWORD %L '
    'NOSUPERUSER BYPASSRLS NOCREATEDB NOCREATEROLE',
    :'worker_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'meridian_worker');
\gexec

-- Réaffirme les attributs même si le rôle préexistait (ne touche pas au mot de passe).
ALTER ROLE meridian_app
    LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
ALTER ROLE meridian_worker
    LOGIN NOSUPERUSER BYPASSRLS NOCREATEDB NOCREATEROLE;

-- Droits DML. Les policies restent seules juges des lignes pour meridian_app ;
-- meridian_worker les contourne par choix (voir ci-dessus).
GRANT USAGE ON SCHEMA public TO meridian_app, meridian_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public
    TO meridian_app, meridian_worker;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public
    TO meridian_app, meridian_worker;

-- Futurs objets créés par le rôle de déploiement : mêmes droits sans rejouer
-- les GRANT à chaque migration.
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner_role" IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO meridian_app, meridian_worker;
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner_role" IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO meridian_app, meridian_worker;

-- Contrôle attendu : app = false/false ; worker = false/true ; jamais superuser.
SELECT rolname, rolsuper, rolbypassrls
FROM pg_roles
WHERE rolname IN ('meridian_app', 'meridian_worker')
ORDER BY rolname;
