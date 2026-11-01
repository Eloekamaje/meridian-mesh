"""RLS Postgres opt-in pour la frontière tenant.

Le code applicatif filtre déjà par tenant ; cette couche ajoute une défense en profondeur au niveau
de la base. Elle reste **opt-in** (`JUMEAU_RLS=1` et activation explicite) pour ne pas casser les
connexions de migration ou de tests qui n'ont pas encore posé `meridian.tenant_id`.

Chaque transaction applicative doit appeler :func:`contexte_tenant` ; sans setting, la policy refuse
les lignes. Les workers qui traitent un tenant à la fois peuvent utiliser
:func:`contexte_tenant_session` pour que le réglage survive à plusieurs transactions courtes (jamais
sur une connexion d'API). L'activation est une opération de déploiement, jamais une écriture
automatique du serveur :

    python -m jumeau.rls --verifier
    python -m jumeau.rls --activer

Le CLI refuse un rôle `SUPERUSER` ou `BYPASSRLS` pour l'activation : les policies ne s'appliquent
pas à un tel rôle. Les workers multi-tenant peuvent, eux, utiliser un rôle dédié `BYPASSRLS` ; voir
``docs/architecture/rls.md`` pour l'ordre d'activation, les rôles et le mode des workers.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
import sys

from jumeau.tenant import normaliser_slug

__all__ = [
    "MODE_WORKER_BYPASS",
    "MODE_WORKER_CONTEXTE",
    "POLITIQUE",
    "TABLES",
    "TABLES_DERIVEES",
    "TENANT_SETTING",
    "TOUTES_LES_TABLES",
    "ConfigurationWorker",
    "activer",
    "configurer_worker",
    "contexte_tenant",
    "contexte_tenant_session",
    "desactiver",
    "est_actif",
    "mode_worker",
    "policies_actives",
    "role_courant",
    "sql_activation",
    "sql_desactivation",
    "verifier",
]

TENANT_SETTING = "meridian.tenant_id"
POLITIQUE = "tenant_isolation"

# Modes de worker : rôle qui contourne RLS, ou rôle soumis aux policies avec un
# contexte de tenant posé par passe.
MODE_WORKER_BYPASS = "bypass"
MODE_WORKER_CONTEXTE = "contexte"


class ConfigurationWorker(RuntimeError):
    """Le worker ne peut pas traiter plusieurs tenants sans contexte sûr."""

# Tables qui portent directement `tenant_id`.
TABLES = (
    "jumeau",
    "source",
    "preuve",
    "claim",
    "revue",
    "contradiction",
    "ancre",
    "consigne",
    "interface_contract",
    "interface_operation",
    "interface_binding",
    "interface_assertion",
    "discovery_run",
    "identity_decision",
    "objet_entreprise",
    "outil_audit",
    "valeur",
    "memoire_durable",
    "prediction_calibration",
    "execution_run",
    "execution_evenement",
    "execution_outbox",
    "execution_timer",
    "execution_effet",
    "execution_approbation",
    "execution_etape",
    "source_schedule",
    "ingestion_run",
)

# Tables filles sans `tenant_id` : la policy vérifie l'appartenance du parent.
# Valeur = (table parente, colonne de jointure dans la table fille).
TABLES_DERIVEES = {
    "claim_preuve": ("claim", "claim_id"),
    "claim_source": ("claim", "claim_id"),
    "verification": ("claim", "claim_id"),
    "fiche_vivante": ("jumeau", "jumeau_id"),
    "evaluation": ("jumeau", "jumeau_id"),
}

TOUTES_LES_TABLES = TABLES + tuple(TABLES_DERIVEES)


def est_actif(env=None) -> bool:
    env = os.environ if env is None else env
    return str(env.get("JUMEAU_RLS") or "").strip().lower() in {"1", "true", "oui", "yes"}


def _selection(tables=None) -> tuple[str, ...]:
    """Valide une sélection de tables et la rend dans l'ordre canonique.

    Les noms de tables sont statiques : aucun fragment SQL ne vient de l'appelant.
    """
    if tables is None:
        return TOUTES_LES_TABLES
    if isinstance(tables, str):
        demandees = {nom.strip() for nom in tables.split(",") if nom.strip()}
    else:
        demandees = {str(nom).strip() for nom in tables}
    inconnues = sorted(demandees - set(TOUTES_LES_TABLES))
    if inconnues:
        raise ValueError(f"tables RLS inconnues : {', '.join(inconnues)}")
    return tuple(nom for nom in TOUTES_LES_TABLES if nom in demandees)


def policies_actives(conn, tables=None, *, completes: bool = False) -> bool:
    """État RLS des tables sélectionnées dans le schéma courant.

    Sans ``completes``, vrai dès qu'au moins une table a RLS activé : les workers s'en
    servent pour détecter une base protégée même si ``JUMEAU_RLS`` n'est pas propagé.
    Avec ``completes=True``, vrai seulement si toutes les tables existent, ont RLS activé
    et forcé : une activation partielle ne suffit pas à garantir une passe par tenant.
    """
    selection = _selection(tables)
    if not selection:
        return False
    ligne = conn.execute(
        "SELECT count(*) = %s, "
        "       coalesce(bool_or(c.relrowsecurity), false), "
        "       coalesce(bool_and(c.relrowsecurity AND c.relforcerowsecurity), false) "
        "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = current_schema() AND c.relname = ANY(%s)",
        (len(selection), list(selection)),
    ).fetchone()
    if not ligne:
        return False
    if completes:
        return bool(ligne[0] and ligne[2])
    return bool(ligne[1])


def _expression_tenant(table: str) -> str:
    """Condition de la policy : directe sur `tenant_id`, ou via la table parente."""
    if table in TABLES_DERIVEES:
        parent, colonne = TABLES_DERIVEES[table]
        return (
            f"EXISTS (SELECT 1 FROM {parent} p WHERE p.id = {table}.{colonne} "
            f"AND p.tenant_id = current_setting('{TENANT_SETTING}', true))"
        )
    return f"tenant_id = current_setting('{TENANT_SETTING}', true)"


def _instructions(table: str) -> tuple[str, ...]:
    """Instructions idempotentes : DROP IF EXISTS précède toujours CREATE POLICY."""
    expression = _expression_tenant(table)
    return (
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        f"DROP POLICY IF EXISTS {POLITIQUE} ON {table}",
        f"CREATE POLICY {POLITIQUE} ON {table} USING ({expression}) WITH CHECK ({expression})",
    )


def sql_activation(tables=None) -> str:
    """SQL d'activation des policies ; les noms de tables sont statiques, aucun input utilisateur."""
    return "\n".join(
        f"{instruction};"
        for table in _selection(tables)
        for instruction in _instructions(table)
    )


