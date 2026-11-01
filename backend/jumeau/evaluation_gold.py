"""Jeu d'or outils/Claims/décisions : chargement, validation et notation hors ligne.

Le jeu réutilise :mod:`jumeau.evaluation_outils` pour la partie choix d'outils, puis note
deux composants purs : le statut attendu des Claims et la décision attendue. Aucun modèle,
aucun réseau, aucune base. Un cas n'est exact que si les trois composants sont exacts.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import inspect
import json
from pathlib import Path
import re
from typing import Any
import unicodedata

from jumeau import evaluation_outils as eo

__all__ = [
    "AUTORITES",
    "CHEMIN_JEU",
    "CasGold",
    "ClaimAttendu",
    "DecisionAttendue",
    "JeuGold",
    "charger",
    "evaluer",
    "valider",
]

AUTORITES = ("lecture", "proposition", "approbation", "decision", "action")
STATUTS_CLAIM = ("PROPOSED", "ACCEPTED", "CONTESTED", "INVALIDATED", "SUPERSEDED")
VERDICTS_DECISION = ("AUCUNE", "PROPOSER", "S_ABSTENIR", "REFUSER")
CHEMIN_JEU = (
    Path(__file__).resolve().parents[2]
    / "plugin" / "meridian" / "evals" / "gold" / "outils-claims-decisions.json"
)

_CHAMPS_CAS = {
    "id", "question", "outils_attendus", "outils_interdits", "criteres",
    "claims", "decision", "tags", "poids",
}
_CHAMPS_CLAIM = {"id", "statut", "preuve_requise"}
_CHAMPS_DECISION = {"verdict", "recommandation", "abstention", "autorite_max"}
_ALIASES_VERDICT = {
    "aucun": "AUCUNE", "aucune": "AUCUNE", "none": "AUCUNE", "rien": "AUCUNE",
    "proposer": "PROPOSER", "propose": "PROPOSER", "proposition": "PROPOSER",
    "recommander": "PROPOSER", "recommande": "PROPOSER",
    "s_abstenir": "S_ABSTENIR", "abstention": "S_ABSTENIR", "abstenir": "S_ABSTENIR",
    "abstain": "S_ABSTENIR", "s_abstient": "S_ABSTENIR",
    "refuser": "REFUSER", "refus": "REFUSER", "reject": "REFUSER", "rejeter": "REFUSER",
}
_ALIASES_STATUT = {
    "ACCEPTED": "ACCEPTED", "ACCEPTE": "ACCEPTED",
    "PROPOSED": "PROPOSED", "PROPOSE": "PROPOSED",
    "CONTESTED": "CONTESTED", "CONTESTE": "CONTESTED",
    "INVALIDATED": "INVALIDATED", "INVALIDE": "INVALIDATED",
    "SUPERSEDED": "SUPERSEDED", "REMPLACE": "SUPERSEDED",
}


def _normaliser(valeur: Any) -> str:
    texte = unicodedata.normalize("NFKD", str(valeur or ""))
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", texte.lower()).strip("_")


def _verdict(valeur: Any) -> str:
    cle = _normaliser(valeur)
    if cle not in _ALIASES_VERDICT:
        raise eo.CasInvalide(f"verdict de décision inconnu : {valeur!r}")
    return _ALIASES_VERDICT[cle]


def _statut_claim(valeur: Any) -> str:
    cle = _normaliser(valeur).upper()
    if cle not in _ALIASES_STATUT:
        raise eo.CasInvalide(f"statut de Claim inconnu : {valeur!r}")
    return _ALIASES_STATUT[cle]


def _autorite(valeur: Any, champ: str) -> str:
    cle = _normaliser(valeur)
    if cle not in AUTORITES:
        raise eo.CasInvalide(f"{champ} : autorité inconnue {valeur!r}")
    return cle


def _booleen(valeur: Any, champ: str) -> bool:
    if not isinstance(valeur, bool):
        raise eo.CasInvalide(f"{champ} : booléen attendu")
    return valeur


@dataclass(frozen=True)
class ClaimAttendu:
    """Un Claim attendu : identifiant, statut et exigence de preuve."""

    id: str
    statut: str
    preuve_requise: bool = False

    def __post_init__(self):
        identifiant = eo._texte(self.id, "claim.id", 160)
        statut = _statut_claim(self.statut)
        preuve = _booleen(self.preuve_requise, "claim.preuve_requise")
        if statut == "ACCEPTED" and not preuve:
            raise eo.CasInvalide(
                f"claim {identifiant} : un Claim ACCEPTED exige une preuve SUPPORT")
        object.__setattr__(self, "id", identifiant)
        object.__setattr__(self, "statut", statut)
        object.__setattr__(self, "preuve_requise", preuve)

    def as_dict(self) -> dict:
        return {"id": self.id, "statut": self.statut, "preuve_requise": self.preuve_requise}


@dataclass(frozen=True)
class DecisionAttendue:
    """La décision attendue : verdict, recommandation, abstention et plafond d'autorité."""

    verdict: str = "AUCUNE"
    recommandation: bool = False
    abstention: bool = False
    autorite_max: str = "lecture"

    def __post_init__(self):
        verdict = _verdict(self.verdict)
        recommandation = _booleen(self.recommandation, "decision.recommandation")
        abstention = _booleen(self.abstention, "decision.abstention")
        autorite_max = _autorite(self.autorite_max, "decision.autorite_max")
        if AUTORITES.index(autorite_max) > AUTORITES.index("proposition"):
            raise eo.CasInvalide(
                "decision.autorite_max : le jeu d'or reste borné à proposition")
        if verdict == "AUCUNE" and (recommandation or abstention):
            raise eo.CasInvalide(
                "decision : aucune décision ne peut recommander ni s'abstenir")
        if verdict == "S_ABSTENIR" and not abstention:
            raise eo.CasInvalide("decision : s_abstenir exige une abstention explicite")
        if verdict == "PROPOSER" and abstention:
            raise eo.CasInvalide("decision : proposer et s'abstenir sont incompatibles")
        object.__setattr__(self, "verdict", verdict)
        object.__setattr__(self, "recommandation", recommandation)
        object.__setattr__(self, "abstention", abstention)
        object.__setattr__(self, "autorite_max", autorite_max)

    def as_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "recommandation": self.recommandation,
            "abstention": self.abstention,
            "autorite_max": self.autorite_max,
        }


