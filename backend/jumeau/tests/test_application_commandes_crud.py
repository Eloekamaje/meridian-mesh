"""CRUD et tests de sources d'une commande, sans HTTP ni Mongo : la couche application ne dépend que du port."""
import asyncio

import pytest

from meridian.application import commandes


class Store:
    def __init__(self, doc=None, connexions=()):
        self.doc = doc
        self.connexions_docs = list(connexions)
        self.crees = []
        self.majs = []
        self.appels = []
        self.maj_ok = True

    async def lire(self, cid):
        self.appels.append(("lire", cid))
        return self.doc

    async def lister(self, *, etat="brouillon", limite=50):
        self.appels.append(("lister", etat, limite))
        return [self.doc] if self.doc else []

    async def creer(self, doc):
        self.crees.append(doc)

    async def mettre_a_jour(self, cid, patch, *, etat="brouillon"):
        self.majs.append((cid, patch, etat))
        return self.maj_ok

    async def connexions(self):
        return self.connexions_docs


def _run(coro):
    return asyncio.run(coro)


def test_creer_commande_ouvre_un_brouillon_et_le_persiste():
    store = Store()
    doc = _run(commandes.creer_commande(
        store, application_id="remboursements", nom="Remboursements",
        proprietaire="Paiements", acteur="ana",
    ))
    assert doc["id"].startswith("cmd-")
    assert (doc["etat"], doc["etape"], doc["sources"]) == ("brouillon", 1, [])
    assert doc["jumeau"] == {"application_id": "remboursements", "nom": "Remboursements",
                             "proprietaire": "Paiements"}
    assert (doc["cree_par"], "cree_le" in doc) == ("ana", True)
    assert store.crees == [doc]
    assert "_id" not in doc


def test_lister_commandes_ne_rend_que_les_brouillons():
    store = Store({"id": "c1", "etat": "brouillon"})
    assert _run(commandes.lister_commandes(store)) == [store.doc]
    assert store.appels == [("lister", "brouillon", 50)]


def test_lire_commande_refuse_une_commande_absente():
    with pytest.raises(commandes.CommandeIntrouvable):
        _run(commandes.lire_commande(Store(None), "c1"))


def test_maj_sans_champ_ne_touche_pas_au_depot():
    store = Store({"id": "c1", "etat": "brouillon"})
    assert _run(commandes.maj_commande(
        store, "c1", {}, prefixes={}, systemes={},
    )) == {"ok": True}
    assert store.appels == [] and store.majs == []


def test_maj_refuse_une_etape_inconnue():
    with pytest.raises(commandes.EtapeInvalide):
        _run(commandes.maj_commande(Store(None), "c1", {"etape": 5}, prefixes={}, systemes={}))


def test_maj_refuse_une_commande_absente_ou_lancee():
    with pytest.raises(commandes.CommandeIntrouvable):
        _run(commandes.maj_commande(Store(None), "c1", {"etape": 2}, prefixes={}, systemes={}))
    with pytest.raises(commandes.CommandeModifiee):
        _run(commandes.maj_commande(
            Store({"id": "c1", "etat": "lancee"}), "c1", {"etape": 2}, prefixes={}, systemes={},
        ))


