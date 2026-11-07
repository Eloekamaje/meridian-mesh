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