@dataclass(frozen=True)
class CasGold:
    """Un cas du jeu d'or : outils, Claims et décision attendus."""

    id: str
    question: str
    outils_attendus: tuple[str, ...]
    outils_interdits: tuple[str, ...] = ()
    criteres: dict = field(default_factory=dict)
    claims: tuple[ClaimAttendu, ...] = ()
    decision: DecisionAttendue = field(default_factory=DecisionAttendue)
    tags: tuple[str, ...] = ()
    poids: float = 1.0

    def __post_init__(self):
        identifiant = eo._texte(self.id, "id", 120)
        question = eo._texte(self.question, "question", 4000)
        attendus = eo._liste_noms(self.outils_attendus, "outils_attendus")
        interdits = eo._liste_noms(self.outils_interdits, "outils_interdits")
        if set(attendus) & set(interdits):
            raise eo.CasInvalide(f"cas {identifiant} : un outil ne peut être attendu et interdit")

        claims: list[ClaimAttendu] = []
        for brut in self.claims or ():
            claim = brut if isinstance(brut, ClaimAttendu) else ClaimAttendu(**dict(brut))
            if any(existant.id == claim.id for existant in claims):
                raise eo.CasInvalide(f"cas {identifiant} : Claim {claim.id} déjà présent")
            claims.append(claim)

        decision = self.decision
        if isinstance(decision, Mapping):
            decision = DecisionAttendue(**dict(decision))
        if not isinstance(decision, DecisionAttendue):
            raise eo.CasInvalide("decision : objet attendu")

        object.__setattr__(self, "id", identifiant)
        object.__setattr__(self, "question", question)
        object.__setattr__(self, "outils_attendus", attendus)
        object.__setattr__(self, "outils_interdits", interdits)
        object.__setattr__(self, "criteres", eo._criteres(self.criteres))
        object.__setattr__(self, "claims", tuple(claims))
        object.__setattr__(self, "decision", decision)
        object.__setattr__(self, "tags", eo._tags(self.tags))
        object.__setattr__(self, "poids", eo._poids(self.poids))

    def as_outils(self) -> eo.CasOr:
        """Vue compatible avec l'évaluateur d'outils existant."""
        return eo.CasOr(
            id=self.id,
            question=self.question,
            outils_attendus=self.outils_attendus,
            outils_interdits=self.outils_interdits,
            criteres=self.criteres,
            poids=self.poids,
            tags=self.tags,
        )

    def attendu(self) -> dict:
        """La sortie de référence qu'un sélectionneur parfait produirait."""
        return {
            "outils": list(self.outils_attendus),
            "texte": "src/app.py#L10-L12" if self.criteres.get("must_cite_preuve") else "",
            "claims": [
                {
                    "id": claim.id,
                    "statut": claim.statut,
                    "preuves": [f"preuve://{claim.id}"] if claim.preuve_requise else [],
                }
                for claim in self.claims
            ],
            "decision": {
                "verdict": self.decision.verdict,
                "recommandation": "Option proposée" if self.decision.recommandation else None,
                "abstention": "Preuve insuffisante" if self.decision.abstention else None,
                "autorite": self.decision.autorite_max,
            },
        }

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "question": self.question,
            "outils_attendus": list(self.outils_attendus),
            "outils_interdits": list(self.outils_interdits),
            "criteres": dict(self.criteres),
            "claims": [claim.as_dict() for claim in self.claims],
            "decision": self.decision.as_dict(),
            "tags": list(self.tags),
            "poids": self.poids,
        }


