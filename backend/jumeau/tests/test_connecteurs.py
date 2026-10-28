"""Ce qu'un connecteur déclare et ce qu'il fait (plan de remédiation L2.5, L2.6).

Le catalogue en annonce douze ; six seulement alimentent un lecteur. `_simuler_test` rendait « prête » une source
PostgreSQL, Kafka ou AWS dont aucun code n'interroge l'hôte : une promesse sans mécanisme, affichée à côté d'un test
de connexion.
"""
from jumeau import connecteurs
from seed_data import CONNECTEURS

BRANCHES = ["github", "confluence", "jira", "servicenow", "cmdb", "datadog"]
NON_BRANCHES = ["postgresql", "oracle", "splunk", "kafka", "apigee", "aws"]


def source(connecteur, **config):
    return {"connecteur": connecteur, "config": config, "perimetre": ["p"]}


def test_seuls_les_connecteurs_implementes_sont_branches():
    assert [c for c in BRANCHES if connecteurs.connecteur_branche(c)] == BRANCHES
    assert [c for c in NON_BRANCHES if connecteurs.connecteur_branche(c)] == []
    # « cmdb » est le même système que ServiceNow, « github » alimente le clone Git.
    assert connecteurs.connecteur_branche("cmdb") == "servicenow"
    assert connecteurs.connecteur_branche("github") == "git"


def test_un_connecteur_non_branche_ne_peut_pas_etre_dit_pret():
    """Avant : {'statut': 'prete'} dès que la configuration était remplie."""
    p = connecteurs.test_simule(source("postgresql", hote="db.interne", port=5432, base="paiements"), CONNECTEURS)
    assert p["statut"] == "non_branche"
    assert "aucun lecteur" in p["erreur"]["detail"]


def test_un_connecteur_branche_garde_ses_controles():
    # Jira et Confluence exigent une connexion et un espace de travail : les contrôles d'avant restent.
    assert connecteurs.test_simule({"connecteur": "jira", "config": {}, "perimetre": ["PAY"]},
                                   CONNECTEURS)["statut"] == "configuration_incomplete"
    complet = connecteurs.test_simule(source("jira", connexion="vault:jira", projet="PAY"), CONNECTEURS)
    assert complet["statut"] == "prete"
    assert connecteurs.test_simule({"connecteur": "confluence",
                                    "config": {"connexion": "vault:wiki", "espace": "TBT"}, "perimetre": []},
                                   CONNECTEURS)["statut"] == "perimetre_vide"


def test_le_catalogue_expose_branche_pour_chaque_connecteur():
    # L'API ajoute `branche` : l'interface ne peut pas présenter un connecteur non branché comme disponible.
    assert {c["id"] for c in CONNECTEURS if connecteurs.connecteur_branche(c["id"])} == set(BRANCHES)
