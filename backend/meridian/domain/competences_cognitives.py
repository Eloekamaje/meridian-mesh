"""Registre des compétences cognitives : fiches pures, spécialités et sélection déterministe.

Une compétence décrit ce qu'un spécialiste sait faire, les outils qu'il peut mobiliser, ses entrées, ses
sorties et ses critères d'évaluation. Le registre ne lit aucune source, n'ouvre aucune base et n'appelle
aucun modèle : il rapproche un profil et une question d'un catalogue fermé, sans inventer de compétence.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import re
from typing import Any
import unicodedata

__all__ = [
    "CATALOGUE_COMPETENCES",
    "SPECIALISTES",
    "Competence",
    "as_dict",
    "competence_par_id",
    "competences_du_specialiste",
    "competences_pour",
    "valider_competences",
]

SPECIALISTES = ("decouverte", "preuve", "impact", "outcome", "outil")
_COMPETENCES_GENERALES = ("rechercher_memoire", "verifier_preuve")
_POSTURES_COMPETENCES = {
    "lire_interfaces": ("explorateur", "investigateur", "concepteur"),
    "compiler_manifestes": ("explorateur", "operateur"),
    "verifier_preuve": ("investigateur", "gardien"),
    "detecter_contradiction": ("investigateur", "gardien"),
    "analyser_impact": ("concepteur", "facilitateur", "operateur"),
    "tracer_chemin": ("investigateur", "concepteur"),
    "retrouver_learning": ("facilitateur", "operateur", "gardien"),
    "mesurer_outcome": ("concepteur", "operateur", "gardien"),
    "modeliser_processus": ("investigateur", "concepteur", "operateur"),
    "faciliter_decision": ("concepteur", "facilitateur", "gardien"),
    "evaluer_risque": ("investigateur", "concepteur", "gardien"),
    "qualifier_donnee": ("investigateur", "concepteur", "operateur"),
    "rechercher_memoire": ("explorateur", "investigateur", "facilitateur"),
    "rediger_adr": ("concepteur", "facilitateur", "gardien"),
}
_INDICES_COMPETENCES = {
    "interface": ("lire_interfaces",),
    "manifeste": ("compiler_manifestes",),
    "preuve": ("verifier_preuve",),
    "preuves": ("verifier_preuve",),
    "prouver": ("verifier_preuve",),
    "contradiction": ("detecter_contradiction",),
    "contradictions": ("detecter_contradiction",),
    "contradictoire": ("detecter_contradiction",),
    "incoherence": ("detecter_contradiction",),
    "impact": ("analyser_impact",),
    "impacts": ("analyser_impact",),
    "dependance": ("tracer_chemin", "analyser_impact"),
    "dependances": ("tracer_chemin", "analyser_impact"),
    "chemin": ("tracer_chemin",),
    "chemins": ("tracer_chemin",),
    "learning": ("retrouver_learning",),
    "lecon": ("retrouver_learning",),
    "outcome": ("mesurer_outcome",),
    "outcomes": ("mesurer_outcome",),
    "benefice": ("mesurer_outcome",),
    "benefices": ("mesurer_outcome",),
    "mesure": ("mesurer_outcome",),
    "mesures": ("mesurer_outcome",),
    "processus": ("modeliser_processus",),
    "workflow": ("modeliser_processus",),
    "decision": ("faciliter_decision",),
    "decisions": ("faciliter_decision",),
    "option": ("faciliter_decision",),
    "options": ("faciliter_decision",),
    "risque": ("evaluer_risque",),
    "risques": ("evaluer_risque",),
    "conformite": ("evaluer_risque", "verifier_preuve"),
    "donnee": ("qualifier_donnee",),
    "donnees": ("qualifier_donnee",),
    "data": ("qualifier_donnee",),
    "qualite": ("qualifier_donnee",),
    "memoire": ("rechercher_memoire",),
    "connaissance": ("rechercher_memoire",),
    "connaissances": ("rechercher_memoire",),
    "adr": ("rediger_adr",),
    "architecture": ("rediger_adr",),
    "architectures": ("rediger_adr",),
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
class Competence:
    """Fiche immuable d'une compétence : spécialité, outils, entrées, sorties et évaluation."""

    id: str
    nom: str
    description: str
    specialiste: str = "outil"
    outils: tuple[str, ...] = ()
    entrees: str = ""
    sorties: str = ""
    lecture_seule: bool = True
    eval: tuple[str, ...] = ()

    def __post_init__(self):
        identifiant = _normaliser(self.id)
        nom = _texte(self.nom, 240)
        description = _texte(self.description, 2000)
        specialiste = _normaliser(self.specialiste)
        if not identifiant:
            raise ValueError("id de compétence obligatoire")
        if not nom:
            raise ValueError("nom de compétence obligatoire")
        if not description:
            raise ValueError("description de compétence obligatoire")
        if specialiste not in SPECIALISTES:
            raise ValueError(f"spécialiste inconnu : {specialiste}")
        object.__setattr__(self, "id", identifiant)
        object.__setattr__(self, "nom", nom)
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "specialiste", specialiste)
        object.__setattr__(self, "outils", _normalises(self.outils))
        object.__setattr__(self, "entrees", _texte(self.entrees, 2000))
        object.__setattr__(self, "sorties", _texte(self.sorties, 2000))
        object.__setattr__(self, "lecture_seule", bool(self.lecture_seule))
        object.__setattr__(self, "eval", _textes(self.eval))

    @property
    def specialite(self) -> str:
        """Alias lisible de la spécialité."""
        return self.specialiste

    def as_dict(self) -> dict:
        """Vue sérialisable de la fiche, sans référence mutable partagée."""
        return {
            "id": self.id,
            "nom": self.nom,
            "description": self.description,
            "specialiste": self.specialiste,
            "outils": list(self.outils),
            "entrees": self.entrees,
            "sorties": self.sorties,
            "lecture_seule": self.lecture_seule,
            "eval": list(self.eval),
        }


