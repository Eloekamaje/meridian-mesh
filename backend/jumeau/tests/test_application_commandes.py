"""Cas d'usage de commande : la couche application ne dépend que du port."""
import asyncio

import pytest

from meridian.application import commandes
from meridian.domain import import_identite


class Store:
    def __init__(self, doc):
        self.doc = doc
        self.appels = []

    async def lire(self, cid):
        self.appels.append(cid)
        return self.doc


def _run(coro):
    return asyncio.run(coro)


def test_apercu_import_rend_identite_et_nouvelles_sources():
    store = Store({"id": "c1", "etat": "brouillon", "sources": []})
    resultat = _run(commandes.apercu_import(
        store, "c1", "manifeste",
        {"jumeau": {"application_id": "remboursements", "nom": "Remboursements",
                    "proprietaire": "Paiements"},
         "sources": [{"connecteur": "github", "nom": "code"}]},
        connus=["github"],
    ))
    assert resultat["identite"]["application_id"] == "remboursements"
    assert [s["nom"] for s in resultat["nouvelles"]] == ["code"]
    assert store.appels == ["c1"]


def test_apercu_import_refuse_une_commande_absente_ou_lancee():
    with pytest.raises(commandes.CommandeIntrouvable):
        _run(commandes.apercu_import(Store(None), "c1", "cmdb", [], connus=[]))
    with pytest.raises(commandes.CommandeModifiee):
        _run(commandes.apercu_import(Store({"id": "c1", "etat": "lancee"}), "c1", "cmdb", [], connus=[]))


def test_apercu_import_refuse_un_connecteur_non_branche():
    store = Store({"id": "c1", "etat": "brouillon", "sources": []})
    with pytest.raises(import_identite.ImportInvalide):
        _run(commandes.apercu_import(
            store, "c1", "manifeste",
            {"jumeau": {"application_id": "remboursements", "nom": "R", "proprietaire": "P"},
             "sources": [{"connecteur": "postgresql", "nom": "db"}]},
            connus=["github"],
        ))
