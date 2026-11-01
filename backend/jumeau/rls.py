"""RLS Postgres opt-in pour la frontière tenant.

Le code applicatif filtre déjà par tenant ; cette couche ajoute une défense en profondeur au niveau
de la base. Elle reste **opt-in** (`JUMEAU_RLS=1` et activation explicite) pour ne pas casser les
connexions de migration ou de tests qui n'ont pas encore posé `meridian.tenant_id`.

Chaque transaction doit appeler :func:`contexte_tenant` ; sans setting, la policy refuse les lignes.
L'activation est une opération de déploiement, jamais une écriture automatique du serveur.
"""
from __future__ import annotations

from contextlib import contextmanager
import os

from jumeau.tenant import normaliser_slug

__all__ = [
    "TABLES",
    "activer",
    "contexte_tenant",
    "desactiver",
    "est_actif",
    "sql_activation",
    "sql_desactivation",
]

TABLES = (
    "jumeau",
    "source",
    "preuve",
    "claim",
    "objet_entreprise",
    "identity_decision",
    "discovery_run",
    "interface_contract",
    "interface_operation",
    "interface_binding",
    "interface_assertion",
    "outil_audit",
    "revue",
    "ancre",
    "consigne",
    "contradiction",
    "memoire_durable",
    "execution_run",
    "execution_evenement",
    "execution_outbox",
    "execution_timer",
    "execution_effet",
    "execution_approbation",
    "execution_etape",
)
POLITIQUE = "tenant_isolation"


def est_actif(env=None) -> bool:
    env = os.environ if env is None else env
    return str(env.get("JUMEAU_RLS") or "").strip().lower() in {"1", "true", "oui", "yes"}


def _policy(table: str) -> str:
    return (
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;\n"
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;\n"
        f"DROP POLICY IF EXISTS {POLITIQUE} ON {table};\n"
        f"CREATE POLICY {POLITIQUE} ON {table} "
        f"USING (tenant_id = current_setting('meridian.tenant_id', true)) "
        f"WITH CHECK (tenant_id = current_setting('meridian.tenant_id', true));"
    )


def sql_activation() -> str:
    """SQL d'activation des policies ; les noms de tables sont statiques, aucun input utilisateur."""
    return "\n".join(_policy(table) for table in TABLES)


def sql_desactivation() -> str:
    return "\n".join(
        f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;\n"
        f"DROP POLICY IF EXISTS {POLITIQUE} ON {table};"
        for table in TABLES
    )


def activer(conn) -> None:
    """Active les policies ; à exécuter par un rôle de déploiement, idéalement hors du trafic."""
    conn.execute(sql_activation())


def desactiver(conn) -> None:
    conn.execute(sql_desactivation())


@contextmanager
def contexte_tenant(conn, tenant):
    """Pose le tenant pour la transaction courante, puis le retire à la fermeture.

    `set_config(..., true)` est local à la transaction Postgres. Le slug est validé avant l'appel ;
    aucun nom de table ni fragment SQL ne vient de l'appelant.
    """
    identifiant = normaliser_slug(tenant)
    conn.execute("SELECT set_config('meridian.tenant_id', %s, true)", (identifiant,))
    try:
        yield identifiant
    finally:
        conn.execute("SELECT set_config('meridian.tenant_id', '', true)")


def main():
    import argparse

    import psycopg

    parseur = argparse.ArgumentParser(description="Active ou désactive les policies RLS tenant")
    groupe = parseur.add_mutually_exclusive_group(required=True)
    groupe.add_argument("--activer", action="store_true")
    groupe.add_argument("--desactiver", action="store_true")
    arguments = parseur.parse_args()
    with psycopg.connect(os.environ["JUMEAU_PG_DSN"]) as conn:
        if arguments.activer:
            activer(conn)
            conn.commit()
            print(f"RLS activé sur {len(TABLES)} tables")
        else:
            desactiver(conn)
            conn.commit()
            print(f"RLS désactivé sur {len(TABLES)} tables")


if __name__ == "__main__":
    main()
