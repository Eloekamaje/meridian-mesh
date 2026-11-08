"""Recopie canonique d'une décision prise dans l'interface Travail (B3).

`decider_case` écrit la décision dans Mongo puis appelle ce module quand la
double écriture Travail est active. La même décision devient un objet
`DECISION` de `objet_entreprise`, toujours tranché par le verdict humain —
jamais auto-confirmé.

L'identifiant d'épisode fait la corrélation Mongo ↔ Postgres : repris du case
(`episode_id`), des objets canoniques déjà liés (`donnees.episode_id`), et à
défaut de l'identifiant du case lui-même. Une `INVESTIGATION` canonique liée —
référencée par le case, portant l'épisode, ou reliée à l'une des `situations`
du case — est chaînée via les fonctions de `boucle` ; une `SITUATION` seule
ouvre d'abord l'investigation de l'épisode ; sans aucun parent canonique, la
décision est persistée seule, son `investigation_id` restant à renseigner quand
l'investigation de l'épisode existera (corrélation par `episode_id`).

Ce module ne touche ni Mongo ni le réseau : l'appelant reste responsable du
fail-soft — une erreur ici ne doit jamais faire échouer la décision Travail.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from meridian.adapters.outbound.postgres import boucle
from meridian.adapters.outbound.postgres import entreprise_depot

__all__ = ["enregistrer_decision_travail"]

_LIMITE_OBJETS = 1000


def _texte(valeur: Any) -> str:
    return str(valeur or "").strip()


def _donnees(objet: Any) -> dict[str, Any]:
    if isinstance(objet, Mapping):
        donnees = objet.get("donnees")
        if isinstance(donnees, Mapping):
            return dict(donnees)
    return {}


def _references(case: Mapping, cle: str) -> list[str]:
    """Ids canoniques déclarés dans le case : champ plat, sous `boucle` ou `canonique`."""
    trouves: list[str] = []
    for source in (case, case.get("boucle"), case.get("canonique")):
        if not isinstance(source, Mapping):
            continue
        valeur = source.get(cle)
        elements = valeur if isinstance(valeur, (list, tuple)) else [valeur]
        for element in elements:
            if isinstance(element, Mapping):
                element = element.get("id")
            identifiant = _texte(element)
            if identifiant and identifiant not in trouves:
                trouves.append(identifiant)
    return trouves


def _situations_du_case(case: Mapping) -> list[str]:
    """Ids de situations déclarés par le case (Mongo ou canoniques, même espace d'id)."""
    ids: list[str] = []
    for element in case.get("situations") or []:
        if isinstance(element, Mapping):
            element = element.get("id")
        identifiant = _texte(element)
        if identifiant and identifiant not in ids:
            ids.append(identifiant)
    return ids


def _lire_type(conn: Any, tenant: str, identifiant: str, type_attendu: str) -> dict | None:
    ligne = entreprise_depot.lire_objet(conn, tenant, identifiant)
    if ligne is not None and boucle._type_de(ligne) == type_attendu:
        return ligne
    return None


def _investigation_liee(conn: Any, tenant: str, case: Mapping, episode_id: str) -> dict | None:
    """L'investigation canonique de l'épisode : référence du case, `episode_id`, ou `situation_id`."""
    for ref in _references(case, "investigation_id"):
        ligne = _lire_type(conn, tenant, ref, "INVESTIGATION")
        if ligne is not None:
            return ligne
    investigations = entreprise_depot.lister_objets(
        conn, tenant, type_="INVESTIGATION", limite=_LIMITE_OBJETS)
    if episode_id:
        for ligne in investigations:
            if _texte(_donnees(ligne).get("episode_id")) == episode_id:
                return ligne
    situations = set(_situations_du_case(case))
    if situations:
        for ligne in investigations:
            if _texte(_donnees(ligne).get("situation_id")) in situations:
                return ligne
    return None


def _situation_liee(conn: Any, tenant: str, case: Mapping, episode_id: str,
                    investigation: dict | None) -> dict | None:
    """La situation canonique de l'épisode : parente de l'investigation, référence du case,
    id Mongo de `case.situations` (le backfill conserve l'identifiant), ou `episode_id`."""
    if investigation is not None:
        situation_id = _texte(_donnees(investigation).get("situation_id"))
        if situation_id:
            ligne = _lire_type(conn, tenant, situation_id, "SITUATION")
            if ligne is not None:
                return ligne
    for ref in _references(case, "situation_id"):
        ligne = _lire_type(conn, tenant, ref, "SITUATION")
        if ligne is not None:
            return ligne
    for identifiant in _situations_du_case(case):
        ligne = _lire_type(conn, tenant, identifiant, "SITUATION")
        if ligne is not None:
            return ligne
    if episode_id:
        for ligne in entreprise_depot.lister_objets(
                conn, tenant, type_="SITUATION", limite=_LIMITE_OBJETS):
            if _texte(_donnees(ligne).get("episode_id")) == episode_id:
                return ligne
    return None


def _episode_id(case: Mapping, situation: Any, investigation: Any) -> str:
    """L'identifiant partagé de l'épisode : le case d'abord, les objets liés ensuite,
    et à défaut l'identifiant du case lui-même."""
    return (_texte(case.get("episode_id"))
            or _texte(_donnees(investigation).get("episode_id"))
            or _texte(_donnees(situation).get("episode_id"))
            or _texte(case.get("id")))


def _contexte(conn: Any, tenant: str, case: Mapping) -> tuple[str, dict | None, dict | None]:
    """Rend `(episode_id, situation, investigation)` canoniques trouvés pour le case."""
    investigation = None
    situation = None
    for ref in _references(case, "investigation_id"):
        investigation = _lire_type(conn, tenant, ref, "INVESTIGATION")
        if investigation is not None:
            break
    for ref in _references(case, "situation_id"):
        situation = _lire_type(conn, tenant, ref, "SITUATION")
        if situation is not None:
            break
    episode_id = _episode_id(case, situation, investigation)
    if investigation is None:
        investigation = _investigation_liee(conn, tenant, case, episode_id)
        episode_id = _episode_id(case, situation, investigation)
    if situation is None:
        situation = _situation_liee(conn, tenant, case, episode_id, investigation)
        episode_id = _episode_id(case, situation, investigation)
    return episode_id, situation, investigation


def _options(case: Mapping, texte: str) -> list[str]:
    """Les options débattues dans le case, complétées du choix humain : `trancher_decision`
    exige que le choix figure parmi les options."""
    options: list[str] = []
    for option in case.get("options") or []:
        titre = _texte(option.get("titre") if isinstance(option, Mapping) else option)
        if titre and titre not in options:
            options.append(titre)
    if texte and not any(texte.casefold() == titre.casefold() for titre in options):
        options.append(texte)
    return options or [texte]


def enregistrer_decision_travail(conn: Any, tenant_id: Any, case: Mapping, decision: Mapping) -> dict:
    """Persiste l'objet canonique `DECISION` correspondant à une décision Travail ; rend la ligne écrite.

    `decision` est le dictionnaire poussé dans `decisions` du case (`texte`, `type`, `quand`,
    `par`). Avec une investigation canonique liée, la chaîne passe par `proposer_decision` puis
    `trancher_decision` et `enregistrer_boucle` ; une situation seule fait d'abord ouvrir
    l'investigation de l'épisode ; sans parent, la décision tranchée est écrite seule —
    `enregistrer_boucle` exigeant `investigation_id`, le dépôt d'objets la persiste directement.
    """
    if not isinstance(case, Mapping):
        raise boucle.BoucleInvalide("case attendu")
    if not isinstance(decision, Mapping):
        raise boucle.BoucleInvalide("décision Travail attendue")
    tenant = _texte(tenant_id) or _texte(case.get("tenant_id")) or "local"
    texte = _texte(decision.get("texte"))
    acteur = _texte(decision.get("par"))
    if not texte or not acteur:
        raise boucle.BoucleInvalide("décision Travail sans texte ou sans auteur")
    quand = _texte(decision.get("quand")) or None
    travail_id = _texte(case.get("id")) or None
    episode_id, situation, investigation = _contexte(conn, tenant, case)
    options = _options(case, texte)
    titre = texte if len(texte) <= 140 else texte[:137].rstrip() + "..."

    objets: list[Any] = []
    if investigation is None and situation is not None:
        investigation = boucle.ouvrir_investigation(
            situation,
            tenant_id=tenant,
            titre=_texte(case.get("titre")) or f"Épisode {episode_id}",
            question=_texte(case.get("objectif")) or f"Instruire la décision du travail {travail_id}",
            episode_id=episode_id,
        )
        objets.append(investigation)

    if investigation is not None:
        proposition = boucle.proposer_decision(
            investigation,
            options,
            titre=titre,
            resume=texte,
            tenant_id=tenant,
            episode_id=episode_id,
            travail_id=travail_id,
        )
        tranchee = boucle.trancher_decision(
            proposition, acteur=acteur, choix=texte, decide_le=quand)
        objets.append(tranchee)
        return boucle.enregistrer_boucle(conn, tenant, objets)[-1]

    # Aucun parent canonique : la décision est persistée seule — `enregistrer_boucle` refuse
    # une DECISION sans `investigation_id`. Même contenu que l'objet proposé puis tranché :
    # statut DECIDED, acteur et choix humains, mode DECLARED (jamais auto-confirmé).
    payload = {
        "id": boucle._nouvel_id("decision"),
        "tenant_id": tenant,
        "famille": "decision",
        "type": "DECISION",
        "mode": "DECLARED",
        "titre": titre,
        "observe_le": quand,
        "donnees": {
            "statut": boucle.STATUT_DECISION_TRANCHEE,
            "acteur": acteur,
            "choix": texte,
            "decide_le": quand or boucle._instant(),
            "options": options,
            "criteres": [],
            "incertitudes": [],
            "resume": texte,
            "episode_id": episode_id,
            "travail_id": travail_id,
            "origine": "travail",
        },
    }
    return entreprise_depot.enregistrer_objet(conn, tenant, payload)
