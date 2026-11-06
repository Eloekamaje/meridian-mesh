"""Le contrat d'action empêche une exécution non confirmée d'être présentée comme faite."""
from meridian.application import contrat_action


def test_une_action_demandee_sans_confirmation_est_transformee_en_proposition():
    reponse = contrat_action.appliquer(
        "Lance une investigation sur les dépendances de Conduit.",
        {"reponse": "J'ai lancé l'investigation : voici la cartographie."},
    )
    assert reponse["comportement"] == "proposer"
    assert reponse["action_en_attente"] == "investigation"
    assert "n'ai pas exécuté" in reponse["reponse"]
    assert "Confirmation requise" in reponse["reponse"]
    assert reponse[contrat_action.APPLIQUER] == "corrige"


def test_une_action_deja_confirmee_est_conservee():
    texte = "Je peux préparer l'investigation. Voulez-vous que je la lance ?"
    reponse = contrat_action.appliquer(
        "Lance une investigation sur Conduit.",
        {"reponse": texte},
    )
    assert reponse["reponse"] == texte
    assert reponse[contrat_action.APPLIQUER] == "conforme"


def test_une_question_ordinaire_n_est_pas_modifiee():
    texte = "Conduit publie des articles."
    reponse = contrat_action.appliquer("Que fait Conduit ?", {"reponse": texte})
    assert reponse == {"reponse": texte}


def test_un_rapport_annonce_sans_artefact_est_corrige():
    reponse = contrat_action.appliquer(
        "Fais-moi un rapport détaillé sur Conduit.",
        {"reponse": "Voici le rapport. J'ai ajouté le rapport au Travail."},
    )
    assert reponse["action_en_attente"] == "rapport"
    assert "aucun rapport n'a été déposé" in reponse["reponse"]
    assert reponse["comportement"] == "proposer"
    assert reponse[contrat_action.APPLIQUER] == "artefact_corrige"


def test_un_rapport_avec_artefact_n_est_pas_corrige():
    texte = "Voici le rapport. J'ai ajouté le rapport au Travail."
    reponse = contrat_action.appliquer(
        "Fais-moi un rapport détaillé sur Conduit.",
        {"reponse": texte, "documentCanvas": "Rapport Conduit"},
    )
    assert reponse["reponse"] == texte
    assert contrat_action.APPLIQUER not in reponse


def test_une_negation_d_execution_ne_declenche_pas_la_correction():
    reponse = contrat_action.appliquer(
        "Lance une investigation sur Conduit.",
        {"reponse": "Je n'ai pas lancé l'investigation. Voulez-vous que je la prépare ?"},
    )
    assert "Correction" not in reponse["reponse"]
    assert reponse[contrat_action.APPLIQUER] == "conforme"
