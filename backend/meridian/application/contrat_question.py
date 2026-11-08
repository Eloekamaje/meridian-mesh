"""Contrat de preuve de la question (plan Cognition IA, B9).

Remplace la qualification par mots-clés français à l'endroit où elle était muette :
plutôt que de deviner une classe d'intention dans les mots de la phrase, le contrat
demande **quel artefact trancherait la question** et le calcule depuis la sonde B8
(``sonde_evidence.sonder``) — ses ``indices``, ses ``manque`` et son ``verdict``,
jamais depuis le lexique de la phrase. Une question en anglais, fautée ou hors
lexique produit donc le même contrat qu'en français correct.

Le contrat rendu est un dict pur :

- ``artefacts_requis`` : ``[{type, sujet, role}]`` — le type d'artefact qui
  trancherait (``claim``, ``proof``, ``twin``, ``document``, ``mesure``), le sujet
  qu'il doit couvrir et le rôle qu'il jouerait ;
- ``manque`` : les manques rapportés par la sonde, propagés tels quels ;
- ``effort`` : ``leger`` | ``standard`` | ``approfondi``, proportionnel à
  l'incertitude (``trivial`` → ``leger``, ``clair`` → ``standard``, le reste →
  ``approfondi``) ;
- ``formulation`` : une phrase qui énonce le contrat — elle sert d'objectif de
  cadrage quand l'appelant n'en impose pas un ;
- ``verdict`` : le verdict de la sonde qui a produit le contrat (``""`` sans sonde).

Sans sonde, ``contrat_pour`` rend un contrat minimal et honnête : une preuve
couvrant la question elle-même, à effort ``standard``. Ce module est pur : pas
d'adapter, pas de base, pas de réseau — il ne lève jamais.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from meridian.application.sonde_evidence import CLAIR, INCERTAIN, TRIVIAL

__all__ = [
    "APPROFONDI", "EFFORTS", "FACTEURS_EFFORT", "LEGER", "MAX_ARTEFACTS",
    "STANDARD", "TYPES_ARTEFACT", "contrat_pour",
]

LEGER, STANDARD, APPROFONDI = "leger", "standard", "approfondi"
EFFORTS = (LEGER, STANDARD, APPROFONDI)
# Facteur appliqué au budget du tour selon l'effort du contrat (D9 — source
# unique partagée par le noyau et le pipeline unifié) : l'incertitude coûte plus
# cher que la confirmation, jamais l'inverse.
FACTEURS_EFFORT = {LEGER: 0.5, STANDARD: 1.0, APPROFONDI: 2.0}
TYPES_ARTEFACT = ("claim", "proof", "twin", "document", "mesure")

MAX_ARTEFACTS = 6     # borne du contrat : au-delà, le cadrage devient illisible
_SEUIL_RIVAL = 0.8    # même seuil que la sonde : deux sujets à moins de 20 % de score


def _texte(valeur: Any, maximum: int = 500) -> str:
    return " ".join(str(valeur or "").split())[:maximum]


def _mappings(valeur: Any) -> list[dict]:
    if valeur is None:
        return []
    try:
        return [dict(v) for v in valeur if isinstance(v, Mapping)]
    except TypeError:
        return []


def _sujet(preuve: Mapping) -> str:
    """L'entité qu'un indice de la sonde désigne, pour en faire un sujet d'artefact."""
    for cle in ("sujet", "jumeau_id", "twin_id", "titre", "objet", "locator", "id"):
        valeur = _texte(preuve.get(cle), 160)
        if valeur:
            return valeur
    return ""


def _type(preuve: Mapping) -> str:
    """Le type d'artefact qu'un indice représente déjà, déduit de sa forme."""
    if preuve.get("jumeau_id") or preuve.get("twin_id"):
        return "twin"
    if preuve.get("claim_id") or preuve.get("predicat"):
        return "claim"
    if preuve.get("locator") or preuve.get("source_id"):
        return "document"
    return "proof"


def _score(preuve: Mapping) -> float | None:
    try:
        return float(preuve.get("score"))
    except (TypeError, ValueError):
        return None


def _artefact(type_: str, sujet: str, role: str) -> dict:
    return {
        "type": _texte(type_, 20) if _texte(type_, 20) in TYPES_ARTEFACT else "proof",
        "sujet": _texte(sujet, 240),
        "role": _texte(role, 240),
    }


def _dedup(artefacts: list[dict]) -> list[dict]:
    vus = set()
    resultat = []
    for artefact in artefacts:
        cle = (artefact["type"], artefact["sujet"].lower())
        if cle not in vus and artefact["sujet"]:
            vus.add(cle)
            resultat.append(artefact)
    return resultat[:MAX_ARTEFACTS]


def _identifiants(indices: list[dict]) -> list[str]:
    """Les identifiants directs que la question cite, rapportés par la sonde."""
    trouves: list[str] = []
    for indice in indices:
        if indice.get("source") != "question":
            continue
        for identifiant in indice.get("identifiants") or ():
            texte = _texte(identifiant, 160)
            if texte and texte not in trouves:
                trouves.append(texte)
    return trouves


