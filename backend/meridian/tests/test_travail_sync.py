"""Backfill et synchronisation incrémentale Travail : fakes, idempotence et curseur."""
import asyncio

from meridian.application.travail_sync import Curseur, remplir, synchroniser


def document(identifiant, maj_le, titre=None):
    return {"_id": identifiant, "id": f"case-{identifiant}", "maj_le": maj_le,
            "cree_le": maj_le, "titre": titre or f"Travail {identifiant}"}


class SourceFaux:
    def __init__(self, documents):
        self.documents = [dict(d) for d in documents]

    async def lister_par_id(self, apres_id, limite):
        documents = sorted(self.documents, key=lambda d: str(d["_id"]))
        if apres_id is not None:
            documents = [d for d in documents if str(d["_id"]) > str(apres_id)]
        return documents[:limite]

    async def lister_apres(self, maj_le, apres_id, limite):
        documents = sorted(self.documents,
                           key=lambda d: (d.get("maj_le") or "", str(d["_id"])))
        if maj_le is not None:
            documents = [
                d for d in documents
                if (d.get("maj_le") or "") > maj_le
                or ((d.get("maj_le") or "") == maj_le
                    and str(d["_id"]) > str(apres_id or ""))
            ]
        return documents[:limite]


class CibleFaux:
    def __init__(self):
        self.documents = {}
        self.upserts = 0
        self.changements = 0

    async def upsert(self, travail):
        self.upserts += 1
        document = dict(travail)
        cle = document["id"]
        if self.documents.get(cle) != document:
            self.changements += 1
        nouveau = cle not in self.documents
        self.documents[cle] = document
        return nouveau


def test_le_backfill_est_idempotent_et_lit_par_lots():
    source = SourceFaux([document("a", "2026-01-01T00:00:00+00:00"),
                         document("b", "2026-01-02T00:00:00+00:00"),
                         document("c", "2026-01-03T00:00:00+00:00")])
    cible = CibleFaux()

    premier = asyncio.run(remplir(source, cible, limite=1))
    assert premier.lus == 3 and premier.ecrits == 3 and premier.lots == 4
    assert set(cible.documents) == {"case-a", "case-b", "case-c"}
    assert cible.changements == 3

    second = asyncio.run(remplir(source, cible, limite=2))
    assert second.lus == 3
    assert cible.changements == 3  # aucun document modifié : la version Postgres ne bougerait pas
    assert cible.documents["case-b"]["_id"] == "b"


def test_le_dry_run_ne_touche_pas_la_cible():
    source = SourceFaux([document("a", "2026-01-01T00:00:00+00:00")])
    bilan = asyncio.run(remplir(source, None, limite=10, appliquer=False))
    assert bilan.lus == 1 and bilan.ecrits == 0


def test_la_synchronisation_reprend_apres_le_curseur_sans_doublon_ni_trou():
    source = SourceFaux([document("a", "2026-01-01T00:00:00+00:00"),
                         document("b", "2026-01-01T00:00:00+00:00"),
                         document("c", "2026-01-02T00:00:00+00:00")])
    cible = CibleFaux()

    curseur = Curseur()
    vus = []
    while True:
        bilan = asyncio.run(synchroniser(source, cible, curseur=curseur, limite=1))
        if not bilan.lus:
            break
        vus.extend(cle for cle in cible.documents if cle not in vus)
        curseur = bilan.curseur
    assert vus == ["case-a", "case-b", "case-c"]
    assert curseur.maj_le == "2026-01-02T00:00:00+00:00" and curseur.id == "c"

    encore = asyncio.run(synchroniser(source, cible, curseur=curseur, limite=5))
    assert encore.lus == 0 and encore.curseur == curseur


def test_une_mise_a_jour_posterieure_est_reprise_seule():
    source = SourceFaux([document("a", "2026-01-01T00:00:00+00:00")])
    cible = CibleFaux()
    premier = asyncio.run(synchroniser(source, cible, limite=10))
    assert premier.lus == 1

    source.documents[0]["maj_le"] = "2026-01-03T00:00:00+00:00"
    source.documents[0]["titre"] = "Travail modifié"
    suite = asyncio.run(synchroniser(source, cible, curseur=premier.curseur, limite=10))
    assert suite.lus == 1 and suite.curseur.maj_le == "2026-01-03T00:00:00+00:00"
    assert cible.documents["case-a"]["titre"] == "Travail modifié"
