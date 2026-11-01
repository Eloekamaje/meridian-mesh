"""Tirage OTLP d'arrière-plan : sources persistées, runs observés, situations et notifications.

Une source OTLP est une ligne `source` de type `OTLP` dont la configuration porte l'URL, la référence de secret,
l'environnement et la fréquence. Le tirage est best-effort par source : une source en panne n'empêche pas les
autres, et aucun URL ni secret résolu ne sort de ce module. Le graphe observé passe par `decouverte_interfaces`
avec `source="otlp"`, ce qui remplace le périmètre runtime existant sans toucher au code déclaré.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from meridian.adapters.outbound.connectors import connecteurs_runtime_pull
from meridian.adapters.outbound.postgres import decouverte_interfaces
from meridian.adapters.outbound.redis import notifications_impacts
from meridian.application import impacts_situations

__all__ = ["sources_otlp", "etat_sources", "tirer", "tirer_et_publier"]

journal = logging.getLogger("meridian.pulls_runtime")
FREQUENCES = {"horaire": 3600, "quotidienne": 86400, "hebdomadaire": 604800}


def _texte(valeur):
    if valeur is None:
        return None
    texte = str(valeur).strip()
    return texte or None


def _configuration(source: dict) -> dict:
    configuration = source.get("configuration")
    if isinstance(configuration, str):
        try:
            configuration = json.loads(configuration)
        except (TypeError, ValueError):
            configuration = {}
    return configuration if isinstance(configuration, dict) else {}


def _source_normalisee(source: dict) -> dict:
    """Vue interne d'une source : URL et référence de secret restent privées au tirage."""
    configuration = _configuration(source)
    return {
        "id": source.get("id"),
        "nom": _texte(source.get("nom")) or _texte(source.get("id")) or "otlp",
        "url": (_texte(configuration.get("url")) or _texte(source.get("url"))
                or _texte(source.get("emplacement"))),
        "secret_ref": (_texte(configuration.get("secret_ref")) or _texte(source.get("secret_ref"))),
        "environment": (_texte(configuration.get("environnement"))
                        or _texte(configuration.get("environment"))
                        or _texte(source.get("environnement"))
                        or _texte(source.get("environment")) or "inconnu"),
        "frequence": configuration.get("frequence"),
        "hotes_autorises": source.get("hotes_autorises") or configuration.get("hotes_autorises"),
        "configuration": configuration,
    }


def _source_publique(source: dict) -> dict:
    """Ce qu'un appelant peut voir d'une source : jamais l'URL, jamais la référence de secret."""
    configuration = _configuration(source)
    return {
        "id": source.get("id"),
        "nom": source.get("nom"),
        "environment": source.get("environment"),
        "frequence": source.get("frequence"),
        "derniere_pull": configuration.get("derniere_pull"),
        "derniere_tentative": configuration.get("derniere_tentative"),
        "derniere_erreur": configuration.get("derniere_erreur"),
    }


def intervalle(source) -> int:
    """Secondes entre deux tirages automatiques ; une fréquence inconnue retombe sur l'horaire."""
    configuration = _configuration(source) if isinstance(source, dict) else {}
    frequence = str(configuration.get("frequence") or (source or {}).get("frequence") or "horaire").lower()
    return FREQUENCES.get(frequence, FREQUENCES["horaire"])


