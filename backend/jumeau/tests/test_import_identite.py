import pytest

from jumeau import import_identite


def test_manifeste_identite_et_sources():
    entrees = import_identite.analyser({
        "jumeau": {"application_id": "remboursements", "nom": "Remboursements", "proprietaire": "Équipe Paiements"},
        "sources": [{"connecteur": "github", "nom": "remboursements", "config": {"connexion": "gh-acme"}}],
    }, "manifeste")
    assert entrees[0]["application_id"] == "remboursements"
    assert entrees[0]["proprietaire"] == "Équipe Paiements"
    assert entrees[0]["sources"][0]["connecteur"] == "github"


def test_cmdb_csv():
    entrees = import_identite.analyser("application_id,nom,proprietaire\nfacturation,Facturation,Finance\n", "cmdb")
    assert [e["application_id"] for e in entrees] == ["facturation"]
    assert entrees[0]["sources"] == []


def test_application_id_et_proprietaire_obligatoires():
    with pytest.raises(import_identite.ImportInvalide):
        import_identite.analyser([{"nom": "Sans id", "proprietaire": "X"}])
    with pytest.raises(import_identite.ImportInvalide):
        import_identite.analyser([{"application_id": "x"}])


def test_application_id_invalide():
    with pytest.raises(import_identite.ImportInvalide):
        import_identite.analyser([{"application_id": "ID MAJUSCULE", "proprietaire": "X"}])


def test_un_secret_dans_le_manifeste_n_est_pas_repris():
    entrees = import_identite.analyser({
        "jumeau": {"application_id": "remboursements", "nom": "Remboursements", "proprietaire": "Paiements"},
        "sources": [{"connecteur": "github", "nom": "code", "config": {"connexion": "gh-acme", "secret": "s3cr3t"}}],
    }, "manifeste")
    assert entrees[0]["sources"][0]["config"] == {"connexion": "gh-acme"}


def test_preparer_separe_les_sources_deja_presentes():
    contenu = {
        "jumeau": {"application_id": "remboursements", "nom": "Remboursements", "proprietaire": "Paiements"},
        "sources": [
            {"connecteur": "github", "nom": "remboursements"},
            {"connecteur": "jira", "nom": "PAY"},
        ],
    }
    prepare = import_identite.preparer(contenu, "manifeste", [("github", "Remboursements")])
    assert [s["nom"] for s in prepare["nouvelles"]] == ["PAY"]
    assert [s["nom"] for s in prepare["ignorees"]] == ["remboursements"]
    assert prepare["identite"]["application_id"] == "remboursements"


def test_preparer_refuse_un_connecteur_non_branche_ou_inconnu():
    contenu = {
        "jumeau": {"application_id": "remboursements", "nom": "Remboursements", "proprietaire": "Paiements"},
        "sources": [{"connecteur": "postgresql", "nom": "base"}],
    }
    with pytest.raises(import_identite.ImportInvalide, match="non branché"):
        import_identite.preparer(contenu, "manifeste", connus=["github", "jira"])


def test_preparer_refuse_plusieurs_identites():
    contenu = [
        {"application_id": "un", "nom": "Un", "proprietaire": "X"},
        {"application_id": "deux", "nom": "Deux", "proprietaire": "Y"},
    ]
    with pytest.raises(import_identite.ImportInvalide, match="une seule identité"):
        import_identite.preparer(contenu, "cmdb")
