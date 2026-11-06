"""Dialogue : actes, références, dernière réponse et corrections."""
from meridian.application import dialogue
from meridian.domain.dialogue import EtatDialogue


def _etat():
    return EtatDialogue(
        travail="t1", acteur="usr-1", sujet="processus de Conduit",
        entites=("conduit",), derniere_question="Quels processus expose Conduit ?",
        derniere_reponse="Conduit expose six processus.",
    )


def test_un_suivi_reprend_les_entites_actives():
    tour = dialogue.preparer_tour("et lesquels concernent les abonnements ?", etat=_etat())
    assert tour["acte"] == "suivi"
    assert "conduit" in tour["entites"]
    assert "Références possibles" in tour.get("references", "")


def test_une_correction_est_explicite_et_transmise():
    tour = dialogue.preparer_tour("non, je parlais des paiements", etat=_etat())
    assert tour["acte"] == "correction"
    assert tour["correction"] == "non, je parlais des paiements"


def test_une_question_meta_est_reconnue():
    tour = dialogue.preparer_tour("pourquoi tu me demandes ça ?", etat=_etat())
    assert tour["acte"] == "meta"


def test_un_nouveau_sujet_est_detecte():
    tour = dialogue.preparer_tour("parle-moi des paiements", etat=_etat())
    assert tour["acte"] == "nouveau_sujet"


def test_mettre_a_jour_conserve_reponse_livrable_et_correction():
    etat = dialogue.mettre_a_jour(
        _etat(), "corrige : je voulais le diagramme des paiements",
        {"reponse": "Voici le diagramme.", "diagrammes": [{"titre": "Paiements"}]})
    assert etat.derniere_reponse == "Voici le diagramme."
    assert etat.dernier_livrable == "Paiements"
    assert etat.corrections
    assert etat.version == 1


def test_le_serpent_ne_prend_pas_une_negation_pour_une_correction():
    tour = dialogue.preparer_tour("je ne comprends pas la question", etat=_etat())
    assert tour["acte"] != "correction"


def test_une_ancienne_conversation_est_reprise_sans_champ_dialogue():
    etat = dialogue.depuis_case({
        "conversation": [
            {"role": "utilisateur", "texte": "Quels processus expose Conduit ?"},
            {"role": "flore", "texte": "Conduit expose six processus."},
        ],
    }, travail="t1", acteur="usr-1")
    assert etat.derniere_question == "Quels processus expose Conduit ?"
    assert etat.derniere_reponse == "Conduit expose six processus."
    assert etat.travail == "t1"


def test_les_jumeaux_mobilises_deviennent_des_entites_actives():
    etat = dialogue.mettre_a_jour(
        EtatDialogue(travail="t1"), "Quels processus expose Conduit ?",
        {"reponse": "Six processus.", "jumeaux_participants": [{"id": "conduit", "nom": "Conduit"}]})
    assert "conduit" in etat.entites
    tour = dialogue.preparer_tour("et lesquels concernent les abonnements ?", etat=etat)
    assert tour["acte"] == "suivi"
    assert "conduit" in tour["entites"]


def test_les_suggestions_proposent_une_suite_sans_executer_d_action():
    etat = EtatDialogue(entites=("conduit",), dernier_livrable="Conduit")
    propositions = dialogue.suggestions(etat, {"diagrammes": [{"titre": "Conduit"}]})
    assert propositions
    assert all(isinstance(valeur, dict) and valeur.get("label") and valeur.get("question")
               for valeur in propositions)
    assert len(propositions) <= 3


def test_un_message_social_reste_un_message_social():
    assert dialogue.preparer_tour("Bonjour Flore !", etat=EtatDialogue())["acte"] == "social"
    assert dialogue.preparer_tour("Bonjour, quels processus expose Conduit ?",
                                  etat=EtatDialogue())["acte"] != "social"
