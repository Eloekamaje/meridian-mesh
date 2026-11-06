"""Scoring hybride : lexical + sémantique + graphe + fraîcheur, sans décider de la vérité."""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone

__all__ = ["cosinus", "score", "tokens"]

_MOTS = re.compile(r"[a-z0-9àâäçéèêëîïôöùûüÿœæ]{3,}")


def tokens(texte) -> set[str]:
    return set(_MOTS.findall(str(texte or "").lower()))


def cosinus(gauche, droite) -> float:
    if not gauche or not droite or len(gauche) != len(droite):
        return 0.0
    produit = sum(float(a) * float(b) for a, b in zip(gauche, droite))
    norme_g = math.sqrt(sum(float(a) ** 2 for a in gauche))
    norme_d = math.sqrt(sum(float(b) ** 2 for b in droite))
    return produit / (norme_g * norme_d) if norme_g and norme_d else 0.0


def _fraicheur(valeur) -> float:
    if not valeur:
        return 0.5
    try:
        date = datetime.fromisoformat(str(valeur).replace("Z", "+00:00"))
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        jours = max(0.0, (datetime.now(timezone.utc) - date).total_seconds() / 86400)
        return 1.0 / (1.0 + jours / 180.0)
    except (TypeError, ValueError):
        return 0.5


def score(question: str, chunk: dict, *,
          vecteur_question=None, proximite: dict[str, float] | None = None) -> float:
    """Score borné d'un chunk ; les poids sont explicites et modifiables en un seul endroit."""
    q = tokens(question)
    c = tokens(" ".join((str(chunk.get("titre") or ""), str(chunk.get("section") or ""),
                         str(chunk.get("texte") or ""))))
    lexical = len(q & c) / len(q | c) if q and c else 0.0
    semantique = cosinus(vecteur_question or (), chunk.get("embedding") or ())
    graphe = 0.0
    if proximite and chunk.get("twin_id"):
        graphe = float(proximite.get(str(chunk["twin_id"]), 0.0))
    elif chunk.get("twin_id") and chunk.get("twin_id") in (chunk.get("twin_ids_actifs") or ()):
        graphe = 1.0
    pertinence = 0.35 * lexical + 0.45 * semantique + 0.15 * graphe
    if pertinence <= 0:
        return 0.0
    return round(pertinence + 0.05 * _fraicheur(chunk.get("updated_at")), 6)
