"""Double lecture Mongo/canonique : comptes et ids manquants, sans écriture."""
import asyncio

from jumeau import parite_mongo
from jumeau.graphe import Arete, GrapheMemoire, NoeudTwin

TENANT = "demo"


class _Db:
    jumeaux = [{"id": "a"}, {"id": "b"}]
    relations = [{"id": "r1"}]
    situations = [{"id": "s1"}]
    initiatives = [{"id": "i1"}]


class _Curseur:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, requete, _params):
        self.requete = requete
        return self

    def fetchall(self):
        if "FROM jumeau" in self.requete:
            return [("a",), ("b",)]
        return [("s1", "SITUATION"), ("i1", "INITIATIVE")]


class _Conn:
    def cursor(self):
        return _Curseur()


def _store():
    store = GrapheMemoire()
    store.upsert_twin(NoeudTwin("a", TENANT, "APPLICATION", "A"))
    store.upsert_twin(NoeudTwin("b", TENANT, "APPLICATION", "B"))
    store.upsert_relation(Arete("r1", TENANT, "a", "b"))
    return store


def test_parite_sans_ecart_et_sans_ecriture():
    rapport = asyncio.run(parite_mongo.comparer(_Db(), _Conn(), _store(), TENANT))

    assert rapport["canonique"] == {
        "identites": 2, "twins_graphe": 2, "relations_graphe": 1, "objets": 2}
    assert rapport["ecarts"] == [
        {"nature": "identite", "mongo": 2, "canonique": 2, "manquants": [], "manquants_total": 0},
        {"nature": "situation", "mongo": 1, "canonique": 1, "manquants": [], "manquants_total": 0},
        {"nature": "initiative", "mongo": 1, "canonique": 1, "manquants": [], "manquants_total": 0},
        {"nature": "relation_graphe", "mongo": 1, "canonique": 1, "manquants": [], "manquants_total": 0},
    ]
