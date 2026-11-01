"""Registre des méthodes cognitives : fiches pures, sélection déterministe et bornée.

Une méthode décrit un enchaînement d'étapes, les artefacts attendus, les postures compatibles et une porte
de sortie humaine ou probante. Le registre ne lit aucune source et n'appelle aucun modèle : il rapproche un
profil et une question d'un catalogue fermé. Aucune méthode hors catalogue n'est inventée.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import re
from typing import Any
import unicodedata

__all__ = [
    "CATALOGUE_METHODES",
    "MODES_PREUVE",
    "POSTURES",
    "Methode",
    "as_dict",
    "methode_par_id",
    "methodes_pour",
    "valider_methodes",
]

POSTURES = ("explorateur", "investigateur", "concepteur", "facilitateur", "operateur", "gardien")
MODES_PREUVE = ("DECLARED", "OBSERVED", "INFERRED", "PROPOSED", "AUCUNE")
_METHODES_GENERALES = ("adr", "postmortem")
_INDICES_METHODES = {
    "besoin": ("babok",),
    "besoins": ("babok",),
    "exigence": ("babok",),
    "exigences": ("babok",),
    "elicitation": ("babok",),
    "processus": ("bpmn",),
    "workflow": ("bpmn",),
    "impact": ("impact_mapping",),
    "impacts": ("impact_mapping",),
    "recit": ("story_mapping",),
    "recits": ("story_mapping",),
    "user_story": ("story_mapping",),
    "sprint": ("scrum", "kanban"),
    "sprints": ("scrum", "kanban"),
    "agile": ("scrum", "kanban"),
    "flux": ("kanban",),
    "priorite": ("okr", "story_mapping"),
    "priorites": ("okr", "story_mapping"),
    "priorisation": ("okr", "story_mapping"),
    "roadmap": ("okr", "story_mapping"),
    "roadmaps": ("okr", "story_mapping"),
    "objectif": ("okr",),
    "objectifs": ("okr",),
    "planning": ("pmbok",),
    "portefeuille": ("pmbok",),
    "incident": ("postmortem",),
    "incidents": ("postmortem",),
    "sla": ("postmortem",),
    "postmortem": ("postmortem",),
    "retour_d_experience": ("postmortem",),
    "architecture": ("adr",),
    "architectures": ("adr",),
    "decision_technique": ("adr",),
    "amelioration": ("a3",),
    "ameliorations": ("a3",),
    "pdca": ("a3",),
    "benefice": ("benefits",),
    "benefices": ("benefits",),
    "risque": ("capa", "pmbok"),
    "risques": ("capa", "pmbok"),
    "conformite": ("capa",),
    "qualite": ("capa", "a3"),
    "data": ("dama",),
    "donnee": ("dama",),
    "donnees": ("dama",),
}


def _texte(valeur: Any, maximum: int = 4000) -> str:
    return " ".join(str(valeur or "").split())[:maximum]


def _normaliser(valeur: Any) -> str:
    texte = unicodedata.normalize("NFKD", str(valeur or ""))
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", texte.lower()).strip("_")


def _composants(valeur: Any) -> tuple[Any, ...]:
    if valeur is None:
        return ()
    if isinstance(valeur, str):
        return tuple(part.strip() for part in re.split(r"[,;|]+", valeur) if part.strip())
    if isinstance(valeur, Mapping):
        if "id" in valeur:
            return (valeur["id"],)
        return tuple(valeur.keys())
    if isinstance(valeur, Iterable):
        resultat = []
        for element in valeur:
            if isinstance(element, Mapping):
                resultat.append(element.get("id") or next(iter(element), None))
            else:
                resultat.append(getattr(element, "id", element))
        return tuple(resultat)
    return (valeur,)


def _normalises(valeur: Any) -> tuple[str, ...]:
    resultat = set()
    for element in _composants(valeur):
        if isinstance(element, Mapping):
            element = element.get("id") or next(iter(element), None)
        else:
            element = getattr(element, "id", element)
        normalise = _normaliser(element)
        if normalise:
            resultat.add(normalise)
    return tuple(sorted(resultat))


def _textes(valeur: Any) -> tuple[str, ...]:
    if valeur is None:
        return ()
    if isinstance(valeur, str):
        valeurs = [valeur]
    elif isinstance(valeur, Mapping):
        valeurs = list(valeur.values())
    elif isinstance(valeur, Iterable):
        valeurs = list(valeur)
    else:
        valeurs = [valeur]
    resultat = []
    for element in valeurs:
        texte = _texte(element)
        if texte and texte not in resultat:
            resultat.append(texte)
    return tuple(resultat)


def _cle(valeur: Any) -> str:
    if isinstance(valeur, Mapping):
        valeur = valeur.get("id") or next(iter(valeur), None)
    else:
        valeur = getattr(valeur, "id", valeur)
    return _normaliser(valeur)


def _valeur(profil: Any, *noms: str, defaut: Any = None) -> Any:
    if profil is None:
        return defaut
    for nom in noms:
        if isinstance(profil, Mapping):
            if nom in profil and profil[nom] is not None:
                return profil[nom]
        else:
            valeur = getattr(profil, nom, None)
            if valeur is not None:
                return valeur
    return defaut


def _contient(question: str, indice: str) -> bool:
    return f"_{indice}_" in f"_{question}_"


@dataclass(frozen=True)
class Methode:
    """Fiche immuable d'une méthode : étapes, artefacts, postures, compétences et porte de sortie."""

    id: str
    nom: str
    description: str
    postures: tuple[str, ...] = ()
    competences: tuple[str, ...] = ()
    artefacts: tuple[str, ...] = ()
    etapes: tuple[str, ...] = ()
    gates: tuple[str, ...] = ()
    version: str = "1.0"
    mode_preuve: str = "DECLARED"
    lecture_seule: bool = True

    def __post_init__(self):
        identifiant = _normaliser(self.id)
        nom = _texte(self.nom, 240)
        description = _texte(self.description, 2000)
        if not identifiant:
            raise ValueError("id de méthode obligatoire")
        if not nom:
            raise ValueError("nom de méthode obligatoire")
        if not description:
            raise ValueError("description de méthode obligatoire")
        postures = _normalises(self.postures)
        inconnues = [posture for posture in postures if posture not in POSTURES]
        if inconnues:
            raise ValueError(f"posture inconnue : {inconnues[0]}")
        mode_preuve = _texte(self.mode_preuve).upper()
        if mode_preuve not in MODES_PREUVE:
            raise ValueError(f"mode de preuve inconnu : {mode_preuve}")
        object.__setattr__(self, "id", identifiant)
        object.__setattr__(self, "nom", nom)
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "postures", postures)
        object.__setattr__(self, "competences", _normalises(self.competences))
        object.__setattr__(self, "artefacts", _textes(self.artefacts))
        object.__setattr__(self, "etapes", _textes(self.etapes))
        object.__setattr__(self, "gates", _textes(self.gates))
        object.__setattr__(self, "version", _texte(self.version, 40) or "1.0")
        object.__setattr__(self, "mode_preuve", mode_preuve)
        object.__setattr__(self, "lecture_seule", bool(self.lecture_seule))

    @property
    def postures_compatibles(self) -> tuple[str, ...]:
        """Alias lisible des postures compatibles."""
        return self.postures

    @property
    def competences_requises(self) -> tuple[str, ...]:
        """Alias lisible des compétences requises."""
        return self.competences

    @property
    def artefacts_attendus(self) -> tuple[str, ...]:
        """Alias lisible des artefacts attendus."""
        return self.artefacts

    @property
    def gate(self) -> str | None:
        """Première porte de sortie de la méthode, ou ``None``."""
        return self.gates[0] if self.gates else None

    def as_dict(self) -> dict:
        """Vue sérialisable de la fiche, sans référence mutable partagée."""
        return {
            "id": self.id,
            "nom": self.nom,
            "description": self.description,
            "postures": list(self.postures),
            "competences": list(self.competences),
            "artefacts": list(self.artefacts),
            "etapes": list(self.etapes),
            "gates": list(self.gates),
            "version": self.version,
            "mode_preuve": self.mode_preuve,
            "lecture_seule": self.lecture_seule,
        }