CATALOGUE_COMPETENCES = (
    Competence(
        id="lire_interfaces",
        nom="Lire les interfaces",
        description="Inventorier les contrats exposés ou consommés et en restituer les frontières.",
        specialiste="decouverte",
        outils=("connecteur_interfaces", "decouverte_interfaces"),
        entrees="spécifications, contrats ou code d'interface",
        sorties="inventaire des interfaces et de leurs contrats",
        lecture_seule=True,
        eval=("inventaire non vide", "source de chaque interface citée"),
    ),
    Competence(
        id="compiler_manifestes",
        nom="Compiler les manifestes",
        description="Normaliser et valider les manifestes déclarés sans ajouter de capacité implicite.",
        specialiste="outil",
        outils=("chargeur_manifestes", "capacites"),
        entrees="manifestes déclarés",
        sorties="capacités normalisées et validées",
        lecture_seule=True,
        eval=("manifeste valide", "aucune capacité inventée"),
    ),
    Competence(
        id="verifier_preuve",
        nom="Vérifier une preuve",
        description="Confronter un claim à ses preuves localisables, à leur fraîcheur et à leur portée.",
        specialiste="preuve",
        outils=("connaissance", "depot", "temporalite"),
        entrees="claim et preuves associées",
        sorties="verdict de preuve et limites",
        lecture_seule=True,
        eval=("preuve localisable", "fraîcheur vérifiée"),
    ),
    Competence(
        id="detecter_contradiction",
        nom="Détecter une contradiction",
        description="Repérer deux affirmations incompatibles et exposer les sources qui s'opposent.",
        specialiste="preuve",
        outils=("contradicteur", "recoupement"),
        entrees="claims, sources et observations",
        sorties="contradictions classées et étayées",
        lecture_seule=True,
        eval=("contradiction étayée", "sources opposées citées"),
    ),
    Competence(
        id="analyser_impact",
        nom="Analyser un impact",
        description="Estimer les effets directs et indirects d'un changement sur la topologie connue.",
        specialiste="impact",
        outils=("impacts_situations", "graphe"),
        entrees="changement et topologie",
        sorties="impacts directs et indirects",
        lecture_seule=True,
        eval=("chemin d'impact justifié", "profondeur bornée"),
    ),
    Competence(
        id="tracer_chemin",
        nom="Tracer un chemin",
        description="Relier une source à une cible par un chemin continu et citer chaque arête.",
        specialiste="impact",
        outils=("graphe", "graphe_neo4j"),
        entrees="nœud source et nœud cible",
        sorties="chemin causal ou de dépendance",
        lecture_seule=True,
        eval=("chemin continu", "arêtes citées"),
    ),
    Competence(
        id="retrouver_learning",
        nom="Retrouver un learning",
        description="Retrouver les leçons et apprentissages reliés à une situation ou à un outcome.",
        specialiste="outcome",
        outils=("memoire_org", "connaissance"),
        entrees="situation ou outcome",
        sorties="leçons et apprentissages reliés",
        lecture_seule=True,
        eval=("leçon sourcée", "périmètre respecté"),
    ),
    Competence(
        id="mesurer_outcome",
        nom="Mesurer un outcome",
        description="Comparer une mesure datée à une cible explicite et restituer l'écart.",
        specialiste="outcome",
        outils=("outcomes", "mesure"),
        entrees="cible et mesures",
        sorties="écart d'outcome et tendance",
        lecture_seule=True,
        eval=("mesure datée", "cible explicite"),
    ),
    Competence(
        id="modeliser_processus",
        nom="Modéliser un processus",
        description="Décrire les étapes, acteurs et points de contrôle d'un processus observable.",
        specialiste="decouverte",
        outils=("bpmn", "graphe"),
        entrees="traces et description du processus",
        sorties="modèle de processus",
        lecture_seule=True,
        eval=("étapes reliées", "points de contrôle identifiés"),
    ),
    Competence(
        id="faciliter_decision",
        nom="Faciliter une décision",
        description="Comparer des options explicites et préparer un arbitrage laissé à l'humain.",
        specialiste="impact",
        outils=("preuve", "options"),
        entrees="options et critères",
        sorties="décision proposée et arbitrages",
        lecture_seule=True,
        eval=("options comparées", "décision humaine"),
    ),
    Competence(
        id="evaluer_risque",
        nom="Évaluer un risque",
        description="Qualifier une menace, son exposition et son mode de preuve sans conclure seul.",
        specialiste="preuve",
        outils=("gardien", "limites", "temporalite"),
        entrees="menace et exposition",
        sorties="risque qualifié et incertitudes",
        lecture_seule=True,
        eval=("probabilité et impact justifiés", "mode de preuve explicite"),
    ),
    Competence(
        id="qualifier_donnee",
        nom="Qualifier une donnée",
        description="Qualifier la qualité, le sens et la sensibilité d'un jeu de données.",
        specialiste="decouverte",
        outils=("modele_entreprise", "dama"),
        entrees="jeu de données et règles",
        sorties="qualité et sensibilité qualifiées",
        lecture_seule=True,
        eval=("règles appliquées", "données sensibles masquées"),
    ),
    Competence(
        id="rechercher_memoire",
        nom="Rechercher en mémoire",
        description="Retrouver des extraits de mémoire organisationnelle dans le périmètre autorisé.",
        specialiste="outil",
        outils=("memoire_org", "pg_recherche", "connaissance"),
        entrees="question et périmètre",
        sorties="extraits mémoire reliés",
        lecture_seule=True,
        eval=("résultat sourcé", "tenant respecté"),
    ),
    Competence(
        id="rediger_adr",
        nom="Rédiger un ADR",
        description="Consigner une décision d'architecture, ses options et ses conséquences.",
        specialiste="impact",
        outils=("depot", "documentation"),
        entrees="décision et options",
        sorties="ADR proposé",
        lecture_seule=False,
        eval=("contexte et conséquences", "validation humaine"),
    ),
)

