"""Résolution déterministe d'un profil humain ou agent, sans modèle, réseau ni base.

Un profil est une composition : posture, méthodes, compétences, domaines et autorité sont
distingués. Un intitulé de poste ne suffit jamais à accorder une autorité : seule une
résolution explicite ou une identité déclarée peut reprendre l'autorité du catalogue, et
l'inférence depuis une question reste toujours en lecture seule. Un profil inconnu retombe
sur ``generaliste`` avec ``inconnu=True`` et une autorité de lecture.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, replace
import math
import re
import unicodedata
from typing import Any

__all__ = [
    "Profil",
    "CATALOGUE_PROFILS",
    "POSTURES",
    "METHODES",
    "AUTORITES",
    "SOURCES",
    "MOTS_CLES_INFERENCE",
    "resoudre_profil",
    "autorite_superieure",
    "autorise",
]

POSTURES = frozenset({
    "explorateur", "investigateur", "concepteur", "facilitateur", "operateur", "gardien",
})
METHODES = frozenset({
    "babok", "bpmn", "impact_mapping", "story_mapping", "scrum", "kanban", "okr", "pmbok",
    "raid", "postmortem", "adr", "a3", "benefits", "capa", "dama",
})
AUTORITES = ("lecture", "proposition", "approbation", "decision", "action")
SOURCES = frozenset({"explicite", "identite", "infere", "defaut"})

_ORDRE_AUTORITE = {autorite: rang for rang, autorite in enumerate(AUTORITES)}
_ACTIONS = {
    "lire": "lecture", "lecture": "lecture",
    "proposer": "proposition", "proposition": "proposition",
    "approuver": "approbation", "approbation": "approbation",
    "decider": "decision", "decision": "decision",
    "executer": "action", "agir": "action", "action": "action",
}


def _verifier_chaine(valeur: Any, nom: str) -> str:
    """Vérifie qu'une valeur est une chaîne non vide."""
    if not isinstance(valeur, str):
        raise TypeError(f"{nom} doit être une chaîne")
    if not valeur.strip():
        raise ValueError(f"{nom} ne peut pas être vide")
    return valeur


def _verifier_tuple(valeur: Any, nom: str, autorisees: frozenset[str] | None = None) -> tuple[str, ...]:
    """Vérifie un tuple de chaînes non vides, éventuellement restreint à un vocabulaire."""
    if not isinstance(valeur, tuple):
        raise TypeError(f"{nom} doit être un tuple")
    for element in valeur:
        if not isinstance(element, str):
            raise TypeError(f"chaque élément de {nom} doit être une chaîne")
        if not element.strip():
            raise ValueError(f"un élément de {nom} ne peut pas être vide")
        if autorisees is not None and element not in autorisees:
            raise ValueError(f"valeur invalide pour {nom} : {element}")
    return valeur


@dataclass(frozen=True)
class Profil:
    """Composition immuable d'un profil, indépendante d'un simple intitulé de poste."""

    id: str
    libelle: str
    postures: tuple[str, ...]
    methodes: tuple[str, ...]
    competences: tuple[str, ...]
    domaines: tuple[str, ...]
    autorite: str
    confiance: float
    source: str
    inconnu: bool

    def __post_init__(self) -> None:
        _verifier_chaine(self.id, "id")
        _verifier_chaine(self.libelle, "libelle")
        _verifier_tuple(self.postures, "postures", POSTURES)
        _verifier_tuple(self.methodes, "methodes", METHODES)
        _verifier_tuple(self.competences, "competences")
        _verifier_tuple(self.domaines, "domaines")
        if not isinstance(self.autorite, str):
            raise TypeError("autorite doit être une chaîne")
        if self.autorite not in AUTORITES:
            raise ValueError(f"autorite invalide : {self.autorite}")
        if isinstance(self.confiance, bool) or not isinstance(self.confiance, (int, float)):
            raise TypeError("confiance doit être un nombre")
        if not math.isfinite(self.confiance) or not 0.0 <= self.confiance <= 1.0:
            raise ValueError("confiance doit être comprise entre 0 et 1")
        object.__setattr__(self, "confiance", float(self.confiance))
        if not isinstance(self.source, str):
            raise TypeError("source doit être une chaîne")
        if self.source not in SOURCES:
            raise ValueError(f"source invalide : {self.source}")
        if not isinstance(self.inconnu, bool):
            raise TypeError("inconnu doit être un booléen")

    def as_dict(self) -> dict[str, Any]:
        """Rend le profil sous forme de dictionnaire sérialisable."""
        return asdict(self)