def sql_desactivation(tables=None) -> str:
    return "\n".join(
        f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;\n"
        f"DROP POLICY IF EXISTS {POLITIQUE} ON {table};"
        for table in _selection(tables)
    )


def activer(conn, tables=None) -> None:
    """Active les policies dans une transaction ; à exécuter par un rôle de déploiement explicite.

    Le CLI vérifie en plus que le rôle ne contourne pas RLS (`SUPERUSER`/`BYPASSRLS`).
    """
    with conn.transaction():
        for table in _selection(tables):
            for instruction in _instructions(table):
                conn.execute(instruction)


def desactiver(conn, tables=None) -> None:
    with conn.transaction():
        for table in _selection(tables):
            conn.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
            conn.execute(f"DROP POLICY IF EXISTS {POLITIQUE} ON {table}")


def role_courant(conn) -> dict:
    """Décrit le rôle connecté et indique s'il contourne RLS."""
    nom = conn.execute("SELECT current_user").fetchone()[0]
    ligne = conn.execute(
        "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = %s", (nom,)
    ).fetchone()
    superuser, bypass = (bool(ligne[0]), bool(ligne[1])) if ligne else (False, False)
    return {
        "nom": nom,
        "superuser": superuser,
        "bypassrls": bypass,
        "contourne_rls": superuser or bypass,
    }


