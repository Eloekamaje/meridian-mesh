"""Preuves discriminantes persistées (plan Cognition IA, D7).

Retrieval dédié aux hypothèses rivales — nouveau module, ``retrieval_memoire``
n'est pas modifié. Deux lectures bornées, aucune écriture, aucune IA :

- :func:`preuves_discriminantes` : pour chaque HYPOTHESIS persistée, les
  preuves/objets qui l'appuient **contre** ses rivales. Les objets de preuve
  sont les ``interface_assertion`` du couple ``(subject, predicate)`` porté par
  le NEED parent (via ``donnees.sujet_detection`` ou ``donnees.preuves``) et les
  preuves déjà embarquées dans le NEED. Chaque objet est attribué à la rivale
  qu'il discrimine le mieux (recouvrement de mots porteurs avec
  ``enonce + preuve_discriminante``) ; un objet qui en appuie plusieurs à égalité
  n'est pas discriminant et part en ``partagees``.
- :func:`suggestions` : la question à valeur maximale pour un NEED — bâtie
  depuis ses hypothesis rivales via :func:`abduction.question_maximale`, prête
  pour le fil d'attention (la forme ``question_socratique`` vient de
  :func:`abduction.ou_question`).

Mode READ : ``hypotheses``, ``besoins``, ``assertions`` et ``need`` remplacent la
lecture en base quand ils sont fournis — ``conn`` peut alors être ``None``.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from meridian.adapters.outbound.postgres import (
    detecteurs_besoins, entreprise_depot,
)
from meridian.application import abduction

__all__ = [
    "preuves_discriminantes",
    "suggestions",
]

_LIMITE_LECTURE = 1000


def _tenant(valeur: Any) -> str:
    return detecteurs_besoins._tenant(valeur)


def _texte(valeur: Any, maximum: int = 1000) -> str:
    return detecteurs_besoins._texte(valeur, maximum)


def _donnees(ligne: Any) -> dict:
    return detecteurs_besoins._donnees(ligne)


def _liste(valeur: Any) -> list:
    if valeur is None:
        return []
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return list(valeur)
    return [valeur]


def _aplatir(ligne: Mapping) -> dict:
    """Ligne ``objet_entreprise`` (ou dict plat) → dict Hypothesis-compatible."""
    donnees = _donnees(ligne)
    return {
        "id": _texte(ligne.get("id")),
        "tenant_id": _texte(ligne.get("tenant_id")),
        "enonce": _texte(donnees.get("enonce") or ligne.get("enonce")),
        "statut": _texte(donnees.get("statut") or ligne.get("statut")) or "EMISE",
        "rival_ids": [
            _texte(r) for r in _liste(donnees.get("rival_ids") or ligne.get("rival_ids"))
            if _texte(r)],
        "preuve_discriminante": _texte(
            donnees.get("preuve_discriminante") or ligne.get("preuve_discriminante")),
        "need_id": _texte(donnees.get("need_id") or ligne.get("need_id")),
        "situation_id": _texte(
            donnees.get("situation_id") or ligne.get("situation_id")),
        "preuves": _liste(donnees.get("preuves") or ligne.get("preuves")),
    }


# --- Lectures bornées ---


def _lire_hypotheses(conn: Any, tenant: str, ids: Iterable | None) -> list[dict]:
    toutes = entreprise_depot.lister_objets(
        conn, tenant, type_="HYPOTHESIS", limite=_LIMITE_LECTURE)
    if ids is None:
        return toutes
    voulus = {_texte(i) for i in ids if _texte(i)}
    return [ligne for ligne in toutes if _texte(ligne.get("id")) in voulus]


def _lire_besoins(conn: Any, tenant: str) -> list[dict]:
    return entreprise_depot.lister_objets(
        conn, tenant, type_="NEED", limite=_LIMITE_LECTURE)


def _lire_assertions(conn: Any, tenant: str) -> list[dict]:
    return detecteurs_besoins._lire_assertions(conn, tenant)


# --- Contexte : le NEED parent et ses objets de preuve ---


def _besoin_par_id(besoins: Iterable[Mapping]) -> dict[str, dict]:
    return {_texte(ligne.get("id")): ligne for ligne in besoins or ()
            if _texte(ligne.get("id"))}


def _besoin_par_hypothese(besoins: Iterable[Mapping]) -> dict[str, dict]:
    """hyp_id → NEED dont ``donnees.hypothese_ids`` la cite."""
    index: dict[str, dict] = {}
    for ligne in besoins or ():
        for hyp_id in _liste(_donnees(ligne).get("hypothese_ids")):
            identifiant = _texte(hyp_id)
            if identifiant and identifiant not in index:
                index[identifiant] = ligne
    return index


def _couple_assertion(ligne_need: Mapping | None) -> tuple[str, str] | None:
    """Couple ``(subject, predicate)`` porté par un NEED contournement."""
    if not isinstance(ligne_need, Mapping):
        return None
    donnees = _donnees(ligne_need)
    sujet = _texte(donnees.get("sujet_detection"))
    if "|" in sujet:
        premiere, seconde = sujet.split("|", 1)
        if _texte(premiere) and _texte(seconde):
            return _texte(premiere), _texte(seconde)
    for preuve in _liste(donnees.get("preuves")):
        if isinstance(preuve, Mapping) and preuve.get("subject") and preuve.get("predicate"):
            return _texte(preuve.get("subject")), _texte(preuve.get("predicate"))
    return None


def _objets_preuve(
    ligne_need: Mapping | None, assertions: Iterable[Mapping],
) -> list[dict]:
    """Objets de preuve candidats : assertions du couple + preuves du NEED."""
    objets: list[dict] = []
    couple = _couple_assertion(ligne_need)
    for assertion in assertions or ():
        if not isinstance(assertion, Mapping):
            continue
        if couple is not None and (
                _texte(assertion.get("subject")) != couple[0]
                or _texte(assertion.get("predicate")) != couple[1]):
            continue
        objets.append({
            "source": "interface_assertion",
            "sujet": _texte(assertion.get("subject")),
            "predicat": _texte(assertion.get("predicate")),
            "objet": _texte(assertion.get("object")),
            "mode": _texte(assertion.get("mode")),
        })
    if isinstance(ligne_need, Mapping):
        for preuve in _liste(_donnees(ligne_need).get("preuves")):
            if isinstance(preuve, Mapping):
                objets.append({"source": "need", **dict(preuve)})
    return objets


def _texte_preuve(objet: Mapping) -> str:
    return " ".join(
        _texte(valeur) for valeur in dict(objet).values()
        if not isinstance(valeur, Mapping))


def _tokens(valeur: Any) -> set[str]:
    return abduction._tokens(valeur)


# --- API ---


def preuves_discriminantes(
    conn: Any, tenant_id: Any, hypothese_ids: Iterable | None = None, *,
    hypotheses: Iterable[Mapping] | None = None,
    besoins: Iterable[Mapping] | None = None,
    assertions: Iterable[Mapping] | None = None,
) -> dict:
    """Pour chaque hypothèse, les preuves/objets qui l'appuient contre ses rivales.

    Chaque objet de preuve (assertion du couple ou preuve du NEED) est confronté
    au **vocabulaire signature** de chaque rivale : les mots porteurs de son
    ``enonce + preuve_discriminante`` qu'aucune autre rivale n'utilise. Un objet
    qui cite le vocabulaire propre à une seule rivale — et elle seule au
    maximum — l'appuie (``appuie``) ; un objet partagé par toutes (le fait
    déclencheur du contournement, typiquement) n'est pas discriminant et rejoint
    ``partagees`` avec le recouvrement complet de chaque rivale, en transparence.

    Rend ``{tenant, hypotheses: {id: {…, appuie, signature}}, partagees, preuves}``.
    """
    tenant = _tenant(tenant_id)
    if hypotheses is not None:
        lignes = [_aplatir(ligne) for ligne in hypotheses]
    else:
        lignes = [_aplatir(ligne) for ligne in
                  _lire_hypotheses(conn, tenant, hypothese_ids)]
    if besoins is not None:
        lot_besoins = list(besoins)
    else:
        lot_besoins = _lire_besoins(conn, tenant)
    par_id, par_hyp = _besoin_par_id(lot_besoins), _besoin_par_hypothese(lot_besoins)
    lot_assertions = (
        list(assertions) if assertions is not None
        else _lire_assertions(conn, tenant))

    par_need: dict[str, list[dict]] = {}
    resultat: dict[str, dict] = {}
    toutes_preuves: list[dict] = []
    vues: set[int] = set()
    for ligne in lignes:
        hyp_id = ligne["id"]
        need = par_id.get(ligne["need_id"]) or par_hyp.get(hyp_id)
        cle_need = _texte((need or {}).get("id")) or "_sans_need"
        if cle_need not in par_need:
            par_need[cle_need] = _objets_preuve(need, lot_assertions)
        marques = _tokens(ligne["enonce"]) | _tokens(ligne["preuve_discriminante"])
        resultat[hyp_id] = {**ligne, "_marques": marques, "_objets": par_need[cle_need]}
        for objet in par_need[cle_need]:
            if id(objet) not in vues:
                vues.add(id(objet))
                toutes_preuves.append(objet)

    # Vocabulaire signature : les mots qu'une seule rivale porte.
    union_rivales: dict[str, set[str]] = {}
    for hyp_id, entree in resultat.items():
        union_rivales[hyp_id] = set().union(
            *(autre["_marques"] for autre_id, autre in resultat.items()
              if autre_id != hyp_id)) if len(resultat) > 1 else set()
        entree["signature"] = sorted(entree["_marques"] - union_rivales[hyp_id])

    partagees: list[dict] = []
    for hyp_id, entree in resultat.items():
        signature = set(entree["signature"])
        appuie: list[dict] = []
        for objet in entree["_objets"]:
            mots = _tokens(_texte_preuve(objet))
            propre = len(mots & signature)
            scores = {
                autre_id: len(mots & autre["_marques"])
                for autre_id, autre in resultat.items()}
            # Vainqueur unique sur le vocabulaire signature : la rivale est
            # réellement départagée ; sinon l'objet est mutualisé.
            meilleurs = [
                autre_id for autre_id, autre in resultat.items()
                if autre_id != hyp_id and len(
                    mots & set(autre["signature"])) >= propre]
            if propre > 0 and not meilleurs:
                appuie.append({"objet": objet, "score": propre})
            elif any(s > 0 for s in scores.values()):
                partagees.append({"objet": objet, "scores": scores})
        entree["appuie"] = appuie

    # Dédup des partagées : un même objet vu par plusieurs rivales n'apparaît
    # qu'une fois, avec les recouvrements de chacune.
    uniques: dict[int, dict] = {}
    for marque in partagees:
        uniques[id(marque["objet"])] = marque
    for entree in resultat.values():
        entree.pop("_marques", None)
        entree.pop("_objets", None)
    return {
        "tenant": tenant,
        "hypotheses": resultat,
        "partagees": list(uniques.values()),
        "preuves": toutes_preuves,
    }


def suggestions(
    conn: Any, tenant_id: Any, need_id: Any, *,
    need: Mapping | None = None,
    hypotheses: Iterable[Mapping] | None = None,
) -> dict | None:
    """Question à valeur maximale pour un NEED, depuis ses hypothèses rivales.

    ``need`` et ``hypotheses`` remplacent la lecture en base (mode READ) : le
    NEED est lu via ``entreprise_depot.lire_objet``, ses rivales via
    ``donnees.hypothese_ids`` — le fil d'attention pourra ensuite appeler cette
    fonction à la passe, sans requête supplémentaire à câbler. Rend ``None`` si
    le NEED est introuvable, un dict à ``question`` vide si aucune rivale n'a de
    preuve discriminante.
    """
    tenant = _tenant(tenant_id)
    ligne = dict(need) if need is not None else entreprise_depot.lire_objet(
        conn, tenant, _texte(need_id))
    if ligne is None:
        return None
    donnees = _donnees(ligne)
    ids = [
        _texte(i) for i in _liste(
            donnees.get("hypothese_ids") or ligne.get("hypothese_ids"))
        if _texte(i)]
    if hypotheses is not None:
        pool = [_aplatir(l) for l in hypotheses]
    elif ids:
        pool = [_aplatir(l) for l in _lire_hypotheses(conn, tenant, ids)]
    else:
        pool = [_aplatir(l) for l in _lire_hypotheses(conn, tenant, None)]
    if ids:
        liees = [h for h in pool if h["id"] in set(ids)]
    else:
        # Repli : les rivales qui nomment ce NEED via leur ``need_id`` — jamais
        # toutes les hypothèses du tenant, un NEED sans lien n'en hérite pas.
        propre = _texte(ligne.get("id"))
        liees = [h for h in pool if propre and h["need_id"] == propre]
    vivantes = [h for h in liees if h["statut"] != "REFUTEE"] or liees
    verdict = abduction.question_maximale(vivantes)
    return {
        "need_id": _texte(ligne.get("id")),
        "signature": _texte(donnees.get("signature")),
        "statut": _texte(donnees.get("statut")),
        "question": verdict["question"],
        "question_socratique": abduction.ou_question(vivantes),
        "couvre": verdict["couvre"],
        "preuve": verdict["preuve"],
        "rivales": [h["id"] for h in vivantes],
        "statuts": {h["id"]: h["statut"] for h in vivantes},
    }
