"""Modèle fédéré d'indexation de code : observations, couverture, provenance."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Mapping

__all__ = ["Observation", "CouvertureFichier", "fusionner", "couverture"]

STATUTS = ("indexe", "partiel", "non_supporte", "ignore", "tronque", "conflit")


def _texte(valeur, maximum=1000) -> str:
    return " ".join(str(valeur or "").split())[:maximum]


@dataclass(frozen=True)
class Observation:
    provider: str
    parser: str
    parser_version: str
    file: str
    language: str
    kind: str
    symbol: str
    start: int = 0
    end: int = 0
    commit: str = ""
    attributes: dict = field(default_factory=dict)
    confidence: float = 1.0
    status: str = "extracted"

    def __post_init__(self):
        if self.status not in {"extracted", "inferred", "ambiguous", "conflict"}:
            raise ValueError(f"statut d'observation inconnu : {self.status!r}")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confiance hors bornes")
        object.__setattr__(self, "provider", _texte(self.provider, 40))
        object.__setattr__(self, "parser", _texte(self.parser, 80))
        object.__setattr__(self, "parser_version", _texte(self.parser_version, 40))
        object.__setattr__(self, "file", _texte(self.file, 1000))
        object.__setattr__(self, "language", _texte(self.language, 40))
        object.__setattr__(self, "kind", _texte(self.kind, 60))
        object.__setattr__(self, "symbol", _texte(self.symbol, 500))
        object.__setattr__(self, "start", max(0, int(self.start or 0)))
        object.__setattr__(self, "end", max(0, int(self.end or self.start or 0)))
        object.__setattr__(self, "commit", _texte(self.commit, 80))
        object.__setattr__(self, "attributes", dict(self.attributes or {}))
        object.__setattr__(self, "confidence", float(self.confidence))

    @property
    def fingerprint(self) -> tuple:
        return (self.file, self.kind, self.symbol, self.start, self.end)

    def as_dict(self) -> dict:
        return {
            "provider": self.provider, "parser": self.parser,
            "parser_version": self.parser_version, "file": self.file,
            "language": self.language, "kind": self.kind, "symbol": self.symbol,
            "start": self.start, "end": self.end, "commit": self.commit,
            "attributes": self.attributes, "confidence": self.confidence,
            "status": self.status,
        }


@dataclass(frozen=True)
class CouvertureFichier:
    file: str
    language: str = ""
    parser: str = ""
    statut: str = "non_supporte"
    raison: str = ""

    def __post_init__(self):
        if self.statut not in STATUTS:
            raise ValueError(f"statut de couverture inconnu : {self.statut!r}")
        object.__setattr__(self, "file", _texte(self.file, 1000))
        object.__setattr__(self, "language", _texte(self.language, 40))
        object.__setattr__(self, "parser", _texte(self.parser, 80))
        object.__setattr__(self, "raison", _texte(self.raison, 500))

    def as_dict(self) -> dict:
        return {"file": self.file, "language": self.language, "parser": self.parser,
                "statut": self.statut, "raison": self.raison}


def fusionner(observations) -> list[Observation]:
    """Déduplique sans écraser un conflit : la provenance reste visible."""
    uniques = {}
    for observation in observations or ():
        if not isinstance(observation, Observation):
            continue
        precedent = uniques.get(observation.fingerprint)
        if precedent is None:
            uniques[observation.fingerprint] = observation
        elif precedent.provider != observation.provider or precedent.status != observation.status:
            uniques[observation.fingerprint] = replace(
                precedent, status="conflict",
                attributes={**precedent.attributes, "providers": [precedent.provider, observation.provider]})
    return sorted(uniques.values(), key=lambda o: (o.file, o.start, o.kind, o.symbol))


def couverture(fichiers, observations) -> list[CouvertureFichier]:
    """Une ligne par fichier : un fichier sans observation est explicitement non supporté."""
    vus = {}
    for observation in observations or ():
        if isinstance(observation, Observation):
            vus.setdefault(observation.file, observation)
    resultat = []
    for fichier in sorted(set(fichiers) | set(vus)):
        observation = vus.get(fichier)
        resultat.append(CouvertureFichier(
            file=fichier,
            language=observation.language if observation else "",
            parser=observation.parser if observation else "",
            statut="indexe" if observation else "non_supporte",
            raison="" if observation else "aucun parser n'a produit d'observation",
        ))
    return resultat
