"""Contrat commun des connecteurs de travail : méthodes et capacités déclarées."""
from meridian.adapters.outbound.travail import PROVIDERS, source_incidents, source_people, source_travail
from meridian.adapters.outbound.travail.azure import AzureDevOpsTravail
from meridian.adapters.outbound.travail.csv import CsvTravail
from meridian.adapters.outbound.travail.jira import JiraTravail
from meridian.adapters.outbound.travail.linear import LinearTravail


def test_tous_les_connecteurs_exposent_le_contrat_de_travail(tmp_path):
    csv = tmp_path / "t.csv"
    csv.write_text("external_id,titre,equipe_id,statut,estimation,unite,maj_source\nA,T,A,a_faire,1,points,2026-01-01\n",
                   encoding="utf-8")
    connecteurs = [
        CsvTravail({"chemin": str(csv)}),
        JiraTravail({"projet": "PAY"}, secret_ref="env:MERIDIAN_JIRA"),
        AzureDevOpsTravail({"organisation": "o", "projet": "p"}, secret_ref="env:MERIDIAN_ADO"),
        LinearTravail({"equipe_id": "T"}, secret_ref="env:MERIDIAN_LINEAR"),
    ]
    for connecteur in connecteurs:
        for methode in ("capacites", "lister_equipes", "lister_elements", "lister_cycles",
                        "lister_releases", "lister_dependances", "lister_temps"):
            assert callable(getattr(connecteur, methode)), f"{connecteur.provider} sans {methode}"
        capacites = connecteur.capacites()
        assert {"equipes", "sprints", "points", "heures", "worklogs", "dependances",
                "releases", "historique"} <= set(capacites)
        assert all(isinstance(valeur, bool) for valeur in capacites.values())
    assert {"jira", "azure_devops", "linear", "csv"} <= set(PROVIDERS)


def test_les_fabriques_respectent_le_provider(tmp_path):
    csv = tmp_path / "t.csv"
    csv.write_text("external_id,titre,equipe_id,statut,maj_source\nA,T,A,a_faire,2026-01-01\n", encoding="utf-8")
    assert source_travail({"provider": "csv", "configuration": {"chemin": str(csv)}}).provider == "csv"
    assert source_travail({"provider": "jira", "configuration": {"projet": "PAY"}}).provider == "jira"
    assert source_travail({"provider": "azure_devops", "configuration": {"organisation": "o", "projet": "p"}}).provider == "azure_devops"
    assert source_travail({"provider": "linear", "configuration": {"equipe_id": "T"}}).provider == "linear"
    assert source_people({"provider": "csv", "configuration": {"chemin": str(csv)}}).provider == "csv"
    assert source_incidents({"provider": "csv", "configuration": {"chemin": str(csv)}}).provider == "csv"
