"""Critique et risque : des propositions typées, sans écriture ni décision."""
from meridian.application.specialiste_critique import SpecialisteCritique
from meridian.application.specialiste_risque import SpecialisteRisque
from meridian.domain.specialistes import ContexteSpecialiste


DOSSIER = {
    "niveau": "N3",
    "demande": {"but": "concevoir", "niveau": "N3", "sensibilite": []},
    "reponse": {"reponse": "Une seule option.", "hypotheses": [], "options": []},
}


def test_le_critique_produit_des_findings_sans_reecrire():
    resultat = SpecialisteCritique().analyser(
        ContexteSpecialiste(tenant="demo", question="Conçois", dossier=DOSSIER))
    assert resultat.statut == "ok"
    assert resultat.propositions
    assert all(p.specialiste == "critique" for p in resultat.propositions)
    assert any(p.type == "RISQUE" for p in resultat.propositions)
    assert all("reponse" not in p.donnees for p in resultat.propositions)


def test_le_critique_signale_un_livrable_absent():
    resultat = SpecialisteCritique().analyser(
        ContexteSpecialiste(tenant="demo", question="Conçois"))
    assert resultat.statut == "partiel"
    assert resultat.propositions[0].type == "QUESTION"


def test_le_risque_detecte_une_action_irreversible():
    resultat = SpecialisteRisque().analyser(
        ContexteSpecialiste(tenant="demo", question="Supprime la table de production"))
    assert resultat.propositions
    assert any(p.type == "RISQUE" for p in resultat.propositions)