CATALOGUE_PROFILS: dict[str, Profil] = {
    "business_analyst": Profil(
        id="business_analyst",
        libelle="Business analyst",
        postures=("investigateur", "facilitateur"),
        methodes=("babok", "impact_mapping", "story_mapping"),
        competences=(
            "modeliser_processus", "rechercher_memoire", "faciliter_decision",
            "analyser_impact", "verifier_preuve",
        ),
        domaines=(),
        autorite="proposition",
        confiance=1.0,
        source="explicite",
        inconnu=False,
    ),
    "analyste_fonctionnel": Profil(
        id="analyste_fonctionnel",
        libelle="Analyste fonctionnel",
        postures=("investigateur", "concepteur"),
        methodes=("bpmn", "babok", "story_mapping"),
        competences=(
            "lire_interfaces", "modeliser_processus", "analyser_impact",
            "verifier_preuve", "rediger_adr",
        ),
        domaines=(),
        autorite="proposition",
        confiance=1.0,
        source="explicite",
        inconnu=False,
    ),
    "developpeur": Profil(
        id="developpeur",
        libelle="Développeur",
        postures=("concepteur", "operateur"),
        methodes=("adr", "postmortem", "kanban"),
        competences=(
            "lire_interfaces", "analyser_impact", "tracer_chemin",
            "rediger_adr", "verifier_preuve",
        ),
        domaines=(),
        autorite="proposition",
        confiance=1.0,
        source="explicite",
        inconnu=False,
    ),
    "product_owner": Profil(
        id="product_owner",
        libelle="Product owner",
        postures=("facilitateur", "concepteur"),
        methodes=("scrum", "story_mapping", "okr"),
        competences=(
            "faciliter_decision", "mesurer_outcome", "retrouver_learning", "analyser_impact",
        ),
        domaines=(),
        autorite="proposition",
        confiance=1.0,
        source="explicite",
        inconnu=False,
    ),
    "scrum_master": Profil(
        id="scrum_master",
        libelle="Scrum master",
        postures=("facilitateur", "gardien"),
        methodes=("scrum", "kanban", "postmortem"),
        competences=(
            "faciliter_decision", "rechercher_memoire", "detecter_contradiction",
            "modeliser_processus",
        ),
        domaines=(),
        autorite="proposition",
        confiance=1.0,
        source="explicite",
        inconnu=False,
    ),
    "chef_projet": Profil(
        id="chef_projet",
        libelle="Chef de projet",
        postures=("facilitateur", "operateur"),
        methodes=("pmbok", "raid", "benefits"),
        competences=(
            "analyser_impact", "mesurer_outcome", "evaluer_risque",
            "rechercher_memoire", "faciliter_decision",
        ),
        domaines=(),
        autorite="proposition",
        confiance=1.0,
        source="explicite",
        inconnu=False,
    ),
    "directeur": Profil(
        id="directeur",
        libelle="Directeur",
        postures=("gardien", "explorateur"),
        methodes=("okr", "benefits"),
        competences=(
            "faciliter_decision", "mesurer_outcome", "evaluer_risque", "analyser_impact",
        ),
        domaines=(),
        autorite="decision",
        confiance=1.0,
        source="explicite",
        inconnu=False,
    ),
    "support": Profil(
        id="support",
        libelle="Support",
        postures=("operateur", "investigateur"),
        methodes=("kanban", "postmortem", "capa"),
        competences=(
            "analyser_impact", "verifier_preuve", "rechercher_memoire",
            "detecter_contradiction",
        ),
        domaines=(),
        autorite="proposition",
        confiance=1.0,
        source="explicite",
        inconnu=False,
    ),
    "risque": Profil(
        id="risque",
        libelle="Risque et conformité",
        postures=("gardien", "investigateur"),
        methodes=("raid", "capa", "a3"),
        competences=(
            "verifier_preuve", "detecter_contradiction", "evaluer_risque",
            "rechercher_memoire",
        ),
        domaines=(),
        autorite="approbation",
        confiance=1.0,
        source="explicite",
        inconnu=False,
    ),
    "data_steward": Profil(
        id="data_steward",
        libelle="Data steward",
        postures=("gardien", "investigateur"),
        methodes=("dama", "impact_mapping"),
        competences=(
            "qualifier_donnee", "rechercher_memoire", "analyser_impact", "verifier_preuve",
        ),
        domaines=(),
        autorite="proposition",
        confiance=1.0,
        source="explicite",
        inconnu=False,
    ),
    "architecte": Profil(
        id="architecte",
        libelle="Architecte",
        postures=("concepteur", "explorateur"),
        methodes=("adr", "impact_mapping"),
        competences=(
            "lire_interfaces", "analyser_impact", "rediger_adr",
            "tracer_chemin", "evaluer_risque",
        ),
        domaines=(),
        autorite="proposition",
        confiance=1.0,
        source="explicite",
        inconnu=False,
    ),
    "generaliste": Profil(
        id="generaliste",
        libelle="Généraliste",
        postures=("explorateur",),
        methodes=(),
        competences=("rechercher_memoire", "faciliter_decision"),
        domaines=(),
        autorite="lecture",
        confiance=0.3,
        source="defaut",
        inconnu=True,
    ),
}