class JeuGold:
    """Un jeu ordonné de cas, chargeable depuis un JSON borné et sans secret."""

    def __init__(self, seed: Any = None) -> None:
        self.seed = seed
        self._cas: list[CasGold] = []

    @property
    def cas(self) -> list[CasGold]:
        return list(self._cas)

    @property
    def taille(self) -> int:
        return len(self._cas)

    def __len__(self) -> int:
        return len(self._cas)

    def __iter__(self):
        return iter(self._cas)

    def ajouter(self, cas: CasGold | Mapping[str, Any]) -> "JeuGold":
        resultat = cas if isinstance(cas, CasGold) else _cas_depuis_dict(cas)
        if len(self._cas) >= eo.MAX_CAS:
            raise eo.CasInvalide(f"jeu : au plus {eo.MAX_CAS} cas")
        if any(existant.id == resultat.id for existant in self._cas):
            raise eo.CasInvalide(f"cas {resultat.id} : identifiant déjà présent")
        self._cas.append(resultat)
        return self

    def charger_json(self, path_or_text: Any) -> "JeuGold":
        texte = eo._lire_borne(path_or_text)
        donnees = eo._charger_json(texte)
        bruts = eo._liste_brute(donnees)
        if len(self._cas) + len(bruts) > eo.MAX_CAS:
            raise eo.CasInvalide(f"jeu : au plus {eo.MAX_CAS} cas")
        nouveaux: list[CasGold] = []
        vus = {cas.id for cas in self._cas}
        for rang, brut in enumerate(bruts):
            if not isinstance(brut, Mapping):
                raise eo.CasInvalide(f"cas n°{rang} : objet attendu")
            try:
                cas = _cas_depuis_dict(brut)
            except eo.CasInvalide as erreur:
                raise eo.CasInvalide(f"cas n°{rang} : {erreur}") from erreur
            if cas.id in vus:
                raise eo.CasInvalide(f"cas n°{rang} : identifiant déjà présent")
            vus.add(cas.id)
            nouveaux.append(cas)
        self._cas.extend(nouveaux)
        return self


def _cas_depuis_dict(brut: Any) -> CasGold:
    if not isinstance(brut, Mapping):
        raise eo.CasInvalide("cas : objet attendu")
    inconnus = sorted(set(brut) - _CHAMPS_CAS)
    if inconnus:
        raise eo.CasInvalide(f"champ inconnu : {inconnus[0]}")
    for requis in ("id", "question", "outils_attendus"):
        if requis not in brut:
            raise eo.CasInvalide(f"champ {requis} manquant")
    for champ in ("outils_attendus", "outils_interdits", "tags"):
        if champ in brut and not isinstance(brut[champ], (list, tuple)):
            raise eo.CasInvalide(f"champ {champ} : liste attendue")
    for rang, claim in enumerate(brut.get("claims") or ()):
        if not isinstance(claim, Mapping):
            raise eo.CasInvalide(f"claims[{rang}] : objet attendu")
        inconnus = sorted(set(claim) - _CHAMPS_CLAIM)
        if inconnus:
            raise eo.CasInvalide(f"claims[{rang}] : champ inconnu {inconnus[0]}")
    decision = brut.get("decision")
    if decision is not None:
        if not isinstance(decision, Mapping):
            raise eo.CasInvalide("decision : objet attendu")
        inconnus = sorted(set(decision) - _CHAMPS_DECISION)
        if inconnus:
            raise eo.CasInvalide(f"decision : champ inconnu {inconnus[0]}")
    try:
        return CasGold(**dict(brut))
    except TypeError as erreur:
        raise eo.CasInvalide(f"cas : {erreur}") from erreur


