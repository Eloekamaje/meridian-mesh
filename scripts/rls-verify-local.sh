#!/usr/bin/env bash
# Preuve RLS « production » sur une base jetable.
#
# Crée une base et des rôles uniques (suffixe = PID du script), applique le schéma,
# active les policies avec un rôle de déploiement NOSUPERUSER NOBYPASSRLS, puis
# prouve avec un second rôle applicatif NOSUPERUSER NOBYPASSRLS que le tenant A ne
# voit jamais le tenant B. Base et rôles sont supprimés dans un trap.
#
# La base cible ($JUMEAU_PG_DSN) n'est jamais modifiée : seules les commandes
# d'administration (CREATE/DROP DATABASE, CREATE/DROP ROLE) passent par ce DSN.
# Le DSN doit porter un rôle avec CREATEDB + CREATEROLE (superuser local accepté).
#
# Usage :
#   export JUMEAU_PG_DSN='postgresql://.../meridian'
#   scripts/rls-verify-local.sh
#
# Variables :
#   JUMEAU_PG_DSN     DSN d'administration (obligatoire ; repli backend/.env)
#   PYTHON            interpréteur avec psycopg (défaut backend/.venv/bin/python)
#   KEEP_VERIFY_DB=1  conserve la base et les rôles pour inspection (pas de cleanup)
#
# Sortie : PASS ou FAIL, avec le détail des contrôles. Code retour 0 seulement si
# toutes les preuves passent et que le nettoyage réussit.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
SCHEMA="$BACKEND/meridian/adapters/outbound/postgres/schema.sql"
PYTHON="${PYTHON:-$BACKEND/.venv/bin/python}"

