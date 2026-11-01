"""Projecteur graphe : consomme les événements d'outbox et applique la topologie au GraphStore."""
from __future__ import annotations

from typing import Any, Mapping

from meridian.application import graphe_sync


class ProjecteurGraphe:
    """Idempotent : `graphe_sync.synchroniser` upsert les Twins et les relations par identifiant."""

    TYPES = frozenset({"graph.synchroniser", "graph.sync"})

    def __init__(self, store):
        self.store = store

    def traiter(self, evenement: Mapping[str, Any]) -> dict | None:
        if evenement.get("type") not in self.TYPES:
            return None
        payload = dict(evenement.get("payload") or {})
        tenant = str(evenement.get("tenant_id") or payload.get("tenant_id") or "")
        if not tenant:
            raise ValueError("projection graphe : tenant absent")
        twins = payload.get("twins") or []
        relations = payload.get("relations") or []
        rapport = graphe_sync.synchroniser(self.store, tenant, twins, relations)
        if rapport.get("erreurs"):
            raise RuntimeError(f"projection graphe en échec : {len(rapport['erreurs'])} erreur(s)")
        return rapport