def charger(chemin: Any = None) -> JeuGold:
    """Charge le jeu d'or par défaut, depuis un chemin/text JSON ou un objet avec clé ``cas``."""
    if chemin is None:
        return JeuGold(seed=20261031).charger_json(CHEMIN_JEU)
    if isinstance(chemin, Mapping):
        jeu = JeuGold(seed=20261031)
        for brut in eo._liste_brute(chemin):
            jeu.ajouter(brut)
        return jeu
    return JeuGold(seed=20261031).charger_json(chemin)


def _liste_cas(jeu: Any) -> list[CasGold]:
    if isinstance(jeu, CasGold):
        return [jeu]
    if isinstance(jeu, JeuGold):
        return jeu.cas
    if isinstance(jeu, Mapping):
        jeu = eo._liste_brute(jeu)
    if isinstance(jeu, (str, bytes)):
        raise TypeError("jeu : JeuGold ou itérable de cas attendu")
    try:
        elements = list(jeu)
    except TypeError as erreur:
        raise TypeError("jeu : JeuGold ou itérable de cas attendu") from erreur
    resultat: list[CasGold] = []
    for element in elements:
        if isinstance(element, CasGold):
            resultat.append(element)
        elif isinstance(element, Mapping):
            resultat.append(_cas_depuis_dict(element))
        else:
            raise eo.CasInvalide("cas : CasGold ou objet attendu")
    return resultat


def valider(jeu: Any = None) -> dict:
    """Valide le jeu sans exécuter de sélectionneur."""
    try:
        cas_liste = _liste_cas(charger() if jeu is None else jeu)
    except (eo.CasInvalide, TypeError) as erreur:
        return {"valide": False, "cas": 0, "erreurs": [str(erreur)]}
    erreurs: list[str] = []
    vus: set[str] = set()
    for rang, cas in enumerate(cas_liste):
        if cas.id in vus:
            erreurs.append(f"cas n°{rang} : identifiant déjà présent")
        vus.add(cas.id)
    return {"valide": not erreurs, "cas": len(cas_liste), "erreurs": erreurs}


def _texte_candidat(valeur: Any) -> str:
    return eo._assainir(valeur, 4000) if valeur is not None else ""


def _claims_candidat(candidat: Any) -> tuple[dict[str, dict], str]:
    if not isinstance(candidat, Mapping):
        return {}, ""
    valeurs = candidat.get("claims", candidat.get("claim", []))
    if valeurs is None:
        valeurs = []
    if isinstance(valeurs, Mapping):
        valeurs = [valeurs]
    if not isinstance(valeurs, (list, tuple)):
        return {}, "claims : liste attendue"
    resultat: dict[str, dict] = {}
    for rang, brut in enumerate(valeurs):
        if not isinstance(brut, Mapping):
            return {}, f"claims[{rang}] : objet attendu"
        identifiant = _texte_candidat(brut.get("id"))
        if not identifiant:
            return {}, f"claims[{rang}] : id obligatoire"
        if identifiant in resultat:
            return {}, f"claims[{rang}] : id déjà présent"
        try:
            statut = _statut_claim(brut.get("statut"))
        except eo.CasInvalide:
            return {}, f"claims[{rang}] : statut inconnu"
        preuves = brut.get("preuves", brut.get("preuve", []))
        if isinstance(preuves, str):
            preuves = [preuves] if preuves.strip() else []
        elif isinstance(preuves, Mapping):
            preuves = [preuves]
        if not isinstance(preuves, (list, tuple)):
            return {}, f"claims[{rang}] : preuves attendues en liste"
        resultat[identifiant] = {
            "statut": statut,
            "preuves": [preuve for preuve in preuves if preuve not in (None, "", [], {})],
        }
    return resultat, ""


