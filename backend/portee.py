"""À qui appartient un travail ? Trois portées, choisies par la personne qui le porte.

    personnel   — seuls le responsable et les participants le voient (c'est le cas d'un travail qu'on vient d'ouvrir) ;
    equipe      — en plus, les membres de l'équipe du responsable (`equipe` de son profil) ;
    entreprise  — tous ceux dont les droits sur les jumeaux du travail le permettent.

La portée ne donne jamais plus de droits que le périmètre : un jumeau hors des droits d'une personne reste invisible pour elle,
quelle que soit la portée du travail. Un travail sans portée (jeu de données d'origine) est d'entreprise.
"""
from __future__ import annotations

from seed_data import EQUIPES, PERSONAS

PORTEES = ("personnel", "equipe", "entreprise")

LIBELLES = {"personnel": "Moi seul", "equipe": "Mon équipe", "entreprise": "Toute l'entreprise"}


def portee_de(case: dict) -> str:
    return case.get("portee") if case.get("portee") in PORTEES else "entreprise"


def equipe_de(persona_id: str):
    return next((p.get("equipe") for p in PERSONAS if p["id"] == persona_id), None)


def libelle_equipe(equipe_id):
    return next((e["label"] for e in EQUIPES if e["id"] == equipe_id), None)


def acces(case: dict, persona_id: str, espace_id: str = "") -> bool:
    """La personne peut-elle voir ce travail (indépendamment du périmètre sur les jumeaux) ?"""
    p = portee_de(case)
    if p == "entreprise":
        return True
    porte = persona_id == case.get("responsable") or persona_id in (case.get("participants") or [])
    if p == "personnel":
        return porte
    mon_equipe = equipe_de(persona_id)
    if case.get("equipe"):
        return porte or (mon_equipe is not None and mon_equipe == case["equipe"])
    return porte or espace_id == case.get("espace")  # travail partagé avant l'existence des équipes : l'espace tient lieu d'équipe