CATALOGUE_METHODES = (
    Methode(
        id="babok",
        nom="BABOK",
        description="Élicitation et consolidation des exigences métier avec traçabilité vers les sources.",
        postures=("explorateur", "investigateur", "concepteur", "facilitateur"),
        competences=("lire_interfaces", "faciliter_decision", "rechercher_memoire"),
        artefacts=("registre des exigences", "glossaire métier", "matrice de traçabilité"),
        etapes=("cadrer la demande", "identifier les parties prenantes", "éliciter les besoins",
                "consolider les exigences", "faire valider le périmètre"),
        gates=("humain : validation des exigences par le commanditaire",),
        version="1.0",
        mode_preuve="DECLARED",
        lecture_seule=True,
    ),
    Methode(
        id="bpmn",
        nom="BPMN",
        description="Modélisation d'un processus, de ses acteurs, de ses points de contrôle et de ses variantes.",
        postures=("investigateur", "concepteur", "facilitateur", "operateur"),
        competences=("modeliser_processus", "tracer_chemin", "lire_interfaces"),
        artefacts=("cartographie BPMN", "points de contrôle", "matrice des responsabilités"),
        etapes=("collecter les traces du processus", "délimiter le périmètre", "modéliser les flux",
                "identifier les contrôles", "confronter le modèle aux observations"),
        gates=("preuve : modèle confronté aux traces et événements observés",),
        version="1.0",
        mode_preuve="OBSERVED",
        lecture_seule=True,
    ),
    Methode(
        id="impact_mapping",
        nom="Impact mapping",
        description="Relier un objectif à ses acteurs, à leurs impacts attendus et aux livrables qui les prouvent.",
        postures=("investigateur", "concepteur", "facilitateur"),
        competences=("analyser_impact", "tracer_chemin", "faciliter_decision"),
        artefacts=("carte d'impact", "hypothèses hiérarchisées", "mesures associées"),
        etapes=("formuler l'objectif", "identifier les acteurs", "décrire les impacts",
                "choisir les livrables", "fixer les mesures"),
        gates=("humain : atelier de validation des impacts avec les parties prenantes",),
        version="1.0",
        mode_preuve="INFERRED",
        lecture_seule=True,
    ),
    Methode(
        id="story_mapping",
        nom="Story mapping",
        description="Découper un parcours utilisateur en récits ordonnés et en incréments livrables.",
        postures=("concepteur", "facilitateur"),
        competences=("analyser_impact", "faciliter_decision", "modeliser_processus"),
        artefacts=("carte des récits", "backlog découpé", "critères d'acceptation"),
        etapes=("reconstituer le parcours", "aligner les récits", "prioriser les tranches",
                "définir les critères d'acceptation"),
        gates=("humain : revue du propriétaire de produit sur l'ordre des tranches",),
        version="1.0",
        mode_preuve="PROPOSED",
        lecture_seule=True,
    ),
    Methode(
        id="scrum",
        nom="Scrum",
        description="Cadence d'itérations avec propriétaire de produit, mêlée quotidienne et revue d'incrément.",
        postures=("concepteur", "facilitateur", "operateur"),
        competences=("faciliter_decision", "mesurer_outcome", "analyser_impact"),
        artefacts=("backlog de produit", "incrément livrable", "définition de fini"),
        etapes=("ordonner le backlog", "planifier l'itération", "suivre la mêlée",
                "revoir l'incrément", "rétrospecter"),
        gates=("humain : revue d'itération et acceptation par le propriétaire de produit",),
        version="1.0",
        mode_preuve="DECLARED",
        lecture_seule=False,
    ),
    Methode(
        id="kanban",
        nom="Kanban",
        description="Visualisation du flux, limitation des travaux en cours et mesure du débit observé.",
        postures=("facilitateur", "operateur"),
        competences=("mesurer_outcome", "tracer_chemin", "faciliter_decision"),
        artefacts=("tableau de flux", "limites de travaux en cours", "métriques de débit"),
        etapes=("cartographier les colonnes", "poser les limites de travaux en cours",
                "mesurer le temps de traversée", "réduire les goulets"),
        gates=("preuve : mesures de flux observées et comparées dans le temps",),
        version="1.0",
        mode_preuve="OBSERVED",
        lecture_seule=True,
    ),
    Methode(
        id="okr",
        nom="OKR",
        description="Objectifs qualitatifs et résultats clés mesurables pour aligner priorités et outcomes.",
        postures=("concepteur", "facilitateur", "operateur"),
        competences=("mesurer_outcome", "analyser_impact", "faciliter_decision"),
        artefacts=("objectifs", "résultats clés", "tableau de suivi"),
        etapes=("formuler l'objectif", "définir des résultats clés mesurables",
                "aligner les initiatives", "suivre les écarts", "réviser au cycle suivant"),
        gates=("humain : validation des résultats clés par le sponsor",),
        version="1.0",
        mode_preuve="PROPOSED",
        lecture_seule=True,
    ),
    Methode(
        id="pmbok",
        nom="PMBOK",
        description="Planification projet, registre RAID et pilotage des risques, hypothèses et dépendances.",
        postures=("facilitateur", "operateur", "gardien"),
        competences=("evaluer_risque", "analyser_impact", "tracer_chemin"),
        artefacts=("registre RAID", "plan projet", "échéancier"),
        etapes=("cadrer le périmètre", "construire l'échéancier", "tenir le registre RAID",
                "piloter les dépendances", "clôturer et capitaliser"),
        gates=("humain : comité de pilotage sur le plan et les risques",),
        version="1.0",
        mode_preuve="DECLARED",
        lecture_seule=False,
    ),
    Methode(
        id="postmortem",
        nom="Postmortem",
        description="Analyse d'incident sans blâme : chronologie, causes racines et actions de prévention.",
        postures=("investigateur", "operateur", "gardien"),
        competences=("verifier_preuve", "detecter_contradiction", "tracer_chemin", "retrouver_learning"),
        artefacts=("chronologie étayée", "causes racines", "actions correctives et préventives"),
        etapes=("figer la chronologie", "confronter les sources", "identifier les causes racines",
                "choisir les actions", "suivre l'efficacité"),
        gates=("preuve : chronologie étayée par journaux, traces et changements",),
        version="1.0",
        mode_preuve="OBSERVED",
        lecture_seule=True,
    ),
    Methode(
        id="adr",
        nom="ADR",
        description="Consigner une décision d'architecture, les options écartées et leurs conséquences.",
        postures=("investigateur", "concepteur", "gardien"),
        competences=("rediger_adr", "faciliter_decision", "evaluer_risque"),
        artefacts=("décision d'architecture", "options comparées", "conséquences et risques"),
        etapes=("exposer le contexte", "comparer les options", "trancher et justifier",
                "consigner les conséquences"),
        gates=("humain : décision d'architecture entérinée par l'autorité compétente",),
        version="1.0",
        mode_preuve="DECLARED",
        lecture_seule=False,
    ),
    Methode(
        id="a3",
        nom="A3",
        description="Résolution structurée par PDCA : constat, analyse, contre-mesure et vérification.",
        postures=("investigateur", "facilitateur", "operateur"),
        competences=("analyser_impact", "evaluer_risque", "mesurer_outcome"),
        artefacts=("rapport A3", "plan PDCA", "preuve de vérification"),
        etapes=("décrire la situation", "analyser les causes", "proposer une contre-mesure",
                "appliquer et vérifier", "standardiser ou corriger"),
        gates=("preuve : résultat mesuré après la contre-mesure",),
        version="1.0",
        mode_preuve="OBSERVED",
        lecture_seule=False,
    ),
    Methode(
        id="benefits",
        nom="Benefits realisation",
        description="Relier un investissement à ses bénéfices attendus, mesurés et réalisés.",
        postures=("concepteur", "operateur", "gardien"),
        competences=("mesurer_outcome", "analyser_impact", "verifier_preuve"),
        artefacts=("business case", "plan de réalisation des bénéfices", "mesures de bénéfices"),
        etapes=("définir les bénéfices", "fixer les cibles et mesures", "suivre la réalisation",
                "comparer aux cibles", "décider de la suite"),
        gates=("preuve : bénéfices mesurés et comparés aux cibles",),
        version="1.0",
        mode_preuve="OBSERVED",
        lecture_seule=True,
    ),
    Methode(
        id="capa",
        nom="CAPA",
        description="Action corrective et préventive : cause racine, plan d'action et preuve d'efficacité.",
        postures=("investigateur", "operateur", "gardien"),
        competences=("evaluer_risque", "verifier_preuve", "detecter_contradiction"),
        artefacts=("fiche CAPA", "analyse de cause racine", "preuve d'efficacité"),
        etapes=("qualifier l'écart", "analyser la cause racine", "définir l'action corrective",
                "définir l'action préventive", "vérifier l'efficacité"),
        gates=("preuve : efficacité de l'action vérifiée sur un cas ultérieur",),
        version="1.0",
        mode_preuve="OBSERVED",
        lecture_seule=False,
    ),
    Methode(
        id="raid",
        nom="RAID",
        description="Registre des risques, actions, incidents et décisions d'un projet ou d'un portefeuille.",
        postures=("facilitateur", "operateur", "gardien"),
        competences=("evaluer_risque", "faciliter_decision", "verifier_preuve"),
        artefacts=("registre RAID", "plan d'action", "revue de risques"),
        etapes=("collecter risques actions incidents décisions", "qualifier et prioriser",
                "assigner un propriétaire et une échéance", "revoir et clôturer"),
        gates=("humain : revue du registre et des risques résiduels",),
        version="1.0",
        mode_preuve="DECLARED",
        lecture_seule=True,
    ),
    Methode(
        id="dama",
        nom="DAMA",
        description="Gestion des données : qualité, lignage, propriété et règles de gouvernance.",
        postures=("investigateur", "concepteur", "gardien"),
        competences=("qualifier_donnee", "modeliser_processus", "verifier_preuve", "compiler_manifestes"),
        artefacts=("catalogue de données", "lignage", "règles de qualité"),
        etapes=("inventorier les jeux de données", "qualifier la sensibilité", "tracer le lignage",
                "définir les règles de qualité", "désigner les propriétaires"),
        gates=("humain : validation du propriétaire de données sur les règles",),
        version="1.0",
        mode_preuve="DECLARED",
        lecture_seule=True,
    ),
)

