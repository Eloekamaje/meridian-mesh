"""Registre capacitaire du harness d'outils de Méridian (ADR-0004).

Un manifeste est un contrat : il déclare une capacité d'entreprise, les objets lus et écrits, les schémas d'entrée
et de sortie, la portée, le coût, le délai maximal, le mode de preuve et les effets de bord. Le registre valide,
versionne, filtre et décrit ces contrats. Il n'exécute aucun outil, ne charge aucun code et n'appelle aucun service.
Les trois outils historiques sont livrés comme adaptateurs déclarés, jamais comme noyau.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import math
import re
from types import MappingProxyType
from typing import Any, Iterable
import unicodedata

CAPACITES = (
    "situer",
    "observer",
    "lire_claims",
    "prouver",
    "relier",
    "maturer",
    "investiguer",
    "decider",
    "agir",
    "mesurer",
    "apprendre",
    "concevoir",
    "mobiliser_expert",
    "chercher_outil",
)
MODES_PREUVE = ("DECLARED", "OBSERVED", "INFERRED", "PROPOSED", "AUCUNE")
SOURCES = ("builtin", "mcp", "manifeste", "openapi", "graphql", "grpc", "asyncapi", "interface")
AXES_PORTEE = ("tenant", "acteur", "perimetre")

_SLUG = r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$"
_VERSION = (
    r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:-([0-9A-Za-z.-]+))?(?:\+([0-9A-Za-z.-]+))?$"
)
_URL = r"(?i)(?:[a-z][a-z0-9+.\-]*://|(?<![\w.])www\.[a-z0-9])"
_HTML = r"<\s*/?\s*[a-zA-Z][^>]*>"
_AFFECTATION_SENSIBLE = (
    r"(?i)(?:api[_-]?key|apikey|access[_-]?token|auth[_-]?token|client[_-]?secret|"
    r"password|passwd|mot[\s_-]*de[\s_-]*passe|secret|token)\s*[:=]\s*['\"]?[A-Za-z0-9_./+~-]{6,}"
)
_JETON_BEARER = r"(?i)\bbearer\s+[A-Za-z0-9_.~+/=-]{12,}"
_CLE_SENSIBLE = (
    r"(?i)(?:api[_-]?key|apikey|access[_-]?token|auth[_-]?token|client[_-]?secret|"
    r"password|passwd|mot[_-]?de[_-]?passe|secret|token)"
)
_VALEURS_EXEMPLE = ("default", "example", "examples", "const", "enum", "value")
_MAX_SCHEMA_PROFONDEUR = 32


class ErreurRegistre(ValueError):
    """Erreur de contrat ou de version du registre."""


class ManifesteInvalide(ErreurRegistre):
    """Le manifeste ne respecte pas les règles de sûreté du registre."""


class ConflitManifeste(ErreurRegistre):
    """Le manifeste entre en conflit avec une version déjà enregistrée."""


class Portee(dict):
    """Vue groupée des trois axes de portée, lisible par clé ou par attribut."""

    __slots__ = ()

    def __getattr__(self, nom: str) -> Any:
        if nom in AXES_PORTEE:
            return self.get(nom)
        raise AttributeError(nom)


def _slug(valeur: Any) -> str:
    if not isinstance(valeur, str):
        raise ManifesteInvalide("nom : chaîne attendue")
    nom = valeur.strip()
    if not nom or len(nom) > 80 or not re.fullmatch(_SLUG, nom):
        raise ManifesteInvalide("nom : slug stable attendu (minuscules, chiffres, . _ -)")
    return nom


def _cle_version(version: str) -> tuple[int, int, int, int, str]:
    correspondance = re.fullmatch(_VERSION, version)
    if correspondance is None:
        raise ManifesteInvalide("version : numéro de version attendu")
    majeur = int(correspondance.group(1))
    mineur = int(correspondance.group(2) or 0)
    correctif = int(correspondance.group(3) or 0)
    avant = correspondance.group(4) or ""
    return (majeur, mineur, correctif, 0 if avant else 1, avant)


def _version(valeur: Any) -> str:
    if not isinstance(valeur, str):
        raise ManifesteInvalide("version : chaîne attendue")
    version = valeur.strip()
    if not version:
        raise ManifesteInvalide("version : valeur vide")
    _cle_version(version)
    return version


def _verifier_texte(texte: str, champ: str) -> None:
    if re.search(_URL, texte):
        raise ManifesteInvalide(f"{champ} : URL arbitraire refusée")
    if re.search(_HTML, texte):
        raise ManifesteInvalide(f"{champ} : HTML refusé")
    if re.search(_AFFECTATION_SENSIBLE, texte) or re.search(_JETON_BEARER, texte):
        raise ManifesteInvalide(f"{champ} : secret détecté")


def _description(valeur: Any) -> str:
    if not isinstance(valeur, str):
        raise ManifesteInvalide("description : chaîne attendue")
    description = valeur.strip()
    if not description:
        raise ManifesteInvalide("description : valeur vide")
    if len(description) > 4000:
        raise ManifesteInvalide("description : trop longue")
    _verifier_texte(description, "description")
    return description


def _capacite(valeur: Any) -> str:
    if not isinstance(valeur, str) or valeur.strip() not in CAPACITES:
        raise ManifesteInvalide("capacite : capacité inconnue")
    return valeur.strip()


def _texte_court(valeur: Any, champ: str) -> str:
    if not isinstance(valeur, str):
        raise ManifesteInvalide(f"{champ} : chaîne attendue")
    texte = valeur.strip()
    if not texte:
        raise ManifesteInvalide(f"{champ} : valeur vide")
    if len(texte) > 256:
        raise ManifesteInvalide(f"{champ} : valeur trop longue")
    _verifier_texte(texte, champ)
    return texte


def _liste_textes(valeur: Any, champ: str) -> tuple[str, ...]:
    if valeur is None:
        return ()
    if isinstance(valeur, str):
        valeurs = [valeur]
    elif isinstance(valeur, (set, frozenset)):
        valeurs = sorted(valeur)
    else:
        try:
            valeurs = list(valeur)
        except TypeError as erreur:
            raise ManifesteInvalide(f"{champ} : liste attendue") from erreur
    sortie: list[str] = []
    for element in valeurs:
        texte = _texte_court(element, champ)
        if texte not in sortie:
            sortie.append(texte)
    return tuple(sortie)


def _portee_valeur(valeur: Any, axe: str) -> str | None:
    if valeur is None:
        return None
    if not isinstance(valeur, str):
        raise ManifesteInvalide(f"portee.{axe} : chaîne attendue")
    texte = valeur.strip()
    if not texte:
        return None
    if len(texte) > 128 or any(ord(caractere) < 32 for caractere in texte):
        raise ManifesteInvalide(f"portee.{axe} : valeur invalide")
    _verifier_texte(texte, f"portee.{axe}")
    return texte


def _portee(portee: Any, tenant: Any, acteur: Any, perimetre: Any) -> dict[str, str | None]:
    valeurs: dict[str, str | None] = {axe: None for axe in AXES_PORTEE}
    if portee is not None:
        if not isinstance(portee, Mapping):
            raise ManifesteInvalide("portee : objet attendu")
        inconnus = set(portee) - set(AXES_PORTEE)
        if inconnus:
            raise ManifesteInvalide("portee : axe inconnu")
        for axe in AXES_PORTEE:
            if axe in portee:
                valeurs[axe] = _portee_valeur(portee[axe], axe)
    for axe, valeur in (("tenant", tenant), ("acteur", acteur), ("perimetre", perimetre)):
        if valeur is None:
            continue
        normalisee = _portee_valeur(valeur, axe)
        if valeurs[axe] is not None and normalisee is not None and valeurs[axe] != normalisee:
            raise ManifesteInvalide(f"portee.{axe} : valeurs contradictoires")
        if normalisee is not None:
            valeurs[axe] = normalisee
    return valeurs


def _verifier_valeur_json(valeur: Any, champ: str, profondeur: int) -> None:
    if profondeur > _MAX_SCHEMA_PROFONDEUR:
        raise ManifesteInvalide(f"{champ} : schéma trop profond")
    if valeur is None or isinstance(valeur, (bool, int, str)):
        if isinstance(valeur, str):
            _verifier_texte(valeur, champ)
        return
    if isinstance(valeur, float):
        if not math.isfinite(valeur):
            raise ManifesteInvalide(f"{champ} : nombre non fini")
        return
    if isinstance(valeur, Mapping):
        for cle, contenu in valeur.items():
            if not isinstance(cle, str) or not cle:
                raise ManifesteInvalide(f"{champ} : clé JSON invalide")
            _verifier_texte(cle, champ)
            if re.search(_CLE_SENSIBLE, cle):
                if isinstance(contenu, str) and contenu.strip():
                    raise ManifesteInvalide(f"{champ} : secret détecté")
                if isinstance(contenu, Mapping):
                    for nom in _VALEURS_EXEMPLE:
                        exemple = contenu.get(nom)
                        if isinstance(exemple, str) and exemple.strip():
                            raise ManifesteInvalide(f"{champ} : secret détecté")
            _verifier_valeur_json(contenu, champ, profondeur + 1)
        return
    if isinstance(valeur, (list, tuple)):
        for contenu in valeur:
            _verifier_valeur_json(contenu, champ, profondeur + 1)
        return
    raise ManifesteInvalide(f"{champ} : valeur non compatible JSON")


def _figer(valeur: Any) -> Any:
    if isinstance(valeur, Mapping):
        return MappingProxyType({cle: _figer(contenu) for cle, contenu in valeur.items()})
    if isinstance(valeur, (list, tuple)):
        return tuple(_figer(contenu) for contenu in valeur)
    return valeur


def _schema(valeur: Any, champ: str) -> Any:
    if not isinstance(valeur, (Mapping, bool)):
        raise ManifesteInvalide(f"{champ} : schéma JSON attendu")
    _verifier_valeur_json(valeur, champ, 0)
    return _figer(valeur)


def _liberer(valeur: Any) -> Any:
    if isinstance(valeur, Mapping):
        return {cle: _liberer(contenu) for cle, contenu in valeur.items()}
    if isinstance(valeur, tuple):
        return [_liberer(contenu) for contenu in valeur]
    return valeur


def _lecture_seule(valeur: Any) -> bool:
    if not isinstance(valeur, bool):
        raise ManifesteInvalide("lecture_seule : booléen attendu")
    return valeur


def _cout(valeur: Any) -> float:
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        raise ManifesteInvalide("cout : nombre attendu")
    cout = float(valeur)
    if not math.isfinite(cout) or cout < 0:
        raise ManifesteInvalide("cout : valeur négative ou non finie")
    return cout


def _timeout(valeur: Any) -> int:
    if isinstance(valeur, bool) or not isinstance(valeur, int) or valeur <= 0:
        raise ManifesteInvalide("timeout_ms : entier positif attendu")
    return valeur


def _mode_preuve(valeur: Any) -> str:
    if not isinstance(valeur, str):
        raise ManifesteInvalide("mode_preuve : chaîne attendue")
    mode = valeur.strip().upper()
    if mode not in MODES_PREUVE:
        raise ManifesteInvalide("mode_preuve : mode inconnu")
    return mode


def _source(valeur: Any) -> str:
    if not isinstance(valeur, str):
        raise ManifesteInvalide("source : chaîne attendue")
    source = valeur.strip().lower()
    if source not in SOURCES:
        raise ManifesteInvalide("source : source inconnue")
    return source


def _signature(valeur: Any) -> str | None:
    if valeur is None:
        return None
    if not isinstance(valeur, str):
        raise ManifesteInvalide("signature : chaîne attendue")
    signature = valeur.strip()
    if not signature:
        return None
    if len(signature) > 2048:
        raise ManifesteInvalide("signature : valeur trop longue")
    _verifier_texte(signature, "signature")
    return signature


@dataclass(frozen=True, init=False)
class ManifesteOutil:
    """Contrat déclaratif d'un adaptateur ; aucun champ n'autorise l'exécution ni le chargement de code."""

    nom: str
    version: str
    description: str
    capacite: str
    schema_entree: Any
    schema_sortie: Any
    types_objets_lus: tuple[str, ...] = ()
    types_objets_ecrits: tuple[str, ...] = ()
    tenant: str | None = None
    acteur: str | None = None
    perimetre: str | None = None
    lecture_seule: bool = True
    cout: float = 0.0
    timeout_ms: int = 5000
    mode_preuve: str = "AUCUNE"
    effets_de_bord: tuple[str, ...] = ()
    source: str = "manifeste"
    signature: str | None = None
    allowlist: tuple[str, ...] = ()

    def __init__(
        self,
        nom: Any,
        version: Any,
        description: Any,
        capacite: Any,
        schema_entree: Any,
        schema_sortie: Any,
        types_objets_lus: Any = (),
        types_objets_ecrits: Any = (),
        portee: Any = None,
        tenant: Any = None,
        acteur: Any = None,
        perimetre: Any = None,
        lecture_seule: Any = True,
        cout: Any = 0.0,
        timeout_ms: Any = 5000,
        mode_preuve: Any = "AUCUNE",
        effets_de_bord: Any = (),
        source: Any = "manifeste",
        signature: Any = None,
        allowlist: Any = (),
    ) -> None:
        portee_normalisee = _portee(portee, tenant, acteur, perimetre)
        lus = _liste_textes(types_objets_lus, "types_objets_lus")
        ecrits = _liste_textes(types_objets_ecrits, "types_objets_ecrits")
        effets = _liste_textes(effets_de_bord, "effets_de_bord")
        seul = _lecture_seule(lecture_seule)
        if seul and ecrits:
            raise ManifesteInvalide("lecture seule : des objets sont déclarés écrits")
        if seul and effets:
            raise ManifesteInvalide("lecture seule : des effets de bord sont déclarés")
        if not seul and not effets:
            raise ManifesteInvalide("écriture : effets de bord obligatoires")
        valeurs = {
            "nom": _slug(nom),
            "version": _version(version),
            "description": _description(description),
            "capacite": _capacite(capacite),
            "schema_entree": _schema(schema_entree, "schema_entree"),
            "schema_sortie": _schema(schema_sortie, "schema_sortie"),
            "types_objets_lus": lus,
            "types_objets_ecrits": ecrits,
            "tenant": portee_normalisee["tenant"],
            "acteur": portee_normalisee["acteur"],
            "perimetre": portee_normalisee["perimetre"],
            "lecture_seule": seul,
            "cout": _cout(cout),
            "timeout_ms": _timeout(timeout_ms),
            "mode_preuve": _mode_preuve(mode_preuve),
            "effets_de_bord": effets,
            "source": _source(source),
            "signature": _signature(signature),
            "allowlist": _liste_textes(allowlist, "allowlist"),
        }
        for cle, valeur in valeurs.items():
            object.__setattr__(self, cle, valeur)

    @property
    def portee(self) -> Portee:
        return Portee(tenant=self.tenant, acteur=self.acteur, perimetre=self.perimetre)

    def __hash__(self) -> int:
        return hash((self.nom, self.version))

    def as_dict(self) -> dict:
        return {
            "nom": self.nom,
            "version": self.version,
            "description": self.description,
            "capacite": self.capacite,
            "types_objets_lus": list(self.types_objets_lus),
            "types_objets_ecrits": list(self.types_objets_ecrits),
            "schema_entree": _liberer(self.schema_entree),
            "schema_sortie": _liberer(self.schema_sortie),
            "portee": self.portee,
            "tenant": self.tenant,
            "acteur": self.acteur,
            "perimetre": self.perimetre,
            "lecture_seule": self.lecture_seule,
            "cout": self.cout,
            "timeout_ms": self.timeout_ms,
            "mode_preuve": self.mode_preuve,
            "effets_de_bord": list(self.effets_de_bord),
            "source": self.source,
            "signature": self.signature,
            "allowlist": list(self.allowlist),
        }


