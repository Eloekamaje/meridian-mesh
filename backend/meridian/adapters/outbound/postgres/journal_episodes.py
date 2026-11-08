"""Journal d'épisodes append-only (D1) : la chaîne canonique devient une vue sur les événements.

Chaque écriture d'objet de la boucle (:func:`enregistrer_boucle`) consigne un événement dans
``evenement_episode`` : tenant, épisode, type et identifiant de l'objet, action (``cree`` ou
``transition``), données minimales (statut, lien causal) et acteur éventuel. La table est
immuable — mêmes triggers ``_immuable`` et ``_sans_truncate`` qu'``outil_audit``.

L'écriture partage la connexion de l'appelant et ne lève jamais : un événement invalide rend
``refuse``, une erreur de base rend ``erreur``, sans empêcher la boucle de se persister. La
transaction du journal est bornée par un savepoint : un échec d'insertion ne contamine pas la
transaction appelante.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

_LIMITE_MAX = 500


class ErreurJournal(ValueError):
    """Événement refusé avant toute écriture."""


def _texte(valeur: Any, champ: str, *, obligatoire: bool = False, limite: int = 512) -> str | None:
    texte = "" if valeur is None else " ".join(str(valeur).split())
    texte = texte[:limite]
    if obligatoire and not texte:
        raise ErreurJournal(f"{champ} obligatoire")
    return texte or None


def _tenant(tenant_id: Any) -> str:
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ErreurJournal("tenant_id obligatoire")
    return tenant_id.strip()[:128]


def _donnees(valeur: Any) -> dict:
    if valeur is None:
        return {}
    if not isinstance(valeur, Mapping):
        raise ErreurJournal("donnees : objet attendu")
    return dict(valeur)


def _limite(limite: Any) -> int:
    if isinstance(limite, bool):
        raise ErreurJournal("limite invalide")
    try:
        valeur = int(limite)
    except (TypeError, ValueError) as erreur:
        raise ErreurJournal("limite invalide") from erreur
    return max(1, min(valeur, _LIMITE_MAX))


def _ligne(ligne: Mapping) -> dict:
    sortie = dict(ligne)
    for cle, valeur in sortie.items():
        if isinstance(valeur, datetime):
            sortie[cle] = valeur.isoformat()
    return sortie


def consigner(conn: Any, tenant_id: Any, evenement: Any) -> dict:
    """Écrit un événement d'épisode ; rend toujours un statut, même si la base échoue."""
    try:
        if not isinstance(evenement, Mapping):
            raise ErreurJournal("evenement : objet attendu")
        valeurs = {
            "tenant_id": _tenant(tenant_id),
            "episode_id": _texte(
                evenement.get("episode_id"), "episode_id", obligatoire=True, limite=256),
            "objet_type": _texte(
                evenement.get("objet_type"), "objet_type", obligatoire=True, limite=64),
            "objet_id": _texte(
                evenement.get("objet_id"), "objet_id", obligatoire=True, limite=256),
            "action": _texte(evenement.get("action"), "action", obligatoire=True, limite=64),
            "donnees": _donnees(evenement.get("donnees")),
            "acteur": _texte(evenement.get("acteur"), "acteur", limite=256),
        }
    except ErreurJournal as erreur:
        return {"statut": "refuse", "insere": False, "id": None, "erreur": str(erreur)}
    except Exception as erreur:
        return {"statut": "refuse", "insere": False, "id": None, "erreur": type(erreur).__name__}

    try:
        with conn.transaction():
            with conn.cursor(row_factory=dict_row) as cur:
                inseree = cur.execute(
                    "INSERT INTO evenement_episode "
                    "(tenant_id, episode_id, objet_type, objet_id, action, donnees, acteur) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                    (valeurs["tenant_id"], valeurs["episode_id"], valeurs["objet_type"],
                     valeurs["objet_id"], valeurs["action"], Jsonb(valeurs["donnees"]),
                     valeurs["acteur"])).fetchone()
    except Exception as erreur:
        return {"statut": "erreur", "insere": False, "id": None, "erreur": type(erreur).__name__}

    return {
        "statut": "ok",
        "insere": inseree is not None,
        "id": inseree["id"] if inseree is not None else None,
    }


def lire_episode(conn: Any, tenant_id: Any, episode_id: Any) -> list[dict]:
    """Les événements d'un épisode du tenant, dans l'ordre d'écriture."""
    tenant = _tenant(tenant_id)
    episode = _texte(episode_id, "episode_id", obligatoire=True, limite=256)
    with conn.cursor(row_factory=dict_row) as cur:
        lignes = cur.execute(
            "SELECT id, tenant_id, episode_id, objet_type, objet_id, action, donnees, acteur, quand "
            "FROM evenement_episode WHERE tenant_id = %s AND episode_id = %s "
            "ORDER BY quand, id",
            (tenant, episode)).fetchall()
    return [_ligne(ligne) for ligne in lignes]


def episodes(conn: Any, tenant_id: Any, limite: Any = 50) -> list[dict]:
    """Les derniers épisodes du tenant, groupés : nombre d'événements et bornes temporelles."""
    tenant = _tenant(tenant_id)
    borne = _limite(limite)
    with conn.cursor(row_factory=dict_row) as cur:
        lignes = cur.execute(
            "SELECT episode_id, count(*) AS evenements, min(quand) AS premier, max(quand) AS dernier "
            "FROM evenement_episode WHERE tenant_id = %s "
            "GROUP BY episode_id ORDER BY dernier DESC, episode_id LIMIT %s",
            (tenant, borne)).fetchall()
    return [_ligne(ligne) for ligne in lignes]


__all__ = [
    "ErreurJournal",
    "consigner",
    "episodes",
    "lire_episode",
]
