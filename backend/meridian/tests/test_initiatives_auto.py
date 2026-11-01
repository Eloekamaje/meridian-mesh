"""Une situation haute peut déposer une proposition d'initiative, jamais une décision."""
import asyncio

from meridian.application import initiatives_auto


class Initiatives:
    def __init__(self):
        self.docs = {}
        self.appels = []

    async def update_one(self, filtre, maj, upsert=False):
        self.appels.append((filtre, maj, upsert))
        if filtre["id"] not in self.docs:
            self.docs[filtre["id"]] = dict(maj["$setOnInsert"])


class Db:
    def __init__(self):
        self.initiatives = Initiatives()


def _situation(priorite="haute"):
    return {"id": "sit-interfaces-tbt-run-1", "titre": "Interface retirée", "resume": "Une rupture.",
            "priorite": priorite, "jumeaux": ["tbt"], "type": "interface"}


def test_une_situation_haute_cree_une_proposition_idempotente():
    db = Db()
    premier = asyncio.run(initiatives_auto.proposer(db, _situation()))
    second = asyncio.run(initiatives_auto.proposer(db, _situation()))

    assert premier["statut"] == "en_attente" and premier["situation_id"] == "sit-interfaces-tbt-run-1"
    assert second["id"] == premier["id"] and len(db.initiatives.docs) == 1


def test_une_situation_normale_ne_cree_rien():
    db = Db()
    assert asyncio.run(initiatives_auto.proposer(db, _situation("normale"))) is None
    assert db.initiatives.docs == {}
