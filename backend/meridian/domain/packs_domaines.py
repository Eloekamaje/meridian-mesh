"""Packs de domaine : chargement borné et validation contre les catalogues existants.

Un pack de domaine n'invente ni méthode, ni compétence, ni spécialiste. Il assemble des fiches
déjà présentes dans les catalogues, déclare un périmètre, des questions d'évaluation et une
frontière d'autorité en lecture seule. Le chargeur ne lit aucune source métier et n'appelle
aucun modèle.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any
import unicodedata

from meridian.domain import competences_cognitives, methodes_cognitives, profils

__all__ = [
    "AUTORITES",
    "DOSSIER_PACKS",
    "MAX_OCTETS_PACK",
    "PackInvalide",
    "PackDomaine",
    "charger_pack",
    "charger_packs",
    "pack_par_id",
    "resoudre_pack",
    "valider_pack",
    "valider_packs",
]

SCHEMA_PACK = "meridian.domain-pack/1"
MAX_OCTETS_PACK = 200_000
NB_EVALUATIONS_MIN = 3
NB_EVALUATIONS_MAX = 5
AUTORITES = ("lecture", "proposition", "approbation", "decision", "action")
DOSSIER_PACKS = Path(__file__).resolve().parents[3] / "plugin" / "meridian" / "domain-packs"

_CHAMPS_PACK = {
    "schema", "id", "nom", "version", "description", "scope", "profils",
    "methodes", "competences", "specialistes", "autorite", "evaluations",
}
_CHAMPS_SCOPE = {
    "domaines", "applications", "situations", "processus", "questions_types",
    "perimetre", "hors_perimetre",
}
_CHAMPS_AUTORITE = {
    "niveau_max", "lecture_seule", "ecriture", "promotion", "execution",
    "approbation_humaine", "limite",
}
_CHAMPS_EVALUATION = {"id", "question", "expected_evidence", "answer_key"}
_CHAMPS_ANSWER_KEY = {"claims", "decision", "forbidden", "abstention"}


class PackInvalide(ValueError):
    """Le pack ne respecte pas le schéma ou référence un élément hors catalogue."""


def _texte(valeur: Any, champ: str, maximum: int = 4000) -> str:
    if not isinstance(valeur, str):
        raise PackInvalide(f"{champ} : chaîne attendue")
    texte = " ".join(valeur.split())
    if not texte:
        raise PackInvalide(f"{champ} : valeur vide")
    if len(texte) > maximum:
        raise PackInvalide(f"{champ} : valeur trop longue")
    return texte


def _normaliser(valeur: Any) -> str:
    texte = unicodedata.normalize("NFKD", str(valeur or ""))
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", texte.lower()).strip("_")


def _liste_textes(valeur: Any, champ: str, *, obligatoire: bool = False) -> tuple[str, ...]:
    if valeur is None:
        if obligatoire:
            raise PackInvalide(f"{champ} : liste obligatoire")
        return ()
    if not isinstance(valeur, (list, tuple)):
        raise PackInvalide(f"{champ} : liste attendue")
    resultat: list[str] = []
    for element in valeur:
        texte = _texte(element, champ, 500)
        if texte not in resultat:
            resultat.append(texte)
    if obligatoire and not resultat:
        raise PackInvalide(f"{champ} : liste vide")
    return tuple(resultat)


def _mapping(valeur: Any, champ: str) -> dict:
    if not isinstance(valeur, Mapping):
        raise PackInvalide(f"{champ} : objet attendu")
    return dict(valeur)


def _champs_inconnus(valeur: Mapping, autorises: set[str], champ: str) -> None:
    inconnus = sorted(set(valeur) - autorises)
    if inconnus:
        raise PackInvalide(f"{champ} : champ inconnu {inconnus[0]}")


def _booleen(valeur: Any, champ: str) -> bool:
    if not isinstance(valeur, bool):
        raise PackInvalide(f"{champ} : booléen attendu")
    return valeur


def _lire_borne(chemin: Path) -> str:
    try:
        taille = chemin.stat().st_size
    except OSError as erreur:
        raise PackInvalide(f"pack illisible : {type(erreur).__name__}") from erreur
    if taille > MAX_OCTETS_PACK:
        raise PackInvalide("pack : fichier trop long")
    try:
        return chemin.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as erreur:
        raise PackInvalide(f"pack illisible : {type(erreur).__name__}") from erreur


def _charger_json(chemin: Path) -> Mapping:
    try:
        donnees = json.loads(_lire_borne(chemin))
    except json.JSONDecodeError as erreur:
        raise PackInvalide(
            f"JSON invalide (ligne {erreur.lineno}, colonne {erreur.colno})") from erreur
    if not isinstance(donnees, Mapping):
        raise PackInvalide("pack : objet JSON attendu")
    return donnees


@dataclass(frozen=True)
class EvaluationPack:
    """Une question d'évaluation avec ses preuves attendues et sa clé de réponse."""

    id: str
    question: str
    expected_evidence: tuple[str, ...]
    answer_key: dict = field(default_factory=dict)

    def __post_init__(self):
        identifiant = _normaliser(self.id)
        if not identifiant:
            raise PackInvalide("évaluation : id obligatoire")
        object.__setattr__(self, "id", identifiant)
        object.__setattr__(self, "question", _texte(self.question, "évaluation.question"))
        object.__setattr__(
            self, "expected_evidence",
            _liste_textes(self.expected_evidence, "évaluation.expected_evidence", obligatoire=True))
        cle = _mapping(self.answer_key, "évaluation.answer_key")
        _champs_inconnus(cle, _CHAMPS_ANSWER_KEY, "évaluation.answer_key")
        claims = _liste_textes(cle.get("claims"), "évaluation.answer_key.claims", obligatoire=True)
        decision = _texte(cle.get("decision"), "évaluation.answer_key.decision")
        forbidden = _liste_textes(cle.get("forbidden"), "évaluation.answer_key.forbidden")
        abstention = _texte(cle.get("abstention"), "évaluation.answer_key.abstention")
        object.__setattr__(self, "answer_key", {
            "claims": list(claims),
            "decision": decision,
            "forbidden": list(forbidden),
            "abstention": abstention,
        })

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "question": self.question,
            "expected_evidence": list(self.expected_evidence),
            "answer_key": {
                "claims": list(self.answer_key["claims"]),
                "decision": self.answer_key["decision"],
                "forbidden": list(self.answer_key["forbidden"]),
                "abstention": self.answer_key["abstention"],
            },
        }


