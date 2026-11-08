"""Port de la boucle canonique : lectures, transitions pures, verrou et persistance.

L'orchestration applicative dépend de cette surface, jamais d'un adaptateur concret. Le
module :mod:`meridian.adapters.outbound.postgres.boucle` la satisfait structurellement et
est injecté par la couche HTTP.

``transaction`` et ``lire_boucle(for_update=True)`` exposent explicitement le verrou et la
frontière transactionnelle sans laisser l'application manipuler l'API psycopg brute.
``nouvelle_situation`` remplace la fuite de la classe ``Situation`` dans le protocole.
"""
from __future__ import annotations

from typing import Any, Protocol

__all__ = [
    "BoucleStore",
    "ObjetInvalide",
    "ObjetExistant",
    "VersionRefusee",
]


class ObjetInvalide(ValueError):
    """Objet refusé avant toute écriture (validation, secret, JSON non sérialisable)."""


class VersionRefusee(ObjetInvalide):
    """La version attendue ne correspond plus à la version stockée."""


class ObjetExistant(ObjetInvalide):
    """Un objet ``(tenant_id, id)`` existe déjà et la création exclusive est demandée."""


class BoucleStore(Protocol):
    """Surface minimale utilisée par :mod:`meridian.application.commandes_boucle`."""

    def transaction(self, conn: Any) -> Any: ...

    def lire_boucle(
        self, conn: Any, tenant_id: str, objet_id: str, *,
        historique: bool = False, as_dict: bool = True, for_update: bool = False,
    ) -> Any: ...

    def enregistrer_boucle(
        self, conn: Any, tenant_id: Any = None, objets: Any = None, *,
        historique: bool = False, as_dict: bool = True, creer: bool = False,
    ) -> Any: ...

    def nouvelle_situation(self, **champs: Any) -> Any: ...

    def nouveau_scenario(self, **champs: Any) -> Any: ...

    def nouvelle_expression(self, **champs: Any) -> Any: ...

    def nouvelle_opportunite(self, **champs: Any) -> Any: ...

    def nouveau_risque(self, **champs: Any) -> Any: ...

    def nouvelle_hypothese(self, **champs: Any) -> Any: ...

    def nouveau_signal(self, **champs: Any) -> Any: ...

    def nouvel_expert(self, **champs: Any) -> Any: ...

    def nouvelle_contribution(self, expert: Any = None, **champs: Any) -> Any: ...

    def muer_opportunite(self, opportunite: Any, vers: str, **champs: Any) -> Any: ...

    def muer_risque(self, risque: Any, vers: str, **champs: Any) -> Any: ...

    def muer_hypothese(self, hypothese: Any, vers: str, **champs: Any) -> Any: ...

    def muer_contribution(self, contribution: Any, vers: str, **champs: Any) -> Any: ...

    def enregistrer_objets(
        self, conn: Any, tenant_id: Any = None, objets: Any = None, *,
        historique: bool = False, as_dict: bool = True,
    ) -> Any: ...

    def lister_objets_exploitation(
        self, conn: Any, tenant_id: str, *, type_: str | None = None,
        situation_id: str | None = None, investigation_id: str | None = None,
        decision_id: str | None = None, expression_id: str | None = None,
        expert_id: str | None = None, hypothesis_id: str | None = None,
        domaine: str | None = None, type_signal: str | None = None,
        statut: str | None = None, limite: int = 100, as_dict: bool = True,
    ) -> list[Any]: ...

    def donnees_de(self, objet: Any) -> dict[str, Any]: ...

    def fusionner_donnees(
        self, conn: Any, tenant_id: Any, objet_id: Any, patch: Any, *,
        historique: bool = True, ajouter: Any = (), mode: str | None = None,
        version_attendue: Any = None,
    ) -> dict[str, Any]: ...

    def ouvrir_investigation(self, situation: Any, **champs: Any) -> Any: ...

    def proposer_decision(self, investigation: Any, options: Any, **champs: Any) -> Any: ...

    def trancher_decision(
        self, decision: Any, acteur: str, choix: str, **champs: Any,
    ) -> Any: ...

    def lancer_initiative(self, decision: Any, **champs: Any) -> Any: ...

    def mesurer_outcome(self, initiative: Any, mesure: Any, **champs: Any) -> Any: ...

    def capitaliser_learning(self, source: Any, **champs: Any) -> Any: ...
