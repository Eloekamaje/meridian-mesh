"""Exécution d'une découverte d'interfaces : collecte, persistance, diff, impacts et journal du run.

Le run est un processus daté : il lit l'état précédent, enregistre le nouveau graphe, compare, calcule les impacts,
puis laisse une ligne `discovery_run` avec ses compteurs, ses changements et ses preuves. Aucun accès réseau, aucun
secret : la collecte ne lit que des fichiers locaux ou des claims déjà extraits.

Choix sur les erreurs : une collecte qui échoue est journalisée avec `status = error` et un message court, puis
l'exception d'origine est relancée telle quelle. Un run n'est jamais silencieusement transformé en succès ; si le
journal lui-même ne peut pas être écrit, l'erreur de collecte reste celle qui remonte.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from psycopg.types.json import Jsonb

from jumeau import decouverte, interfaces, interfaces_depot
from jumeau.connecteur_interfaces import collecter

__all__ = ["executer"]

STATUTS = ("ok", "partial", "error")
_LONGUEUR_ERREUR = 200


def _maintenant() -> datetime:
    return datetime.now(timezone.utc)


def _message_court(erreur: BaseException) -> str:
    texte = " ".join(str(erreur).split())
    return (texte or type(erreur).__name__)[:_LONGUEUR_ERREUR]


def _collecter(application_id, racine, claims, environment) -> interfaces.InterfaceGraph:
    morceaux = []
    if racine is not None:
        morceaux.append(collecter(racine, application_id, environment))
    if claims is not None:
        morceaux.append(interfaces.depuis_claims(application_id, claims, environment))
    return interfaces.merge(morceaux)


def _journaliser(conn, *, run_id, tenant_id, application_id, source, environment, started_at, ended_at,
                 status, stats, changes, impacts, error) -> dict:
    if status not in STATUTS:
        raise ValueError(f"statut de run invalide : {status!r}")
    with conn.transaction():
        conn.execute(
            "INSERT INTO discovery_run "
            "(id, tenant_id, application_id, source, environment, started_at, ended_at, status, stats, changes, "
            "impacts, error) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (run_id, tenant_id, application_id, source, environment, started_at, ended_at, status,
             Jsonb(stats), Jsonb(changes), Jsonb(impacts), error))
    return {
        "id": run_id, "tenant_id": tenant_id, "application_id": application_id, "source": source,
        "environment": environment, "started_at": started_at.isoformat(), "ended_at": ended_at.isoformat(),
        "status": status, "stats": stats, "changes": changes, "impacts": impacts, "error": error,
    }


def executer(conn, tenant_id, application_id, racine=None, claims=None, environment="inconnu",
             source="local") -> dict:
    """Collecte puis persiste un graphe d'interfaces et journalise le run correspondant.

    `racine` fait passer par le connecteur de fichiers, `claims` par les revendications `EXPOSE` du code ; les deux
    peuvent être fournis et sont alors fusionnés. Le graphe d'avant est relu pour l'application, le graphe d'après
    est enregistré, puis `diff_graphs` et `impacts` sont calculés. Les impacts lisent aussi le contexte du tenant
    entier, afin qu'une assertion `CONSOMME` d'une autre application reste une preuve valable.

    Rend `{"run", "changements", "impacts", "graphe"}`. En cas d'erreur, le run `error` est écrit puis l'exception
    est relancée.
    """
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError("tenant_id vide : découverte refusée")
    if not isinstance(application_id, str) or not application_id.strip():
        raise ValueError("application_id vide : découverte refusée")
    tenant_id, application_id = tenant_id.strip(), application_id.strip()

    run_id = f"run-{uuid.uuid4()}"
    started_at = _maintenant()
    try:
        graph = _collecter(application_id, racine, claims, environment)
        avant = interfaces_depot.lire_graph(conn, tenant_id, application_id)
        contexte = interfaces_depot.lire_graph(conn, tenant_id)
        compte = interfaces_depot.enregistrer(conn, tenant_id, graph, remplacer=True)
        changements = decouverte.diff_graphs(avant, graph)
        constats = decouverte.impacts(changements, interfaces.merge([contexte, graph]))
    except Exception as erreur:  # noqa: BLE001 - toute panne de collecte ou de dépôt doit laisser une trace
        ended_at = _maintenant()
        try:
            _journaliser(
                conn, run_id=run_id, tenant_id=tenant_id, application_id=application_id, source=source,
                environment=environment, started_at=started_at, ended_at=ended_at, status="error", stats={},
                changes=[], impacts=[], error=_message_court(erreur))
        except Exception:  # noqa: BLE001 - le journal ne doit pas masquer l'erreur d'origine
            pass
        raise

    ended_at = _maintenant()
    status = "partial" if graph.partial else "ok"
    changements_json = [change.as_dict() for change in changements]
    impacts_json = [constat.as_dict() for constat in constats]
    stats = {
        **compte,
        "changements": len(changements_json),
        "impacts": len(impacts_json),
        "partial": bool(graph.partial),
        "diagnostics": list(graph.diagnostics),
    }
    run = _journaliser(
        conn, run_id=run_id, tenant_id=tenant_id, application_id=application_id, source=source,
        environment=environment, started_at=started_at, ended_at=ended_at, status=status, stats=stats,
        changes=changements_json, impacts=impacts_json, error=None)
    return {"run": run, "changements": changements_json, "impacts": impacts_json, "graphe": graph.as_dict()}
