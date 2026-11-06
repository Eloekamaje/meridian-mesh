"""Épistémologie : présupposés, faits de recherche et révision de croyance."""
from meridian.application import epistemie
from meridian.domain import epistemie as domaine


def test_une_question_causale_expose_son_presuppose():
    frame = epistemie.analyser_question("Pourquoi paiements est-il déployé au Japon ?")
    assert frame.tache == "diagnostiquer"
    assert frame.presuppositions
    assert frame.presuppositions[0].statut == "INCONNU"
    assert frame.presuppositions[0].bloquant
    assert frame.questions_bloquantes


def test_un_constat_peut_confirmer_un_presuppose():
    constats = [{"texte": "paiements est deploye au japon", "preuves": ["p-1"], "twin_id": "paiements"}]
    frame = epistemie.analyser_question(
        "Pourquoi paiements est-il déployé au Japon ?", constats=constats)
    assert frame.presuppositions[0].statut == "CONNU"
    assert not frame.presuppositions[0].bloquant


def test_la_recherche_devient_des_faits_de_contexte():
    resultat = {
        "claims": [{"id": 1, "jumeau_id": "paiements", "sujet": "paiements",
                    "predicat": "DEPLOYE_A", "objet": "France"}],
        "contradictions": [{"id": 2, "jumeau_id": "paiements",
                            "enonce": "paiements est déployé en France et au Japon"}],
        "contre": [{"preuve_id": 3, "locator": "config:prod", "claim_id": 1}],
    }
    faits = epistemie.faits_depuis_recherche(resultat)
    assert {f["type"] for f in faits} == {"CLAIM", "CONTRADICTION", "PREUVE_CONTRE"}
    assert faits[1]["donnees"]["contradiction"] is True


def test_une_revision_conserve_l_ancien_statut():
    belief = domaine.Belief(sujet="paiements", predicat="DEPLOYE_A", objet="Japon",
                            statut="SUPPOSE")
    revision = epistemie.reviser(
        belief, nouveau_statut="CONTREDIT", motif="source contraire", acteur="demo",
        preuves_ajoutees=["p-2"])
    assert revision.ancien_statut == "SUPPOSE"
    assert revision.nouveau_statut == "CONTREDIT"
    assert revision.preuves_ajoutees == ("p-2",)


def test_un_diagramme_d_architecture_est_une_conception_et_garde_son_objet():
    frame = epistemie.analyser_question(
        "je veux un diagrame d'architecture deu processus de gestion des abonnées",
        {"objet": "gestion des abonnées"})
    assert frame.tache == "concevoir"
    assert frame.objet == "gestion des abonnées"
