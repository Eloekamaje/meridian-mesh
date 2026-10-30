"""Composition de la réponse par lentille de profil, sur un socle de faits invariant.

Le socle (propositions, preuves, incertitudes, limites) est identique quel que soit le profil.
Le profil ne change que la lecture, l'ordre, le vocabulaire, les actions proposées et les prochaines
étapes. Aucun fait n'est créé, retiré ou réécrit par la lentille ; aucune action n'est exécutée.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from jumeau import composition, profils

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
    elif not actions_autorisees:
        actions_autorisees = (_ACTIONS_PROFIL.get(profil.id, _ACTIONS_PROFIL["generaliste"])[0],)
    prochaines = _PROCHAINES.get(profil.id, _PROCHAINES["generaliste"])
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
        actions=actions_autorisees,
        autorite=autorite,
        prochaines_etapes=tuple(prochaines),
        avertissements=tuple(dict.fromkeys(avertissements)),
    )
