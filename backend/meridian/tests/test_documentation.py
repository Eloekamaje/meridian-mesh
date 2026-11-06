"""Recherche documentaire bornée : Confluence/SharePoint deviennent un contexte citable."""
from meridian.application import documentation
from meridian.adapters.outbound.connectors.lecteurs import LecteurMemoire


DOCS = {
    "12": {"titre": "Politique d'abonnement", "versions": {"3": ["Souscription", "Résiliation à J+30"]}},
}


def _lecteur():
    return LecteurMemoire("Wiki Confluence", "TBT", DOCS, systeme="confluence")


def test_la_recherche_documentaire_rend_un_extrait_et_un_locator():
    resultat = documentation.collecter([_lecteur()], "résiliation")
    assert len(resultat) == 1
    assert resultat[0]["systeme"] == "confluence"
    assert resultat[0]["locator"] == "confluence://TBT/12@3#L1-L2"
    assert "Résiliation" in resultat[0]["extrait"]


def test_une_source_en_panne_ne_bloque_pas_les_autres():
    class Panne:
        systeme = "sharepoint"
        nom = "SharePoint"
        def chercher(self, _):
            raise RuntimeError("injoignable")
    resultat = documentation.collecter([Panne(), _lecteur()], "résiliation")
    assert len(resultat) == 1


def test_la_lecture_sharepoint_d_un_texte_est_bornee():
    from meridian.adapters.outbound.connectors import sharepoint
    assert sharepoint._lignes_document(b"# Titre\n\nContenu\n", "note.md") == ["# Titre", "Contenu"]
