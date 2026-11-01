"""À qui appartient un travail ? Trois portées, choisies par la personne qui le porte.

    personnel   — seuls le responsable et les participants le voient (c'est le cas d'un travail qu'on vient d'ouvrir) ;
    entreprise  — tous ceux dont les droits sur les jumeaux du travail le permettent.

La portée ne donne jamais plus de droits que le périmètre : un jumeau hors des droits d'une personne reste invisible
pour elle, quelle que soit la portée du travail. Un travail sans portée (jeu de données d'origine) est d'entreprise.
"""
from __future__ import annotations

PORTEES = ("personnel", "entreprise")


def portee_de(case: dict) -> str:
    return case.get("portee") if case.get("portee") in PORTEES else "entreprise"


def acces(case: dict, acteur: str) -> bool:
    """L'acteur peut-il voir ce travail (indépendamment du périmètre sur les jumeaux) ?"""
    if case.get("statut") == "conversation":  # privée à son auteur, quelle que soit la portée
        return acteur == case.get("auteur")
    if portee_de(case) == "entreprise":
        return True
    return acteur == case.get("responsable") or acteur in (case.get("participants") or [])
