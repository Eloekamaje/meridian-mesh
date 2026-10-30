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


def _reponse(profil_id, question="Pourquoi les paiements ralentissent ?"):
    profil = profils.resoudre_profil(profil=profil_id)
    plan = composition.planifier(profil, question)
    return reponse_cognitive.composer(question, profil, plan, DOSSIER)


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