def test_maj_protege_les_sources_et_le_statut():
    store = Store(
        {"id": "c1", "etat": "brouillon",
         "sources": [{"id": "s1", "statut": "a_configurer"},
                     {"id": "s2", "statut": "prete"}]},
        connexions=[{"id": "gh-acme", "reference": "vault:gh"},
                    {"id": "jr-acme", "reference": "vault:jr", "hote": "banque.atlassian.net"}],
    )
    patch = {"sources": [
        {"id": "s1", "connecteur": "github", "statut": "prete",
         "config": {"connexion": "gh-acme", "secret": "s3cr3t", "token": "autre"}},
        {"id": "s2", "connecteur": "jira", "statut": "prete",
         "config": {"connexion": "jr-acme", "hote": "evil.example.com"}},
        {"id": "s3", "connecteur": "github", "statut": "prete",
         "config": {"connexion": "jr-acme"}},
        {"id": "s4", "connecteur": "postgresql", "config": {"secret": "brut"}},
    ]}
    r = _run(commandes.maj_commande(
        store, "c1", patch,
        prefixes={"github": "gh-", "jira": "jr-"}, systemes={"jira"},
        maintenant="2026-01-01T00:00:00+00:00",
    ))
    assert r == {"ok": True, "maj_le": "2026-01-01T00:00:00+00:00"}
    sources = store.majs[0][1]["sources"]
    assert sources[0]["statut"] == "a_configurer"  # « prête » ne s'attribue pas
    assert sources[0]["config"] == {"connexion": "gh-acme", "secret": "vault:gh"}
    assert sources[1]["statut"] == "prete" and sources[1]["config"]["hote"] == "banque.atlassian.net"
    assert sources[2]["config"]["secret"] == ""  # connexion d'un autre connecteur refusée
    assert sources[3]["config"] == {}
    assert "s3cr3t" not in str(store.majs) and "brut" not in str(store.majs)
    assert store.majs[0][2] == "brouillon"


def test_maj_signale_une_course_avec_le_lancement():
    store = Store({"id": "c1", "etat": "brouillon"})
    store.maj_ok = False
    with pytest.raises(commandes.CommandeModifiee):
        _run(commandes.maj_commande(
            store, "c1", {"etape": 2}, prefixes={}, systemes={},
        ))


def test_tester_sources_ne_teste_que_les_sources_demandees():
    appels = []

    async def tester(source):
        appels.append(source["id"])
        return {"ok": True, "message": "connexion vérifiée", "statut": "prete"}

    store = Store({"id": "c1", "etat": "brouillon",
                   "sources": [{"id": "s1", "connecteur": "github"},
                               {"id": "s2", "connecteur": "jira"}]})
    resultats, modifie = _run(commandes.tester_sources(
        store, "c1", ["s2"], tester=tester, maintenant="2026-01-01T00:00:00+00:00",
    ))
    assert modifie and appels == ["s2"]
    assert resultats == {"s2": {"ok": True, "message": "connexion vérifiée", "statut": "prete"}}
    sources = store.majs[0][1]["sources"]
    assert "statut" not in sources[0]
    assert sources[1]["statut"] == "prete"
    assert store.majs[0][1]["maj_le"] == "2026-01-01T00:00:00+00:00"


def test_tester_sans_source_selectionnee_n_ecrit_pas():
    store = Store({"id": "c1", "etat": "brouillon", "sources": [{"id": "s1"}]})

    async def tester(source):
        raise AssertionError("aucune source ne devait être testée")

    assert _run(commandes.tester_sources(store, "c1", [], tester=tester)) == ({}, False)
    assert store.majs == []


def test_tester_refuse_une_commande_absente_ou_lancee_et_une_course():
    async def tester(source):
        return {}

    with pytest.raises(commandes.CommandeIntrouvable):
        _run(commandes.tester_sources(Store(None), "c1", ["s1"], tester=tester))
    with pytest.raises(commandes.CommandeModifiee):
        _run(commandes.tester_sources(
            Store({"id": "c1", "etat": "lancee"}), "c1", ["s1"], tester=tester,
        ))
    store = Store({"id": "c1", "etat": "brouillon", "sources": [{"id": "s1"}]})
    store.maj_ok = False
    with pytest.raises(commandes.CommandeModifiee):
        _run(commandes.tester_sources(store, "c1", ["s1"], tester=tester))


def test_naissance_possible_exige_code_ou_ancre_et_substance():
    assert commandes.naissance_possible({"github"})
    assert commandes.naissance_possible({"servicenow", "datadog"})
    assert commandes.naissance_possible({"cmdb", "confluence"})
    assert not commandes.naissance_possible({"datadog"})
    assert not commandes.naissance_possible({"servicenow"})
    assert not commandes.naissance_possible({"jira", "servicenow"})