@dataclass(frozen=True)
class AutoritePack:
    """Frontière d'autorité du pack : lecture seule, aucune écriture ni décision."""

    niveau_max: str = "lecture"
    lecture_seule: bool = True
    ecriture: bool = False
    promotion: bool = False
    execution: bool = False
    approbation_humaine: bool = True
    limite: str = ""

    def __post_init__(self):
        niveau = _normaliser(self.niveau_max)
        if niveau not in AUTORITES:
            raise PackInvalide(f"autorité inconnue : {self.niveau_max!r}")
        lecture_seule = _booleen(self.lecture_seule, "autorite.lecture_seule")
        ecriture = _booleen(self.ecriture, "autorite.ecriture")
        promotion = _booleen(self.promotion, "autorite.promotion")
        execution = _booleen(self.execution, "autorite.execution")
        if not lecture_seule or ecriture or promotion or execution:
            raise PackInvalide(
                "autorite : un pack de domaine est en lecture seule, sans écriture, promotion ni exécution")
        if AUTORITES.index(niveau) > AUTORITES.index("proposition"):
            raise PackInvalide(
                "autorite.niveau_max : un pack de domaine ne dépasse pas proposition")
        object.__setattr__(self, "niveau_max", niveau)
        object.__setattr__(self, "lecture_seule", lecture_seule)
        object.__setattr__(self, "ecriture", ecriture)
        object.__setattr__(self, "promotion", promotion)
        object.__setattr__(self, "execution", execution)
        object.__setattr__(
            self, "approbation_humaine",
            _booleen(self.approbation_humaine, "autorite.approbation_humaine"))
        object.__setattr__(self, "limite", _texte(self.limite, "autorite.limite"))

    def as_dict(self) -> dict:
        return {
            "niveau_max": self.niveau_max,
            "lecture_seule": self.lecture_seule,
            "ecriture": self.ecriture,
            "promotion": self.promotion,
            "execution": self.execution,
            "approbation_humaine": self.approbation_humaine,
            "limite": self.limite,
        }


