"""Analyse épistémique d'une question : présupposés, besoins, croyances et plan de sources.

Les heuristiques sont volontairement déterministes et conservatrices : elles ne prétendent pas
comprendre toute la langue. Elles rendent explicite ce qu'une question suppose, afin que le noyau
puisse le vérifier ou demander confirmation avant de répondre.
"""
from __future__ import annotations

from collections.abc import Mapping
import re
import unicodedata

from meridian.domain import dossier_raisonnement as dossier_domaine
from meridian.domain import epistemie as domaine

__all__ = [
    "analyser_question",
    "beliefs_depuis_constats",
    "faits_depuis_recherche",
    "planifier_sources",
    "reviser",
]

_MOTS_CAUSE = ("pourquoi", "comment se fait-il", "qu'est-ce qui explique", "d'ou vient")
_MOTS_TEMPS = ("quand", "depuis quand", "a quelle date")
_MOTS_LIEU = ("ou est", "ou se trouve", "ou a")
_TACHE = {
    "diagramme": "concevoir", "diagrame": "concevoir", "diagrammes": "concevoir", "schema": "concevoir",
    "dessine": "concevoir", "dessiner": "concevoir", "maquette": "concevoir",
    "concevoir": "concevoir", "conception": "concevoir",
    "pourquoi": "diagnostiquer", "comment se fait-il": "diagnostiquer",
    "quand": "situer", "depuis quand": "situer", "a quelle date": "situer",
    "combien": "mesurer", "qui": "identifier", "ou est": "situer",
}


def _normaliser(valeur) -> str:
    texte = unicodedata.normalize("NFKD", str(valeur or ""))
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return " ".join(texte.lower().replace("’", "'").replace("'", " ").replace("?", " ").split())


def _texte(valeur, maximum=1000) -> str:
    return " ".join(str(valeur or "").split())[:maximum]


def _clause_presupposee(question: str) -> str:
    normalise = _normaliser(question)
    for marqueur in (*_MOTS_CAUSE, *_MOTS_TEMPS, *_MOTS_LIEU):
        if normalise.startswith(marqueur + " ") or f" {marqueur} " in normalise:
            index = normalise.find(marqueur)
            reste = normalise[index + len(marqueur):].strip()
            reste = re.sub(r"^(est-ce que|est ce que)\s+", "", reste)
            reste = re.sub(r"\b(est|a|fait|peut|doit|va|sera|s agit)-(il|elle|on|ce)\b", r"\1", reste)
            if len(reste.split()) >= 3:
                return _texte(reste, 500)
    return ""


def _statut_presuppose(texte: str, constats=(), contradictions=()) -> tuple[str, tuple[str, ...], tuple[str, ...], float, str]:
    texte_normalise = _normaliser(texte)
    for contradiction in contradictions or ():
        if texte_normalise and texte_normalise in _normaliser(contradiction):
            return "CONTREDIT", (), (), 0.0, "contradiction explicite dans le contexte"
    for constat in constats or ():
        contenu = _normaliser(
            constat.get("texte") if isinstance(constat, Mapping) else getattr(constat, "texte", ""))
        if texte_normalise and (texte_normalise in contenu or contenu in texte_normalise):
            preuves = constat.get("preuves") if isinstance(constat, Mapping) else getattr(constat, "preuves", ())
            twins = ()
            if isinstance(constat, Mapping):
                twin = constat.get("twin_id")
                twins = (twin,) if twin else ()
            return "CONNU", tuple(preuves or ()), twins, 0.8, "constat de contexte"
    return "INCONNU", (), (), 0.0, "aucune preuve dans le contexte"


def analyser_question(question: str, contexte: Mapping | None = None,
                      constats=(), contradictions=()) -> domaine.QuestionFrame:
    """Extrait la tâche et les présupposés matériels d'une question."""
    contexte = dict(contexte or {})
    normalise = _normaliser(question)
    if str(contexte.get("acte") or "").lower() == "meta":
        return domaine.QuestionFrame(
            question=question, tache="expliquer",
            objet=_texte(contexte.get("application_id") or contexte.get("objet"), 240),
            presuppositions=(), inconnues=(), questions_bloquantes=(),
            materialite="faible",
        )
    tache = "repondre"
    for indice, valeur in _TACHE.items():
        if normalise.startswith(indice + " ") or f" {indice} " in normalise:
            tache = valeur
            break
    if any(mot in normalise for mot in _MOTS_CAUSE):
        tache = "diagnostiquer"
    clause = _clause_presupposee(question)
    presuppositions = []
    if clause:
        statut, preuves, twins, confiance, motif = _statut_presuppose(
            clause, constats, contradictions)
        presuppositions.append(domaine.Presupposition(
            texte=clause, statut=statut, materiel=True,
            preuves=preuves, twins=twins, confiance=confiance, motif=motif))
    if contexte.get("presuppositions"):
        for valeur in contexte["presuppositions"]:
            if isinstance(valeur, Mapping):
                presuppositions.append(domaine.Presupposition(**valeur))
    questions = []
    for presupposition in presuppositions:
        if presupposition.bloquant:
            questions.append(f"Confirmez-vous que {presupposition.texte} ?")
    return domaine.QuestionFrame(
        question=question, tache=tache, objet=_texte(contexte.get("application_id") or contexte.get("objet"), 240),
        presuppositions=tuple(presuppositions),
        inconnues=tuple(p.texte for p in presuppositions if p.bloquant),
        questions_bloquantes=tuple(questions),
        materialite="forte" if questions else "faible",
    )