_ALIAS_SOURCES: dict[str, tuple[str, ...]] = {
    "business_analyst": (
        "business analyst", "business analyste", "business analysis", "ba",
        "analyste affaires", "analyste d affaires", "analyste metier", "analyse metier",
    ),
    "analyste_fonctionnel": (
        "analyste fonctionnel", "analyste fonctionnelle", "functional analyst", "af",
        "analyste si", "analyste systeme", "analyste fonctionnel si",
    ),
    "developpeur": (
        "developpeur", "developpeuse", "developpeurs", "developpeuses", "dev", "developer",
        "software engineer", "ingenieur logiciel", "ingenieure logiciel", "programmeur",
        "programmeuse", "tech lead", "lead developer", "developpeur full stack",
        "developpeur backend", "developpeur frontend", "developpeur web",
        "ingenieur developpement", "qa engineer", "testeur", "testeuse", "developpement",
    ),
    "product_owner": (
        "product owner", "product owners", "po", "proprietaire du produit", "owner produit",
        "product manager", "chef de produit", "responsable produit", "produit",
    ),
    "scrum_master": (
        "scrum master", "scrum masters", "sm", "agile coach", "coach agile", "coach scrum",
        "facilitateur agile",
    ),
    "chef_projet": (
        "chef de projet", "chef de projets", "cheffe de projet", "project manager",
        "project lead", "chef de projet si", "chef de projet informatique",
        "directeur de projet", "directrice de projet", "gestionnaire de projet", "pmo",
        "bureau des projets", "projet",
    ),
    "directeur": (
        "directeur", "directrice", "direction", "directeur general", "directrice generale",
        "dg", "daf", "dsi", "cio", "cto", "ceo", "chief", "executive", "sponsor",
        "sponsor executif", "directeur metier", "directeur informatique",
        "chief information officer", "chief technology officer", "chief executive officer",
    ),
    "support": (
        "support", "support technique", "service desk", "helpdesk", "help desk",
        "technicien support", "technicienne support", "agent support", "exploitation",
        "support production", "run", "sre", "operateur support", "customer support",
        "support client", "assistance",
    ),
    "risque": (
        "risque", "risques", "risk", "risk manager", "gestionnaire de risque",
        "gestionnaire des risques", "conformite", "compliance", "compliance officer",
        "controleur", "controleur interne", "auditeur", "audit interne", "risk officer",
        "cro", "rssi", "controle interne",
    ),
    "data_steward": (
        "data steward", "data stewards", "intendant des donnees", "referent donnees",
        "referente donnees", "gestionnaire de donnees", "data owner", "data manager",
        "qualiticien donnees", "data steward metier", "data analyst", "analyste data",
        "analyste donnees", "responsable data", "data", "donnees", "lignage",
    ),
    "architecte": (
        "architecte", "architecte solution", "architecte logiciel", "architecte technique",
        "architecte entreprise", "architecte d entreprise", "architect", "solution architect",
        "enterprise architect", "technical architect", "urbaniste si", "architecte si",
        "architecte data", "architecture",
    ),
    "generaliste": (
        "generaliste", "generalist", "autre", "autres", "collaborateur", "collaboratrice",
        "utilisateur", "utilisatrice", "user",
    ),
}

