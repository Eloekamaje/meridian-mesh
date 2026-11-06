"""Chunking et scoring hybride : le retrieval reste borné et explicable."""
from meridian.application import chunking, retrieval_hybride


def test_le_chunking_conserve_les_lignes_et_les_sections():
    lignes = ["# Politique", "Souscription immédiate.", "Résiliation à J+30.", "# Facturation", "Mensuelle."]
    chunks = chunking.decouper(lignes)
    assert chunks
    assert chunks[0]["section"] == "Politique"
    assert chunks[0]["debut"] == 1
    assert chunks[-1]["section"] == "Facturation"
    assert all(chunk["debut"] <= chunk["fin"] for chunk in chunks)


def test_le_score_combine_lexical_semantique_et_graphe():
    chunk = {"texte": "abonnement résiliation préavis", "embedding": [1.0, 0.0],
             "twin_id": "conduit", "twin_ids_actifs": ["conduit"], "updated_at": "2026-01-01T00:00:00+00:00"}
    score = retrieval_hybride.score("résiliation abonnement", chunk, vecteur_question=[1.0, 0.0])
    assert score > 0.5


def test_un_chunk_sans_rapport_ne_gagne_pas_par_la_seule_recence():
    chunk = {"texte": "météo et jardinage", "embedding": [0.0, 1.0], "updated_at": "2026-11-01T00:00:00+00:00"}
    score = retrieval_hybride.score("résiliation abonnement", chunk, vecteur_question=[1.0, 0.0])
    assert score < 0.2


def test_acl_documentaire_filtre_avant_le_prompt():
    from meridian.adapters.outbound.postgres import chunk_store
    assert chunk_store._acl_autorise({}) is True
    assert chunk_store._acl_autorise({"public": True}) is True
    assert chunk_store._acl_autorise({"roles": ["Architecte"]}, role="Architecte") is True
    assert chunk_store._acl_autorise({"users": ["usr-1"]}, acteur="usr-2") is False
    assert chunk_store._acl_autorise({"espaces": ["finance"]}, espace="rh") is False


def test_un_lecteur_memoire_peut_etre_parcouru_pour_le_backfill():
    from meridian.adapters.outbound.connectors.lecteurs import LecteurMemoire
    lecteur = LecteurMemoire("docs", "TBT", {"1": {"titre": "A", "versions": {"1": ["x"]}}}, systeme="confluence")
    assert list(lecteur.parcourir()) == ["1"]


def test_acl_strict_refuse_une_acl_absente(monkeypatch):
    from meridian.adapters.outbound.postgres import chunk_store
    monkeypatch.setenv("ACL_STRICT", "1")
    assert chunk_store._acl_autorise({}) is False
    assert chunk_store._acl_autorise({"public": True}) is True
