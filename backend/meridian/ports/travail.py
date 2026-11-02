"""Port du store Travail : le fil Aujourd'hui et l'Atlas ne doivent pas connaître Mongo."""
from __future__ import annotations

from typing import Any, Protocol


class TravailStore(Protocol):
    async def lister(self, filtre: dict[str, Any] | None = None,
                     limite: int = 200) -> list[dict[str, Any]]: ...

    async def lister_recents(self, limite: int | None = 500) -> list[dict[str, Any]]: ...

    async def lire(self, cid: str) -> dict[str, Any] | None: ...

    async def compter(self) -> int: ...

    async def upsert(self, travail: dict[str, Any]) -> bool: ...

    async def mettre_a_jour(self, cid: str, champs: dict[str, Any]) -> bool: ...


class TravailSource(Protocol):
    """Source de synchronisation : les cas Mongo, lus par lots stables."""

    async def lister_par_id(self, apres_id: str | None, limite: int) -> list[dict[str, Any]]: ...

    async def lister_apres(self, maj_le: str | None, apres_id: str | None,
                           limite: int) -> list[dict[str, Any]]: ...


class SourceTravail(Protocol):
    """Un outil de gestion du travail (Jira, Azure DevOps, Linear, CSV...), distinct du store Travail."""

    provider: str

    def capacites(self) -> dict[str, bool]:
        """sprints, points, heures, worklogs, dependances, releases, historique, equipes."""

    def lister_equipes(self) -> list[dict[str, Any]]:
        """[{id, nom, domaine?, parent?}] — identifiants externes, pas encore mappés Méridian."""

    def lister_elements(self, depuis: str | None = None, limite: int = 500) -> list[dict[str, Any]]:
        """Éléments normalisables ; `depuis` est le curseur du provider."""

    def lister_cycles(self) -> list[dict[str, Any]]:
        """[{id, equipe_id, nom, debut, fin, termine?}]."""

    def lister_releases(self) -> list[dict[str, Any]]:
        """[{id, nom, date_cible?, statut?}]."""

    def lister_dependances(self) -> list[dict[str, Any]]:
        """[{source_id, cible_id, type}] ; liens explicites seulement."""

    def lister_temps(self) -> list[dict[str, Any]]:
        """[{element_id, equipe_id?, periode, valeur, unite}] agrégé si possible."""


class SourcePeople(Protocol):
    provider: str

    def lister_equipes(self) -> list[dict[str, Any]]: ...

    def lister_membres(self, equipe_id: str | None = None) -> list[dict[str, Any]]: ...

    def lister_capacites(self, debut: str | None = None, fin: str | None = None) -> list[dict[str, Any]]: ...

    def lister_competences(self, equipe_id: str | None = None) -> list[dict[str, Any]]: ...

    def lister_allocations(self, equipe_id: str | None = None) -> list[dict[str, Any]]: ...

    def lister_absences(self, equipe_id: str | None = None,
                        debut: str | None = None, fin: str | None = None) -> list[dict[str, Any]]: ...


class SourceFinance(Protocol):
    provider: str

    def lister_budgets(self) -> list[dict[str, Any]]: ...

    def lister_couts(self) -> list[dict[str, Any]]: ...

    def lister_taux(self) -> list[dict[str, Any]]: ...


class SourceValeur(Protocol):
    provider: str

    def lister_valeurs(self, initiative_id: str | None = None) -> list[dict[str, Any]]: ...


class SourceIncidents(Protocol):
    provider: str

    def lister_charge_non_planifiee(self, debut: str | None = None, fin: str | None = None) -> list[dict[str, Any]]: ...
