"""Ports étroits du runtime d'investigation applicative.

Le domaine ne connaît ni fournisseur de modèle, ni système de fichiers. Un adapter de
modèle produit des objets JSON ; un retriever exécute uniquement les outils explicitement
autorisés, par exemple :class:`ExplorationHarness`.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from meridian.domain.investigation import ContributionInvestigation


class AdaptateurModeleInvestigation(Protocol):
    async def repondre(self, requete: Mapping[str, Any]) -> Mapping[str, Any]: ...


class RechercheInvestigation(Protocol):
    async def executer(self, nom: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]: ...


class ValidateurInvestigation(Protocol):
    async def valider(
        self, contribution: ContributionInvestigation
    ) -> ContributionInvestigation: ...


__all__ = [
    "AdaptateurModeleInvestigation", "RechercheInvestigation", "ValidateurInvestigation",
]