MOTS_CLES_INFERENCE: dict[str, tuple[str, ...]] = {
    "developpeur": (
        "api", "apis", "code", "test", "tests", "endpoint", "endpoints", "bug", "bugs",
        "implementation", "pull request", "revue de code", "microservice",
        "developpement logiciel",
    ),
    "product_owner": (
        "priorite", "priorites", "priorisation", "roadmap", "roadmaps", "benefice",
        "benefices", "backlog", "valeur produit", "okr", "okrs",
    ),
    "support": (
        "incident", "incidents", "sla", "production", "panne", "pannes", "ticket",
        "tickets", "outage", "support", "indisponibilite", "service degrade",
    ),
    "risque": (
        "risque", "risques", "conformite", "controle", "controles", "audit", "audits",
        "reglementation", "regulation", "vulnerabilite", "vulnerabilites",
    ),
    "business_analyst": (
        "besoin", "besoins", "user story", "user stories", "story", "exigence",
        "exigences", "cadrage", "expression de besoin",
    ),
    "analyste_fonctionnel": (
        "processus", "process", "bpmn", "specification", "specifications", "flux metier",
        "analyse fonctionnelle",
    ),
    "architecte": (
        "architecture", "architectures", "interface", "interfaces", "integration",
        "integrations", "adr", "urbanisation", "cartographie applicative",
    ),
    "data_steward": (
        "data", "donnees", "lignage", "lineage", "referentiel", "referentiels",
        "qualite des donnees", "dictionnaire de donnees",
    ),
    "directeur": (
        "budget", "budgets", "arbitrage", "arbitrages", "decision", "decisions", "comite",
        "comites", "strategie", "strategies", "investissement", "direction",
    ),
    "scrum_master": (
        "scrum", "sprint", "sprints", "agile", "retrospective", "retrospectives",
        "facilitation", "obstacle",
    ),
    "chef_projet": (
        "planning", "jalon", "jalons", "livrable", "livrables", "coordination projet",
        "suivi projet",
    ),
}


def _normaliser(valeur: str) -> str:
    """Normalise un libellé : minuscules, sans accents, séparateurs ramenés à l'espace."""
    texte = unicodedata.normalize("NFKD", valeur)
    texte = "".join(caractere for caractere in texte if not unicodedata.combining(caractere))
    return re.sub(r"[^a-z0-9]+", " ", texte.casefold()).strip()


def _construire_alias() -> dict[str, str]:
    """Construit la table des identifiants, libellés et alias normalisés."""
    alias: dict[str, str] = {}
    for identifiant, profil in CATALOGUE_PROFILS.items():
        alias.setdefault(_normaliser(identifiant), identifiant)
        alias.setdefault(_normaliser(profil.libelle), identifiant)
        for libelle in _ALIAS_SOURCES.get(identifiant, ()):
            alias.setdefault(_normaliser(libelle), identifiant)
    return alias


_ALIAS = _construire_alias()
_ALIAS_TRIES = tuple(
    sorted(_ALIAS, key=lambda libelle: (-len(libelle.split()), -len(libelle), libelle))
)
_MOTS_CLES_NORMALISES = tuple(
    (identifiant, tuple(dict.fromkeys(_normaliser(mot) for mot in mots)))
    for identifiant, mots in MOTS_CLES_INFERENCE.items()
)


def _profil_pour_libelle(valeur: str) -> Profil | None:
    """Retrouve un profil par identifiant ou alias, exact puis par mots contenus."""
    texte = _normaliser(valeur)
    if not texte:
        return None
    identifiant = _ALIAS.get(texte)
    if identifiant is not None:
        return CATALOGUE_PROFILS[identifiant]
    jetons = set(texte.split())
    for alias in _ALIAS_TRIES:
        mots = alias.split()
        if len(mots) == 1 and len(alias) <= 3:
            continue
        if set(mots) <= jetons:
            return CATALOGUE_PROFILS[_ALIAS[alias]]
    return None


