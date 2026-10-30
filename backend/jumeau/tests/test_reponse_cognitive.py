"""AnswerComposer : même socle de faits, lectures et actions adaptées au profil."""
import pytest

from jumeau import composition, profils, reponse_cognitive

DOSSIER = {
    "tenant": "demo",
    "statut": "ok",
    "propositions": [
        {"specialiste": "impact", "type": "IMPACT", "titre": "Impact de paiements",
         "resume": "3 aval, 4 amont", "preuves": ["paiements", "r1"], "confiance": 0.7,
         "actions": ("ouvrir_impact",), "donnees": {"aval": 3}},
        {"specialiste": "preuve", "type": "RISQUE", "titre": "Preuve périmée",
         "resume": "preuve ancienne", "preuves": ["p1"], "confiance": 0.85,
         "actions": ("demander_preuve",), "donnees": {}},
        {"specialiste": "outcome", "type": "QUESTION", "titre": "Aucun learning réutilisable",
         "resume": "mesurer", "preuves": [], "confiance": 0.6,
         "actions": ("mesurer_outcome",), "donnees": {}},
    ],
    "specialistes": [
        {"specialiste": "impact", "statut": "ok", "propositions": [], "limites": []},
        {"specialiste": "preuve", "statut": "partiel", "propositions": [], "limites": ["preuve incomplète"]},
    ],
    "limites": ["propositions non canoniques"],
}

DOSSIER_DECISION = {
    "tenant": "demo",
    "statut": "ok",
    "baseline": {"periode": "30j", "valeur": 3.5},
    "propositions": [
        {"specialiste": "outcome", "type": "OUTCOME",
         "titre": "Temps de parcours ramené à 2 j",
         "resume": "outcome observé",
         "preuves": ["o1"], "confiance": 0.8, "actions": (),
         "donnees": {"valeur_observee": 2.0, "baseline": 3.5}},
        {"specialiste": "impact", "type": "OPTION", "titre": "Option A",
         "resume": "livrer d'abord les cartes", "preuves": ["p-a"],
         "confiance": 0.6, "actions": (), "donnees": {}},
        {"specialiste": "impact", "type": "PROPOSITION", "titre": "Option B",
         "resume": "stabiliser d'abord", "preuves": ["p-b"],
         "confiance": 0.4, "actions": (),
         "donnees": {"recommandation": "Option B"}},
        {"specialiste": "outcome", "type": "QUESTION",
         "titre": "Quelle condition inverse ?",
         "resume": "condition de retournement", "preuves": [],
         "confiance": 0.5, "actions": (), "donnees": {}},
    ],
    "specialistes": [],
    "limites": [],
}


def _reponse(profil_id, question="Pourquoi les paiements ralentissent ?",
             dossier=DOSSIER):
    profil = profils.resoudre_profil(profil=profil_id)
    plan = composition.planifier(profil, question)
    return reponse_cognitive.composer(question, profil, plan, dossier)


def test_meme_socle_de_faits_pour_deux_profils():
    dev = _reponse("developpeur")
    po = _reponse("product_owner")
    assert dev.socle.as_dict() == po.socle.as_dict()
    assert {f["titre"] for f in dev.socle.faits} == {f["titre"] for f in po.socle.faits}


def test_les_lectures_et_actions_different_selon_le_profil():
    dev = _reponse("developpeur")
    po = _reponse("product_owner")
    support = _reponse("support")

    assert set(dev.lecture) & {"impact_technique", "interfaces", "risques"}
    assert "benefice" not in dev.lecture
    assert "impact_client" in po.lecture
    assert set(po.lecture) != set(dev.lecture)
    assert "incident" in support.lecture or "sla" in support.lecture
    assert dev.actions != po.actions


def test_un_profil_inconnu_reste_en_lecture_et_n_a_pas_d_action():
    reponse = _reponse("inconnu", "question vague")
    assert reponse.profil.inconnu is True
    assert reponse.autorite == "lecture"
    assert reponse.actions == ()
    assert any("lecture" in avertissement or "inconnu" in avertissement
               for avertissement in reponse.avertissements)


def test_un_dossier_vide_ne_produit_aucune_invention():
    profil = profils.resoudre_profil(profil="developpeur")
    plan = composition.planifier(profil, "question")
    reponse = reponse_cognitive.composer("question", profil, plan, {"propositions": []})
    assert reponse.socle.faits == ()
    assert any("aucun fait" in avertissement for avertissement in reponse.avertissements)


