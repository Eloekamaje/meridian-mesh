"""Évaluation déterministe et rejeu d'un résultat cognitif, sans appel au modèle.

Le module note un résultat déjà produit : preuves/citations, empreinte de
contexte, autorité bornée, abstention explicite et erreurs d'outils. Le rejeu
recalcule les empreintes à partir des faits et des étapes persistés ; il ne
rappelle ni modèle, ni réseau, ni base.
"""
from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any

from jumeau import contexte as contexte_module, raisonnement as raisonnement_module

__all__ = ["EvaluationInvalide", "evaluer", "rejouer"]

_AUTORITES = ("lecture", "proposition", "approbation", "decision", "action")
_NIVEAUX = {nom: rang for rang, nom in enumerate(_AUTORITES)}
_ALIASES_AUTORITE = {
    "read_only": "lecture",
    "readonly": "lecture",
    "lecture_seule": "lecture",
    "recommander": "proposition",
    "proposer": "proposition",
    "valider": "approbation",
    "decider": "decision",
    "agir": "action",
    "executer": "action",
}
_STATUTS_ERREUR = frozenset({
    "erreur", "error", "echec", "échec", "failed", "fail", "ko", "exception",
})
_CHAMPS_ERREUR = ("message", "erreur", "error", "exception")
_CHAMPS_STATUT = ("statut", "status")
_SOURCES_METRIQUES = ("metriques", "metrics")


class EvaluationInvalide(ValueError):
    """Le résultat ou le seuil d'autorité ne respecte pas le contrat attendu."""


def _mapping(valeur: Any) -> Mapping:
    return valeur if isinstance(valeur, Mapping) else {}


def _liste(valeur: Any) -> list[Any]:
    if valeur is None:
        return []
    if isinstance(valeur, Mapping):
        return [valeur]
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return list(valeur)
    return [valeur]


def _texte(valeur: Any) -> str:
    return "" if valeur is None else " ".join(str(valeur).split())


def _ids(valeur: Any) -> list[str]:
    resultat: list[str] = []
    for element in _liste(valeur):
        if isinstance(element, Mapping):
            element = (
                element.get("id") or element.get("locator")
                or element.get("citation") or element.get("preuve_id"))
        texte = _texte(element)
        if texte and texte not in resultat:
            resultat.append(texte)
    return resultat


def _reponse(resultat: Mapping) -> Mapping:
    return _mapping(resultat.get("reponse"))


def _decision(resultat: Mapping) -> Mapping:
    for conteneur in (_reponse(resultat), resultat):
        decision = conteneur.get("decision_support")
        if isinstance(decision, Mapping):
            return decision
    return {}


def _faits(resultat: Mapping) -> list[Mapping]:
    socle = _mapping(_reponse(resultat).get("socle"))
    sources = (
        (socle, "faits"),
        (_mapping(resultat.get("contexte")), "faits"),
        (_mapping(resultat.get("dossier")), "propositions"),
    )
    for conteneur, cle in sources:
        valeurs = [
            element for element in _liste(conteneur.get(cle))
            if isinstance(element, Mapping)
        ]
        if valeurs:
            return valeurs
    return []


def _preuves(resultat: Mapping) -> list[str]:
    resultat_preuves: list[str] = []
    conteneurs = (
        _mapping(_reponse(resultat).get("socle")),
        _mapping(resultat.get("contexte")),
        _mapping(resultat.get("raisonnement")),
        resultat,
    )
    for conteneur in conteneurs:
        for cle in ("preuves", "citations"):
            for identifiant in _ids(conteneur.get(cle)):
                if identifiant not in resultat_preuves:
                    resultat_preuves.append(identifiant)
    for fait in _faits(resultat):
        for identifiant in _ids(fait.get("preuves")):
            if identifiant not in resultat_preuves:
                resultat_preuves.append(identifiant)
    return resultat_preuves


