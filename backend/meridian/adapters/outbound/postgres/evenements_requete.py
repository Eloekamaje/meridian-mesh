"""Épilogue de requête (plan Cognition IA, C8) : chaque tour laisse un événement.

La table ``evenement_requete`` (``schema.sql``) enregistre, par requête : le hash de la
question (jamais le texte), la classe de réponse, le verdict de la sonde B8, les preuves
consultées, la confiance, les citations vérifiées et non résolues (groundedness C7), le
modèle, les jetons et la durée. Quand la réponse n'est pas concluante,
``inconnu_question`` est vrai : le détecteur B7 ``question_non_tranchee`` pourra
consommer ces événements — ``non_concluante`` reprend ici la même règle que
``detecteurs_besoins._non_concluante`` (lien documenté, non câblé à ce stade).

Fail-soft : ``consigner`` ne lève jamais (rend ``None``) — un tour ne dépend jamais de
son épilogue.
"""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import logging
import unicodedata
from typing import Any

__all__ = ["consigner", "construire", "non_concluante", "question_hash"]

journal = logging.getLogger("meridian.evenements_requete")

# Mêmes marqueurs que detecteurs_besoins._MARQUEURS_TEXTE (B7) : une absence bornée ou
# un repli laissent la question ouverte — l'événement le dit sans que B7 relise le texte.
_MARQUEURS_TEXTE = (
    "non observé dans",
    "preuve d'absence",
    "aucun twin dans le périmètre",
    "assez de connaissances pour répondre",
    "pas pu interpréter",
)
_STATUTS_NON_CONCLUANTS = {"clarification_requise", "partiel", "echec"}


def _normaliser(valeur: Any) -> str:
    texte = unicodedata.normalize("NFKD", str(valeur or "").lower())
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return " ".join(texte.split())


def question_hash(question: Any) -> str:
    """Empreinte de la question normalisée — le texte brut n'est jamais stocké."""
    return hashlib.sha256(_normaliser(question).encode("utf-8")).hexdigest()


def non_concluante(reponse: Mapping) -> str | None:
    """Raison pour laquelle une réponse de tour n'est pas concluante, sinon ``None``.

    Même règle que le détecteur B7 ``question_non_tranchee``
    (``detecteurs_besoins._non_concluante``), appliquée à la réponse du tour elle-même
    plutôt qu'à un message du miroir ``travail``.
    """
    if not isinstance(reponse, Mapping):
        return "réponse absente"
    resolution = reponse.get("resolution")
    if isinstance(resolution, Mapping):
        statut = str(resolution.get("statut") or "").strip().lower()
        if resolution.get("absent") or statut == "absent":
            return "absence concluante (resolution.absent)"
        if resolution.get("ambigu") or statut == "ambigu":
            return "identité non tranchée (resolution.ambigu)"
    if reponse.get("limite") or reponse.get("limite_preuve"):
        return "limite déclarée par la réponse"
    statut = str(reponse.get("raisonnement_statut") or reponse.get("statut") or "").strip().lower()
    if statut in _STATUTS_NON_CONCLUANTS:
        return f"réponse {statut}"
    if str(reponse.get("origine") or "").strip().lower() == "repli":
        return "réponse de repli (origine=repli)"
    texte = str(reponse.get("reponse") or reponse.get("texte") or "")
    for marqueur in _MARQUEURS_TEXTE:
        if marqueur in texte:
            return f"texte non concluant : « {marqueur} »"
    return None


def _entier(valeur: Any) -> int | None:
    try:
        return int(valeur)
    except (TypeError, ValueError):
        return None


def _reel(valeur: Any) -> float | None:
    try:
        nombre = float(valeur)
    except (TypeError, ValueError):
        return None
    return nombre if nombre == nombre else None  # NaN exclu


def construire(reponse: Mapping, *, question: Any = None, episode_id: Any = None,
               duree_ms: Any = None) -> dict:
    """L'événement normalisé d'un tour, prêt pour ``consigner`` — déterministe, sans base.

    ``confiance`` : la clé ``confiance`` de la réponse si elle existe, sinon la part de
    citations vérifiées du rapport groundedness ; jamais un chiffre inventé.
    """
    raison = non_concluante(reponse)  # avant normalisation : une non-réponse est non concluante
    reponse = reponse if isinstance(reponse, Mapping) else {}
    sonde = reponse.get("sonde") if isinstance(reponse.get("sonde"), Mapping) else {}
    grounded = reponse.get("groundedness") if isinstance(reponse.get("groundedness"), Mapping) else {}
    usage = reponse.get("usage") if isinstance(reponse.get("usage"), Mapping) else {}
    confiance = _reel(reponse.get("confiance"))
    if confiance is None and grounded.get("total"):
        verifiees = _reel(grounded.get("verifiees"))
        confiance = round(verifiees / grounded["total"], 4) if verifiees is not None else None
    return {
        "question_hash": question_hash(question),
        "classe": str(reponse.get("comportement") or "")[:64] or None,
        "verdict_sonde": str(sonde.get("verdict") or "")[:32] or None,
        "preuves_consultees": len(reponse.get("preuves") or ()) + len(sonde.get("preuves") or ()),
        "confiance": confiance,
        "citations_verifiees": _entier(grounded.get("verifiees")),
        "non_resolues": _entier(grounded.get("non_resolues")),
        "inconnu_question": raison is not None,
        "inconnu_raison": raison,
        "episode_id": str(episode_id)[:128] if episode_id else None,
        "model": str(usage.get("modele") or "")[:128] or None,
        "tokens": _entier(usage.get("total")),
        "duree_ms": _reel(duree_ms),
    }


def consigner(conn, tenant_id: Any, evenement: Mapping) -> int | None:
    """Insère l'événement du tour ; rend l'id de la ligne, ``None`` si l'écriture échoue.

    Jamais bloquant : toute erreur (table absente, connexion coupée, données invalides)
    est journalisée en debug et rendue par ``None`` — l'épilogue ne peut pas casser un tour.
    """
    try:
        tenant = str(tenant_id or "").strip()[:128]
        if not tenant:
            raise ValueError("tenant_id obligatoire")
        donnees = dict(evenement or {})
        if not donnees.get("question_hash"):
            donnees["question_hash"] = question_hash("")
        with conn.cursor() as cur:
            ligne = cur.execute(
                """INSERT INTO evenement_requete
                       (tenant_id, question_hash, classe, verdict_sonde, preuves_consultees,
                        confiance, citations_verifiees, non_resolues, inconnu_question,
                        inconnu_raison, episode_id, model, tokens, duree_ms)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (tenant, donnees["question_hash"], donnees.get("classe"),
                 donnees.get("verdict_sonde"), _entier(donnees.get("preuves_consultees")) or 0,
                 _reel(donnees.get("confiance")), _entier(donnees.get("citations_verifiees")),
                 _entier(donnees.get("non_resolues")), bool(donnees.get("inconnu_question")),
                 str(donnees.get("inconnu_raison") or "")[:500] or None,
                 donnees.get("episode_id"), donnees.get("model"),
                 _entier(donnees.get("tokens")), _reel(donnees.get("duree_ms"))),
            ).fetchone()
        return int(ligne[0]) if ligne else None
    except Exception:
        journal.debug("événement de requête non consigné", exc_info=True)
        return None
