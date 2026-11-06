"""Cas d'usage de commande : la couche application ne dépend que du port."""
import asyncio

import pytest

from meridian.application import commandes
from meridian.domain import import_identite


class Store:
    def __init__(self, doc):
        self.doc = doc
        self.appels = []
        self.crees = []

    async def lire(self, cid):
        self.appels.append(cid)
        return self.doc

    async def creer(self, doc):
        self.crees.append(doc)


def _run(coro):
    return asyncio.run(coro)


def test_creer_commande_team_sans_application_id_genere_un_twin_id_stable():
    store = Store(None)
    doc = _run(commandes.creer_commande(
        store, type_twin="TEAM", nom="Équipe paiements", proprietaire="DSI", acteur="ana",
    ))
    jumeau = doc["jumeau"]
    assert jumeau["type_twin"] == "TEAM"
    assert jumeau["twin_id"].startswith("team-")
    assert jumeau["application_id"] == "" and "candidat" not in jumeau
    assert store.crees == [doc]


def test_creer_commande_ecosystem_accepte_perimetre_et_identifiants():
    store = Store(None)
    doc = _run(commandes.creer_commande(
        store, type_twin="ECOSYSTEM", twin_id="eco-paiements",
        nom="Écosystème", proprietaire="DSI", perimetre="Paiements",
        identifiants={"team_id": "eq-paiements"}, acteur="ana",
    ))
    assert doc["jumeau"] == {
        "type_twin": "ECOSYSTEM", "twin_id": "eco-paiements", "application_id": "",
        "nom": "Écosystème", "proprietaire": "DSI", "perimetre": "Paiements",
        "identifiants": {"team_id": "eq-paiements"},
    }


def test_creer_commande_application_exige_un_app_id_ou_le_mode_candidat():
    with pytest.raises(commandes.IdentiteInvalide, match="application_id requis"):
        _run(commandes.creer_commande(
            Store(None), type_twin="APPLICATION", nom="App", proprietaire="Équipe",
            acteur="ana",
        ))
    doc = _run(commandes.creer_commande(
        Store(None), type_twin="APPLICATION", candidat=True,
        nom="App candidate", proprietaire="Équipe", acteur="ana",
    ))
    assert doc["jumeau"]["twin_id"].startswith("app-")
    assert doc["jumeau"]["candidat"] is True


def test_creer_commande_application_conserve_twin_id_et_application_id():
    doc = _run(commandes.creer_commande(
        Store(None), type_twin="APPLICATION", twin_id="twin-paiements",
        application_id="paiements", nom="Paiements", proprietaire="Équipe", acteur="ana",
    ))
    assert doc["jumeau"]["twin_id"] == "twin-paiements"
    assert doc["jumeau"]["application_id"] == "paiements"


def test_creer_commande_team_refuse_un_application_id():
    with pytest.raises(commandes.IdentiteInvalide, match="application_id interdit"):
        _run(commandes.creer_commande(
            Store(None), type_twin="TEAM", application_id="paiements",
            nom="Équipe", proprietaire="DSI", acteur="ana",
        ))


def test_creer_commande_resource_utilise_l_identifiant_externe_si_present():
    doc = _run(commandes.creer_commande(
        Store(None), type_twin="RESOURCE", nom="Base CRM", proprietaire="Infra",
        identifiants={"resource_id": "ci-4242"}, acteur="ana",
    ))
    assert doc["jumeau"]["twin_id"] == "ci-4242"
    assert doc["jumeau"]["identifiants"] == {"resource_id": "ci-4242"}


def test_creer_commande_sans_type_reste_compatible_avec_l_ancien_brouillon():
    doc = _run(commandes.creer_commande(
        Store(None), application_id="paiements", nom="Paiements",
        proprietaire="Équipe paiements", acteur="ana",
    ))
    assert doc["jumeau"] == {
        "application_id": "paiements", "nom": "Paiements",
        "proprietaire": "Équipe paiements",
    }


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


def test_suivre_naissance_rend_l_etat_ou_non_lancee():
    store = Store({"id": "c1", "jumeau_id": "app", "naissance": {"etat": "en_cours"}})
    assert _run(commandes.suivre_naissance(store, "c1"))["etat"] == "en_cours"
    store = Store({"id": "c1"})
    assert _run(commandes.suivre_naissance(store, "c1"))["etat"] == "non_lancee"
    with pytest.raises(commandes.CommandeIntrouvable):
        _run(commandes.suivre_naissance(Store(None), "c1"))
