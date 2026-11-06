"""Cadrage conversationnel : un slot, une question, une réponse routée."""
from meridian.application import cadrage_conversationnel as cadrage
from meridian.application import noyau_raisonnement as noyau


QUESTION = "je veux un diagrame d'architecture du processus de gestion des abonnés"


def _initial():
    demande = noyau.qualifier(QUESTION)
    return cadrage.initialiser(QUESTION, demande)


def test_le_diagramme_pose_d_abord_la_question_existant_ou_cible():
    etat = _initial()
    assert etat.statut == "en_attente"
    assert etat.question_en_attente.slot == "existant_ou_cible"
    assert "existant" in etat.question_en_attente.texte
    assert etat.posees == 1


def test_une_reponse_de_perimetre_ne_repond_pas_a_la_question_existant_ou_cible():
    etat = cadrage.recevoir_reponse(_initial(), "juste les abonnements")
    assert etat.slot("perimetre").valeur == "juste les abonnements"
    assert etat.slot("existant_ou_cible").valeur == ""
    assert etat.question_en_attente.slot == "existant_ou_cible"
    assert "juste les abonnements" in etat.question_en_attente.texte
    assert etat.posees == 2


def test_une_reponse_existante_ou_cible_est_routée_au_bon_slot():
    etat = cadrage.recevoir_reponse(_initial(), "cible")
    assert etat.slot("existant_ou_cible").valeur == "cible"
    assert etat.question_en_attente.slot == "perimetre"


def test_apres_le_budget_on_infere_au_lieu_de_boucler():
    etat = cadrage.recevoir_reponse(_initial(), "juste les abonnements")
    etat = cadrage.recevoir_reponse(etat, "juste les abonnements")
    assert etat.statut == "pret"
    assert etat.question_en_attente is None
    assert etat.slot("existant_ou_cible").valeur == "cible"
    assert etat.slot("existant_ou_cible").statut == "infere"


def test_le_contexte_ne_duplique_pas_la_reponse_dans_tous_les_champs():
    etat = cadrage.recevoir_reponse(_initial(), "juste les abonnements")
    etat = cadrage.recevoir_reponse(etat, "cible")
    contexte = cadrage.contexte_pour_noyau(etat)
    assert contexte["objectif"] == QUESTION
    assert contexte["perimetre"] == "juste les abonnements"
    assert contexte["existant_ou_cible"] == "cible"
    assert contexte["contraintes"] == []
    assert contexte["criteres_succes"] == []
    assert contexte["utilisateurs"] == []
    assert contexte["sans_questions"] is True


def test_une_question_simple_n_ouvre_pas_de_cadrage():
    question = "Qui es-tu ?"
    etat = cadrage.initialiser(question, noyau.qualifier(question))
    assert etat.statut == "pret"
    assert etat.question_en_attente is None


def test_une_demande_deja_ciblee_ne_repose_pas_la_question_existant_ou_cible():
    question = "je veux une architecture cible du processus de gestion des abonnés"
    etat = cadrage.initialiser(question, noyau.qualifier(question))
    assert etat.slot("existant_ou_cible").valeur == "cible"
    assert etat.question_en_attente is None or etat.question_en_attente.slot != "existant_ou_cible"


def test_fais_en_un_diagramme_reprend_le_sujet_et_l_existant_du_fil():
    from meridian.domain.dialogue import EtatDialogue
    question = "Fais-en un diagramme."
    etat_dialogue = EtatDialogue(
        sujet="Quels processus expose Conduit ?", entites=("conduit",),
        derniere_reponse="Conduit expose quatre opérations d'abonnement.")
    tour = {"acte": "suivi", "entites": ["conduit"],
            "derniere_reponse": etat_dialogue.derniere_reponse}
    etat = cadrage.initialiser(question, noyau.qualifier(question), {
        "dialogue": tour,
    })
    assert etat.statut == "pret"
    assert etat.slot("existant_ou_cible").valeur == "existant"
    assert etat.slot("existant_ou_cible").statut == "infere"
    assert etat.slot("perimetre").valeur == "conduit"


def test_une_question_meta_ne_rouvre_pas_un_cadrage():
    question = "pourquoi tu ne l'as pas dessiné ?"
    contexte = {
        "dialogue": {
            "acte": "meta",
            "entites": ["conduit"],
            "derniere_reponse": "Le registre des abonnements tient en une table.",
        },
        "objet": "conduit",
    }
    etat = cadrage.initialiser(question, noyau.qualifier(question, {**contexte, "sans_questions": True}), contexte)

    assert etat.question_en_attente is None
    assert etat.statut == "pret"
    demande = noyau.qualifier(question, {"acte": "meta"})
    assert (demande.but, demande.niveau) == ("expliquer", "N1")