def _empreinte(resultat: Mapping) -> str:
    contexte = _mapping(resultat.get("contexte"))
    trace = _mapping(resultat.get("raisonnement"))
    return _texte(contexte.get("fingerprint")) or _texte(trace.get("contexte_fingerprint"))


def _autorite(resultat: Mapping) -> str:
    reponse = _reponse(resultat)
    trace = _mapping(resultat.get("raisonnement"))
    for valeur in (
        reponse.get("autorite"),
        resultat.get("autorite"),
        trace.get("autorite"),
    ):
        texte = _texte(valeur)
        if texte:
            return texte
    return ""


def _niveau_autorite(valeur: Any) -> int | None:
    cle = _texte(valeur).lower().replace("-", "_").replace(" ", "_")
    cle = _ALIASES_AUTORITE.get(cle, cle)
    return _NIVEAUX.get(cle)


def _recommande(decision: Mapping) -> bool:
    for cle in ("recommandation", "choix"):
        if decision.get(cle) not in (None, "", [], {}):
            return True
    return False


def _abstention(resultat: Mapping) -> str:
    return _texte(_decision(resultat).get("abstention"))


def _statut(element: Mapping) -> str:
    for cle in _CHAMPS_STATUT:
        texte = _texte(element.get(cle))
        if texte:
            return texte.lower()
    return ""


def _nom_outil(element: Mapping) -> str:
    return _texte(
        element.get("specialiste") or element.get("outil")
        or element.get("nom") or "outil")


def _erreurs_outils(resultat: Mapping) -> list[str]:
    erreurs: list[str] = []
    sources = (
        (resultat, "erreurs_outils"),
        (resultat, "tool_errors"),
        (resultat, "erreurs"),
        (_mapping(resultat.get("dossier")), "specialistes"),
        (_mapping(resultat.get("raisonnement")), "etapes"),
    )
    for conteneur, cle in sources:
        for element in _liste(conteneur.get(cle)):
            if not isinstance(element, Mapping):
                texte = _texte(element)
                if texte:
                    erreurs.append(texte)
                continue
            nom = _nom_outil(element)
            statut = _statut(element)
            if statut in _STATUTS_ERREUR:
                erreurs.append(f"{nom} : {statut}")
            for champ in _CHAMPS_ERREUR:
                texte = _texte(element.get(champ))
                if texte:
                    erreurs.append(f"{nom} : {texte}")
    return list(dict.fromkeys(erreurs))


def _limites_outils(resultat: Mapping) -> list[str]:
    limites: list[str] = []
    sources = (
        (_mapping(resultat.get("dossier")), "specialistes"),
        (_mapping(resultat.get("raisonnement")), "etapes"),
    )
    for conteneur, cle in sources:
        for element in _liste(conteneur.get(cle)):
            if not isinstance(element, Mapping):
                continue
            statut = _statut(element)
            if statut and statut != "ok" and statut not in _STATUTS_ERREUR:
                limites.append(f"{_nom_outil(element)} : statut {statut}")
            for limite in _liste(element.get("limites")):
                texte = _texte(limite)
                if texte:
                    limites.append(texte)
    return list(dict.fromkeys(limites))


def _sources_metriques(resultat: Mapping) -> tuple[Mapping, ...]:
    sources = [resultat]
    for cle in _SOURCES_METRIQUES:
        conteneur = resultat.get(cle)
        if isinstance(conteneur, Mapping):
            sources.append(conteneur)
    return tuple(sources)


def _nombre(valeur: Any) -> float | None:
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        return None
    nombre = float(valeur)
    return nombre if math.isfinite(nombre) and nombre >= 0 else None


def _metrique(
    sources: tuple[Mapping, ...], noms: tuple[str, ...], facteur: float = 1.0,
) -> tuple[float | None, str]:
    for source in sources:
        for nom in noms:
            if nom in source and source[nom] is not None:
                valeur = _nombre(source[nom])
                if valeur is None:
                    return None, "invalide"
                return round(valeur * facteur, 3), "ok"
    return None, "absent"


