"""Contrat de contribution d'une investigation menée par un jumeau.

Ce module ne lance aucun modèle et ne persiste rien. Il constitue la frontière de
validation entre une enquête (LLM ou déterministe) et le domaine : une affirmation
observée ou inférée porte des preuves versionnées, les inconnues restent explicites,
et le runtime vérifie les sources contre son périmètre d'autorisation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Mapping

__all__ = [
    "MODES_CLAIM",
    "STATUTS_INVESTIGATION",
    "BudgetInvestigation",
    "ClaimInvestigation",
    "ContributionInvestigation",
    "CouvertureInvestigation",
    "InconnueInvestigation",
    "PorteeInvestigation",
    "PreuveInvestigation",
    "SuiviInvestigation",
    "contribution_depuis_dict",
    "valider_perimetre",
]

MODES_CLAIM = ("observed", "inferred", "unknown")
STATUTS_INVESTIGATION = (
    "created", "running", "waiting_source", "waiting_human", "suspended",
    "completed", "completed_with_gaps", "budget_exhausted", "failed",
)


def _texte(valeur, champ: str, maximum: int, *, requis: bool = False) -> str:
    texte = " ".join(str(valeur or "").split())
    if requis and not texte:
        raise ValueError(f"{champ} obligatoire")
    if len(texte) > maximum:
        raise ValueError(f"{champ} trop long (maximum {maximum} caractères)")
    return texte


def _textes(valeurs, champ: str, maximum: int = 500) -> tuple[str, ...]:
    if valeurs is None:
        return ()
    if isinstance(valeurs, str):
        valeurs = (valeurs,)
    resultat = []
    for valeur in valeurs:
        texte = _texte(valeur, champ, maximum)
        if texte:
            if texte in resultat:
                raise ValueError(f"{champ} contient un doublon : {texte}")
            resultat.append(texte)
    return tuple(resultat)


def _date(valeur, champ: str, *, requis: bool = True) -> str:
    texte = _texte(valeur, champ, 80, requis=requis)
    if not texte:
        return ""
    try:
        date = datetime.fromisoformat(texte.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{champ} doit être une date ISO 8601") from exc
    if date.tzinfo is None:
        raise ValueError(f"{champ} doit porter un fuseau horaire")
    return texte


def _objets(valeurs, type_, champ: str):
    if valeurs is None:
        return ()
    resultat = tuple(valeurs)
    if any(not isinstance(valeur, type_) for valeur in resultat):
        raise TypeError(f"{champ} doit contenir des {type_.__name__}")
    return resultat


def _document(valeur, champ: str, cles: set[str]) -> dict:
    if not isinstance(valeur, Mapping):
        raise TypeError(f"{champ} doit être un objet")
    document = dict(valeur)
    inconnues = sorted(set(document) - cles)
    if inconnues:
        raise ValueError(f"{champ} contient des champs inconnus : {', '.join(inconnues)}")
    return document


def _liste_documents(valeur, champ: str) -> tuple:
    if valeur is None:
        return ()
    if not isinstance(valeur, (list, tuple)):
        raise TypeError(f"{champ} doit être une liste")
    return tuple(valeur)


@dataclass(frozen=True)
class PreuveInvestigation:
    source_id: str
    locator: str
    version: str
    type: str
    observee_le: str
    repository: str = ""
    commit: str = ""
    fichier: str = ""
    symbole: str = ""
    lignes: tuple[int, int] | tuple = ()

    def __post_init__(self):
        object.__setattr__(self, "source_id", _texte(self.source_id, "preuve.source_id", 200, requis=True))
        object.__setattr__(self, "locator", _texte(self.locator, "preuve.locator", 2000, requis=True))
        object.__setattr__(self, "version", _texte(self.version, "preuve.version", 200, requis=True))
        object.__setattr__(self, "type", _texte(self.type, "preuve.type", 40, requis=True).lower())
        object.__setattr__(self, "observee_le", _date(self.observee_le, "preuve.observee_le"))
        object.__setattr__(self, "repository", _texte(self.repository, "preuve.repository", 300))
        object.__setattr__(self, "commit", _texte(self.commit, "preuve.commit", 160))
        object.__setattr__(self, "fichier", _texte(self.fichier, "preuve.fichier", 1000))
        object.__setattr__(self, "symbole", _texte(self.symbole, "preuve.symbole", 500))
        lignes = tuple(self.lignes or ())
        if lignes:
            if len(lignes) != 2 or any(not isinstance(n, int) for n in lignes):
                raise ValueError("preuve.lignes attend [début, fin]")
            if lignes[0] < 1 or lignes[1] < lignes[0]:
                raise ValueError("preuve.lignes hors bornes")
        object.__setattr__(self, "lignes", lignes)

    @property
    def fingerprint(self) -> tuple[str, str, str]:
        return self.source_id, self.locator, self.version

    def as_dict(self) -> dict:
        return {
            "source_id": self.source_id, "locator": self.locator,
            "version": self.version, "type": self.type,
            "observee_le": self.observee_le, "repository": self.repository,
            "commit": self.commit, "fichier": self.fichier,
            "symbole": self.symbole, "lignes": list(self.lignes),
        }


@dataclass(frozen=True)
class PorteeInvestigation:
    repositories: tuple[str, ...] = ()
    points_entree: tuple[str, ...] = ()
    modules: tuple[str, ...] = ()
    environnements: tuple[str, ...] = ()
    parcours: tuple[str, ...] = ()
    conditions: tuple[str, ...] = ()

    def __post_init__(self):
        for champ, maximum in (("repositories", 300), ("points_entree", 500), ("modules", 300),
                               ("environnements", 120), ("parcours", 1000), ("conditions", 1000)):
            object.__setattr__(self, champ, _textes(getattr(self, champ), f"portée.{champ}", maximum))

    def as_dict(self) -> dict:
        return {champ: list(getattr(self, champ)) for champ in (
            "repositories", "points_entree", "modules", "environnements", "parcours", "conditions")}


@dataclass(frozen=True)
class ClaimInvestigation:
    id: str
    affirmation: str
    mode: str
    portee: PorteeInvestigation = field(default_factory=PorteeInvestigation)
    preuves: tuple[PreuveInvestigation, ...] = ()
    contre_preuves: tuple[PreuveInvestigation, ...] = ()
    confiance: float = 0.0
    limites: tuple[str, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "id", _texte(self.id, "claim.id", 160, requis=True))
        object.__setattr__(self, "affirmation", _texte(self.affirmation, "claim.affirmation", 2000, requis=True))
        mode = _texte(self.mode, "claim.mode", 20, requis=True).lower()
        if mode not in MODES_CLAIM:
            raise ValueError(f"claim.mode inconnu : {mode!r}")
        object.__setattr__(self, "mode", mode)
        if not isinstance(self.portee, PorteeInvestigation):
            raise TypeError("claim.portee doit être une PorteeInvestigation")
        preuves = _objets(self.preuves, PreuveInvestigation, "claim.preuves")
        contre = _objets(self.contre_preuves, PreuveInvestigation, "claim.contre_preuves")
        empreintes = [preuve.fingerprint for preuve in (*preuves, *contre)]
        if len(empreintes) != len(set(empreintes)):
            raise ValueError("claim contient une preuve dupliquée")
        if mode in {"observed", "inferred"} and not preuves:
            raise ValueError(f"claim {mode} exige au moins une preuve")
        try:
            confiance = float(self.confiance)
        except (TypeError, ValueError) as exc:
            raise ValueError("claim.confiance doit être un nombre") from exc
        if not 0.0 <= confiance <= 1.0:
            raise ValueError("claim.confiance hors bornes")
        object.__setattr__(self, "preuves", preuves)
        object.__setattr__(self, "contre_preuves", contre)
        object.__setattr__(self, "confiance", confiance)
        object.__setattr__(self, "limites", _textes(self.limites, "claim.limites", 1000))

    def as_dict(self) -> dict:
        return {
            "id": self.id, "affirmation": self.affirmation, "mode": self.mode,
            "portee": self.portee.as_dict(),
            "preuves": [preuve.as_dict() for preuve in self.preuves],
            "contre_preuves": [preuve.as_dict() for preuve in self.contre_preuves],
            "confiance": round(self.confiance, 3), "limites": list(self.limites),
        }


@dataclass(frozen=True)
class InconnueInvestigation:
    question: str
    consequence: str
    source_necessaire: str

    def __post_init__(self):
        object.__setattr__(self, "question", _texte(self.question, "inconnue.question", 2000, requis=True))
        object.__setattr__(self, "consequence", _texte(self.consequence, "inconnue.consequence", 1000, requis=True))
        object.__setattr__(self, "source_necessaire", _texte(
            self.source_necessaire, "inconnue.source_necessaire", 500, requis=True))

    def as_dict(self) -> dict:
        return {"question": self.question, "consequence": self.consequence,
                "source_necessaire": self.source_necessaire}


@dataclass(frozen=True)
class SuiviInvestigation:
    twin_id: str
    question: str
    relation: str

    def __post_init__(self):
        object.__setattr__(self, "twin_id", _texte(self.twin_id, "suivi.twin_id", 160, requis=True))
        object.__setattr__(self, "question", _texte(self.question, "suivi.question", 2000, requis=True))
        object.__setattr__(self, "relation", _texte(self.relation, "suivi.relation", 500, requis=True))

    def as_dict(self) -> dict:
        return {"twin_id": self.twin_id, "question": self.question, "relation": self.relation}


@dataclass(frozen=True)
class CouvertureInvestigation:
    examinees: tuple[str, ...] = ()
    inaccessibles: tuple[str, ...] = ()
    non_supportees: tuple[str, ...] = ()
    tronquee: bool = False
    limites: tuple[str, ...] = ()

    def __post_init__(self):
        groupes = {}
        for champ in ("examinees", "inaccessibles", "non_supportees"):
            valeurs = _textes(getattr(self, champ), f"couverture.{champ}", 200)
            groupes[champ] = valeurs
            object.__setattr__(self, champ, valeurs)
        toutes = [valeur for valeurs in groupes.values() for valeur in valeurs]
        if len(toutes) != len(set(toutes)):
            raise ValueError("une source ne peut avoir deux états de couverture")
        object.__setattr__(self, "tronquee", bool(self.tronquee))
        object.__setattr__(self, "limites", _textes(self.limites, "couverture.limites", 1000))

    def as_dict(self) -> dict:
        return {"examinees": list(self.examinees), "inaccessibles": list(self.inaccessibles),
                "non_supportees": list(self.non_supportees), "tronquee": self.tronquee,
                "limites": list(self.limites)}


@dataclass(frozen=True)
class BudgetInvestigation:
    appels_max: int = 0
    appels_utilises: int = 0
    tokens_max: int = 0
    tokens_utilises: int = 0
    secondes_max: int = 0
    secondes_utilisees: int = 0

    def __post_init__(self):
        for champ in ("appels_max", "appels_utilises", "tokens_max", "tokens_utilises",
                      "secondes_max", "secondes_utilisees"):
            valeur = getattr(self, champ)
            if not isinstance(valeur, int) or valeur < 0:
                raise ValueError(f"budget.{champ} doit être un entier positif ou nul")

    @property
    def epuise(self) -> bool:
        return any(maximum > 0 and utilise >= maximum for maximum, utilise in (
            (self.appels_max, self.appels_utilises), (self.tokens_max, self.tokens_utilises),
            (self.secondes_max, self.secondes_utilisees)))

    def as_dict(self) -> dict:
        return {champ: getattr(self, champ) for champ in (
            "appels_max", "appels_utilises", "tokens_max", "tokens_utilises",
            "secondes_max", "secondes_utilisees")}


@dataclass(frozen=True)
class ContributionInvestigation:
    investigation_id: str
    question_id: str
    twin_id: str
    horodatage: str
    statut: str
    claims: tuple[ClaimInvestigation, ...] = ()
    inconnues: tuple[InconnueInvestigation, ...] = ()
    suivis: tuple[SuiviInvestigation, ...] = ()
    couverture: CouvertureInvestigation = field(default_factory=CouvertureInvestigation)
    budget: BudgetInvestigation = field(default_factory=BudgetInvestigation)

    def __post_init__(self):
        for champ in ("investigation_id", "question_id", "twin_id"):
            object.__setattr__(self, champ, _texte(getattr(self, champ), champ, 160, requis=True))
        object.__setattr__(self, "horodatage", _date(self.horodatage, "horodatage"))
        statut = _texte(self.statut, "statut", 40, requis=True).lower()
        if statut not in STATUTS_INVESTIGATION:
            raise ValueError(f"statut d'investigation inconnu : {statut!r}")
        object.__setattr__(self, "statut", statut)
        claims = _objets(self.claims, ClaimInvestigation, "claims")
        inconnues = _objets(self.inconnues, InconnueInvestigation, "inconnues")
        suivis = _objets(self.suivis, SuiviInvestigation, "suivis")
        ids = [claim.id for claim in claims]
        if len(ids) != len(set(ids)):
            raise ValueError("identifiant de claim dupliqué")
        questions = [inconnue.question for inconnue in inconnues]
        if len(questions) != len(set(questions)):
            raise ValueError("question inconnue dupliquée")
        destinations = [(suivi.twin_id, suivi.question) for suivi in suivis]
        if len(destinations) != len(set(destinations)):
            raise ValueError("suivi dupliqué")
        if not isinstance(self.couverture, CouvertureInvestigation):
            raise TypeError("couverture doit être une CouvertureInvestigation")
        if not isinstance(self.budget, BudgetInvestigation):
            raise TypeError("budget doit être un BudgetInvestigation")
        claims_inconnus = any(claim.mode == "unknown" for claim in claims)
        if statut == "completed" and (claims_inconnus or inconnues or self.couverture.inaccessibles
                                       or self.couverture.non_supportees or self.couverture.tronquee):
            raise ValueError("une investigation avec des lacunes doit être completed_with_gaps")
        if statut == "budget_exhausted" and not self.budget.epuise:
            raise ValueError("budget_exhausted exige un budget épuisé")
        object.__setattr__(self, "claims", claims)
        object.__setattr__(self, "inconnues", inconnues)
        object.__setattr__(self, "suivis", suivis)

    def as_dict(self) -> dict:
        return {
            "investigation_id": self.investigation_id, "question_id": self.question_id,
            "twin_id": self.twin_id, "horodatage": self.horodatage, "statut": self.statut,
            "claims": [claim.as_dict() for claim in self.claims],
            "inconnues": [inconnue.as_dict() for inconnue in self.inconnues],
            "suivis": [suivi.as_dict() for suivi in self.suivis],
            "couverture": self.couverture.as_dict(), "budget": self.budget.as_dict(),
        }


def contribution_depuis_dict(valeur: Mapping) -> ContributionInvestigation:
    """Construit le contrat depuis une sortie JSON et refuse tout champ non prévu.

    Cette fonction ne valide pas les autorisations : celles-ci viennent du runtime et sont
    appliquées ensuite avec :func:`valider_perimetre`.
    """
    racine = _document(valeur, "contribution", {
        "investigation_id", "question_id", "twin_id", "horodatage", "statut",
        "claims", "inconnues", "suivis", "couverture", "budget",
    })

    def construire_preuve(objet, champ):
        document = _document(objet, champ, {
            "source_id", "locator", "version", "type", "observee_le", "repository",
            "commit", "fichier", "symbole", "lignes",
        })
        if "lignes" in document:
            document["lignes"] = tuple(document["lignes"] or ())
        return PreuveInvestigation(**document)

    claims = []
    for index, objet in enumerate(_liste_documents(racine.get("claims"), "claims")):
        document = _document(objet, f"claims[{index}]", {
            "id", "affirmation", "mode", "portee", "preuves", "contre_preuves",
            "confiance", "limites",
        })
        portee = _document(document.pop("portee", {}), f"claims[{index}].portee", {
            "repositories", "points_entree", "modules", "environnements", "parcours", "conditions",
        })
        document["portee"] = PorteeInvestigation(**portee)
        document["preuves"] = tuple(construire_preuve(p, f"claims[{index}].preuves")
                                     for p in _liste_documents(
                                         document.get("preuves"), f"claims[{index}].preuves"))
        document["contre_preuves"] = tuple(construire_preuve(p, f"claims[{index}].contre_preuves")
                                            for p in _liste_documents(
                                                document.get("contre_preuves"),
                                                f"claims[{index}].contre_preuves"))
        claims.append(ClaimInvestigation(**document))

    inconnues = []
    for index, objet in enumerate(_liste_documents(racine.get("inconnues"), "inconnues")):
        document = _document(objet, f"inconnues[{index}]", {
            "question", "consequence", "source_necessaire",
        })
        inconnues.append(InconnueInvestigation(**document))

    suivis = []
    for index, objet in enumerate(_liste_documents(racine.get("suivis"), "suivis")):
        document = _document(objet, f"suivis[{index}]", {"twin_id", "question", "relation"})
        suivis.append(SuiviInvestigation(**document))

    couverture = _document(racine.get("couverture") or {}, "couverture", {
        "examinees", "inaccessibles", "non_supportees", "tronquee", "limites",
    })
    budget = _document(racine.get("budget") or {}, "budget", {
        "appels_max", "appels_utilises", "tokens_max", "tokens_utilises",
        "secondes_max", "secondes_utilisees",
    })
    donnees = {cle: valeur for cle, valeur in racine.items()
               if cle not in {"claims", "inconnues", "suivis", "couverture", "budget"}}
    return ContributionInvestigation(
        **donnees, claims=tuple(claims), inconnues=tuple(inconnues), suivis=tuple(suivis),
        couverture=CouvertureInvestigation(**couverture), budget=BudgetInvestigation(**budget),
    )


def valider_perimetre(contribution: ContributionInvestigation, sources_autorisees: Iterable[str],
                      *, twin_id: str | None = None) -> ContributionInvestigation:
    """Valide les sources contre le périmètre fourni par le runtime, jamais par le modèle.

    Rend la contribution pour permettre ``contribution = valider_perimetre(...)``. Toute
    source citée dans une preuve ou la couverture doit être explicitement autorisée.
    """
    if not isinstance(contribution, ContributionInvestigation):
        raise TypeError("contribution attendue")
    autorisees = {_texte(source, "source autorisée", 200, requis=True) for source in sources_autorisees}
    if twin_id is not None and contribution.twin_id != _texte(twin_id, "twin_id autorisé", 160, requis=True):
        raise PermissionError("contribution d'un jumeau hors périmètre")
    references = set(contribution.couverture.examinees + contribution.couverture.inaccessibles
                     + contribution.couverture.non_supportees)
    for claim in contribution.claims:
        references.update(preuve.source_id for preuve in (*claim.preuves, *claim.contre_preuves))
    interdites = sorted(references - autorisees)
    if interdites:
        raise PermissionError(f"source hors périmètre effectif : {', '.join(interdites)}")
    return contribution
