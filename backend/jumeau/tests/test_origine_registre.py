"""Les vues disent d'où vient un jumeau (plan de remédiation L2.1).

Le registre ne contient plus de jumeaux mockés : les entrées réelles naissent d'une source.
"""
import pytest

from jumeau import registre

server = pytest.importorskip("server")


def test_un_jumeau_reel_se_declare_reel():
    p = server.projete_jumeau({"id": "conduit", "nom": "Conduit", "reel": True}, "existence")
    assert (p["reel"], p["origine"]) == (True, "reel")


def test_un_jumeau_de_demonstration_se_declare_demonstration():
    p = server.projete_jumeau({"id": "paiements", "nom": "Paiements"}, "existence")
    assert (p["reel"], p["origine"]) == (False, "demonstration")


def test_le_registre_marque_les_jumeaux_reels_en_entrant():
    doc = registre.document({"id": "tbt", "nom": "TBT", "domaine": "P", "mission": None, "equipe": "eq",
                             "curseur": "a" * 12, "claims": 10, "depots": 1, "types": ["GIT"], "liste_depots": []})
    assert doc["reel"] is True


def test_la_decouverte_des_sources_ne_fabrique_plus_de_liste(monkeypatch):
    """L2.6 : six sources inventées étaient rendues comme « détectées », dans le chemin de production."""
    import asyncio

    class Commandes:
        async def find_one(self, *a, **k):
            return {"id": "c1", "etat": "brouillon", "sources": [{"connecteur": "github", "nom": "Dépôt TBT"}]}

    class Db:
        commandes = Commandes()

    monkeypatch.setattr(server, "db", Db())
    r = asyncio.run(server.apercu_import("c1", server.ImportApercu(
        mode="cmdb", contenu=[{"application_id": "tbt", "nom": "TBT", "proprietaire": "Équipe TBT"}])))
    assert r["detectees"] == 1 and r["nouvelles"] == []
    assert r["presentes"] == [{"connecteur": "github", "nom": "Dépôt TBT"}]  # ce qui est déclaré, rien de plus