_METHODES_PAR_ID = {methode.id: methode for methode in CATALOGUE_METHODES}


def methode_par_id(identifiant: Any) -> Methode | None:
    """Rend la méthode du catalogue portant cet identifiant, ou ``None`` si elle n'existe pas."""
    return _METHODES_PAR_ID.get(_cle(identifiant))


def as_dict(methode: Any) -> dict:
    """Vue sérialisable d'une méthode du catalogue, acceptée par identifiant ou par fiche."""
    fiche = methode if isinstance(methode, Methode) else methode_par_id(methode)
    if fiche is None:
        raise ValueError(f"méthode inconnue : {methode!r}")
    return fiche.as_dict()


def valider_methodes(ids: Any) -> tuple[Methode, ...]:
    """Valide des identifiants et rend les méthodes correspondantes, sans doublon.

    Un identifiant absent du catalogue lève ``ValueError`` : aucune méthode n'est inventée.
    """
    resultat: list[Methode] = []
    for valeur in _composants(ids):
        methode = _METHODES_PAR_ID.get(_cle(valeur))
        if methode is None:
            raise ValueError(f"méthode inconnue : {valeur!r}")
        if methode not in resultat:
            resultat.append(methode)
    return tuple(resultat)


def methodes_pour(profil: Any = None, question: str = "", limite: int = 6) -> list[Methode]:
    """Sélectionne au plus ``limite`` méthodes du catalogue pour un profil et une question.

    Le profil peut être un mapping ou un objet portant ``postures``, ``methodes`` et ``competences``.
    Les identifiants explicites du profil priment, puis les postures, les compétences et enfin les
    indices de la question. Sans aucun signal, un noyau général minimal est rendu. Le résultat est
    toujours un sous-ensemble du catalogue, trié de façon stable.
    """
    postures = set(_normalises(_valeur(profil, "postures", "posture", "postures_compatibles")))
    methodes = set(_normalises(_valeur(profil, "methodes", "methods", "methodes_cognitives")))
    competences = set(_normalises(_valeur(profil, "competences", "skills", "competences_requises")))
    texte = _normaliser(question)
    try:
        borne = int(limite)
    except (TypeError, ValueError):
        borne = 6
    borne = max(0, min(borne, len(CATALOGUE_METHODES)))
    if borne == 0:
        return []
    scores = []
    for methode in CATALOGUE_METHODES:
        score = 0
        if methode.id in methodes or _normaliser(methode.nom) in methodes:
            score += 1000
        score += 10 * len(set(methode.postures) & postures)
        score += 3 * len(set(methode.competences) & competences)
        for indice, cibles in _INDICES_METHODES.items():
            if _contient(texte, indice) and methode.id in cibles:
                score += 20
        if score:
            scores.append((score, methode))
    if not scores:
        return [methode for methode in valider_methodes(_METHODES_GENERALES)][:borne]
    scores.sort(key=lambda element: (-element[0], element[1].id))
    return [methode for _, methode in scores[:borne]]