def _noter_claims(cas: CasGold, candidat: Any) -> tuple[float, bool, list[str], bool, bool]:
    attendus = {claim.id: claim for claim in cas.claims}
    choisis, erreur = _claims_candidat(candidat)
    if erreur:
        return 0.0, False, [erreur], bool(choisis), bool(attendus)
    manquants = sorted(set(attendus) - set(choisis))
    extras = sorted(set(choisis) - set(attendus))
    raisons: list[str] = []
    erreurs = 0
    for identifiant in sorted(set(attendus) & set(choisis)):
        attendu = attendus[identifiant]
        choisi = choisis[identifiant]
        if choisi["statut"] != attendu.statut:
            raisons.append(
                f"claim {identifiant} : statut {choisi['statut']} au lieu de {attendu.statut}")
            erreurs += 1
        if attendu.preuve_requise and not choisi["preuves"]:
            raisons.append(f"claim {identifiant} : preuve SUPPORT absente")
            erreurs += 1
    if manquants:
        raisons.append("claims attendus manquants: " + ", ".join(manquants))
    if extras:
        raisons.append("claims en trop: " + ", ".join(extras))
    union = set(attendus) | set(choisis)
    corrects = len(set(attendus) & set(choisis)) - min(erreurs, len(set(attendus) & set(choisis)))
    score = (corrects / len(union)) if union else 1.0
    exact = not manquants and not extras and not erreurs
    if exact:
        score = 1.0
        raisons = ["claims exacts"]
    return (round(max(0.0, min(1.0, score)), 4), exact, raisons,
            bool(extras), bool(manquants))


def _decision_candidat(candidat: Any) -> tuple[dict, str]:
    if not isinstance(candidat, Mapping):
        return {
            "verdict": "AUCUNE",
            "recommandation": False,
            "abstention": False,
            "autorite": "lecture",
        }, ""
    decision = candidat.get("decision", candidat.get("decision_support", {}))
    if decision is None:
        decision = {}
    if not isinstance(decision, Mapping):
        return {}, "decision : objet attendu"
    try:
        verdict = _verdict(decision.get("verdict") or decision.get("statut") or "AUCUNE")
    except eo.CasInvalide:
        return {}, "decision : verdict inconnu"
    recommandation = (
        decision.get("recommandation") or decision.get("recommendation")
        or decision.get("choix"))
    abstention = decision.get("abstention")
    autorite = decision.get("autorite") or decision.get("autorite_max")
    try:
        autorite = _autorite(autorite or "lecture", "decision.autorite")
    except eo.CasInvalide:
        return {}, "decision : autorité inconnue"
    return {
        "verdict": verdict,
        "recommandation": bool(_texte_candidat(recommandation)),
        "abstention": bool(_texte_candidat(abstention)),
        "autorite": autorite,
    }, ""


def _noter_decision(cas: CasGold, candidat: Any) -> tuple[float, bool, list[str]]:
    attendu = cas.decision
    choisi, erreur = _decision_candidat(candidat)
    if erreur:
        return 0.0, False, [erreur]
    verifications = {
        "verdict": choisi["verdict"] == attendu.verdict,
        "recommandation": choisi["recommandation"] == attendu.recommandation,
        "abstention": choisi["abstention"] == attendu.abstention,
        "autorite": AUTORITES.index(choisi["autorite"]) <= AUTORITES.index(attendu.autorite_max),
    }
    raisons: list[str] = []
    if not verifications["verdict"]:
        raisons.append(
            f"décision : verdict {choisi['verdict']} au lieu de {attendu.verdict}")
    if not verifications["recommandation"]:
        raisons.append("décision : recommandation inattendue")
    if not verifications["abstention"]:
        raisons.append("décision : abstention inattendue")
    if not verifications["autorite"]:
        raisons.append(
            f"décision : autorité {choisi['autorite']} supérieure à {attendu.autorite_max}")
    score = sum(1 for ok in verifications.values() if ok) / len(verifications)
    exact = all(verifications.values())
    if exact:
        score = 1.0
        raisons = ["décision exacte"]
    return round(score, 4), exact, raisons


def _appeler_selectionneur(selectionneur: Callable, cas: CasGold) -> tuple[Any, str]:
    try:
        candidat = selectionneur(cas)
        if inspect.isawaitable(candidat):
            candidat = asyncio.run(eo._attendre(candidat))
    except Exception as erreur:  # noqa: BLE001 - un sélectionneur ne bloque pas la notation
        return None, f"sélectionneur en erreur ({type(erreur).__name__})"
    return candidat, ""


