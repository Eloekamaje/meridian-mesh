"""Le port Travail est isolé de Mongo par un adapter testable."""
import asyncio

from meridian.adapters.outbound.mongo.travail_depot import TravailDepot


async def _async(valeur):
    return valeur


class Collection:
    def __init__(self):
        self.documents = [{"id": "c1", "titre": "Un"}, {"id": "c2", "titre": "Deux"}]
        self.maj = []

    def find(self, filtre, projection):
        documents = [d for d in self.documents if all(d.get(k) == v for k, v in filtre.items())]

        class Curseur:
            async def to_list(self, limite):
                return documents[:limite]

        return Curseur()

    async def find_one(self, filtre, projection):
        return next((d for d in self.documents if all(d.get(k) == v for k, v in filtre.items())), None)

    async def update_one(self, filtre, maj):
        self.maj.append((filtre, maj))
        return type("Resultat", (), {"matched_count": 1})()


def test_lister_lire_et_mettre_a_jour_sans_mongo():
    collection = Collection()
    depot = TravailDepot(collection)
    assert asyncio.run(depot.lister(limite=1)) == [{"id": "c1", "titre": "Un"}]
    assert asyncio.run(depot.lire("c2"))["titre"] == "Deux"
    assert asyncio.run(depot.mettre_a_jour("c1", {"titre": "Modifié"}))
    assert collection.maj == [({"id": "c1"}, {"$set": {"titre": "Modifié"}})]
