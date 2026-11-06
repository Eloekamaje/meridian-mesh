"""Scénarios de rejeu multi-tours : la conversation ne doit pas perdre le fil."""
from meridian.application import dialogue
from meridian.domain.dialogue import EtatDialogue


def _jouer(questions, reponses):
    etat = EtatDialogue(travail="scenario", acteur="usr-1")
    actes = []
    for question, reponse in zip(questions, reponses):
        tour = dialogue.preparer_tour(question, etat=etat)
        actes.append(tour["acte"])
        etat = dialogue.mettre_a_jour(etat, question, reponse)
    return etat, actes


def test_scenario_suivi_et_reference():
    etat, actes = _jouer(
        ["Quels processus expose Conduit ?", "Et lesquels concernent les abonnements ?"],
        [{"reponse": "Six processus.", "jumeaux_participants": [{"id": "conduit"}]},
         {"reponse": "Quatre opérations d'abonnement."}],
    )
    assert actes == ["question", "suivi"]
    assert "conduit" in etat.entites
    assert "abonnements" in etat.derniere_question


def test_scenario_correction_puis_retour_au_sujet():
    etat, actes = _jouer(
        ["Quels processus expose Conduit ?", "Non, je parlais des paiements"],
        [{"reponse": "Six processus.", "jumeaux_participants": [{"id": "conduit"}]},
         {"reponse": "Je corrige sur paiements."}],
    )
    assert actes == ["question", "correction"]
    assert etat.corrections
    assert etat.derniere_reponse == "Je corrige sur paiements."


def test_scenario_nouveau_sujet():
    etat, actes = _jouer(
        ["Quels processus expose Conduit ?", "Parle-moi des paiements"],
        [{"reponse": "Six processus.", "jumeaux_participants": [{"id": "conduit"}]},
         {"reponse": "Paiements."}],
    )
    assert actes[-1] == "nouveau_sujet"
    assert etat.sujet == "Parle-moi des paiements"
