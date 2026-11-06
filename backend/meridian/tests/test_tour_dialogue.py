"""ÉtatTour : version, fallback historique et invariants de la question ouverte."""
from meridian.application import tour_dialogue
from meridian.domain.cadrage import CadrageConversationnel, QuestionCadrage, SlotCadrage
from meridian.domain.dialogue import EtatDialogue


def test_depuis_case_ancien_reconstruit_dialogue_et_cadrage():
    case = {
        "id": "t1",
        "conversation": [
            {"role": "utilisateur", "texte": "Parle-moi de Conduit"},
            {"role": "flore", "texte": "Conduit publie des articles."},
        ],
        "dialogue": {"sujet": "Conduit", "entites": ["conduit"]},
        "cadrage_conversationnel": {
            "question": "un diagramme ?", "type_livrable": "diagramme",
            "slots": [], "question_en_attente": None, "posees": 0, "statut": "pret",
        },
    }

    etat = tour_dialogue.EtatTour.depuis_case(case)

    assert etat.version == 0
    assert etat.dialogue.sujet == "Conduit"
    assert etat.dialogue.entites == ("conduit",)
    assert etat.cadrage is not None and etat.cadrage.statut == "pret"


def test_version_et_aller_retour_etat_tour():
    etat = tour_dialogue.EtatTour(
        version=3,
        dialogue=EtatDialogue(sujet="Conduit", entites=("conduit",)),
        cadrage=CadrageConversationnel(
            question="q", type_livrable="reponse",
            slots=(SlotCadrage(id="perimetre"),),
            question_en_attente=QuestionCadrage(id="q1", slot="perimetre", texte="Quel périmètre ?"),
            posees=1, statut="en_attente"),
    )

    relu = tour_dialogue.EtatTour.depuis_case({"id": "t1", "etat_tour": etat.as_dict()})

    assert relu.version == 3
    assert relu.a_poser_question()
    assert relu.question_en_attente().slot == "perimetre"
    assert relu.avec(dialogue=EtatDialogue(sujet="Autre")).version == 4


def test_etat_tour_malforme_ne_leve_pas():
    etat = tour_dialogue.EtatTour.depuis_case({"id": "t1", "etat_tour": {"version": "x", "dialogue": None}})
    assert etat.version == 0
    assert etat.cadrage is None