_COMPETENCES_PAR_ID = {competence.id: competence for competence in CATALOGUE_COMPETENCES}


def competence_par_id(identifiant: Any) -> Competence | None:
    """Rend la compétence du catalogue portant cet identifiant, ou ``None`` si elle n'existe pas."""
    return _COMPETENCES_PAR_ID.get(_cle(identifiant))


def as_dict(competence: Any) -> dict:
    """Vue sérialisable d'une compétence du catalogue, acceptée par identifiant ou par fiche."""
    fiche = competence if isinstance(competence, Competence) else competence_par_id(competence)
    if fiche is None:
        raise ValueError(f"compétence inconnue : {competence!r}")
    return fiche.as_dict()


def valider_competences(ids: Any) -> tuple[Competence, ...]:
    """Valide des identifiants et rend les compétences correspondantes, sans doublon.

    Un identifiant absent du catalogue lève ``ValueError`` : aucune compétence n'est inventée.
    """
    resultat: list[Competence] = []
    for valeur in _composants(ids):
        competence = _COMPETENCES_PAR_ID.get(_cle(valeur))
        if competence is None:
            raise ValueError(f"compétence inconnue : {valeur!r}")
        if competence not in resultat:
            resultat.append(competence)
    return tuple(resultat)


def competences_du_specialiste(specialiste: Any, limite: int | None = None) -> tuple[Competence, ...]:
    """Rend les compétences du spécialiste demandé, dans l'ordre du catalogue.

    Un spécialiste inconnu rend un tuple vide ; ``limite`` borne le résultat sans changer l'ordre.
    """
    cle = _normaliser(specialiste)
    resultat = tuple(competence for competence in CATALOGUE_COMPETENCES if competence.specialiste == cle)
    if limite is None:
        return resultat
    try:
        borne = int(limite)
    except (TypeError, ValueError):
        borne = len(resultat)
    return resultat[:max(0, min(borne, len(resultat)))]


