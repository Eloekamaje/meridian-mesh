"""B9 — contrat de preuve de la question : la sonde dicte ce qui trancherait."""
from meridian.application import contrat_question as contrat_module
from meridian.application import noyau_raisonnement as noyau
from meridian.application import sonde_evidence


def _sonde_identifiant_non_resolu(question="montre-moi le ticket ABC-123"):
    return sonde_evidence.sonder(question, recherche_lexicale=lambda q: [])


def _sonde_claire(question="quelles dépendances a l'application ?"):
    return sonde_evidence.sonder(
        question,
        recherche_lexicale=lambda q: [
            {"id": "c1", "jumeau_id": "orders",
             "objet": "DEPEND_DE orders → clients", "score": 0.9},
        ])


def test_question_anglaise_ou_fautee_produit_un_contrat():
    """Hors lexique français, la phrase n'est plus classée muette : le contrat
    vient de la sonde, pas des mots."""
    question = "why is the paymnt srvce failingg?"
    sans_sonde = contrat_module.contrat_pour(question)
    assert sans_sonde["effort"] == "standard"
    assert sans_sonde["artefacts_requis"]
    assert sans_sonde["formulation"]
    avec_sonde = contrat_module.contrat_pour(
        question,
        sonde_evidence.sonder(question, recherche_lexicale=lambda q: []))
    assert avec_sonde["effort"] == "approfondi"
    assert avec_sonde["artefacts_requis"]
    assert question in avec_sonde["formulation"]


def test_sonde_incertaine_exige_des_artefacts_et_un_effort_approfondi():
    sonde = _sonde_identifiant_non_resolu()
    contrat = contrat_module.contrat_pour("montre-moi le ticket ABC-123", sonde)
    assert contrat["verdict"] == "incertain"
    assert contrat["effort"] == "approfondi"
    assert contrat["artefacts_requis"]
    # L'identifiant cité et non résolu devient un artefact qui le désignerait.
    assert any(
        a["type"] == "document" and "ABC-123" in a["sujet"]
        for a in contrat["artefacts_requis"])
    assert contrat["manque"] == sonde["manque"]


def test_interpretations_rivales_demandent_une_mesure_discriminante():
    sonde = sonde_evidence.sonder(
        "conduite ?",
        recherche_lexicale=lambda q: [
            {"id": "c1", "jumeau_id": "conduite", "objet": "x", "score": 1.0},
            {"id": "c2", "jumeau_id": "conduit", "objet": "y", "score": 0.9}])
    contrat = contrat_module.contrat_pour("conduite ?", sonde)
    assert contrat["effort"] == "approfondi"
    assert any(
        a["type"] == "mesure" and "conduite" in a["sujet"] and "conduit" in a["sujet"]
        for a in contrat["artefacts_requis"])


def test_sonde_claire_donne_un_effort_standard_et_les_artefacts_trouves():
    contrat = contrat_module.contrat_pour(
        "quelles dépendances a l'application ?", _sonde_claire())
    assert contrat["verdict"] == "clair"
    assert contrat["effort"] == "standard"
    assert any(
        a["type"] == "twin" and a["sujet"] == "orders"
        for a in contrat["artefacts_requis"])


def test_sonde_triviale_donne_un_effort_leger():
    sonde = sonde_evidence.sonder(
        "montre-moi le ticket ABC-123",
        recherche_lexicale=lambda q: [
            {"id": "t1", "locator": "doc://tickets/ABC-123",
             "objet": "ticket ABC-123 résolu", "score": 0.9}])
    contrat = contrat_module.contrat_pour("montre-moi le ticket ABC-123", sonde)
    assert contrat["verdict"] == "trivial"
    assert contrat["effort"] == "leger"
    assert contrat["artefacts_requis"]