if [[ -z "${JUMEAU_PG_DSN:-}" && -f "$BACKEND/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    . "$BACKEND/.env"
    set +a
fi

if [[ -z "${JUMEAU_PG_DSN:-}" ]]; then
    printf 'ERREUR : JUMEAU_PG_DSN requis (DSN d’administration avec CREATEDB/CREATEROLE).\n' >&2
    exit 2
fi
if [[ ! -x "$PYTHON" ]]; then
    printf 'ERREUR : interpréteur Python introuvable : %s\n' "$PYTHON" >&2
    exit 2
fi
if ! command -v psql >/dev/null 2>&1; then
    printf 'ERREUR : psql introuvable dans le PATH.\n' >&2
    exit 2
fi
if [[ ! -f "$SCHEMA" ]]; then
    printf 'ERREUR : schéma introuvable : %s\n' "$SCHEMA" >&2
    exit 2
fi

export PYTHONPATH="$BACKEND${PYTHONPATH:+:$PYTHONPATH}"

SUFFIX="$$"
DB="meridian_rls_verify_${SUFFIX}"
OWNER="meridian_rls_owner_${SUFFIX}"
APP="meridian_rls_app_${SUFFIX}"

DB_CREATED=0
OWNER_CREATED=0
APP_CREATED=0

# Construit un DSN dérivé du DSN d'administration. $1 = rôle, $2 = base,
# $3 = "1" pour conserver le mot de passe d'origine, "0" pour le retirer
# (le mot de passe est alors fourni par PGPASSWORD, jamais par la ligne de commande).
dsn_variant() {
    "$PYTHON" - "$JUMEAU_PG_DSN" "$1" "$2" "$3" <<'PY'
import sys

from psycopg.conninfo import conninfo_to_dict, make_conninfo

dsn, user, dbname, keep_password = sys.argv[1:5]
params = conninfo_to_dict(dsn)
if user:
    params["user"] = user
if dbname:
    params["dbname"] = dbname
if keep_password != "1":
    params.pop("password", None)
print(make_conninfo(**params))
PY
}

mot_de_passe() {
    "$PYTHON" -c 'import secrets; print(secrets.token_hex(24))'
}

ADMIN_DSN="$(dsn_variant '' postgres 1)"
ADMIN_DB_DSN="$(dsn_variant '' "$DB" 1)"
OWNER_DSN="$(dsn_variant "$OWNER" "$DB" 0)"
APP_DSN="$(dsn_variant "$APP" "$DB" 0)"
OWNER_PASSWORD="$(mot_de_passe)"
APP_PASSWORD="$(mot_de_passe)"

cleanup() {
    local code=$?
    trap - EXIT

    if [[ "${KEEP_VERIFY_DB:-0}" == "1" ]]; then
        printf 'CONSERVÉ : base %s ; rôles %s et %s (KEEP_VERIFY_DB=1).\n' \
            "$DB" "$OWNER" "$APP"
    else
        if [[ $DB_CREATED -eq 1 ]]; then
            # Coupe les connexions résiduelles avant le DROP DATABASE.
            psql "$ADMIN_DSN" -X -q -v ON_ERROR_STOP=0 \
                -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity \
                    WHERE datname = '$DB' AND pid <> pg_backend_pid()" \
                >/dev/null 2>&1 || true
            if psql "$ADMIN_DSN" -X -q -v ON_ERROR_STOP=1 \
                -c "DROP DATABASE IF EXISTS \"$DB\"" >/dev/null 2>&1; then
                printf 'cleanup : base %s supprimée.\n' "$DB"
            else
                printf 'cleanup : ÉCHEC de la suppression de la base %s.\n' "$DB" >&2
                code=1
            fi
        fi
        if [[ $APP_CREATED -eq 1 ]]; then
            if psql "$ADMIN_DSN" -X -q -v ON_ERROR_STOP=1 \
                -c "DROP ROLE IF EXISTS \"$APP\"" >/dev/null 2>&1; then
                printf 'cleanup : rôle %s supprimé.\n' "$APP"
            else
                printf 'cleanup : ÉCHEC de la suppression du rôle %s.\n' "$APP" >&2
                code=1
            fi
        fi
        if [[ $OWNER_CREATED -eq 1 ]]; then
            if psql "$ADMIN_DSN" -X -q -v ON_ERROR_STOP=1 \
                -c "DROP ROLE IF EXISTS \"$OWNER\"" >/dev/null 2>&1; then
                printf 'cleanup : rôle %s supprimé.\n' "$OWNER"
            else
                printf 'cleanup : ÉCHEC de la suppression du rôle %s.\n' "$OWNER" >&2
                code=1
            fi
        fi
    fi

    if [[ $code -eq 0 ]]; then
        printf 'PASS : isolation RLS prouvée avec un rôle applicatif NOSUPERUSER NOBYPASSRLS.\n'
    else
        printf 'FAIL : preuve RLS incomplète (code %s).\n' "$code" >&2
    fi
    exit "$code"
}
trap cleanup EXIT

printf '== RLS local : base jetable %s ==\n' "$DB"
printf '   propriétaire/déploiement : %s\n' "$OWNER"
printf '   applicatif              : %s\n' "$APP"

printf '\n== 1/6 Création des rôles et de la base ==\n'
psql "$ADMIN_DSN" -X -q -v ON_ERROR_STOP=1 \
    -c "CREATE ROLE \"$OWNER\" LOGIN PASSWORD '$OWNER_PASSWORD' \
        NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE"
OWNER_CREATED=1
psql "$ADMIN_DSN" -X -q -v ON_ERROR_STOP=1 \
    -c "CREATE ROLE \"$APP\" LOGIN PASSWORD '$APP_PASSWORD' \
        NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE"
APP_CREATED=1
psql "$ADMIN_DSN" -X -q -v ON_ERROR_STOP=1 \
    -c "CREATE DATABASE \"$DB\" OWNER \"$OWNER\""
DB_CREATED=1
psql "$ADMIN_DB_DSN" -X -q -v ON_ERROR_STOP=1 \
    -c "GRANT USAGE, CREATE ON SCHEMA public TO \"$OWNER\""
printf '   rôles créés (LOGIN NOSUPERUSER NOBYPASSRLS) et base créée.\n'

printf '\n== 2/6 Application du schéma comme rôle propriétaire ==\n'
PGPASSWORD="$OWNER_PASSWORD" \
PGOPTIONS="${PGOPTIONS:+$PGOPTIONS }-c client_min_messages=warning" \
    psql "$OWNER_DSN" -X -q -v ON_ERROR_STOP=1 -f "$SCHEMA"
printf '   schéma appliqué : %s\n' "${SCHEMA#"$ROOT"/}"

printf '\n== 3/6 Droits DML du rôle applicatif ==\n'
PGPASSWORD="$OWNER_PASSWORD" psql "$OWNER_DSN" -X -q -v ON_ERROR_STOP=1 <<SQL
GRANT USAGE ON SCHEMA public TO "$APP";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "$APP";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "$APP";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "$APP";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO "$APP";
SQL
printf '   SELECT/INSERT/UPDATE/DELETE et séquences accordés à %s.\n' "$APP"

printf '\n== 4/6 Activation RLS (rôle propriétaire non-superuser) ==\n'
if ! PGPASSWORD="$OWNER_PASSWORD" "$PYTHON" -m meridian.adapters.outbound.postgres.rls \
    --activer --dsn "$OWNER_DSN"; then
    printf 'ERREUR : activation RLS refusée ou incomplète.\n' >&2
    exit 1
fi

printf '\n== 5/6 Vérification avec le rôle applicatif ==\n'
if ! PGPASSWORD="$APP_PASSWORD" "$PYTHON" -m meridian.adapters.outbound.postgres.rls \
    --verifier --dsn "$APP_DSN"; then
    printf 'ERREUR : le rapport --verifier échoue pour le rôle applicatif.\n' >&2
    exit 1
fi

printf '\n== 6/6 Preuve d’isolation tenant avec le rôle applicatif ==\n'
PGPASSWORD="$APP_PASSWORD" "$PYTHON" - "$APP_DSN" "$APP" <<'PY'
import sys

import psycopg

from meridian.adapters.outbound.postgres import rls

dsn, role_attendu = sys.argv[1:3]
TENANTS = {
    "tenant-a": ("rls-proof-a", "rls-proof-objet-a"),
    "tenant-b": ("rls-proof-b", "rls-proof-objet-b"),
}


def ids(conn):
    return [ligne[0] for ligne in conn.execute("SELECT id FROM jumeau ORDER BY id").fetchall()]


with psycopg.connect(dsn, autocommit=True) as conn:
    role = rls.role_courant(conn)
    assert role["nom"] == role_attendu, role
    assert not role["contourne_rls"], f"rôle {role_attendu} contourne RLS : {role}"

    # Sans contexte tenant, aucune ligne n'est visible.
    assert conn.execute("SELECT count(*) FROM jumeau").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM objet_entreprise").fetchone()[0] == 0

    # Chaque tenant écrit et relit ses propres lignes via le helper applicatif.
    for tenant, (jumeau_id, objet_id) in TENANTS.items():
        with rls.contexte_tenant(conn, tenant):
            conn.execute(
                "INSERT INTO jumeau (id, tenant_id, nom, equipe) VALUES (%s, %s, %s, %s)",
                (jumeau_id, tenant, tenant.upper(), "rls-verify"),
            )
            conn.execute(
                "INSERT INTO objet_entreprise (id, tenant_id, famille, type, mode) "
                "VALUES (%s, %s, 'connaissance', 'RLS_PROOF', 'DECLARED')",
                (objet_id, tenant),
            )
            assert ids(conn) == [jumeau_id]
            assert conn.execute(
                "SELECT id FROM objet_entreprise ORDER BY id").fetchall() == [(objet_id,)]

    # Tenant A ne voit ni les lignes ni l'identifiant de B, et inversement.
    with rls.contexte_tenant(conn, "tenant-a"):
        assert ids(conn) == ["rls-proof-a"]
        assert conn.execute(
            "SELECT count(*) FROM objet_entreprise WHERE tenant_id = 'tenant-b'"
        ).fetchone()[0] == 0
    with rls.contexte_tenant(conn, "tenant-b"):
        assert ids(conn) == ["rls-proof-b"]
        assert conn.execute(
            "SELECT count(*) FROM objet_entreprise WHERE tenant_id = 'tenant-a'"
        ).fetchone()[0] == 0

    # Le WITH CHECK refuse une écriture croisée : contexte A, ligne tenant B.
    try:
        with rls.contexte_tenant(conn, "tenant-a"):
            conn.execute(
                "INSERT INTO jumeau (id, tenant_id, nom, equipe) "
                "VALUES ('rls-proof-cross', 'tenant-b', 'B', 'rls-verify')"
            )
    except psycopg.Error as exc:
        if exc.sqlstate != "42501":
            raise
        print(f"   INSERT croisé refusé par WITH CHECK (SQLSTATE {exc.sqlstate}).")
    else:
        raise AssertionError("WITH CHECK n'a pas refusé une écriture vers tenant-b")

    # Après sortie du contexte, le setting est retiré : plus aucune ligne.
    assert conn.execute("SELECT count(*) FROM jumeau").fetchone()[0] == 0
    assert conn.execute(
        "SELECT count(*) FROM jumeau WHERE id = 'rls-proof-cross'").fetchone()[0] == 0

    print(f"   rôle applicatif : {role['nom']} (superuser={role['superuser']}, "
          f"bypassrls={role['bypassrls']})")
    print("   tenant-a : 1 jumeau + 1 objet ; tenant-b : 1 jumeau + 1 objet.")
    print("   hors contexte : 0 ligne ; accès croisé : 0 ligne.")
PY