def _canonique(manifeste: ManifesteOutil) -> str:
    return json.dumps(
        manifeste.as_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _manifeste(valeur: Any) -> ManifesteOutil:
    if isinstance(valeur, ManifesteOutil):
        return valeur
    if isinstance(valeur, Mapping):
        return ManifesteOutil(**valeur)
    raise TypeError("manifeste attendu")


def _filtre(valeur: Any, nom: str) -> str | None:
    if valeur is None or valeur == "*":
        return None
    if not isinstance(valeur, str):
        raise ManifesteInvalide(f"{nom} : chaîne attendue")
    return valeur.strip() or None


def _autorise(manifeste: ManifesteOutil, tenant: Any, acteur: Any, perimetre: Any) -> bool:
    for axe, demande in (("tenant", tenant), ("acteur", acteur), ("perimetre", perimetre)):
        if demande is None:
            continue
        offre = getattr(manifeste, axe)
        if offre in (None, "*"):
            continue
        if offre != demande:
            return False
    return True


def _normaliser_texte(texte: Any) -> str:
    decompose = unicodedata.normalize("NFKD", str(texte or "").lower())
    sans_accents = "".join(caractere for caractere in decompose if not unicodedata.combining(caractere))
    return " ".join(re.findall(r"[a-z0-9]+", sans_accents))


class RegistreCapacites:
    """Catalogue en mémoire : validation, versions, portée et recherche lexicale, sans exécution."""

    def __init__(self, manifestes: Iterable[Any] | None = None) -> None:
        self._actifs: dict[str, ManifesteOutil] = {}
        self._historique: dict[str, dict[str, ManifesteOutil]] = {}
        for manifeste in manifestes or ():
            self.enregistrer(manifeste)

    def enregistrer(self, manifeste: Any) -> ManifesteOutil:
        contrat = _manifeste(manifeste)
        nom = contrat.nom
        historique = self._historique.setdefault(nom, {})
        if contrat.version in historique:
            ancien = historique[contrat.version]
            if _canonique(ancien) == _canonique(contrat):
                if self._actifs.get(nom) is ancien:
                    return ancien
                raise ConflitManifeste("version déjà enregistrée, non active")
            raise ConflitManifeste("même nom et même version avec un contenu différent")
        actif = self._actifs.get(nom)
        if actif is not None:
            cle_nouvelle = _cle_version(contrat.version)
            cle_active = _cle_version(actif.version)
            if cle_nouvelle < cle_active:
                raise ConflitManifeste("downgrade de version refusé")
            if cle_nouvelle == cle_active and actif.version == contrat.version:
                if _canonique(actif) == _canonique(contrat):
                    return actif
                raise ConflitManifeste("même nom et même version avec un contenu différent")
        historique[contrat.version] = contrat
        self._actifs[nom] = contrat
        return contrat

    def lister(
        self,
        tenant: Any = None,
        acteur: Any = None,
        perimetre: Any = None,
        capacite: Any = None,
        lecture_seule: Any = None,
    ) -> list[ManifesteOutil]:
        tenant = _filtre(tenant, "tenant")
        acteur = _filtre(acteur, "acteur")
        perimetre = _filtre(perimetre, "perimetre")
        if capacite is not None:
            capacite = _capacite(capacite)
        if lecture_seule is not None and not isinstance(lecture_seule, bool):
            raise ManifesteInvalide("lecture_seule : booléen attendu")
        resultat = [
            manifeste
            for manifeste in self._actifs.values()
            if (capacite is None or manifeste.capacite == capacite)
            and (lecture_seule is None or manifeste.lecture_seule is lecture_seule)
            and _autorise(manifeste, tenant, acteur, perimetre)
        ]
        return sorted(resultat, key=lambda manifeste: (manifeste.nom, _cle_version(manifeste.version)))

    def chercher(
        self,
        requete: Any,
        tenant: Any = None,
        acteur: Any = None,
        perimetre: Any = None,
        capacite: Any = None,
        lecture_seule: Any = None,
    ) -> list[ManifesteOutil]:
        candidats = self.lister(tenant, acteur, perimetre, capacite, lecture_seule)
        jetons = _normaliser_texte(requete).split()
        if not jetons:
            return candidats
        scores: list[tuple[int, ManifesteOutil]] = []
        for manifeste in candidats:
            nom = _normaliser_texte(manifeste.nom)
            capacite_outil = _normaliser_texte(manifeste.capacite)
            description = _normaliser_texte(manifeste.description)
            objets = _normaliser_texte(" ".join((*manifeste.types_objets_lus, *manifeste.types_objets_ecrits)))
            if not all(
                jeton in nom or jeton in capacite_outil or jeton in description or jeton in objets
                for jeton in jetons
            ):
                continue
            score = 0
            for jeton in jetons:
                score += 5 if jeton in nom else 0
                score += 4 if jeton in capacite_outil else 0
                score += 2 if jeton in description else 0
                score += 2 if jeton in objets else 0
            scores.append((score, manifeste))
        scores.sort(key=lambda paire: (-paire[0], paire[1].nom, _cle_version(paire[1].version)))
        return [manifeste for _, manifeste in scores]

    def decrire(self, nom: Any) -> ManifesteOutil | None:
        if not isinstance(nom, str):
            return None
        return self._actifs.get(nom.strip())

    def versions(self, nom: Any) -> list[ManifesteOutil]:
        if not isinstance(nom, str):
            return []
        historique = self._historique.get(nom.strip(), {})
        return sorted(historique.values(), key=lambda manifeste: _cle_version(manifeste.version))

    def capacites(self) -> list[str]:
        return list(CAPACITES)

    def as_dict(self) -> dict:
        return {
            "capacites": self.capacites(),
            "outils": [manifeste.as_dict() for manifeste in self.lister()],
        }

    def __len__(self) -> int:
        return len(self._actifs)

    def __iter__(self):
        return iter(self.lister())

    def __contains__(self, nom: Any) -> bool:
        return isinstance(nom, str) and nom.strip() in self._actifs


_SCHEMA_RESOUDRE_ENTREE = {
    "type": "object",
    "properties": {
        "terme": {
            "type": "string",
            "description": "nom, identifiant ou dépôt mentionné par l'interlocuteur",
        }
    },
    "required": ["terme"],
    "additionalProperties": False,
}
_SCHEMA_RESOUDRE_SORTIE = {
    "type": "object",
    "properties": {
        "choix": {"type": ["string", "null"]},
        "statut": {"type": "string"},
        "candidats": {"type": "array", "items": {"type": "string"}},
        "requires_confirmation": {"type": "boolean"},
        "motif": {"type": "string"},
    },
    "required": ["choix", "statut", "candidats", "requires_confirmation", "motif"],
    "additionalProperties": False,
}
_SCHEMA_LISTER_ENTREE = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}
_SCHEMA_LISTER_SORTIE = {
    "type": "object",
    "properties": {
        "applications": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "nom": {"type": "string"},
                    "domaine": {"type": ["string", "null"]},
                },
                "required": ["id", "nom", "domaine"],
                "additionalProperties": False,
            },
        },
        "total": {"type": "integer"},
        "tronque": {"type": "boolean"},
    },
    "required": ["applications", "total", "tronque"],
    "additionalProperties": False,
}
_SCHEMA_MOBILISER_ENTREE = {
    "type": "object",
    "properties": {
        "jumeaux": {"type": "array", "items": {"type": "string"}},
        "question": {"type": "string", "description": "mission confiée aux jumeaux"},
    },
    "required": ["jumeaux", "question"],
    "additionalProperties": False,
}
_SCHEMA_MOBILISER_SORTIE = {
    "type": "object",
    "properties": {
        "statut": {"type": "string"},
        "jumeaux": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["statut", "jumeaux"],
    "additionalProperties": False,
}
_SCHEMA_CONCEVOIR_ENTREE = {
    "type": "object",
    "properties": {
        "question": {"type": "string", "description": "application à concevoir et besoin visé"},
    },
    "required": ["question"],
    "additionalProperties": False,
}
_SCHEMA_CONCEVOIR_SORTIE = {
    "type": "object",
    "properties": {
        "titre": {"type": "string"},
        "resume": {"type": "string"},
        "hypotheses": {"type": "array", "items": {"type": "string"}},
        "composants": {"type": "array", "items": {"type": "object"}},
        "liens": {"type": "array", "items": {"type": "object"}},
        "hors_scope": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["titre", "resume", "hypotheses", "composants", "liens", "hors_scope"],
    "additionalProperties": False,
}


def manifestes_integres() -> list[ManifesteOutil]:
    """Les quatre outils intégrés, décrits comme adaptateurs read-only du noyau capacitaire."""
    return [
        ManifesteOutil(
            nom="lister_applications",
            version="1.0.0",
            description=(
                "Liste les applications réellement visibles dans le périmètre courant, avec un index borné. "
                "Lecture seule, sans mobilisation ni conclusion."
            ),
            capacite="situer",
            types_objets_lus=("Application", "Twin"),
            schema_entree=_SCHEMA_LISTER_ENTREE,
            schema_sortie=_SCHEMA_LISTER_SORTIE,
            lecture_seule=True,
            cout=0.0,
            timeout_ms=5000,
            mode_preuve="DECLARED",
            source="builtin",
            allowlist=("meridian.builtin",),
        ),
        ManifesteOutil(
            nom="resoudre_application",
            version="1.0.0",
            description=(
                "Résout un terme vers une application visible du registre, avec ses candidats et son incertitude, "
                "sans mobiliser aucun jumeau."
            ),
            capacite="situer",
            types_objets_lus=("Application", "Twin", "Source"),
            schema_entree=_SCHEMA_RESOUDRE_ENTREE,
            schema_sortie=_SCHEMA_RESOUDRE_SORTIE,
            lecture_seule=True,
            cout=0.0,
            timeout_ms=5000,
            mode_preuve="DECLARED",
            source="builtin",
            allowlist=("meridian.builtin",),
        ),
        ManifesteOutil(
            nom="mobiliser_jumeaux",
            version="1.0.0",
            description=(
                "Mobilise des jumeaux autorisés pour une mission précise et rend une contribution étayée par des "
                "citations de leur code."
            ),
            capacite="mobiliser_expert",
            types_objets_lus=("Twin", "Claim", "Preuve"),
            schema_entree=_SCHEMA_MOBILISER_ENTREE,
            schema_sortie=_SCHEMA_MOBILISER_SORTIE,
            lecture_seule=True,
            cout=0.0,
            timeout_ms=300000,
            mode_preuve="OBSERVED",
            source="builtin",
            allowlist=("meridian.builtin",),
        ),
        ManifesteOutil(
            nom="concevoir_architecture",
            version="1.0.0",
            description=(
                "Conçoit une architecture cible explicitement proposée pour une application inexistante, sans "
                "consulter de jumeau ni fabriquer de preuve."
            ),
            capacite="concevoir",
            types_objets_lus=(),
            schema_entree=_SCHEMA_CONCEVOIR_ENTREE,
            schema_sortie=_SCHEMA_CONCEVOIR_SORTIE,
            lecture_seule=True,
            cout=0.0,
            timeout_ms=300000,
            mode_preuve="PROPOSED",
            source="builtin",
            allowlist=("meridian.builtin",),
        ),
    ]


__all__ = [
    "CAPACITES",
    "MODES_PREUVE",
    "SOURCES",
    "AXES_PORTEE",
    "ErreurRegistre",
    "ManifesteInvalide",
    "ConflitManifeste",
    "Portee",
    "ManifesteOutil",
    "RegistreCapacites",
    "manifestes_integres",
]