@dataclass(frozen=True)
class PackDomaine:
    """Un pack validé : périmètre, catalogues activés, évaluations et autorité."""

    id: str
    nom: str
    version: str
    description: str
    scope: dict
    profils: tuple[str, ...]
    methodes: tuple[str, ...]
    competences: tuple[str, ...]
    specialistes: tuple[str, ...]
    autorite: AutoritePack
    evaluations: tuple[EvaluationPack, ...]
    schema: str = SCHEMA_PACK

    def __post_init__(self):
        identifiant = _normaliser(self.id)
        if not identifiant:
            raise PackInvalide("id de pack obligatoire")
        if self.schema != SCHEMA_PACK:
            raise PackInvalide(f"schéma de pack inconnu : {self.schema!r}")
        object.__setattr__(self, "id", identifiant)
        object.__setattr__(self, "nom", _texte(self.nom, "nom", 240))
        object.__setattr__(self, "version", _texte(self.version, "version", 40))
        object.__setattr__(self, "description", _texte(self.description, "description", 2000))

        scope = _mapping(self.scope, "scope")
        _champs_inconnus(scope, _CHAMPS_SCOPE, "scope")
        if not _liste_textes(scope.get("domaines"), "scope.domaines", obligatoire=True):
            raise PackInvalide("scope.domaines : liste vide")
        scope_normalise = {}
        for cle in ("domaines", "applications", "situations", "processus", "questions_types"):
            scope_normalise[cle] = list(
                _liste_textes(scope.get(cle), f"scope.{cle}"))
        for cle in ("perimetre", "hors_perimetre"):
            scope_normalise[cle] = _texte(scope.get(cle), f"scope.{cle}")
        object.__setattr__(self, "scope", scope_normalise)

        profils_pack = _liste_textes(self.profils, "profils")
        inconnus = [profil for profil in profils_pack
                    if profils.resoudre_profil(profil=profil).inconnu]
        if inconnus:
            raise PackInvalide(f"profil inconnu : {inconnus[0]}")
        try:
            methodes = methodes_cognitives.valider_methodes(self.methodes)
        except ValueError as erreur:
            raise PackInvalide(f"methodes : {erreur}") from erreur
        if not methodes:
            raise PackInvalide("methodes : liste vide")
        try:
            competences = competences_cognitives.valider_competences(self.competences)
        except ValueError as erreur:
            raise PackInvalide(f"competences : {erreur}") from erreur
        if not competences:
            raise PackInvalide("competences : liste vide")
        specialistes = _liste_textes(self.specialistes, "specialistes", obligatoire=True)
        inconnus = [specialiste for specialiste in specialistes
                    if _normaliser(specialiste) not in competences_cognitives.SPECIALISTES]
        if inconnus:
            raise PackInvalide(f"spécialiste inconnu : {inconnus[0]}")

        autorite = self.autorite
        if isinstance(autorite, Mapping):
            autorite = _mapping(autorite, "autorite")
            _champs_inconnus(autorite, _CHAMPS_AUTORITE, "autorite")
            autorite = AutoritePack(**autorite)
        if not isinstance(autorite, AutoritePack):
            raise PackInvalide("autorite : objet attendu")

        evaluations: list[EvaluationPack] = []
        if not isinstance(self.evaluations, (list, tuple)):
            raise PackInvalide("evaluations : liste attendue")
        if not NB_EVALUATIONS_MIN <= len(self.evaluations) <= NB_EVALUATIONS_MAX:
            raise PackInvalide(
                f"evaluations : entre {NB_EVALUATIONS_MIN} et {NB_EVALUATIONS_MAX} questions attendues")
        for brut in self.evaluations:
            if isinstance(brut, EvaluationPack):
                evaluation = brut
            elif isinstance(brut, Mapping):
                brut = _mapping(brut, "evaluation")
                _champs_inconnus(brut, _CHAMPS_EVALUATION, "evaluation")
                evaluation = EvaluationPack(**brut)
            else:
                raise PackInvalide("evaluation : objet attendu")
            if any(existante.id == evaluation.id for existante in evaluations):
                raise PackInvalide(f"évaluation {evaluation.id} : identifiant déjà présent")
            evaluations.append(evaluation)

        object.__setattr__(self, "profils", tuple(_normaliser(p) for p in profils_pack))
        object.__setattr__(self, "methodes", tuple(methode.id for methode in methodes))
        object.__setattr__(self, "competences", tuple(competence.id for competence in competences))
        object.__setattr__(self, "specialistes", tuple(_normaliser(s) for s in specialistes))
        object.__setattr__(self, "autorite", autorite)
        object.__setattr__(self, "evaluations", tuple(evaluations))

    def as_dict(self) -> dict:
        return {
            "schema": self.schema,
            "id": self.id,
            "nom": self.nom,
            "version": self.version,
            "description": self.description,
            "scope": {
                cle: (list(valeur) if isinstance(valeur, list) else valeur)
                for cle, valeur in self.scope.items()
            },
            "profils": list(self.profils),
            "methodes": list(self.methodes),
            "competences": list(self.competences),
            "specialistes": list(self.specialistes),
            "autorite": self.autorite.as_dict(),
            "evaluations": [evaluation.as_dict() for evaluation in self.evaluations],
        }