def _valeurs_identite(valeur: Any) -> tuple[str, ...]:
    """Rend les chaînes exploitables d'une valeur d'identité, sans lever sur un champ vide."""
    if isinstance(valeur, str):
        return (valeur,)
    if isinstance(valeur, (list, tuple)):
        return tuple(element for element in valeur if isinstance(element, str))
    if isinstance(valeur, (set, frozenset)):
        return tuple(sorted(element for element in valeur if isinstance(element, str)))
    return ()


def _domaines(valeur: Any, nom: str) -> tuple[str, ...]:
    """Conserve les domaines comme contexte, dans l'ordre reçu et sans doublon exact."""
    if valeur is None:
        return ()
    if isinstance(valeur, str):
        valeurs: Iterable[Any] = (valeur,)
    elif isinstance(valeur, (bytes, bytearray, Mapping)):
        raise TypeError(f"{nom} doit être une chaîne ou un itérable de chaînes")
    else:
        try:
            valeurs = tuple(valeur)
        except TypeError as erreur:
            raise TypeError(f"{nom} doit être une chaîne ou un itérable de chaînes") from erreur
    resultat: list[str] = []
    for element in valeurs:
        if not isinstance(element, str):
            raise TypeError(f"chaque élément de {nom} doit être une chaîne")
        propre = element.strip()
        if propre and propre not in resultat:
            resultat.append(propre)
    return tuple(resultat)


def _plafond(autorite_max: str | None) -> str | None:
    """Valide le plafond d'autorité demandé."""
    if autorite_max is None:
        return None
    if not isinstance(autorite_max, str):
        raise TypeError("autorite_max doit être une chaîne ou None")
    if autorite_max not in AUTORITES:
        raise ValueError(f"autorite_max invalide : {autorite_max}")
    return autorite_max


def _borner(autorite: str, plafond: str | None) -> str:
    """Abaisse une autorité au plafond sans jamais la relever."""
    if plafond is None or _ORDRE_AUTORITE[autorite] <= _ORDRE_AUTORITE[plafond]:
        return autorite
    return plafond


def _avec_domaines(profil: Profil, domaines: tuple[str, ...]) -> Profil:
    """Copie un profil en conservant les domaines fournis comme contexte."""
    if profil.domaines == domaines:
        return profil
    return replace(profil, domaines=domaines)


def _profil_explicite(profil: Profil, domaines: tuple[str, ...], plafond: str | None) -> Profil:
    """Rend un profil explicitement demandé, avec son autorité de catalogue bornée."""
    return replace(
        _avec_domaines(profil, domaines),
        source="explicite",
        confiance=1.0,
        autorite=_borner(profil.autorite, plafond),
    )


def _profil_identite(profil: Profil, domaines: tuple[str, ...], plafond: str | None) -> Profil:
    """Rend un profil déduit d'une identité déclarée, sans inférence de question."""
    return replace(
        _avec_domaines(profil, domaines),
        source="identite",
        confiance=0.9,
        autorite=_borner(profil.autorite, plafond),
    )


def _profil_infere(profil: Profil, domaines: tuple[str, ...], confiance: float,
                   plafond: str | None) -> Profil:
    """Rend un profil inféré : l'inférence ne confère jamais plus que la lecture."""
    return replace(
        _avec_domaines(profil, domaines),
        source="infere",
        confiance=confiance,
        autorite=_borner("lecture", plafond),
        inconnu=False,
    )


def _profil_defaut(domaines: tuple[str, ...], plafond: str | None,
                   confiance: float = 0.25) -> Profil:
    """Rend le profil généraliste inconnu, en lecture seule."""
    base = CATALOGUE_PROFILS["generaliste"]
    return replace(
        _avec_domaines(base, domaines),
        source="defaut",
        confiance=confiance,
        autorite=_borner("lecture", plafond),
        inconnu=True,
    )


