"""Composition de la réponse par lentille de profil, sur un socle de faits invariant.

Le socle (propositions, preuves, incertitudes, limites) est identique quel que soit le profil.
Le profil ne change que la lecture, l'ordre, le vocabulaire, les actions proposées et les prochaines
étapes. Aucun fait n'est créé, retiré ou réécrit par la lentille ; aucune action n'est exécutée.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import math
import re
from typing import Any
import unicodedata

from meridian.application import composition
from meridian.domain import profils

__all__ = ["ReponseCognitive", "Socle", "composer", "sections_pour"]

_SECTIONS = {
    "developpeur": ("impact_technique", "interfaces", "changements", "risques", "tests"),
    "architecte": ("architecture", "interfaces", "adr", "impact", "risques"),
    "product_owner": ("impact_client", "priorite", "benefice", "options", "decision_attendue"),
    "business_analyst": ("besoin", "processus", "exigences", "parties_prenantes", "risques"),
    "analyste_fonctionnel": ("besoin", "processus", "exigences", "ecarts", "risques"),
    "scrum_master": ("facilitation", "obstacles", "retrospective", "options"),
    "chef_projet": ("plan", "raid", "benefices", "risques", "options"),
    "directeur": ("exposition", "benefice", "risque", "options", "arbitrage"),
    "support": ("incident", "sla", "mitigation", "processus", "risques"),
    "risque": ("risques", "controles", "preuves", "conformite", "options"),
    "data_steward": ("donnees", "qualite", "lignage", "risques", "options"),
    "generaliste": ("synthese", "faits", "limites", "questions"),
}

_GROUPES_TYPE = {
    "IMPACT": ("impact_technique", "impact_client", "impact", "exposition"),
    "MODELE": ("architecture", "interfaces", "processus", "plan", "donnees", "lignage", "synthese"),
    "RISQUE": ("risques", "risque", "controles", "conformite", "tests"),
    "PREUVE": ("preuves", "conformite", "tests", "risques"),
    "CONSTAT": ("faits", "synthese", "processus", "qualite", "preuves"),
    "LEARNING": ("benefice", "benefices", "options", "synthese"),
    "OUTCOME": ("benefice", "benefices", "impact_client", "synthese"),
    "QUESTION": ("questions", "decision_attendue", "options"),
    "PROPOSITION": ("options", "changements", "adr", "exigences", "mitigation", "controles"),
    "ACTION": ("options", "mitigation", "plan", "changements"),
    "HYPOTHESE": ("options", "questions", "risques"),
}

_TYPES_OPTION = frozenset({"OPTION", "PROPOSITION", "ACTION", "QUESTION"})
_TYPES_CONDITION = frozenset({"QUESTION", "HYPOTHESE"})
_MOTS_CONDITION = (
    "condition", "reverse", "retournement", "inverse", "renversement")
_SIGNAUX_OUTCOME = frozenset({"OUTCOME", "LEARNING"})
_CHAMPS_BASELINE = (
    "baseline", "baselines", "baseline_valeur", "valeur_baseline",
    "valeur_initiale", "valeur_de_reference", "mesure_initiale")
_CHAMPS_OUTCOME = (
    "outcome", "outcomes", "outcome_ids", "outcome_valeur",
    "valeur_outcome", "valeur_observee", "observe", "resultat",
    "resultats", "resultat_observe", "benefice")

_ACTIONS_PROFIL = {
    "developpeur": ("verifier_interface", "ouvrir_impact", "preparer_changement", "preparer_test"),
    "architecte": ("ouvrir_impact", "preparer_adr", "verifier_interface"),
    "product_owner": ("arbitrer_priorite", "verifier_benefice", "ouvrir_decision"),
    "business_analyst": ("verifier_besoin", "ouvrir_processus", "demander_preuve"),
    "analyste_fonctionnel": ("verifier_exigence", "ouvrir_processus", "demander_specification"),
    "scrum_master": ("faciliter_decision", "lever_obstacle", "ouvrir_retrospective"),
    "chef_projet": ("ouvrir_raid", "verifier_benefice", "ouvrir_plan"),
    "directeur": ("ouvrir_arbitrage", "verifier_benefice", "ouvrir_decision"),
    "support": ("ouvrir_incident", "verifier_sla", "preparer_mitigation", "ouvrir_postmortem"),
    "risque": ("verifier_controle", "demander_preuve", "ouvrir_capa"),
    "data_steward": ("verifier_lignage", "qualifier_donnee", "ouvrir_regle"),
    "generaliste": ("qualifier_profil", "demander_perimetre"),
}

_PROCHAINES = {
    "developpeur": ("Vérifier les interfaces et l'impact technique.", "Préparer le changement et son test."),
    "architecte": ("Vérifier les interfaces et les décisions d'architecture.", "Préparer un ADR."),
    "product_owner": ("Arbitrer la priorité et le bénéfice attendu.", "Ouvrir la décision si nécessaire."),
    "business_analyst": ("Valider le besoin et les parties prenantes.", "Consolider les exigences."),
    "analyste_fonctionnel": ("Valider le processus et les écarts.", "Préciser la spécification."),
    "scrum_master": ("Faciliter la décision et lever les obstacles.", "Préparer la rétrospective."),
    "chef_projet": ("Mettre à jour le RAID et le plan.", "Vérifier les bénéfices."),
    "directeur": ("Comparer les options et arbitrer.", "Suivre l'outcome."),
    "support": ("Ouvrir l'incident, vérifier le SLA et mitiger.", "Préparer le postmortem."),
    "risque": ("Vérifier les preuves et les contrôles.", "Ouvrir une CAPA si l'écart est confirmé."),
    "data_steward": ("Vérifier le lignage et la qualité.", "Désigner le propriétaire des règles."),
    "generaliste": ("Qualifier le profil et le périmètre.", "Reformuler la décision attendue."),
}


def _texte(valeur: Any, maximum=2200) -> str:
    return " ".join(str(valeur or "").split())[:maximum]


def _faits(dossier: Mapping) -> tuple[dict, ...]:
    propositions = dossier.get("propositions") or ()
    resultat = []
    for proposition in propositions:
        if not isinstance(proposition, Mapping):
            continue
        resultat.append(dict(proposition))
    return tuple(resultat)


def _preuves(faits: tuple[dict, ...]) -> tuple[str, ...]:
    preuves = []
    for fait in faits:
        for preuve in fait.get("preuves") or ():
            texte = _texte(preuve, 400)
            if texte and texte not in preuves:
                preuves.append(texte)
    return tuple(preuves)


def _donnees_fait(fait: Mapping) -> Mapping:
    donnees = fait.get("donnees")
    return donnees if isinstance(donnees, Mapping) else {}


def _slug(valeur: str) -> str:
    texte = unicodedata.normalize("NFKD", _texte(valeur, 240))
    texte = texte.encode("ascii", "ignore").decode().lower()
    texte = re.sub(r"[^a-z0-9]+", "-", texte).strip("-")
    return texte[:80].strip("-") or "option"


def _identifiant_option(label: str, vus: set[str]) -> str:
    base = _slug(label)
    identifiant = base
    rang = 2
    while identifiant in vus:
        identifiant = f"{base}-{rang}"
        rang += 1
    vus.add(identifiant)
    return identifiant


def _confiance_fait(fait: Mapping) -> float | None:
    valeur = fait.get("confiance")
    if isinstance(valeur, bool) or valeur is None:
        return None
    try:
        nombre = float(valeur)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(nombre):
        return None
    return round(max(0.0, min(1.0, nombre)), 3)


def _preuves_fait(fait: Mapping) -> list[str]:
    valeurs = fait.get("preuves") or ()
    if isinstance(valeurs, (str, Mapping)):
        valeurs = [valeurs]
    resultat = []
    for preuve in valeurs:
        if isinstance(preuve, Mapping):
            preuve = preuve.get("id") or preuve.get("locator")
        texte = _texte(preuve, 300)
        if texte and texte not in resultat:
            resultat.append(texte)
    return resultat


def _options(faits: tuple[dict, ...]) -> list[dict]:
    options = []
    vus: set[str] = set()
    for fait in faits:
        type_ = _texte(fait.get("type"), 40).upper()
        if type_ not in _TYPES_OPTION:
            continue
        label = _texte(fait.get("titre"), 240)
        if not label:
            continue
        options.append({
            "id": _identifiant_option(label, vus),
            "label": label,
            "type": type_,
            "confiance": _confiance_fait(fait),
            "preuves": _preuves_fait(fait),
        })
        if len(options) >= 4:
            break
    return options


def _texte_explicite(valeur: Any, fait: Mapping) -> str | None:
    if valeur is None or valeur is False:
        return None
    if isinstance(valeur, str):
        return _texte(valeur, 500) or None
    if isinstance(valeur, Mapping):
        for cle in ("label", "titre", "texte", "resume", "id", "option_id"):
            texte = _texte(valeur.get(cle), 500)
            if texte:
                return texte
        return None
    if isinstance(valeur, (list, tuple)):
        for element in valeur:
            texte = _texte_explicite(element, fait)
            if texte:
                return texte
        return None
    if valeur is True:
        return _texte(fait.get("titre") or fait.get("resume"), 500) or None
    return None


def _recommandation(faits: tuple[dict, ...]) -> str | None:
    for fait in faits:
        donnees = _donnees_fait(fait)
        for source in (fait, donnees):
            for cle in ("recommandation", "recommendation",
                        "recommande", "recommended"):
                if cle in source:
                    texte = _texte_explicite(source[cle], fait)
                    if texte:
                        return texte
    return None


def _conditions_retournement(faits: tuple[dict, ...]) -> list[str]:
    conditions = []
    for fait in faits:
        type_ = _texte(fait.get("type"), 40).upper()
        donnees = _donnees_fait(fait)
        textes = [
            _texte(fait.get("titre"), 500),
            _texte(fait.get("resume"), 500),
            " ".join(
                _texte(valeur, 500) for valeur in donnees.values()
                if isinstance(valeur, str)),
        ]
        texte = " ".join(textes).casefold()
        explicites = []
        for source in (fait, donnees):
            for cle in ("conditions_de_retournement",
                        "conditions_retournement",
                        "condition_de_retournement",
                        "condition_retournement", "conditions",
                        "condition"):
                valeur = source.get(cle)
                if isinstance(valeur, str):
                    texte_valeur = _texte(valeur, 500)
                    if texte_valeur:
                        explicites.append(texte_valeur)
                elif isinstance(valeur, (list, tuple)):
                    for element in valeur:
                        if isinstance(element, Mapping):
                            element = (element.get("texte")
                                       or element.get("label")
                                       or element.get("titre"))
                        texte_element = _texte(element, 500)
                        if texte_element:
                            explicites.append(texte_element)
        if (type_ not in _TYPES_CONDITION and not explicites
                and not any(mot in texte for mot in _MOTS_CONDITION)):
            continue
        if explicites:
            valeurs = explicites
        else:
            titre = _texte(fait.get("titre"), 500)
            resume = _texte(fait.get("resume"), 500)
            porteurs = [
                valeur for valeur in (titre, resume)
                if valeur and any(
                    mot in valeur.casefold() for mot in _MOTS_CONDITION)]
            valeurs = porteurs or [titre or resume]
        for valeur in valeurs:
            if valeur and valeur not in conditions:
                conditions.append(valeur)
    return conditions


def _confiance_options(options: list[dict]) -> dict | None:
    valeurs = [
        option["confiance"] for option in options
        if isinstance(option.get("confiance"), (int, float))]
    if not valeurs:
        return None
    return {
        "min": min(valeurs),
        "moyenne": round(sum(valeurs) / len(valeurs), 3),
    }


def _renseigne(valeur: Any) -> bool:
    if valeur is None or valeur is False:
        return False
    if isinstance(valeur, bool):
        return valeur
    if isinstance(valeur, str):
        return bool(_texte(valeur, 200))
    if isinstance(valeur, (int, float)):
        return valeur != 0
    if isinstance(valeur, Mapping):
        return bool(valeur)
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return bool(valeur)
    return True


def _mentionne_signal(texte: str) -> bool:
    texte = texte.casefold()
    if not any(mot in texte for mot in ("baseline", "outcome")):
        return False
    return not any(
        negation in texte
        for negation in ("aucun", "aucune", "sans ", "pas de ", "pas d",
                         "manque", "absent", "absente", "inconnu",
                         "inconnue", "non mesur", "à mesurer"))


def _signaux_decision(
        faits: tuple[dict, ...], dossier: Mapping) -> bool:
    sources = list(faits)
    for source in (dossier, dossier.get("valeur"),
                   dossier.get("valeur_ledger")):
        if isinstance(source, Mapping):
            sources.append(source)
    for source in sources:
        type_ = _texte(source.get("type"), 40).upper()
        if type_ in _SIGNAUX_OUTCOME or type_ == "BASELINE":
            return True
        for conteneur in (source, _donnees_fait(source)):
            for cle in _CHAMPS_BASELINE + _CHAMPS_OUTCOME:
                if _renseigne(conteneur.get(cle)):
                    return True
            for cle in ("outcomes", "benefices_renseignes"):
                valeur = conteneur.get(cle)
                if (isinstance(valeur, (int, float))
                        and not isinstance(valeur, bool) and valeur > 0):
                    return True
        if type_ in _TYPES_CONDITION:
            continue
        texte = " ".join((
            _texte(source.get("titre"), 500),
            _texte(source.get("resume"), 500)))
        if _mentionne_signal(texte):
            return True
    return False


def _decision_support(
        faits: tuple[dict, ...], dossier: Mapping, autorite: str,
        prochaines: tuple[str, ...]) -> dict:
    options = _options(faits)
    raisons = []
    if not faits:
        raisons.append("aucun fait vérifié : décision impossible")
    if autorite == "lecture":
        raisons.append("autorité de lecture : aucune décision recommandée")
    if not _signaux_decision(faits, dossier):
        raisons.append(
            "signaux baseline/outcome absents : décision non étayée")
    return {
        "options": options,
        "recommandation": _recommandation(faits),
        "confiance": _confiance_options(options),
        "conditions_de_retournement": _conditions_retournement(faits),
        "abstention": " ; ".join(raisons) if raisons else None,
        "autorite": autorite,
        "prochaines_etapes": list(prochaines),
    }


def _limites(plan: composition.PlanComposition, dossier: Mapping) -> tuple[str, ...]:
    valeurs = list(plan.avertissements) + list(dossier.get("limites") or ())
    for resultat in dossier.get("specialistes") or ():
        if not isinstance(resultat, Mapping):
            continue
        if resultat.get("statut") != "ok":
            valeurs.append(
                f"{resultat.get('specialiste', 'spécialiste')} : {resultat.get('statut', 'partiel')}"
                + (f" ({resultat['erreur']})" if resultat.get("erreur") else "")
            )
        valeurs.extend(resultat.get("limites") or ())
    return tuple(dict.fromkeys(_texte(valeur, 500) for valeur in valeurs if _texte(valeur, 500)))


def _section_pour(fait: Mapping, sections: tuple[str, ...]) -> str:
    type_ = _texte(fait.get("type"), 40).upper()
    for candidate in _GROUPES_TYPE.get(type_, ()):
        if candidate in sections:
            return candidate
    return sections[0] if sections else "synthese"


def sections_pour(profil) -> tuple[str, ...]:
    """Les sections de lecture d'un profil connu, ou la lentille généraliste."""
    identifiant = profil.id if isinstance(profil, profils.Profil) else _texte(profil, 80)
    return _SECTIONS.get(identifiant, _SECTIONS["generaliste"])