def mode_worker(role: dict) -> str:
    """Mode d'un worker déduit du rôle connecté.

    ``BYPASSRLS`` (ou superuser) balaie tous les tenants sans contexte ; sinon le
    worker doit poser ``meridian.tenant_id`` lui-même, tenant par tenant.
    """
    return MODE_WORKER_BYPASS if role.get("contourne_rls") else MODE_WORKER_CONTEXTE


def configurer_worker(conn, *, tenants=(), env=None, multi: bool = True) -> dict:
    """Valide la stratégie RLS d'un worker avant sa première passe.

    - rôle ``BYPASSRLS`` : balayage global autorisé, policies non appliquées au worker ;
    - rôle soumis aux policies : liste de tenants obligatoire (une passe par tenant),
      et un seul tenant par processus si ``multi=False``.

    ``JUMEAU_RLS=1`` ou des policies déjà actives en base déclenchent la validation :
    un worker ne doit jamais scanner tous les tenants en croyant poser un contexte unique.
    """
    role = role_courant(conn)
    mode = mode_worker(role)
    politiques = policies_actives(conn)
    completes = politiques and policies_actives(conn, completes=True)
    actif = est_actif(env) or politiques
    selection = tuple(dict.fromkeys(
        normaliser_slug(str(tenant).strip())
        for tenant in (tenants or ())
        if str(tenant or "").strip()
    ))
    if selection and not politiques:
        raise ConfigurationWorker(
            "JUMEAU_WORKER_TENANTS exige des policies RLS actives : sans policy, "
            "le contexte de tenant ne filtre aucune requête. Activer RLS ou retirer "
            "la liste de tenants (voir docs/architecture/rls.md)."
        )
    if selection and not completes:
        raise ConfigurationWorker(
            "JUMEAU_WORKER_TENANTS exige l'activation RLS complète : une activation "
            "partielle laisserait des tables visibles pour tous les tenants. "
            "Relancer `python -m jumeau.rls --activer` sans --tables, ou retirer la "
            "liste de tenants (voir docs/architecture/rls.md)."
        )
    if selection and mode == MODE_WORKER_BYPASS:
        raise ConfigurationWorker(
            "JUMEAU_WORKER_TENANTS est incompatible avec un rôle BYPASSRLS : "
            "le rôle ignore les policies, donc le contexte ne limite pas les lignes. "
            "Utiliser un rôle NOBYPASSRLS ou retirer la liste de tenants."
        )
    if actif and mode != MODE_WORKER_BYPASS:
        if not selection:
            raise ConfigurationWorker(
                "RLS actif : worker multi-tenant sans stratégie de tenant. "
                "Déclarer JUMEAU_WORKER_TENANTS (passe par tenant) ou utiliser "
                "JUMEAU_WORKER_PG_DSN avec un rôle dédié BYPASSRLS "
                "(voir docs/architecture/rls.md)."
            )
        if not multi and len(selection) != 1:
            raise ConfigurationWorker(
                "RLS actif : ce worker ne traite qu'un tenant par processus. "
                "Déclarer exactement un tenant dans JUMEAU_WORKER_TENANTS, ou "
                "utiliser un rôle dédié BYPASSRLS."
            )
    return {"role": role, "mode": mode, "rls": actif, "policies": politiques,
            "policies_completes": completes, "tenants": selection}


def _expression_attendue(table: str, expression: str) -> bool:
    texte = " ".join(str(expression or "").lower().split())
    if TENANT_SETTING not in texte or "current_setting" not in texte:
        return False
    if table in TABLES_DERIVEES:
        return "exists" in texte and table in texte
    return "tenant_id" in texte


