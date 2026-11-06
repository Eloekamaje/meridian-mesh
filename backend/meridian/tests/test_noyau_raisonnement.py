"""Noyau de raisonnement : niveaux, clarification, critique et gates."""
import asyncio

from meridian.application import noyau_raisonnement as noyau
from meridian.domain import dossier_raisonnement as domaine


def test_question_simple_reste_directe():
    demande = noyau.qualifier("Qui es-tu ?")
    assert demande.niveau == "N0"
    assert demande.but == "repondre"
    assert demande.questions == ()


def test_conception_ambiguë_demande_un_cadrage_avant_de_générer():
    demande = noyau.qualifier("Peux-tu dessiner une architecture pour une application de dating ?")
    assert demande.niveau == "N3"
    assert demande.but == "concevoir"
    assert demande.ambiguite >= 0.6
    assert len(demande.questions) >= 3

    cadre = noyau.cadrer(demande)
    assert cadre.questions_bloquantes
    assert not cadre.complet


def test_dessiner_une_application_existante_est_une_illustration():
    demande = noyau.qualifier(
        "Dessine le fonctionnement de l'application meridian, avec les étapes principales.",
        {"twin_ids": ["meridian"]})
    assert demande.but == "expliquer"
    assert demande.niveau in {"N1", "N2"}
    assert demande.questions == ()


def test_sans_questions_permet_de_continuer_avec_hypothèses():
    demande = noyau.qualifier("Conçois une application", {"sans_questions": True})
    cadre = noyau.cadrer(demande, {"sans_questions": True})
    assert not cadre.questions_bloquantes
    assert cadre.hypotheses


def test_tour_bloqué_ne_génère_pas_de_livraison():
    appels = []

    async def generer(cadre, plan):
        appels.append((cadre, plan))
        return {"reponse": "ne doit pas être appelé"}

    dossier = asyncio.run(noyau.executer_tour(
        "Peux-tu dessiner une architecture pour une application de dating ?", generer))
    assert appels == []
    assert dossier.statut == "clarification_requise"
    assert dossier.reponse["questions"]


def test_tour_complet_avec_options_critique_et_validation():
    async def generer(cadre, plan):
        return {
            "reponse": "Deux options sont proposées.",
            "hypotheses": [{"texte": "Le besoin est mobile", "test": "valider avec le commanditaire"}],
            "options": [
                {"titre": "Option A", "avantages": ["simple"], "risques": ["coût"]},
                {"titre": "Option B", "avantages": ["solide"], "risques": ["complexité"]},
            ],
            "validation": [{"hypothese": "Le besoin est mobile", "critere": "prototype accepté"}],
            "preuves": ["brief"],
        }

    dossier = asyncio.run(noyau.executer_tour(
        "Conçois une application", generer, contexte={"sans_questions": True}))
    assert dossier.statut == "proposition"
    assert len(dossier.options) == 2
    assert dossier.critiques
    assert all(g.statut != "echec" for g in dossier.gates)


def test_un_livrable_sans_options_est_bloqué_même_en_mode_provisoire():
    async def generer(cadre, plan):
        return {"reponse": "Une seule réponse.", "hypotheses": ["h"], "validation": ["v"]}

    dossier = asyncio.run(noyau.executer_tour(
        "Conçois une application", generer, contexte={"sans_questions": True}, strict=False))
    assert dossier.statut == "partiel"
    assert any(g.id == "G-KRN-03" and g.statut == "echec" for g in dossier.gates)
    assert any(f.rubrique == "options" for c in dossier.critiques for f in c.findings)


def test_schema_trop_dense_est_un_finding_majeur():
    reponse = {
        "reponse": "Schéma",
        "hypotheses": ["h"],
        "options": [{"titre": "A", "risques": ["r"]}, {"titre": "B", "risques": ["r"]}],
        "validation": [{"hypothese": "h", "critere": "c"}],
        "schemas": [{"boites": [{"id": str(i)} for i in range(12)],
                     "fleches": [{} for _ in range(20)]}],
    }
    dossier = noyau.analyser_reponse("Conçois une application", reponse,
                                     contexte={"sans_questions": True})
    assert any(f.rubrique == "schema" for c in dossier.critiques for f in c.findings)