def competences_pour(profil: Any = None, question: str = "", limite: int = 8) -> list[Competence]:
    """Sélectionne au plus ``limite`` compétences du catalogue pour un profil et une question.

    Le profil peut être un mapping ou un objet portant ``competences``, ``postures`` et
    ``specialiste``. Les compétences explicites priment, puis la spécialité, les postures et enfin
    les indices de la question. Sans aucun signal, un noyau général minimal est rendu. Le résultat
    est toujours un sous-ensemble du catalogue, trié de façon stable.
    """
    competences = set(_normalises(_valeur(profil, "competences", "skills", "competences_requises")))
    postures = set(_normalises(_valeur(profil, "postures", "posture", "postures_compatibles")))
    specialistes = set(_normalises(_valeur(profil, "specialiste", "specialistes", "specialite")))
    texte = _normaliser(question)
    try:
        borne = int(limite)
    except (TypeError, ValueError):
        borne = 8
    borne = max(0, min(borne, len(CATALOGUE_COMPETENCES)))
    if borne == 0:
        return []
    scores = []
    for competence in CATALOGUE_COMPETENCES:
        score = 0
        if competence.id in competences or _normaliser(competence.nom) in competences:
            score += 1000
        if competence.specialiste in specialistes:
            score += 30
        score += 10 * len(set(_POSTURES_COMPETENCES.get(competence.id, ())) & postures)
        for indice, cibles in _INDICES_COMPETENCES.items():
            if _contient(texte, indice) and competence.id in cibles:
                score += 20
        if score:
            scores.append((score, competence))
    if not scores:
        return [competence for competence in valider_competences(_COMPETENCES_GENERALES)][:borne]
    scores.sort(key=lambda element: (-element[0], element[1].id))
    return [competence for _, competence in scores[:borne]]
