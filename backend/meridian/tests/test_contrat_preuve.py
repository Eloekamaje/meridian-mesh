"""Le contrat de preuve signale une liste factuelle non sourcée."""
from meridian.application import contrat_preuve


def test_liste_non_sourcee_recoit_une_limite():
    texte = ("Dépendances :\n"
             "- FastAPI\n- Uvicorn\n- Pydantic\n")
    reponse = contrat_preuve.appliquer({"reponse": texte})
    assert reponse[contrat_preuve.LIMITE] is True
    assert "Limite de preuve" in reponse["reponse"]
    assert reponse[contrat_preuve.APPLIQUER] == "limite_ajoutee"


def test_liste_sourcee_est_conservee():
    texte = ("Dépendances :\n"
             "- FastAPI [1](#preuve-1)\n- Uvicorn [2](#preuve-2)\n- Pydantic [3](#preuve-3)\n")
    reponse = contrat_preuve.appliquer({"reponse": texte})
    assert reponse["reponse"] == texte
    assert reponse[contrat_preuve.APPLIQUER] == "conforme"


def test_deux_elements_ne_declenchent_pas_la_limite():
    texte = "Dépendances :\n- FastAPI\n- Uvicorn\n"
    reponse = contrat_preuve.appliquer({"reponse": texte})
    assert reponse[contrat_preuve.APPLIQUER] == "non_applicable"


def test_un_refus_n_est_pas_modifie():
    texte = "Je ne peux pas répondre.\n- a\n- b\n- c\n"
    reponse = contrat_preuve.appliquer({"reponse": texte, "comportement": "refuser"})
    assert reponse["reponse"] == texte
    assert reponse[contrat_preuve.APPLIQUER] == "non_applicable"
