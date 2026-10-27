"""Le Travail comme état de l'agent : Flore planifie et écrit dans le Travail (base Mongo jetable)."""
import asyncio
import os
import uuid

import pytest

from jumeau.travail import EcritureTravail, etat_texte

pytestmark = pytest.mark.skipif(not os.environ.get("MONGO_URL"), reason="MONGO_URL non défini")


def avec_travail(test):
    """Exécute `test(ecriture, db)` sur un Travail neuf dans une base jetable."""
    from motor.motor_asyncio import AsyncIOMotorClient

    async def scenario():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        nom = f"test_jumeau_{uuid.uuid4().hex[:8]}"
        db = client[nom]
        await db.cases.insert_one({"id": "t1", "titre": "Retirer TBT", "objectif": "Mesurer l'impact du retrait de TBT",
                                   "questions": [{"texte": "Qui appelle TBT ?", "resolue": True}],
                                   "hypotheses": [], "options": [], "livrables": [], "historique": []})
        try:
            return await test(EcritureTravail(db, "t1"), db)
        finally:
            await client.drop_database(nom)
            client.close()
    return asyncio.run(scenario())


def test_planifier_ajoute_les_etapes_sans_doublon_et_garde_les_resolues():
    async def test(e, db):
        await e.planifier(["Qui appelle TBT ?", "Quelles données TBT conserve-t-elle ?"], "Tracer les appelants")
        c = await db.cases.find_one({"id": "t1"})
        assert c["questions"] == [{"texte": "Qui appelle TBT ?", "resolue": True},
                                  {"texte": "Quelles données TBT conserve-t-elle ?", "resolue": False}]
        assert c["prochaine_etape"] == "Tracer les appelants"
        assert c["historique"][-1]["texte"].startswith("Plan mis à jour par Flore")
    avec_travail(test)


def test_resoudre_une_etape():
    async def test(e, db):
        await e.planifier(["Quelles données TBT conserve-t-elle ?"], "")
        assert await e.resoudre("Quelles données TBT conserve-t-elle ?") is True
        assert await e.resoudre("Inconnue") is False
        c = await db.cases.find_one({"id": "t1"})
        assert all(q["resolue"] for q in c["questions"])
    avec_travail(test)


def test_hypothese_option_livrable_et_resume_au_format_des_travaux():
    async def test(e, db):
        h = await e.hypothese("TBT n'est appelée que par le portail")
        o = await e.option("Retrait progressif", "Couper le portail d'abord", "faible")
        l = await e.livrable("Fiche d'impact", "Trois appelants…")
        await e.resume("Deux appelants identifiés.")
        c = await db.cases.find_one({"id": "t1"})
        assert c["hypotheses"] == [h] and h["statut"] == "a_valider" and h["id"] == "hyp-1"
        assert c["options"] == [o] and o["statut"] == "a_evaluer" and o["risque"] == "faible"
        assert c["livrables"] == [l] and l["titre"] == "Fiche d'impact"
        assert c["resume"] == "Deux appelants identifiés."
    avec_travail(test)


def test_valeurs_bornees_et_risque_normalise():
    async def test(e, db):
        o = await e.option("x" * 500, "y" * 9000, "énorme")
        assert len(o["titre"]) <= 120 and len(o["description"]) <= 4000 and o["risque"] == "moyen"
        with pytest.raises(ValueError):
            await e.hypothese("   ")
    avec_travail(test)


def test_etat_texte_resume_le_travail_pour_le_contexte_de_flore():
    texte = etat_texte({"titre": "Retirer TBT", "objectif": "Mesurer l'impact",
                        "questions": [{"texte": "Qui appelle TBT ?", "resolue": True}, {"texte": "Quelles données ?", "resolue": False}],
                        "hypotheses": [{"texte": "Seul le portail", "statut": "a_valider"}],
                        "options": [{"titre": "Retrait progressif", "statut": "a_evaluer"}],
                        "livrables": [{"titre": "Fiche d'impact"}], "prochaine_etape": "Tracer"})
    for attendu in ("Mesurer l'impact", "[x] Qui appelle TBT ?", "[ ] Quelles données ?", "Seul le portail",
                    "Retrait progressif", "Fiche d'impact", "Tracer"):
        assert attendu in texte
