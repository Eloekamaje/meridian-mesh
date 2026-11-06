"""Primitives de chemins partagées par l'extraction et le moteur de liens.

Un seul endroit pour :

- normaliser un chemin (slashes, `..`, query, `;jsessionid`) ;
- découper en segments ;
- reconnaître un segment variable (`{id}`, `:id`, `<id>`, `*`) ;
- comparer un motif de route à un chemin réel ;
- calculer le meilleur suffixe commun entre un appel et une exposition.

Le module est pur : aucune lecture de fichier, aucun réseau, aucune base.
"""
from __future__ import annotations

import posixpath
import re

__all__ = [
    "est_variable",
    "motif_compatible",
    "normaliser",
    "prefixe",
    "score_suffixe",
    "segment_compatible",
    "segments",
]

_RE_JSESSIONID = re.compile(r";jsessionid=[^/?#]*", re.I)
_RE_SLASHES = re.compile(r"/+")


def normaliser(chemin) -> str:
    texte = str(chemin or "").strip().replace("\\", "/")
    texte = _RE_JSESSIONID.sub("", texte)
    texte = texte.split("?", 1)[0].split("#", 1)[0]
    texte = _RE_SLASHES.sub("/", texte)
    if not texte:
        return ""
    if texte == "/":
        return "/"
    absolu = texte.startswith("/")
    normalise = posixpath.normpath(texte)
    if normalise == ".":
        return ""
    if absolu and not normalise.startswith("/"):
        normalise = "/" + normalise
    return normalise.rstrip("/") or "/"


def segments(chemin) -> list[str]:
    return [segment for segment in normaliser(chemin).split("/") if segment]


def est_variable(segment: str) -> bool:
    texte = str(segment or "")
    return (texte.startswith("{") or texte.startswith(":")
            or texte in ("*", "**") or texte.startswith("${")
            or (texte.startswith("<") and texte.endswith(">")))


def segment_compatible(gauche: str, droite: str) -> bool:
    if est_variable(gauche) or est_variable(droite):
        return True
    return str(gauche or "").casefold() == str(droite or "").casefold()


def _motif_regex(motif: str) -> re.Pattern | None:
    normalise = normaliser(motif)
    if not normalise:
        return None
    morceaux: list[str] = []
    position = 0
    while position < len(normalise):
        if normalise.startswith("**", position):
            morceaux.append(".*")
            position += 2
        elif normalise[position] == "*":
            morceaux.append("[^/]*")
            position += 1
        elif normalise[position] == "{":
            fin = normalise.find("}", position)
            if fin < 0:
                return None
            morceaux.append("[^/]+")
            position = fin + 1
        elif normalise[position] == "<":
            fin = normalise.find(">", position)
            if fin < 0:
                return None
            morceaux.append("[^/]+")
            position = fin + 1
        else:
            morceaux.append(re.escape(normalise[position]))
            position += 1
    try:
        return re.compile("^" + "".join(morceaux) + "$")
    except re.error:
        return None


def motif_compatible(motif: str, chemin: str) -> bool:
    """Vrai si `chemin` satisfait le motif de route, variables et jokers compris."""
    normalise = normaliser(motif)
    cible = normaliser(chemin)
    if not normalise or not cible:
        return False
    if not any(caractere in normalise for caractere in "*{<"):
        return normalise.casefold() == cible.casefold()
    regex = _motif_regex(normalise)
    return bool(regex and regex.match(cible))


def score_suffixe(consommateur: str, producteur: str) -> int:
    """Score de suffixe commun ; 0 si le rapprochement serait trop vague.

    Le suffixe doit atteindre la fin des deux chemins, ce qui absorbe un préfixe de
    passerelle ou un contexte applicatif sans confondre `/accounts` avec `/{id}`.
    """
    gauche, droite = segments(consommateur), segments(producteur)
    if not gauche or not droite:
        return 0
    meilleur = 0
    for i in range(len(gauche)):
        for j in range(len(droite)):
            taille = min(len(gauche) - i, len(droite) - j)
            if taille == 0 or i + taille != len(gauche) or j + taille != len(droite):
                continue
            paires = list(zip(gauche[i:], droite[j:]))
            if not all(segment_compatible(a, b) for a, b in paires):
                continue
            litteral = any(not est_variable(a) and not est_variable(b) for a, b in paires)
            if not litteral:
                continue
            score = taille * 2
            if i == 0 and j == 0:
                score += 2
            meilleur = max(meilleur, score)
    return meilleur


def prefixe(prefixe: str, chemin: str) -> bool:
    gauche, droite = segments(prefixe), segments(chemin)
    if not gauche:
        return True
    if len(gauche) > len(droite):
        return False
    return all(segment_compatible(a, b) for a, b in zip(gauche, droite))
