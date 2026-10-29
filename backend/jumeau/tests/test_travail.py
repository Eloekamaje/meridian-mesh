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
        assert c["hypotheses"] == [h] and h["statut"] == "a_valider" and h["id"].startswith("hyp-")
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


def test_identifiants_uniques_et_doublons_ignores():
    async def test(e, db):
        await db.cases.update_one({"id": "t1"}, {"$push": {"hypotheses": {"id": "hyp-1", "texte": "ajoutée à la main"}}})
        h1 = await e.hypothese("Seul le portail appelle TBT")
        h2 = await e.hypothese("Seul le portail appelle TBT")
        o1 = await e.option("Retrait progressif", "", "faible")
        o2 = await e.option("Retrait progressif", "autre texte", "faible")
        c = await db.cases.find_one({"id": "t1"})
        ids = [h["id"] for h in c["hypotheses"]]
        assert len(ids) == len(set(ids)) == 2 and h1 == h2 and o1 == o2 and len(c["options"]) == 1
    avec_travail(test)


def test_un_livrable_de_meme_titre_est_mis_a_jour_pas_duplique():
    async def test(e, db):
        await e.livrable("Fiche d'impact", "v1")
        await e.livrable("Fiche d'impact", "v2")
        c = await db.cases.find_one({"id": "t1"})
        assert [l["contenu"] for l in c["livrables"]] == ["v2"]
    avec_travail(test)


def test_planifier_n_ecrase_pas_une_question_ajoutee_entre_temps_et_borne_les_etapes():
    async def test(e, db):
        await db.cases.update_one({"id": "t1"}, {"$push": {"questions": {"texte": "Ajoutée par l'équipe", "resolue": False}}})
        await e.planifier([f"Étape {n}" for n in range(30)], "")
        c = await db.cases.find_one({"id": "t1"})
        textes = [q["texte"] for q in c["questions"]]
        assert "Ajoutée par l'équipe" in textes and len(textes) == 2 + EcritureTravail.MAX_ETAPES
    avec_travail(test)


def _msgs(n):
    """n messages alternés interlocuteur / Flore (n // 2 échanges)."""
    return [{"role": "utilisateur" if k % 2 == 0 else "flore", "texte": "m"} for k in range(n)]


def test_rappel_quand_le_plan_n_a_pas_bouge_depuis_plusieurs_echanges():
    plan = [{"texte": "A", "resolue": False}]
    base = {"titre": "T", "questions": plan, "plan_au_message": 2}
    assert "n'a pas bougé depuis 4 échanges" in etat_texte({**base, "conversation": _msgs(10)})
    assert "Rappel" not in etat_texte({**base, "conversation": _msgs(6)})
    assert "Rappel" not in etat_texte({"titre": "T", "questions": plan, "conversation": _msgs(10)})
    fini = [{"texte": "A", "resolue": True}]
    assert "Rappel" not in etat_texte({**base, "questions": fini, "conversation": _msgs(10)})


def test_rappel_de_planifier_une_seule_fois_et_sans_compter_la_veille():
    assert "Pas encore de plan" in etat_texte({"titre": "T", "conversation": _msgs(4)})
    assert "Pas encore de plan" not in etat_texte({"titre": "T", "conversation": _msgs(2)})
    assert "Pas encore de plan" not in etat_texte({"titre": "T", "conversation": _msgs(6)})  # déjà rappelé
    veille = [{"role": "evenement", "texte": "v"}] * 5
    assert "Pas encore de plan" not in etat_texte({"titre": "T", "conversation": _msgs(2) + veille})


def test_planifier_et_lever_une_etape_enregistrent_la_position_dans_la_conversation():
    async def test(e, db):
        await db.cases.update_one({"id": "t1"}, {"$set": {"conversation": _msgs(4)}})
        await e.planifier(["Étape A"], "")
        assert (await e.etat())["plan_au_message"] == 4
        await db.cases.update_one({"id": "t1"}, {"$set": {"conversation": _msgs(8)}})
        await e.resoudre("Étape A")
        assert (await e.etat())["plan_au_message"] == 8
    avec_travail(test)


def test_precision_s_inscrit_dans_le_travail_puis_se_retire_une_fois():
    async def test(e, db):
        await e.precision("Quel périmètre ?", ["Le portail seul", " Tout le SI "])
        c = await db.cases.find_one({"id": "t1"})
        assert c["precision"] == {"question": "Quel périmètre ?", "options": ["Le portail seul", "Tout le SI"]}
        assert c["historique"][-1]["texte"].startswith("Précision demandée par Flore")
        with pytest.raises(ValueError):  # une seule précision par réponse
            await e.precision("Autre question ?", ["x", "y"])
        assert await e.retirer_precision() == c["precision"]
        assert await e.retirer_precision() is None
    avec_travail(test)


@pytest.mark.parametrize("question,options", [
    ("", ["a", "b"]), ("Q ?", ["a"]), ("Q ?", list("abcde")), ("Q ?", ["a", "  "]),
    ("Q ?", ["a", "b\nc"]), ("Q ?", ["a", "A"]), ("Q ?", ["a", "x" * 81]), ("Q ?", None),
])
def test_precision_refuse_les_arguments_invalides(question, options):
    async def test(e, db):
        with pytest.raises(ValueError):
            await e.precision(question, options)
        assert "precision" not in await db.cases.find_one({"id": "t1"})
    avec_travail(test)


def test_eprouver_une_hypothese_inscrit_le_constat_sans_la_valider():
    async def test(e, db):
        await e.hypothese("Aucune autre application n'appelle Conduit")
        await e.eprouver("Aucune autre application n'appelle Conduit", "tombe", ["conduit:app/api.py#L3-L9"])
        await e.eprouver("Conduit garde ses données sur un seul disque", "indecise", [])  # absente : créée
        c = await db.cases.find_one({"id": "t1"})
        h1, h2 = c["hypotheses"]
        assert h1["statut"] == "a_valider"  # le constat de Flore ne décide pas : l'équipe valide
        assert h1["epreuve"]["verdict"] == "tombe" and h1["epreuve"]["preuves"] == ["conduit:app/api.py#L3-L9"]
        assert h2["texte"] == "Conduit garde ses données sur un seul disque" and h2["epreuve"]["verdict"] == "indecise"
        assert c["historique"][-1]["texte"].startswith("Hypothèse mise à l'épreuve par Flore")
        with pytest.raises(ValueError):
            await e.eprouver("x", "peut-etre", [])
    avec_travail(test)