def _lecture(faits: tuple[dict, ...], sections: tuple[str, ...]) -> dict[str, list[dict]]:
    lecture = {section: [] for section in sections}
    for fait in faits:
        section = _section_pour(fait, sections)
        lecture.setdefault(section, []).append(fait)
    return {section: valeurs for section, valeurs in lecture.items() if valeurs}


@dataclass(frozen=True)
class Socle:
    faits: tuple[dict, ...] = ()
    preuves: tuple[str, ...] = ()
    incertitudes: tuple[str, ...] = ()
    limites: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "faits": [dict(fait) for fait in self.faits],
            "preuves": list(self.preuves),
            "incertitudes": list(self.incertitudes),
            "limites": list(self.limites),
        }


@dataclass(frozen=True)
class ReponseCognitive:
    question: str
    profil: profils.Profil
    composition: composition.PlanComposition
    socle: Socle
    lecture: dict[str, list[dict]] = field(default_factory=dict)
    decision_support: dict = field(default_factory=dict)
    actions: tuple[str, ...] = ()
    autorite: str = "lecture"
    prochaines_etapes: tuple[str, ...] = ()
    avertissements: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "question": self.question,
            "profil": self.profil.as_dict(),
            "composition": self.composition.as_dict(),
            "socle": self.socle.as_dict(),
            "lecture": {section: [dict(fait) for fait in faits]
                        for section, faits in self.lecture.items()},
            "decision_support": {
                **self.decision_support,
                "options": [
                    dict(option)
                    for option in self.decision_support.get("options", ())
                ],
                "conditions_de_retournement": list(
                    self.decision_support.get(
                        "conditions_de_retournement", ())),
                "prochaines_etapes": list(
                    self.decision_support.get("prochaines_etapes", ())),
            },
            "actions": list(self.actions),
            "autorite": self.autorite,
            "prochaines_etapes": list(self.prochaines_etapes),
            "avertissements": list(self.avertissements),
        }


