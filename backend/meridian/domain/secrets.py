"""Règles communes de refus des secrets dans les URL.

Un seul endroit pour les trois modèles de liens : une URL avec identifiants ou avec
une clé de requête sensible est refusée, jamais recopiée.
"""
from __future__ import annotations

from urllib.parse import parse_qsl, urlsplit

__all__ = ["CLES_SECRETES", "sans_secret"]

CLES_SECRETES = frozenset({
    "password", "passwd", "secret", "token", "credential", "authorization",
    "api_key", "apikey", "access_key", "private_key", "client_secret",
})


def sans_secret(valeur: str, champ: str) -> str:
    """Refuse les identifiants et les clés sensibles d'une URL, rend le texte sinon."""
    texte = str(valeur or "")
    if "://" not in texte:
        return texte
    try:
        parties = urlsplit(texte)
    except ValueError as exc:
        raise ValueError(f"{champ} : URL invalide") from exc
    if parties.username is not None or parties.password is not None or "@" in parties.netloc:
        raise ValueError(f"{champ} : identifiants interdits dans une URL")
    for cle, _ in parse_qsl(parties.query, keep_blank_values=True):
        if cle.strip().lower() in CLES_SECRETES:
            raise ValueError(f"{champ} : secret interdit dans une URL")
    return texte
