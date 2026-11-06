"""Règles communes de lecture de fichiers pour les connecteurs.

Les parcours restent propres à chaque consommateur (index de liens, graphe
d'interfaces), mais le refus du binaire et le décodage du texte sont partagés.
"""
from __future__ import annotations

__all__ = ["DOSSIERS_TECHNIQUES", "decoder_texte", "est_binaire"]

DOSSIERS_TECHNIQUES = frozenset({
    ".git", ".hg", ".svn", "node_modules", "vendor", "build", "dist",
    ".venv", "venv", "__pycache__", ".cache",
})


def est_binaire(donnees: bytes) -> bool:
    """NUL ou majorité d'octets de contrôle : le fichier n'est pas du texte."""
    if b"\x00" in donnees:
        return True
    echantillon = donnees[:4096]
    if not echantillon:
        return False
    controles = sum(1 for octet in echantillon if octet < 9 or 13 < octet < 32)
    return controles / len(echantillon) > 0.3


def decoder_texte(donnees: bytes, *, latin1: bool = True) -> str | None:
    """Décode en UTF-8, avec repli latin-1 seulement si demandé."""
    try:
        return donnees.decode("utf-8-sig")
    except UnicodeDecodeError:
        if not latin1:
            return None
        return donnees.decode("latin-1")