def composer(
    question: str,
    profil: profils.Profil,
    plan: composition.PlanComposition,
    dossier: Mapping,
    *,
    autorite_max: str | None = None,
) -> ReponseCognitive:
    """Assemble une réponse située sans modifier le socle de faits."""
    if not isinstance(question, str):
        raise ValueError("question : texte attendu")
    if not isinstance(profil, profils.Profil):
        raise TypeError("profil : Profil attendu")
    if not isinstance(plan, composition.PlanComposition):
        raise TypeError("plan : PlanComposition attendu")
    if not isinstance(dossier, Mapping):
        raise TypeError("dossier : objet attendu")
    if plan.profil.id != profil.id:
        raise ValueError("le plan et le profil ne correspondent pas")

    faits = _faits(dossier)
    limites = _limites(plan, dossier)
    incertitudes = tuple(
        _texte(fait.get("titre"), 300) for fait in faits
        if _texte(fait.get("type"), 40).upper() in {"QUESTION", "HYPOTHESE"})
    lecture = _lecture(faits, sections_pour(profil))
    actions = []
    for fait in faits:
        for action in fait.get("actions") or ():
            texte = _texte(action, 120)
            if texte and texte not in actions:
                actions.append(texte)
    actions_autorisees = tuple(
        action for action in actions
        if action in _ACTIONS_PROFIL.get(profil.id, _ACTIONS_PROFIL["generaliste"])
    )
    autorite = plan.autorite
    if autorite_max is not None:
        ordre = ("lecture", "proposition", "approbation", "decision", "action")
        if autorite_max not in ordre:
            raise ValueError("autorité maximale inconnue")
        autorite = ordre[min(ordre.index(autorite), ordre.index(autorite_max))]
    if profil.inconnu:
        autorite = "lecture"
        actions_autorisees = ()
    prochaines = _PROCHAINES.get(profil.id, _PROCHAINES["generaliste"])
    decision_support = _decision_support(
        faits, dossier, autorite, prochaines)
    avertissements = list(limites)
    if not faits:
        avertissements.append("aucun fait vérifié dans le dossier : réponse bornée, aucune invention")
    return ReponseCognitive(
        question=_texte(question, 4000),
        profil=profil,
        composition=plan,
        socle=Socle(
            faits=faits, preuves=_preuves(faits),
            incertitudes=incertitudes, limites=limites),
        lecture=lecture,
        decision_support=decision_support,
        actions=actions_autorisees,
        autorite=autorite,
        prochaines_etapes=tuple(prochaines),
        avertissements=tuple(dict.fromkeys(avertissements)),
    )