def planifier_sources(question_frame: domaine.QuestionFrame,
                      contexte: Mapping | None = None) -> domaine.SourcePlan:
    contexte = dict(contexte or {})
    twins = tuple(contexte.get("twin_ids") or ())
    sources = tuple(contexte.get("source_ids") or ())
    claims = tuple(contexte.get("claim_ids") or ())
    if question_frame.tache == "concevoir":
        twins = ()
        ordre = ("claims", "sources", "memoire")
    elif question_frame.tache in {"diagnostiquer", "situer", "mesurer"}:
        ordre = ("twins", "claims", "sources", "memoire")
    else:
        ordre = ("claims", "sources", "twins", "memoire")
    return domaine.SourcePlan(
        twins=twins, claims=claims, sources=sources, memoire=("memoire",),
        ordre=ordre,
        budget={"twins": 4 if twins else 0, "claims": 20, "sources": 8, "secondes": 30},
        conditions_arret=("preuve suffisante", "budget épuisé", "contradiction non résolue"),
        justification=(f"tâche={question_frame.tache}",),
    )


def faits_depuis_recherche(resultat) -> list[dict]:
    """Convertit une recherche de claims/contradictions en faits de contexte bornés."""
    if not isinstance(resultat, Mapping):
        return []
    faits = []
    for claim in resultat.get("claims") or ():
        if not isinstance(claim, Mapping):
            continue
        sujet = _texte(claim.get("sujet") or "")
        predicat = _texte(claim.get("predicat") or "CLAIM")
        objet = _texte(claim.get("objet") or "")
        texte = f"{sujet} · {predicat} · {objet}".strip(" ·")
        if not texte:
            continue
        faits.append({
            "id": claim.get("id"), "type": "CLAIM", "titre": texte,
            "resume": texte, "specialiste": "claim", "confiance": 0.7,
            "preuves": [],
            "donnees": {"twin_id": claim.get("jumeau_id"), "claim_id": claim.get("id")},
        })
    for contradiction in resultat.get("contradictions") or ():
        if not isinstance(contradiction, Mapping):
            continue
        texte = _texte(contradiction.get("enonce"))
        if texte:
            faits.append({
                "id": contradiction.get("id"), "type": "CONTRADICTION", "titre": texte,
                "resume": texte, "specialiste": "contradiction", "confiance": 0.4,
                "preuves": [contradiction.get("preuve_a"), contradiction.get("preuve_b")],
                "donnees": {"twin_id": contradiction.get("jumeau_id"), "contradiction": True},
            })
    for preuve in resultat.get("contre") or ():
        if not isinstance(preuve, Mapping):
            continue
        locator = _texte(preuve.get("locator") or preuve.get("preuve_id"))
        if locator:
            faits.append({
                "id": preuve.get("preuve_id"), "type": "PREUVE_CONTRE",
                "titre": f"Preuve contraire : {locator}", "resume": locator,
                "specialiste": "preuve", "confiance": 0.8,
                "preuves": [preuve.get("preuve_id")],
                "donnees": {"claim_id": preuve.get("claim_id"), "contradiction": True},
            })
    return faits


def beliefs_depuis_constats(constats=()) -> tuple[domaine.Belief, ...]:
    resultat = []
    for constat in constats or ():
        if isinstance(constat, Mapping):
            texte = _texte(constat.get("texte") or constat.get("titre"))
            twin = _texte(constat.get("twin_id"))
            preuves = tuple(constat.get("preuves") or ())
            contradictions = tuple(constat.get("contradictions") or ())
            confiance = constat.get("confiance", 0.5)
        else:
            texte = _texte(getattr(constat, "texte", ""))
            twin = _texte(getattr(constat, "twin_id", ""))
            preuves = tuple(getattr(constat, "preuves", ()) or ())
            contradictions = tuple(getattr(constat, "contradictions", ()) or ())
            confiance = getattr(constat, "confiance", 0.5)
        if not texte:
            continue
        statut = "CONTREDIT" if contradictions else ("CONNU" if preuves else "SUPPOSE")
        resultat.append(domaine.Belief(
            sujet=twin or _texte(constat.get("provenance") if isinstance(constat, Mapping) else getattr(constat, "provenance", "")) or "contexte",
            predicat="CONSTAT",
            objet=texte[:240],
            mode="OBSERVED" if preuves else "INFERRED",
            statut=statut, confiance=confiance, preuves=preuves, twins=(twin,) if twin else (),
            conditions_retournement=("preuve contraire", "péremption"),
        ))
    return tuple(resultat)


def reviser(belief: domaine.Belief, *, nouveau_statut: str, motif: str,
            acteur: str = "", preuves_ajoutees=(), preuves_retirees=()) -> domaine.BeliefRevision:
    if nouveau_statut.upper() not in domaine.CROYANCES:
        raise ValueError(f"statut de révision inconnu : {nouveau_statut!r}")
    return domaine.BeliefRevision(
        belief_id=belief.id, ancien_statut=belief.statut, nouveau_statut=nouveau_statut.upper(),
        motif=motif, acteur=acteur,
        preuves_ajoutees=tuple(preuves_ajoutees or ()),
        preuves_retirees=tuple(preuves_retirees or ()),
    )
