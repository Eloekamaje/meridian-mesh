"""Port de la boucle canonique : lectures, transitions pures et persistance.

L'orchestration applicative dépend de cette surface, jamais d'un adaptateur concret. Le
module :mod:`meridian.adapters.outbound.postgres.boucle` la satisfait structurellement et
est injecté par la couche HTTP.
"""
from __future__ import annotations

from typing import Any, Protocol


class BoucleStore(Protocol):
    """Surface minimale utilisée par :mod:`meridian.application.commandes_boucle`."""

    Situation: Any

    def lire_boucle(
        self, conn: Any, tenant_id: str, objet_id: str, *,
        historique: bool = False, as_dict: bool = True,
    ) -> Any: ...

    def enregistrer_boucle(
        self, conn: Any, tenant_id: Any = None, objets: Any = None, *,
        historique: bool = False, as_dict: bool = True,
    ) -> Any: ...

    def ouvrir_investigation(self, situation: Any, **champs: Any) -> Any: ...

    def proposer_decision(self, investigation: Any, options: Any, **champs: Any) -> Any: ...

    def trancher_decision(
        self, decision: Any, acteur: str, choix: str, **champs: Any,
    ) -> Any: ...

    def lancer_initiative(self, decision: Any, **champs: Any) -> Any: ...

    def mesurer_outcome(self, initiative: Any, mesure: Any, **champs: Any) -> Any: ...

    def capitaliser_learning(self, source: Any, **champs: Any) -> Any: ...
