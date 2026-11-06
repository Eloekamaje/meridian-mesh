import pytest

from meridian.domain import import_identite


def test_manifeste_team_sans_application_id():
    entrees = import_identite.analyser({
        "jumeau": {"type_twin": "TEAM", "team_id": "eq-paiements",
                   "nom": "Équipe paiements", "proprietaire": "DSI"},
        "sources": [{"connecteur": "confluence", "nom": "espace paiements"}],
    }, "manifeste")
    assert entrees[0]["type_twin"] == "TEAM"
    assert entrees[0]["twin_id"] == "eq-paiements"
    assert entrees[0]["application_id"] == ""
    assert entrees[0]["identifiants"]["team_id"] == "eq-paiements"


def test_manifeste_application_candidate_sans_application_id():
    entrees = import_identite.analyser({
        "jumeau": {"type_twin": "APPLICATION", "twin_id": "app-candidate",
                   "candidat": True, "nom": "Candidate", "proprietaire": "Équipe"},
        "sources": [],
    }, "manifeste")
    assert entrees[0]["twin_id"] == "app-candidate"
    assert entrees[0]["application_id"] == ""


def test_manifeste_resource_identifiant_externe():
    entrees = import_identite.analyser({
        "jumeau": {"type_twin": "RESOURCE", "resource_id": "ci-4242",
                   "nom": "Base CRM", "proprietaire": "Infra"},
        "sources": [],
    }, "manifeste")
    assert entrees[0]["twin_id"] == "ci-4242"
    assert entrees[0]["identifiants"] == {"resource_id": "ci-4242"}


def test_manifeste_team_refuse_un_application_id():
    with pytest.raises(import_identite.ImportInvalide, match="application_id interdit"):
        import_identite.analyser([{
            "type_twin": "TEAM", "application_id": "paiements",
            "nom": "Équipe", "proprietaire": "DSI",
        }], "manifeste")


def test_manifeste_identite_et_sources():
    entrees = import_identite.analyser({
        "jumeau": {"application_id": "remboursements", "nom": "Remboursements", "proprietaire": "Équipe Paiements"},
        "sources": [{"connecteur": "github", "nom": "remboursements", "config": {"connexion": "gh-acme"}}],
    }, "manifeste")
    assert entrees[0]["application_id"] == "remboursements"
    assert entrees[0]["proprietaire"] == "Équipe Paiements"
    assert entrees[0]["sources"][0]["connecteur"] == "github"


def test_perimetre_id_fourni_est_conserve():
    entrees = import_identite.analyser({
        "jumeau": {"application_id": "remboursements", "nom": "Remboursements",
                   "proprietaire": "Paiements", "perimetre": "Paiements Europe",
                   "perimetre_id": "portefeuille-cartes"},
    }, "manifeste")
    assert entrees[0]["perimetre"] == "Paiements Europe"
    assert entrees[0]["perimetre_id"] == "portefeuille-cartes"


def test_perimetre_id_absent_est_derive_du_texte():
    entrees = import_identite.analyser({
        "jumeau": {"application_id": "remboursements", "nom": "Remboursements",
                   "proprietaire": "Paiements", "perimetre": "Périmètre Paiements & Cartes"},
    }, "manifeste")
    assert entrees[0]["perimetre"] == "Périmètre Paiements & Cartes"
    assert entrees[0]["perimetre_id"] == "perimetre-paiements-cartes"


def test_preparer_propage_le_perimetre_id():
    prepare = import_identite.preparer({
        "jumeau": {"application_id": "remboursements", "nom": "Remboursements",
                   "proprietaire": "Paiements", "perimetre_id": "portefeuille-cartes"},
    }, "manifeste")
    assert prepare["identite"]["perimetre_id"] == "portefeuille-cartes"


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