def verifier(conn, tables=None) -> dict:
    """Vérifie l'existence des tables, RLS activé/forcé et la policy attendue.

    Le rapport est volontairement sérialisable (dict) pour être testé et affiché par le CLI.
    """
    selection = _selection(tables)
    schema = conn.execute("SELECT current_schema()").fetchone()[0]
    role = role_courant(conn)
    resultats = []
    for table in selection:
        ligne = conn.execute(
            "SELECT c.relrowsecurity, c.relforcerowsecurity "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = current_schema() AND c.relname = %s",
            (table,),
        ).fetchone()
        if ligne is None:
            resultats.append({
                "table": table, "existe": False, "rls": False, "forcee": False,
                "politique": False, "using_ok": False, "with_check_ok": False,
                "autres_politiques": (), "ok": False,
            })
            continue
        politiques = conn.execute(
            "SELECT policyname, coalesce(qual, ''), coalesce(with_check, '') "
            "FROM pg_policies WHERE schemaname = current_schema() AND tablename = %s "
            "ORDER BY policyname",
            (table,),
        ).fetchall()
        notre = next((p for p in politiques if p[0] == POLITIQUE), None)
        autres = tuple(p[0] for p in politiques if p[0] != POLITIQUE)
        using_ok = bool(notre and _expression_attendue(table, notre[1]))
        with_check_ok = bool(notre and _expression_attendue(table, notre[2]))
        resultat = {
            "table": table,
            "existe": True,
            "rls": bool(ligne[0]),
            "forcee": bool(ligne[1]),
            "politique": notre is not None,
            "using_ok": using_ok,
            "with_check_ok": with_check_ok,
            "autres_politiques": autres,
            "ok": bool(ligne[0] and ligne[1] and notre and using_ok and with_check_ok and not autres),
        }
        resultats.append(resultat)
    tables_ok = all(resultat["ok"] for resultat in resultats)
    role_protege = not role["contourne_rls"]
    return {
        "schema": schema,
        "role": role,
        "tables": resultats,
        "tables_ok": tables_ok,
        "role_protege": role_protege,
        "ok": tables_ok and role_protege,
    }


@contextmanager
def contexte_tenant(conn, tenant):
    """Pose le tenant pour la transaction courante, puis le retire à la fermeture.

    `set_config(..., true)` est local à la transaction Postgres. Le helper ouvre lui-même une
    transaction (ou un savepoint si l'appelant en a déjà une) : il fonctionne donc aussi sur une
    connexion `autocommit=True`. Le slug est validé avant l'appel ; aucun nom de table ni fragment
    SQL ne vient de l'appelant.
    """
    identifiant = normaliser_slug(tenant)
    with conn.transaction():
        conn.execute("SELECT set_config('meridian.tenant_id', %s, true)", (identifiant,))
        try:
            yield identifiant
        finally:
            try:
                conn.execute("SELECT set_config('meridian.tenant_id', '', true)")
            except Exception:
                # Transaction déjà avortée par le corps : le reset est impossible, mais le
                # rollback du bloc transactionnel annulera de toute façon le SET LOCAL.
                # Toute autre erreur de reset reste visible.
                statut = getattr(getattr(conn, "info", None), "transaction_status", None)
                if str(getattr(statut, "name", statut)) != "INERROR":
                    raise


@contextmanager
def contexte_tenant_session(conn, tenant):
    """Pose le tenant pour la **session**, puis le retire à la fermeture.

    Réservé aux connexions worker dédiées qui traitent un tenant à la fois : contrairement à
    :func:`contexte_tenant`, ce réglage survit aux transactions, donc le worker peut enchaîner
    plusieurs transactions courtes (planification, claim, ingestion) sans garder une transaction
    ouverte pendant un appel réseau. La connexion ne doit jamais servir un autre tenant entre-temps ;
    le ``finally`` remet le setting à vide.

    Ne jamais utiliser ce helper pour l'API : une connexion mutualisée garderait le tenant.
    """
    identifiant = normaliser_slug(tenant)
    conn.execute("SELECT set_config(%s, %s, false)", (TENANT_SETTING, identifiant))
    try:
        yield identifiant
    finally:
        try:
            conn.execute("SELECT set_config(%s, '', false)", (TENANT_SETTING,))
        except Exception:
            statut = getattr(getattr(conn, "info", None), "transaction_status", None)
            if str(getattr(statut, "name", statut)) != "INERROR":
                raise