def _profil_depuis_identite(identite: Mapping[str, Any]) -> Profil | None:
    """Cherche un profil dans les champs d'identité, dans l'ordre de priorité déclaré."""
    for cle in ("role", "poste", "fonction", "equipe", "groups", "persona"):
        if cle not in identite:
            continue
        for valeur in _valeurs_identite(identite[cle]):
            profil = _profil_pour_libelle(valeur)
            if profil is not None:
                return profil
    return None


def _profil_depuis_question(question: str) -> tuple[Profil, float] | None:
    """Retrouve le profil le plus spécifique par mots-clés, sans modèle ni hasard."""
    texte = f" {_normaliser(question)} "
    meilleur: tuple[int, int, str] | None = None
    for rang, (identifiant, mots) in enumerate(_MOTS_CLES_NORMALISES):
        trouves = sum(1 for mot in mots if f" {mot} " in texte)
        if trouves == 0:
            continue
        cle = (trouves, -rang, identifiant)
        if meilleur is None or cle[:2] > meilleur[:2]:
            meilleur = cle
    if meilleur is None:
        return None
    trouves, _, identifiant = meilleur
    confiance = min(0.8, 0.55 + 0.1 * (trouves - 1))
    return CATALOGUE_PROFILS[identifiant], confiance


def resoudre_profil(
    profil: str | None = None,
    identite: Mapping[str, Any] | None = None,
    question: str = "",
    domaines: Iterable[str] = (),
    autorite_max: str | None = None,
) -> Profil:
    """Résout un profil par composition, sans jamais accorder d'autorité par inférence.

    Priorité : profil explicite reconnu, identité déclarée, mots-clés de la question, puis
    généraliste inconnu en lecture seule. Un identifiant explicite inconnu ne déclenche pas
    l'inférence : il retombe sur le défaut en signalant ``inconnu=True``. Les domaines
    fournis restent un contexte et ne sont jamais interprétés comme des packs connus.
    """
    if profil is not None and not isinstance(profil, str):
        raise TypeError("profil doit être une chaîne ou None")
    if identite is not None and not isinstance(identite, Mapping):
        raise TypeError("identite doit être un mapping ou None")
    if not isinstance(question, str):
        raise TypeError("question doit être une chaîne")
    plafond = _plafond(autorite_max)
    contextes = list(_domaines(domaines, "domaines"))
    if identite is not None:
        for domaine in _domaines(identite.get("domaines"), "identite.domaines"):
            if domaine not in contextes:
                contextes.append(domaine)
    contexte = tuple(contextes)

    if profil is not None:
        trouve = _profil_pour_libelle(profil)
        if trouve is not None:
            return _profil_explicite(trouve, contexte, plafond)
        return _profil_defaut(contexte, plafond, confiance=0.2)

    if identite is not None:
        trouve = _profil_depuis_identite(identite)
        if trouve is not None:
            return _profil_identite(trouve, contexte, plafond)

    infere = _profil_depuis_question(question)
    if infere is not None:
        trouve, confiance = infere
        return _profil_infere(trouve, contexte, confiance, plafond)

    return _profil_defaut(contexte, plafond)


def _autorite(valeur: str | Profil) -> str:
    """Extrait et valide une autorité depuis un profil ou une chaîne."""
    if isinstance(valeur, Profil):
        return valeur.autorite
    if not isinstance(valeur, str):
        raise TypeError("l'autorité doit être un profil ou une chaîne")
    if valeur not in AUTORITES:
        raise ValueError(f"autorité invalide : {valeur}")
    return valeur


def autorite_superieure(a: str | Profil, b: str | Profil) -> bool:
    """Indique si l'autorité ``a`` est strictement supérieure à l'autorité ``b``."""
    return _ORDRE_AUTORITE[_autorite(a)] > _ORDRE_AUTORITE[_autorite(b)]


def autorise(profil: Profil, action: str) -> bool:
    """Indique si le profil possède l'autorité requise pour une action nommée."""
    if not isinstance(profil, Profil):
        raise TypeError("profil doit être un Profil")
    if not isinstance(action, str):
        raise TypeError("action doit être une chaîne")
    requise = _ACTIONS.get(_normaliser(action))
    if requise is None:
        raise ValueError(f"action inconnue : {action}")
    return _ORDRE_AUTORITE[profil.autorite] >= _ORDRE_AUTORITE[requise]
