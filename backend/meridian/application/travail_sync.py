"""Synchronisation Travail Mongo -> Postgres : backfill complet et rattrapage incrémental.

Le module ne connaît ni Mongo ni psycopg : il orchestre une source (`lister_par_id`,
`lister_apres`) et une cible (`upsert`). Les adapters fournissent les deux. Aucune
suppression n'est demandée ; un cas retiré de Mongo reste dans le read model.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Curseur:
    """Position de synchronisation : `maj_le` puis `_id` départagent les égalités."""
    maj_le: str | None = None
    id: str | None = None


@dataclass
class Bilan:
    lus: int = 0
    ecrits: int = 0
    lots: int = 0
    supprimes: int = 0
    curseur: Curseur = field(default_factory=Curseur)


def _identifiant(document: dict[str, Any]) -> str:
    valeur = document.get("_id")
    if valeur is None:
        valeur = document.get("id")
    if valeur is None:
        raise ValueError("document sans identifiant Mongo ni id applicatif")
    return str(valeur)


def _document(document: dict[str, Any]) -> dict[str, Any]:
    propre = dict(document)
    identifiant = _identifiant(document)
    propre["_id"] = identifiant
    propre.setdefault("id", identifiant)
    if not propre.get("id"):
        raise ValueError("document sans id applicatif")
    return propre


async def supprimer_absents(source, cible) -> int:
    """Retire du read model les cas qui n'existent plus dans la source (balayage complet)."""
    source_ids = await source.identifiants()
    cible_ids = cible.identifiants()
    absents = sorted(cible_ids - source_ids)
    if not absents:
        return 0
    return int(await cible.supprimer_plusieurs(absents))


async def remplir(source, cible, *, limite: int = 500, appliquer: bool = True,
                  max_lots: int | None = None, supprimer_les_absents: bool = False) -> Bilan:
    """Backfill complet, idempotent : relit les cas par `_id` croissant et les upsert."""
    bilan = Bilan()
    apres: str | None = None
    while True:
        lot = await source.lister_par_id(apres, limite)
        bilan.lots += 1
        if not lot:
            break
        for document in lot:
            propre = _document(document)
            if appliquer:
                await cible.upsert(propre)
                bilan.ecrits += 1
            bilan.lus += 1
            apres = _identifiant(document)
        if len(lot) < limite or (max_lots is not None and bilan.lots >= max_lots):
            break
    if supprimer_les_absents and appliquer and cible is not None:
        bilan.supprimes = await supprimer_absents(source, cible)
    return bilan


async def synchroniser(source, cible, *, curseur: Curseur | None = None,
                       limite: int = 200, appliquer: bool = True,
                       max_lots: int | None = None) -> Bilan:
    """Rattrapage incrémental : ne lit que `maj_le` > curseur (ou `_id` > curseur à égalité)."""
    position = curseur or Curseur()
    bilan = Bilan(curseur=position)
    while True:
        lot = await source.lister_apres(position.maj_le, position.id, limite)
        bilan.lots += 1
        if not lot:
            break
        for document in lot:
            propre = _document(document)
            if appliquer:
                await cible.upsert(propre)
                bilan.ecrits += 1
            bilan.lus += 1
            position = Curseur(maj_le=propre.get("maj_le") or position.maj_le,
                               id=_identifiant(document))
        bilan.curseur = position
        if len(lot) < limite or (max_lots is not None and bilan.lots >= max_lots):
            break
    return bilan