def test_sans_sonde_le_contrat_est_minimal_et_honnete():
    contrat = contrat_module.contrat_pour("n'importe quelle question")
    assert contrat["effort"] == "standard"
    assert contrat["manque"] == []
    assert contrat["verdict"] == ""
    assert contrat["artefacts_requis"] == [{
        "type": "proof",
        "sujet": "n'importe quelle question",
        "role": "couvre la question",
    }]
    # Même sans sonde, rien n'est déduit des mots : le sujet est la question entière.
    vide = contrat_module.contrat_pour("")
    assert vide["artefacts_requis"] == []


def test_sonde_non_mapping_est_un_contrat_minimal():
    contrat = contrat_module.contrat_pour("question", sonde="pas-une-sonde")
    assert contrat["effort"] == "standard"
    assert contrat["artefacts_requis"]


def test_cadrer_consomme_la_sonde_du_contexte():
    question = "montre-moi le ticket ABC-123"
    sonde = _sonde_identifiant_non_resolu(question)
    demande = noyau.qualifier(question)
    cadre = noyau.cadrer(demande, {"sonde": sonde})
    assert cadre.source == "contrat"
    # L'objectif est la formulation du contrat (ce qui trancherait), pas la phrase.
    assert "Trancher" in cadre.objectif
    assert "ABC-123" in cadre.objectif
    # Le manque de la sonde devient une inconnue, pas une question à l'utilisateur.
    assert any("non résolu" in inconnue for inconnue in cadre.inconnues)
    assert any("rivale" in risque or "tranché" in risque for risque in cadre.risques)
    assert not cadre.questions_bloquantes


def test_cadrer_sans_sonde_reste_sur_la_qualification():
    demande = noyau.qualifier("Qui es-tu ?")
    cadre = noyau.cadrer(demande, {})
    assert cadre.source == "qualifier"
    assert cadre.objectif == "Qui es-tu ?"
    assert cadre.inconnues == ()


def test_planifier_approfondit_quand_la_sonde_est_incertaine():
    question = "montre-moi le ticket ABC-123"
    contrat = contrat_module.contrat_pour(
        question, _sonde_identifiant_non_resolu(question))
    demande = noyau.qualifier(question)
    cadre = noyau.cadrer(demande, {"sonde": _sonde_identifiant_non_resolu(question)})
    plan = noyau.planifier(demande, cadre, contrat=contrat)
    assert plan.budget["appels_outils"] == 24
    assert plan.budget["secondes"] == 60
    assert "effort=approfondi" in plan.justification
    assert "source=contrat" in plan.justification
    assert plan.conditions_arret[0] == "artefacts requis du contrat obtenus"
    # L'incertitude relève le seuil de preuve : déclaré → observé.
    assert plan.seuil_preuve == "observed"


def test_planifier_sans_contrat_est_inchange():
    demande = noyau.qualifier("Qui es-tu ?")
    cadre = noyau.cadrer(demande)
    plan = noyau.planifier(demande, cadre)
    assert plan.budget["appels_outils"] == 12
    assert plan.budget["secondes"] == 30
    assert "effort=standard" not in plan.justification
    assert "source=contrat" not in plan.justification
    assert plan.seuil_preuve == "declared"


def test_preparer_dossier_porte_le_contrat_et_marque_la_source():
    question = "montre-moi le ticket ABC-123"
    dossier = noyau.preparer_dossier(
        question, contexte={"sonde": _sonde_identifiant_non_resolu(question)})
    assert dossier.cadre.source == "contrat"
    assert dossier.contrat["effort"] == "approfondi"
    assert dossier.contrat["artefacts_requis"]
    assert dossier.plan.budget["appels_outils"] == 24
    vue = dossier.as_dict()
    assert vue["cadre"]["source"] == "contrat"
    assert vue["contrat"]["artefacts_requis"]


def test_preparer_dossier_sans_sonde_reste_en_qualifier():
    dossier = noyau.preparer_dossier("Qui es-tu ?", contexte={})
    assert dossier.cadre.source == "qualifier"
    assert dossier.contrat == {}
    assert dossier.as_dict()["cadre"]["source"] == "qualifier"
