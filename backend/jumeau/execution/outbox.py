"""Dispatcher d'outbox : sélection, publication et marquage transactionnels."""
from __future__ import annotations

import logging
from typing import Any, Callable, Mapping

from jumeau.execution import depot

journal = logging.getLogger("meridian.execution.outbox")


class DispatcherOutbox:
    def __init__(self, connect: Callable[[], Any], publieurs: Mapping[str, Callable[[Mapping[str, Any]], Any]] | None = None):
        self.connect = connect
        self.publieurs = dict(publieurs or {})

    def _publier(self, ligne: Mapping[str, Any]) -> None:
        publieur = self.publieurs.get(ligne["type"])
        if publieur is None:
            journal.debug("outbox : type sans consommateur %s", ligne["type"])
            return
        publieur(ligne)

    def traiter(self, limite: int = 100) -> int:
        conn = self.connect()
        try:
            return depot.publier_outbox(conn, self._publier, limite=limite)
        finally:
            close = getattr(conn, "close", None)
            if close:
                close()


def planifier_projection(conn, tenant_id: str, twins, relations, run_id: str = "graph") -> int:
    """Producteur d'événement de projection, transactionnel avec l'appelant.

    Les doubles de test du gardien n'exposent pas de transaction : dans ce cas, la projection
    d'outbox est simplement ignorée, le graphe direct restant la preuve de la synchronisation.
    """
    if not hasattr(conn, "transaction") or not hasattr(conn, "execute"):
        return 0
    with conn.transaction():
        return depot.ajouter_outbox(conn, tenant_id, run_id, "graph.synchroniser", {
            "twins": list(twins or ()),
            "relations": list(relations or ()),
        })
