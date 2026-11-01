"""La couverture d'un jumeau est calculée, pas forfaitaire (plan de remédiation L2.7).

Avant : `min(20 + 12 * nb_sources, 88)` appliqué avec un `1` en dur — **tout jumeau réel affichait 32 %**, qu'il
porte 26 faits établis ou 725 connaissances. Un chiffre qui ne mesurait rien.
"""
from meridian.adapters.outbound.mongo import registre


def test_la_couverture_est_la_part_de_ce_qui_est_etabli():
    assert registre.couverture(26, 27) == 49      # Conduit
    assert registre.couverture(184, 58) == 76     # Méridian Mesh
    assert registre.couverture(94, 44) == 68      # Nouveau jumeau


def test_ecrire_sans_prouver_fait_baisser_la_couverture():
    assert registre.couverture(10, 0) == 100
    assert registre.couverture(10, 10) == 50
    assert registre.couverture(10, 90) == 10


def test_un_jumeau_sans_connaissance_n_affiche_pas_un_pourcentage_invente():
    assert registre.couverture(0, 0) == 0
    assert registre.couverture(None, None) == 0


def test_le_document_du_registre_utilise_les_comptes_du_jumeau():
    doc = registre.document({"id": "tbt", "nom": "TBT", "domaine": "Paiement", "mission": None, "equipe": "eq",
                             "curseur": "a" * 12, "claims": 53, "depots": 1, "etablis": 26, "hypotheses": 27,
                             "types": ["GIT"], "liste_depots": []})
    assert doc["couverture"] == 49 and doc["reel"] is True