def _noter_cas(cas: CasGold, selectionneur: Callable) -> tuple[dict, bool, bool, bool]:
    candidat, erreur = _appeler_selectionneur(selectionneur, cas)
    outils = eo.evaluer(
        cas.as_outils(),
        lambda _: candidat if candidat is not None else [],
    )
    detail_outils = outils["details"][0]
    if erreur:
        detail_outils["ok"] = False
        detail_outils["score"] = 0.0
        detail_outils["raisons"] = [erreur]
    score_claims, ok_claims, raisons_claims, frappe_claims, manque_claims = _noter_claims(
        cas, candidat)
    score_decision, ok_decision, raisons_decision = _noter_decision(cas, candidat)
    score = round(
        detail_outils["score"] * 0.4 + score_claims * 0.3 + score_decision * 0.3, 4)
    ok = bool(detail_outils["ok"] and ok_claims and ok_decision)
    if ok:
        score = 1.0
    raisons = []
    if not detail_outils["ok"]:
        raisons.extend(detail_outils["raisons"])
    if not ok_claims:
        raisons.extend(raisons_claims)
    if not ok_decision:
        raisons.extend(raisons_decision)
    detail = {
        "cas_id": cas.id,
        "ok": ok,
        "score": score,
        "outils": {
            "choisis": list(detail_outils["outils_choisis"]),
            "ok": bool(detail_outils["ok"]),
            "score": detail_outils["score"],
        },
        "claims": {
            "ok": ok_claims,
            "score": score_claims,
        },
        "decision": {
            "ok": ok_decision,
            "score": score_decision,
        },
        "raisons": raisons or ["cas exact"],
    }
    return detail, ok, bool(frappe_claims or not detail_outils["ok"]), bool(
        manque_claims or not detail_outils["ok"])


def evaluer(jeu: Any = None, selectionneur: Callable | None = None) -> dict:
    """Note un sélectionneur sur les trois composants d'un jeu d'or."""
    if selectionneur is None:
        selectionneur = lambda cas: cas.attendu()
    if not callable(selectionneur):
        raise TypeError("selectionneur : appelable attendu")
    cas_liste = _liste_cas(charger() if jeu is None else jeu)
    resultats = []
    faux_positifs = 0
    faux_negatifs = 0
    for cas in cas_liste:
        detail, ok, frappe, manque = _noter_cas(cas, selectionneur)
        resultats.append(detail)
        faux_positifs += int(frappe)
        faux_negatifs += int(manque)
    poids_total = sum(cas.poids for cas in cas_liste)
    passe = sum(1 for resultat in resultats if resultat["ok"])
    pass_rate = (
        round(sum(cas.poids for cas, resultat in zip(cas_liste, resultats) if resultat["ok"])
              / poids_total, 4) if poids_total else 0.0)
    score_moyen = (
        round(sum(cas.poids * resultat["score"]
                  for cas, resultat in zip(cas_liste, resultats)) / poids_total, 4)
        if poids_total else 0.0)
    par_tag: dict[str, dict] = {}
    for tag in sorted({tag for cas in cas_liste for tag in cas.tags}):
        paires = [(cas, resultat) for cas, resultat in zip(cas_liste, resultats)
                  if tag in cas.tags]
        poids_tag = sum(cas.poids for cas, _ in paires)
        passe_tag = sum(1 for _, resultat in paires if resultat["ok"])
        par_tag[tag] = {
            "passe": passe_tag,
            "total": len(paires),
            "pass_rate": (
                round(sum(cas.poids for cas, resultat in paires if resultat["ok"])
                      / poids_tag, 4) if poids_tag else 0.0),
            "score_moyen": (
                round(sum(cas.poids * resultat["score"] for cas, resultat in paires)
                      / poids_tag, 4) if poids_tag else 0.0),
        }
    return {
        "passe": passe,
        "total": len(resultats),
        "pass_rate": pass_rate,
        "score_moyen": score_moyen,
        "par_tag": par_tag,
        "faux_positifs": faux_positifs,
        "faux_negatifs": faux_negatifs,
        "details": resultats,
    }


if __name__ == "__main__":
    print(json.dumps(evaluer(), ensure_ascii=False, indent=2))