def _depuis_mapping(donnees: Mapping) -> PackDomaine:
    donnees = dict(donnees)
    _champs_inconnus(donnees, _CHAMPS_PACK, "pack")
    try:
        return PackDomaine(**donnees)
    except TypeError as erreur:
        raise PackInvalide(f"pack : {erreur}") from erreur


def _charger_source(source: Any) -> PackDomaine:
    if isinstance(source, PackDomaine):
        return source
    if isinstance(source, Mapping):
        return _depuis_mapping(source)
    if isinstance(source, Path):
        return _depuis_mapping(_charger_json(source))
    if isinstance(source, str):
        if source.lstrip().startswith("{"):
            try:
                donnees = json.loads(source)
            except json.JSONDecodeError as erreur:
                raise PackInvalide(
                    f"JSON invalide (ligne {erreur.lineno}, colonne {erreur.colno})") from erreur
            if not isinstance(donnees, Mapping):
                raise PackInvalide("pack : objet JSON attendu")
            return _depuis_mapping(donnees)
        return _depuis_mapping(_charger_json(Path(source)))
    raise PackInvalide("pack : chemin, identifiant, objet JSON ou fiche attendu")


def charger_pack(source: Any, dossier: Any = None) -> PackDomaine:
    """Charge un pack par identifiant, chemin, objet JSON ou fiche déjà validée."""
    if isinstance(source, str) and not source.lstrip().startswith("{"):
        if "/" not in source and "\\" not in source and not source.endswith(".json"):
            for pack in charger_packs(dossier):
                if pack.id == _normaliser(source):
                    return pack
            raise PackInvalide(f"pack inconnu : {source}")
    return _charger_source(source)


def charger_packs(dossier: Any = None) -> tuple[PackDomaine, ...]:
    """Charge tous les packs ``*.json`` d'un dossier, par ordre d'identifiant."""
    racine = Path(dossier) if dossier is not None else DOSSIER_PACKS
    if not racine.is_dir():
        raise PackInvalide(f"dossier de packs introuvable : {racine}")
    packs: list[PackDomaine] = []
    for chemin in sorted(racine.glob("*.json")):
        pack = _charger_source(chemin)
        if any(existant.id == pack.id for existant in packs):
            raise PackInvalide(f"pack {pack.id} : identifiant déjà présent")
        packs.append(pack)
    return tuple(sorted(packs, key=lambda pack: pack.id))


def pack_par_id(identifiant: Any, dossier: Any = None) -> PackDomaine | None:
    """Rend le pack portant cet identifiant, ou ``None`` s'il n'existe pas."""
    cle = _normaliser(identifiant)
    if not cle:
        return None
    for pack in charger_packs(dossier):
        if pack.id == cle:
            return pack
    return None


def resoudre_pack(source: Any, dossier: Any = None) -> PackDomaine:
    """Résout un pack par identifiant lisible, puis par chemin/objet si nécessaire."""
    return charger_pack(source, dossier)


def valider_pack(source: Any) -> dict:
    """Valide un pack et rend un rapport JSON-safe, sans exécution ni lecture métier."""
    try:
        pack = charger_pack(source)
    except PackInvalide as erreur:
        return {"valide": False, "erreurs": [str(erreur)], "schema": SCHEMA_PACK}
    return {"valide": True, "erreurs": [], "schema": SCHEMA_PACK, "pack": pack.as_dict()}


def valider_packs(dossier: Any = None) -> dict:
    """Valide tous les packs d'un dossier."""
    try:
        packs = charger_packs(dossier)
    except PackInvalide as erreur:
        return {"valide": False, "packs": 0, "erreurs": [str(erreur)], "schema": SCHEMA_PACK}
    return {
        "valide": True,
        "packs": len(packs),
        "erreurs": [],
        "schema": SCHEMA_PACK,
        "ids": [pack.id for pack in packs],
    }


if __name__ == "__main__":
    print(json.dumps(valider_packs(), ensure_ascii=False, indent=2))