def _rapport_texte(rapport: dict) -> str:
    role = rapport["role"]
    lignes = [
        f"schéma : {rapport['schema']}",
        f"rôle   : {role['nom']}"
        + (" (SUPERUSER/BYPASSRLS : les policies ne s'appliquent pas)" if role["contourne_rls"] else ""),
    ]
    for resultat in rapport["tables"]:
        manques = []
        if not resultat["existe"]:
            manques.append("table absente")
        if resultat["existe"]:
            if not resultat["rls"]:
                manques.append("RLS non activé")
            if not resultat["forcee"]:
                manques.append("RLS non forcé")
            if not resultat["politique"]:
                manques.append("policy absente")
            if resultat["politique"] and not (resultat["using_ok"] and resultat["with_check_ok"]):
                manques.append("policy inattendue")
            if resultat["autres_politiques"]:
                manques.append("policies supplémentaires : " + ", ".join(resultat["autres_politiques"]))
        etat = "ok" if resultat["ok"] else "KO"
        lignes.append(f"  {etat:2} {resultat['table']}" + (f" — {' ; '.join(manques)}" if manques else ""))
    lignes.append(
        f"résultat : {'OK' if rapport['ok'] else 'KO'}"
        + ("" if rapport["role_protege"] else " (rôle contournant RLS)")
    )
    return "\n".join(lignes)


def main(argv=None) -> int:
    import argparse

    import psycopg

    parseur = argparse.ArgumentParser(
        description="Active, désactive ou vérifie les policies RLS tenant (opération explicite).",
        epilog="Voir docs/architecture/rls.md pour l'ordre d'activation et le rôle applicatif requis.",
    )
    groupe = parseur.add_mutually_exclusive_group(required=True)
    groupe.add_argument("--activer", action="store_true", help="créer/remplacer les policies (idempotent)")
    groupe.add_argument("--desactiver", action="store_true", help="retirer les policies et désactiver RLS")
    groupe.add_argument("--verifier", action="store_true", help="vérifier l'état sans modifier la base")
    parseur.add_argument("--dsn", default=None, help="DSN Postgres (défaut : JUMEAU_PG_DSN)")
    parseur.add_argument(
        "--tables", default=None,
        help="sous-ensemble de tables séparé par des virgules (défaut : toutes les tables couvertes)",
    )
    arguments = parseur.parse_args(argv)

    dsn = arguments.dsn or os.environ.get("JUMEAU_PG_DSN")
    if not dsn:
        print("JUMEAU_PG_DSN (ou --dsn) requis", file=sys.stderr)
        return 2
    try:
        selection = _selection(arguments.tables)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if not selection:
        print("aucune table sélectionnée", file=sys.stderr)
        return 2

    with psycopg.connect(dsn, autocommit=True) as conn:
        role = role_courant(conn)
        if arguments.desactiver:
            desactiver(conn, selection)
            print(f"RLS désactivé sur {len(selection)} tables (rôle {role['nom']})")
            return 0
        if role["contourne_rls"]:
            if arguments.activer:
                print(
                    f"REFUS : le rôle « {role['nom']} » est SUPERUSER ou BYPASSRLS ; "
                    "les policies RLS ne s'appliqueraient pas à ce rôle. "
                    "Utilisez le DSN d'un rôle applicatif NOSUPERUSER NOBYPASSRLS "
                    "(voir docs/architecture/rls.md).",
                    file=sys.stderr,
                )
                return 2
            print(
                f"AVERTISSEMENT : le rôle « {role['nom']} » est SUPERUSER ou BYPASSRLS ; "
                "les policies ne protègent pas ce rôle.",
                file=sys.stderr,
            )
        if arguments.activer:
            activer(conn, selection)
        rapport = verifier(conn, selection)
        print(_rapport_texte(rapport))
        if arguments.activer:
            return 0 if rapport["tables_ok"] else 1
        return 0 if rapport["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