def _rivales(preuves: list[dict]) -> tuple[str, ...]:
    """Les deux interprétations à scores proches, si la sonde n'a pas tranché."""
    notes = sorted(
        (
            (score, sujet)
            for score, sujet in ((_score(p), _sujet(p)) for p in preuves)
            if score is not None and sujet
        ),
        reverse=True,
    )
    if len(notes) < 2:
        return ()
    (meilleur, premier), (second, rival) = notes[0], notes[1]
    if premier != rival and meilleur > 0 and second >= _SEUIL_RIVAL * meilleur:
        return (premier, rival)
    return ()


def _formulation(question: str, artefacts: list[dict], verdict: str, effort: str) -> str:
    source = f"verdict {verdict}" if verdict else "sonde absente"
    if artefacts:
        requis = "; ".join(
            f"{a['type']} «{a['sujet']}» — {a['role']}" for a in artefacts)
        return _texte(
            f"Trancher «{question}» exige : {requis} ({source}, effort {effort}).", 1000)
    return _texte(
        f"Trancher «{question}» exige une preuve qui la couvre "
        f"({source}, effort {effort}).", 1000)


def contrat_pour(question: Any, sonde: Mapping | None = None, *,
                 effort: Any = None) -> dict:
    """Le contrat de preuve : ce qui trancherait ``question``, vu depuis la sonde.

    ``sonde`` est le résultat de ``sonde_evidence.sonder`` — ``None`` ou non-mapping
    rend le contrat minimal. ``effort`` demandé (D9) est borné aux profils connus
    et, quand il est honoré, remplace l'effort déduit du verdict : les artefacts
    restent ceux de la sonde, la formulation énonce l'effort effectif. La
    fonction ne lève jamais : un contrat pauvre est un constat, pas une erreur.
    """
    question_texte = _texte(question, 500)
    effort_demande = _texte(effort, 20).lower()
    if not isinstance(sonde, Mapping):
        artefacts = (
            [_artefact("proof", question_texte, "couvre la question")]
            if question_texte else []
        )
        return {
            "artefacts_requis": artefacts,
            "manque": [],
            "effort": effort_demande if effort_demande in EFFORTS else STANDARD,
            "formulation": _formulation(
                question_texte, artefacts, "",
                effort_demande if effort_demande in EFFORTS else STANDARD),
            "verdict": "",
        }

    verdict = _texte(sonde.get("verdict"), 20).lower()
    indices = _mappings(sonde.get("indices"))
    preuves = _mappings(sonde.get("preuves"))
    manque = [
        _texte(m, 500) for m in (sonde.get("manque") or ()) if _texte(m, 500)
    ]
    identifiants = _identifiants(indices)
    artefacts: list[dict] = []

    if verdict == TRIVIAL:
        # L'artefact qui tranche est déjà trouvé : le contrat le nomme, l'effort est léger.
        for preuve in preuves[:3]:
            artefacts.append(_artefact(
                _type(preuve), _sujet(preuve) or question_texte,
                "restitue la réponse sans raisonnement"))
        if not artefacts:
            artefacts.append(_artefact(
                "document", identifiants[0] if identifiants else question_texte,
                "désigné par la question et confirmé par la sonde"))
        effort = LEGER
    elif verdict == CLAIR:
        # Des preuves couvrent le sujet : le contrat liste les artefacts qui confirment.
        for preuve in preuves:
            artefacts.append(_artefact(
                _type(preuve), _sujet(preuve) or question_texte,
                "confirme la réponse"))
        if not artefacts:
            artefacts.append(_artefact(
                "proof", question_texte, "confirme la réponse"))
        effort = STANDARD
    else:
        # Incertain — ou verdict inattendu : chaque manque dit quel artefact trancherait.
        if verdict != INCERTAIN:
            manque = [*manque, f"verdict de sonde inattendu : {verdict or 'absent'}"]
        for identifiant in identifiants:
            artefacts.append(_artefact(
                "document", identifiant, "résout l'identifiant cité"))
        premier, rival = (_rivales(preuves) + ("", ""))[:2]
        if premier and rival:
            artefacts.append(_artefact(
                "mesure", f"{premier} vs {rival}",
                "départage les interprétations rivales"))
        if not preuves or any("aucune preuve" in m for m in manque):
            artefacts.append(_artefact(
                "proof", question_texte, "couvre le sujet de la question"))
        for m in manque:
            if m.endswith("indisponible"):
                artefacts.append(_artefact(
                    "proof", m[: -len(" indisponible")].strip(),
                    "résultat de la sonde à rejouer"))
        if not artefacts:
            artefacts.append(_artefact(
                "proof", question_texte, "tranche la question"))
        effort = APPROFONDI

    artefacts = _dedup(artefacts)
    effort = effort_demande if effort_demande in EFFORTS else effort
    return {
        "artefacts_requis": artefacts,
        "manque": manque,
        "effort": effort,
        "formulation": _formulation(question_texte, artefacts, verdict, effort),
        "verdict": verdict,
    }
