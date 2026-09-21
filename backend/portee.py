"""À qui appartient un travail ? Trois portées, choisies par la personne qui le porte.

    personnel   — seuls le responsable et les participants le voient (c'est le cas d'un travail qu'on vient d'ouvrir) ;
    equipe      — en plus, tous ceux qui travaillent dans le même espace (l'équipe) ;
    entreprise  — tous ceux dont les droits sur les jumeaux du travail le permettent.

La portée ne donne jamais plus de droits que le périmètre : un jumeau hors des droits d'une personne reste invisible pour elle,
quelle que soit la portée du travail. Un travail sans portée (jeu de données d'origine) est d'entreprise.
"""
from __future__ import annotations

PORTEES = ("personnel", "equipe", "entreprise")

LIBELLES = {"personnel": "Moi seul", "equipe": "Mon équipe", "entreprise": "Toute l'entreprise"}


def portee_de(case: dict) -> str:
    return case.get("portee") if case.get("portee") in PORTEES else "entreprise"


def acces(case: dict, persona_id: str, espace_id: str) -> bool:
    """La personne, dans son espace courant, peut-elle voir ce travail (indépendamment du périmètre sur les jumeaux) ?"""
    p = portee_de(case)
    if p == "entreprise":
        return True
    porte = persona_id == case.get("responsable") or persona_id in (case.get("participants") or [])
    if p == "personnel":
        return porte
    return porte or espace_id == case.get("espace")