def test_un_plan_d_un_autre_profil_est_refuse():
    dev = profils.resoudre_profil(profil="developpeur")
    po = profils.resoudre_profil(profil="product_owner")
    plan = composition.planifier(dev, "question")
    with pytest.raises(ValueError, match="profil"):
        reponse_cognitive.composer("question", po, plan, DOSSIER)


def test_decision_support_s_abstient_sans_fait():
    profil = profils.resoudre_profil(profil="developpeur")
    plan = composition.planifier(profil, "question")
    reponse = reponse_cognitive.composer(
        "question", profil, plan, {"propositions": []})
    support = reponse.decision_support

    assert support["options"] == []
    assert support["recommandation"] is None
    assert support["confiance"] is None
    assert support["conditions_de_retournement"] == []
    assert "aucun fait" in support["abstention"]
    assert support["autorite"] == reponse.autorite
    assert support["prochaines_etapes"] == list(reponse.prochaines_etapes)


def test_decision_support_partage_les_faits_entre_dev_et_po():
    dev = _reponse("developpeur")
    po = _reponse("product_owner")

    assert dev.socle.faits == po.socle.faits
    for cle in ("options", "recommandation", "confiance",
                "conditions_de_retournement", "abstention"):
        assert dev.decision_support[cle] == po.decision_support[cle]
    assert dev.decision_support["prochaines_etapes"] == list(
        dev.prochaines_etapes)
    assert po.decision_support["prochaines_etapes"] == list(
        po.prochaines_etapes)


def test_decision_support_ne_cree_pas_de_recommandation():
    reponse = _reponse("developpeur")

    assert reponse.decision_support["options"]
    assert reponse.decision_support["recommandation"] is None


def test_decision_support_derive_les_options_des_faits():
    reponse = _reponse("developpeur", dossier=DOSSIER_DECISION)
    support = reponse.decision_support

    assert [option["label"] for option in support["options"]] == [
        "Option A", "Option B", "Quelle condition inverse ?"]
    assert [option["id"] for option in support["options"]] == [
        "option-a", "option-b", "quelle-condition-inverse"]
    assert {option["type"] for option in support["options"]} == {
        "OPTION", "PROPOSITION", "QUESTION"}
    assert support["options"][0]["preuves"] == ["p-a"]
    assert support["confiance"] == {"min": 0.4, "moyenne": 0.5}
    assert support["recommandation"] == "Option B"


def test_decision_support_limite_les_options_a_quatre():
    dossier = {"propositions": [
        {"type": "ACTION", "titre": f"Action {rang}", "confiance": 0.5,
         "preuves": [], "donnees": {}}
        for rang in range(1, 7)
    ]}
    reponse = _reponse("developpeur", dossier=dossier)

    assert len(reponse.decision_support["options"]) == 4


def test_decision_support_s_abstient_en_autorite_lecture():
    reponse = _reponse("inconnu", dossier=DOSSIER_DECISION)
    support = reponse.decision_support

    assert reponse.autorite == "lecture"
    assert support["autorite"] == "lecture"
    assert support["options"]
    assert "lecture" in support["abstention"]


def test_decision_support_ne_s_abstient_pas_avec_baseline_et_outcome():
    reponse = _reponse("developpeur", dossier=DOSSIER_DECISION)

    assert reponse.decision_support["abstention"] is None


def test_decision_support_conditions_de_retournement():
    dossier = {"propositions": [
        {"type": "CONSTAT", "titre": "Retournement si le volume double",
         "resume": "", "confiance": 0.5, "preuves": [], "donnees": {}},
        {"type": "HYPOTHESE", "titre": "Hypothèse de charge",
         "resume": "", "confiance": 0.5, "preuves": [], "donnees": {}},
        {"type": "ACTION", "titre": "Action conditionnelle",
         "resume": "", "confiance": 0.5, "preuves": [],
         "donnees": {"conditions_de_retournement": ["si volume baisse"]}},
    ]}
    conditions = _reponse(
        "developpeur", dossier=dossier
    ).decision_support["conditions_de_retournement"]

    assert "Retournement si le volume double" in conditions
    assert "Hypothèse de charge" in conditions
    assert "si volume baisse" in conditions


def test_decision_support_est_dans_as_dict():
    reponse = _reponse("developpeur")

    assert reponse.as_dict()["decision_support"] == reponse.decision_support
