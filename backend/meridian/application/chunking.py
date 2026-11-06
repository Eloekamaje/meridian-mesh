"""Découpage de documents en sections citables, avec lignes et chevauchement bornés."""
from __future__ import annotations

from typing import Iterable

__all__ = ["decouper"]


def _texte(lignes) -> str:
    return "\n".join(" ".join(str(ligne).split()) for ligne in lignes if str(ligne).strip())


def decouper(lignes: Iterable[str], *, max_caracteres: int = 1000,
             chevauchement: int = 150) -> list[dict]:
    """Découpe par section puis par taille, en conservant les bornes de lignes.

    Le locator final est reconstruit par l'appelant avec le système, l'espace, la référence
    et la version de la source : un chunk n'est jamais détaché de sa preuve.
    """
    lignes = [str(ligne).rstrip() for ligne in lignes if str(ligne).strip()]
    if not lignes:
        return []
    max_caracteres = max(200, int(max_caracteres))
    chevauchement = max(0, min(int(chevauchement), max_caracteres // 2))
    sections: list[tuple[str, list[tuple[int, str]]]] = []
    section = ""
    courantes: list[tuple[int, str]] = []
    for numero, ligne in enumerate(lignes, 1):
        if ligne.lstrip().startswith("#"):
            if courantes:
                sections.append((section, courantes))
            section, courantes = ligne.lstrip("# ").strip(), []
        courantes.append((numero, ligne))
    if courantes:
        sections.append((section, courantes))

    resultat: list[dict] = []
    ordinal = 0
    for titre, contenu in sections:
        bloc: list[tuple[int, str]] = []
        taille = 0
        for numero, ligne in contenu:
            if bloc and taille + len(ligne) + 1 > max_caracteres:
                resultat.append({
                    "ordinal": ordinal,
                    "section": titre,
                    "debut": bloc[0][0],
                    "fin": bloc[-1][0],
                    "texte": _texte(l for _, l in bloc),
                })
                ordinal += 1
                # Chevauchement : on reprend les dernières lignes du bloc, sans dépasser la moitié.
                repris, taille_reprise = [], 0
                for item in reversed(bloc):
                    if taille_reprise + len(item[1]) + 1 > chevauchement:
                        break
                    repris.insert(0, item)
                    taille_reprise += len(item[1]) + 1
                bloc, taille = repris, taille_reprise
            bloc.append((numero, ligne))
            taille += len(ligne) + 1
        if bloc:
            resultat.append({
                "ordinal": ordinal,
                "section": titre,
                "debut": bloc[0][0],
                "fin": bloc[-1][0],
                "texte": _texte(l for _, l in bloc),
            })
            ordinal += 1
    return [chunk for chunk in resultat if chunk["texte"].strip()]