def test_domaine_sensible_sans_risques_déclenche_une_critique():
    reponse = {
        "reponse": "Architecture",
        "hypotheses": ["h"],
        "options": [{"titre": "A", "risques": ["r"]}, {"titre": "B", "risques": ["r"]}],
        "validation": [{"hypothese": "h", "critere": "c"}],
    }
    dossier = noyau.analyser_reponse(
        "Conçois une application de santé pour des mineurs", reponse,
        contexte={"sans_questions": True})
    assert "sante" in dossier.demande.sensibilite
    assert any(f.rubrique == "risque" for c in dossier.critiques for f in c.findings)


def test_analyser_reponse_attache_le_dossier_au_livrable():
    dossier = noyau.analyser_reponse("Qui es-tu ?", {"reponse": "Flore"})
    assert dossier.reponse["raisonnement"]["niveau"] == "N0"
    assert dossier.reponse["raisonnement_statut"] == "reponse"


def test_les_objets_du_dossier_sont_sérialisables():
    demande = noyau.qualifier("Qui es-tu ?")
    cadre = noyau.cadrer(demande)
    plan = noyau.planifier(demande, cadre)
    dossier = domaine.DossierRaisonnement(
        question="Qui es-tu ?", tenant="demo", demande=demande, cadre=cadre, plan=plan)
    vue = dossier.as_dict()
    assert vue["niveau"] == "N0"
    assert vue["demande"]["but"] == "repondre"
    assert vue["plan"]["operations"]


def test_une_premisse_non_verifiee_bloque_le_pourquoi():
    appel = []

    async def generer(cadre, plan):
        appel.append(True)
        return {"reponse": "Réponse causale"}

    dossier = asyncio.run(noyau.executer_tour(
        "Pourquoi paiements est-il déployé au Japon ?", generer,
        contexte={"twin_ids": ["paiements"]}))
    assert appel == []
    assert dossier.statut == "clarification_requise"
    assert dossier.question_frame is not None
    assert dossier.question_frame.bloquantes
    assert any("Confirmez" in question for question in dossier.cadre.questions_bloquantes)
    assert dossier.source_plan is not None
    assert dossier.source_plan.twins == ("paiements",)


def test_une_premisse_confirmée_par_un_constat_devient_une_croyance():
    dossier = noyau.preparer_dossier(
        "Pourquoi paiements est-il déployé au Japon ?",
        contexte={"twin_ids": ["paiements"]},
        pack_contexte={"faits": [{
            "titre": "paiements est déployé au Japon",
            "type": "CONSTAT", "confiance": 0.9, "preuves": ["p-1"],
            "donnees": {"twin_id": "paiements"},
        }]},
    )
    assert dossier.question_frame is not None
    assert dossier.question_frame.presuppositions[0].statut == "CONNU"
    assert not dossier.question_frame.bloquantes
    assert dossier.beliefs


def test_les_croyances_sont_reprises_au_tour_suivant():
    premier = noyau.preparer_dossier(
        "Quelles dépendances pour paiements ?",
        contexte={"twin_ids": ["paiements"]},
        pack_contexte={"faits": [{
            "titre": "paiements dépend de cartes", "type": "CONSTAT",
            "confiance": 0.8, "preuves": ["p-1"],
            "donnees": {"twin_id": "paiements"},
        }]},
    )
    second = noyau.preparer_dossier(
        "Et pour les remboursements ?",
        contexte={
            "twin_ids": ["paiements"],
            "beliefs": [b.as_dict() for b in premier.beliefs],
            "revisions": [r.as_dict() for r in premier.revisions],
        },
    )
    assert second.beliefs
    assert {b.id for b in second.beliefs} >= {b.id for b in premier.beliefs}


def test_une_question_meta_ne_bloque_pas_la_generation():
    appels = []

    async def generer(cadre, plan):
        appels.append((cadre, plan))
        return {"reponse": "Je ne l'ai pas dessiné parce que tu avais demandé le modèle de données."}

    dossier = asyncio.run(noyau.executer_tour(
        "pourquoi tu ne l'as pas dessiné ?", generer,
        contexte={"acte": "meta", "sans_questions": True}))

    assert len(appels) == 1
    assert dossier.statut == "reponse"
    assert not dossier.cadre.questions_bloquantes
    assert not dossier.question_frame.questions_bloquantes