def due(source, maintenant=None) -> bool:
    """Vrai si le dernier tirage réussi est assez ancien (ou n'existe pas)."""
    configuration = _configuration(source) if isinstance(source, dict) else {}
    dernier = configuration.get("derniere_pull")
    if not dernier:
        return True
    try:
        moment = datetime.fromisoformat(str(dernier).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return True
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    maintenant = maintenant or datetime.now(timezone.utc)
    if maintenant.tzinfo is None:
        maintenant = maintenant.replace(tzinfo=timezone.utc)
    return (maintenant - moment).total_seconds() >= intervalle(source)


def _marquer(conn, source, *, succes=False, erreur=None) -> None:
    """Range l'état de tirage dans la configuration de la source, sans jamais y mettre URL ni secret."""
    identifiant = source.get("id")
    if identifiant is None:
        return
    maintenant = datetime.now(timezone.utc).isoformat()
    patch = {"derniere_tentative": maintenant}
    if succes:
        patch["derniere_pull"] = maintenant
        patch["derniere_erreur"] = None
    else:
        patch["derniere_erreur"] = (str(erreur or "tirage impossible")[:200])
    conn.execute(
        "UPDATE source SET configuration = coalesce(configuration, '{}'::jsonb) || %s WHERE id = %s",
        (Jsonb(patch), identifiant))


def _identifiants(jumeau, conn=None) -> tuple[str, str]:
    if isinstance(jumeau, dict):
        identifiant, tenant_id = _texte(jumeau.get("id")), _texte(jumeau.get("tenant_id"))
    else:
        identifiant, tenant_id = _texte(jumeau), None
    if not identifiant:
        raise ValueError("jumeau sans identifiant : tirage OTLP refusé")
    if not tenant_id and conn is not None:
        ligne = conn.execute("SELECT tenant_id FROM jumeau WHERE id = %s", (identifiant,)).fetchone()
        if ligne:
            tenant_id = _texte(ligne.get("tenant_id") if isinstance(ligne, dict) else ligne[0])
    if not tenant_id:
        raise ValueError("jumeau sans tenant : tirage OTLP refusé")
    return identifiant, tenant_id


def sources_otlp(conn, jumeau_id) -> list[dict]:
    """Les sources OTLP persistées du jumeau, configuration et référence de secret comprises.

    La configuration (jsonb) est prioritaire sur les colonnes historiques `url`/`emplacement` et `secret_ref`.
    Le secret n'est jamais résolu ici : seule sa référence est rendue, au tirage de la résoudre.
    """
    identifiant = _texte(jumeau_id)
    if not identifiant:
        raise ValueError("jumeau_id vide : sources OTLP refusées")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM source WHERE jumeau_id = %s AND type = 'OTLP' ORDER BY nom, id", (identifiant,))
        lignes = cur.fetchall()
    return [_source_normalisee(ligne) for ligne in lignes]


def tirer(conn, jumeau, source) -> dict:
    """Tire une source OTLP, exécute la découverte et rend le run observé.

    Le graphe est fusionné par `decouverte_interfaces` (`source="otlp"`, `remplacer=True`) : les contrats runtime
    et assertions OTLP sont remplacés, le code déclaré reste intact. La source rendue ne contient ni URL ni secret.
    """
    identifiant, tenant_id = _identifiants(jumeau, conn)
    normalisee = _source_normalisee(source)
    url = normalisee["url"]
    if not url:
        raise ValueError(f"source OTLP {normalisee['nom']} sans URL")
    graphe = connecteurs_runtime_pull.depuis_url(
        identifiant, url, normalisee["secret_ref"], normalisee["environment"], "otlp",
        hotes_autorises=normalisee["hotes_autorises"])
    resultat = decouverte_interfaces.executer(
        conn, tenant_id, identifiant, graph=graphe, environment=normalisee["environment"], source="otlp")
    _marquer(conn, source, succes=True)
    return {
        "source": _source_publique(normalisee),
        "run": resultat["run"],
        "changements": resultat["changements"],
        "impacts": resultat["impacts"],
        "graphe": resultat["graphe"],
    }


async def _publier_situation(db, situation: dict) -> None:
    """Publie la situation d'interface et archive les précédentes du même jumeau (comme le gardien)."""
    prefixe = situation["id"].rsplit("-", 1)[0] + "-"
    await db.situations.update_many(
        {"id": {"$regex": f"^{re.escape(prefixe)}", "$ne": situation["id"]}, "statut": "active"},
        {"$set": {"statut": "archivee"}})
    await db.situations.replace_one({"id": situation["id"]}, situation, upsert=True)


async def tirer_et_publier(db, conn, jumeau, sources=None, force=False) -> list[dict]:
    """Tire chaque source OTLP, publie situation et notification si impact, et rend les runs réussis.

    `sources` peut être fourni (endpoint manuel, tests) ; sinon les sources persistées du jumeau sont relues.
    Une erreur de source est journalisée sans interrompre les suivantes ; une erreur de publication ne retire pas
    le run déjà obtenu. Aucun URL ni secret n'apparaît dans les valeurs rendues.
    """
    identifiant = _texte(jumeau.get("id") if isinstance(jumeau, dict) else jumeau)
    if sources is None:
        try:
            sources = await asyncio.to_thread(sources_otlp, conn, identifiant)
        except Exception as erreur:  # noqa: BLE001 - le gardien ne bloque pas sur une lecture de sources
            journal.warning("tirage OTLP %s : sources illisibles (%s)", identifiant, type(erreur).__name__)
            return []
    runs = []
    for source in sources or []:
        normalisee = _source_normalisee(source)
        if not force and not due(source):
            journal.info("tirage OTLP %s : source %s pas encore due", identifiant, normalisee["nom"])
            continue
        try:
            resultat = await asyncio.to_thread(tirer, conn, jumeau, normalisee)
        except Exception as erreur:  # noqa: BLE001 - une source en panne ne bloque pas les autres
            journal.warning("tirage OTLP %s : source %s en échec (%s)", identifiant, normalisee["nom"],
                            type(erreur).__name__)
            try:
                _marquer(conn, source, erreur=type(erreur).__name__)
            except Exception:  # noqa: BLE001
                pass
            continue
        run = resultat.get("run") or {}
        runs.append(run)
        try:
            situation = impacts_situations.situation_depuis_run(run, jumeau)
            if situation:
                await _publier_situation(db, situation)
                await notifications_impacts.publier_notification(db, jumeau, run, situation)
        except Exception as erreur:  # noqa: BLE001 - la publication se rejoue à la passe suivante
            journal.warning("tirage OTLP %s : publication de %s impossible (%s)", identifiant,
                            normalisee["nom"], type(erreur).__name__)
    return runs


def etat_sources(conn, jumeau_id) -> list[dict]:
    """Vue publique des sources OTLP : état, fréquence et dernière erreur, jamais URL/secret."""
    return [_source_publique(source) for source in sources_otlp(conn, jumeau_id)]