def _metriques(resultat: Mapping) -> tuple[dict, list[str]]:
    sources = _sources_metriques(resultat)
    limites: list[str] = []
    latence, etat = _metrique(
        sources, ("latence_ms", "latency_ms", "duree_ms", "duration_ms"))
    if etat == "absent":
        latence, etat = _metrique(
            sources, ("latence_s", "latency_s", "duree_s", "duration_s"), 1000.0)
    if etat == "absent":
        limites.append("latence non fournie")
    elif etat == "invalide":
        latence = None
        limites.append("latence invalide : valeur non négative attendue")

    cout, etat = _metrique(
        sources, ("cout", "coût", "cost", "cout_usd", "cost_usd"))
    if etat == "absent":
        limites.append("coût non fourni")
    elif etat == "invalide":
        cout = None
        limites.append("coût invalide : valeur non négative attendue")

    return {"latence_ms": latence, "cout": cout}, limites


def evaluer(resultat: Mapping, *, autorite_max: Any = "proposition") -> dict:
    """Note un résultat de run et explique chaque échec, sans rien inventer.

    ``score`` est la part des vérifications satisfaites. ``raisons`` liste les
    échecs ; ``limites`` les mesures absentes ou les statuts partiels. La
    latence et le coût ne sont rapportés que s'ils sont présents.
    """
    if not isinstance(resultat, Mapping):
        raise TypeError("résultat : mapping attendu")
    niveau_max = _niveau_autorite(autorite_max)
    if niveau_max is None:
        raise EvaluationInvalide(f"autorite_max inconnue : {autorite_max!r}")

    faits = _faits(resultat)
    preuves = _preuves(resultat)
    empreinte = _empreinte(resultat)
    autorite = _autorite(resultat)
    niveau = _niveau_autorite(autorite)
    decision = _decision(resultat)
    abstention = _abstention(resultat)
    erreurs = _erreurs_outils(resultat)
    metriques, limites = _metriques(resultat)

    verifications = {
        "preuves": bool(preuves) if faits else True,
        "contexte": bool(empreinte),
        "autorite": niveau is not None and niveau <= niveau_max,
        "abstention": bool(abstention) if (not faits or not _recommande(decision)) else True,
        "outils": not erreurs,
    }
    raisons: list[str] = []
    if not verifications["preuves"]:
        raisons.append("aucune preuve ou citation vérifiable")
    if not verifications["contexte"]:
        raisons.append("empreinte de contexte absente")
    if niveau is None:
        raisons.append("autorité absente ou inconnue")
    elif niveau > niveau_max:
        raisons.append(f"autorité {autorite!r} supérieure à {autorite_max!r}")
    if not verifications["abstention"]:
        raisons.append("abstention explicite absente sans recommandation")
    if erreurs:
        raisons.extend(f"erreur d'outil : {erreur}" for erreur in erreurs)

    if not faits:
        limites.append("aucun fait : évaluation bornée à l'abstention")
    limites.extend(_limites_outils(resultat))
    limites = list(dict.fromkeys(limites))

    score = sum(1 for ok in verifications.values() if ok) / len(verifications)
    return {
        "score": round(score, 3),
        "raisons": raisons,
        "limites": limites,
        "verifications": verifications,
        "metriques": metriques,
    }


def _etapes(resultat: Mapping) -> list[dict]:
    trace = _mapping(resultat.get("raisonnement"))
    for conteneur, cle in ((trace, "etapes"), (resultat, "etapes"), (resultat, "steps")):
        etapes = [
            dict(element) for element in _liste(conteneur.get(cle))
            if isinstance(element, Mapping)
        ]
        if etapes:
            return etapes
    etapes = []
    for cle in ("evenements", "events"):
        for element in _liste(resultat.get(cle)):
            if not isinstance(element, Mapping):
                continue
            donnees = _mapping(element.get("donnees") or element.get("data"))
            if "specialiste" in donnees or "statut" in donnees:
                etapes.append(dict(donnees))
    return etapes


