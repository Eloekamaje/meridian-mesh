"""B8 — la sonde pré-raisonnement : trivial | clair | incertain, sur recherches injectées."""
from meridian.application import sonde_evidence as sonde


def test_lookup_identifiant_confirme_est_trivial():
    resultat = sonde.sonder(
        "montre-moi le ticket ABC-123",
        recherche_lexicale=lambda q: [{"id": "c1", "objet": "ticket ABC-123 résolu", "score": 0.9}])
    assert resultat["verdict"] == "trivial"
    assert resultat["preuves"]


def test_citation_code_confirmee_est_trivial():
    resultat = sonde.sonder(
        "montre src/app.py#L10-L12",
        recherche_lexicale=lambda q: [
            {"id": "p1", "locator": "git://repo@ab12:src/app.py#L10-L12", "score": 1.0}])
    assert resultat["verdict"] == "trivial"


def test_identifiant_non_resolu_est_incertain():
    resultat = sonde.sonder(
        "montre-moi le ticket ABC-123",
        recherche_lexicale=lambda q: [])
    assert resultat["verdict"] == "incertain"
    assert any("non résolu" in manque for manque in resultat["manque"])


def test_identifiant_sans_indice_confirmant_est_incertain():
    """Des indices qui ne confirment pas l'identifiant cité ne rendent pas la question triviale."""
    resultat = sonde.sonder(
        "montre-moi le ticket ABC-123",
        recherche_lexicale=lambda q: [{"id": "c1", "objet": "dépendance orders → clients", "score": 0.9}])
    assert resultat["verdict"] == "incertain"
    assert any("non résolu" in manque for manque in resultat["manque"])


def test_preuves_presentes_couvrant_le_sujet_est_clair():
    resultat = sonde.sonder(
        "quelles dépendances a l'application ?",
        recherche_lexicale=lambda q: [{"id": "c1", "objet": "DEPEND_DE orders → clients", "score": 0.9}])
    assert resultat["verdict"] == "clair"
    assert resultat["indices"][0]["trouves"] == 1


def test_aucune_preuve_est_incertain():
    resultat = sonde.sonder(
        "question jamais vue",
        recherche_lexicale=lambda q: [], memoire=lambda q: [])
    assert resultat["verdict"] == "incertain"
    assert any("aucune preuve" in manque for manque in resultat["manque"])


def test_sans_aucune_sonde_est_incertain():
    resultat = sonde.sonder("question")
    assert resultat["verdict"] == "incertain"


def test_interpretations_rivales_est_incertain():
    """Deux sujets à scores proches : la sonde refuse de trancher."""
    resultat = sonde.sonder(
        "conduite ?",
        recherche_lexicale=lambda q: [
            {"id": "c1", "jumeau_id": "conduite", "objet": "x", "score": 1.0},
            {"id": "c2", "jumeau_id": "conduit", "objet": "y", "score": 0.9}])
    assert resultat["verdict"] == "incertain"
    assert any("rivales" in manque for manque in resultat["manque"])


def test_scores_tranches_ne_sont_pas_rivales():
    resultat = sonde.sonder(
        "conduite ?",
        recherche_lexicale=lambda q: [
            {"id": "c1", "jumeau_id": "conduite", "objet": "x", "score": 1.0},
            {"id": "c2", "jumeau_id": "conduit", "objet": "y", "score": 0.5}])
    assert resultat["verdict"] == "clair"


def test_sonde_en_panne_est_un_manque_pas_une_erreur():
    def panne(question):
        raise RuntimeError("postgres down")
    resultat = sonde.sonder("question", recherche_lexicale=panne)
    assert resultat["verdict"] == "incertain"
    assert any("lexicale indisponible" in manque for manque in resultat["manque"])


def test_les_trois_sources_sont_consultees():
    resultat = sonde.sonder(
        "question couverte",
        recherche_lexicale=lambda q: [{"id": "c1", "objet": "claim", "score": 0.9}],
        graphe=lambda q: [{"id": "g1", "titre": "voisin", "score": 0.5}],
        memoire=lambda q: [{"id": "m1", "contenu": "souvenir"}])
    assert resultat["verdict"] == "clair"
    sources = {indice["source"] for indice in resultat["indices"]}
    assert sources == {"lexicale", "graphe", "memoire"}


def test_reponse_triviale_restitue_les_indices_sans_modele():
    resultat = sonde.sonder(
        "montre ABC-123",
        recherche_lexicale=lambda q: [{"id": "c1", "objet": "ABC-123 livré", "score": 1.0}])
    reponse = sonde.reponse_triviale(resultat)
    assert "ABC-123" in reponse["reponse"]
    assert reponse["comportement"] == "repondre"
    assert reponse["sonde"]["verdict"] == "trivial"
    assert reponse["preuves"]