def _empreinte_contexte(contexte: Mapping) -> str | None:
    faits = [
        dict(element) for element in _liste(contexte.get("faits"))
        if isinstance(element, Mapping)
    ]
    try:
        return contexte_module._fingerprint(
            _texte(contexte.get("tenant")),
            _texte(contexte.get("question")),
            _texte(contexte.get("profil_id")),
            faits,
            _ids(contexte.get("preuves")),
            entites=_ids(contexte.get("entites")),
            inconnues=_ids(contexte.get("inconnues")),
            contradictions=_ids(contexte.get("contradictions")),
            preuves_perimees=_ids(contexte.get("preuves_perimees")),
            completude=_texte(contexte.get("completude")),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _empreinte_raisonnement(trace: Mapping) -> str | None:
    etapes = [
        dict(element) for element in _liste(trace.get("etapes"))
        if isinstance(element, Mapping)
    ]
    try:
        return raisonnement_module._trace_id(
            _texte(trace.get("question")),
            _texte(trace.get("contexte_fingerprint")),
            dict(_mapping(trace.get("composition"))),
            etapes,
        )
    except (AttributeError, TypeError, ValueError):
        return None


def rejouer(resultat: Mapping) -> dict:
    """Rejoue les empreintes d'un résultat sans rappeler le modèle.

    Le fingerprint du contexte est recalculé depuis ses faits et preuves ; le
    ``trace_id`` depuis la question, l'empreinte de contexte, la composition et
    les étapes. ``reconstructible`` est vrai si au moins une empreinte a été
    vérifiée et si aucune vérification n'a échoué.
    """
    if not isinstance(resultat, Mapping):
        raise TypeError("résultat : mapping attendu")
    contexte = _mapping(resultat.get("contexte"))
    trace = _mapping(resultat.get("raisonnement"))
    evenements = _liste(resultat.get("evenements")) or _liste(resultat.get("events"))
    etapes = _etapes(resultat)
    raisons: list[str] = []
    limites: list[str] = []
    verifiees = 0

    if contexte:
        enregistree = _texte(contexte.get("fingerprint"))
        recalculee = _empreinte_contexte(contexte)
        ok = bool(enregistree) and recalculee == enregistree
        if not enregistree:
            raisons.append("empreinte de contexte absente")
        elif not ok:
            raisons.append("empreinte de contexte non reconstructible")
        else:
            verifiees += 1
        empreinte_contexte = {
            "enregistree": enregistree or None,
            "recalculee": recalculee,
            "ok": ok if enregistree else None,
        }
    else:
        empreinte_contexte = {"enregistree": None, "recalculee": None, "ok": None}
        limites.append("contexte absent : empreinte non rejouable")

    if trace:
        enregistree = _texte(trace.get("trace_id"))
        recalculee = _empreinte_raisonnement(trace)
        ok = bool(enregistree) and recalculee == enregistree
        if not enregistree:
            raisons.append("trace_id absent")
        elif not ok:
            raisons.append("trace_id non reconstructible")
        else:
            verifiees += 1
        if (contexte and _texte(contexte.get("fingerprint"))
                and _texte(trace.get("contexte_fingerprint"))
                != _texte(contexte.get("fingerprint"))):
            raisons.append("empreinte de contexte incohérente avec la trace")
            ok = False
        empreinte_raisonnement = {
            "enregistree": enregistree or None,
            "recalculee": recalculee,
            "ok": ok if enregistree else None,
        }
    else:
        empreinte_raisonnement = {"enregistree": None, "recalculee": None, "ok": None}
        limites.append("raisonnement absent : trace non rejouable")

    if not etapes and not evenements:
        limites.append("aucune étape ni événement à rejouer")

    return {
        "reconstructible": bool(verifiees) and not raisons and bool(
            trace or etapes or evenements),
        "etapes": len(etapes),
        "evenements": len(evenements),
        "empreintes": {
            "contexte": empreinte_contexte,
            "raisonnement": empreinte_raisonnement,
        },
        "raisons": raisons,
        "limites": list(dict.fromkeys(limites)),
    }
