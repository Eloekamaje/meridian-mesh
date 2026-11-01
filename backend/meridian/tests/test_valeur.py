"""Value Ledger : validation, écarts comparables et persistance tenant."""
import pytest

from meridian.adapters.outbound.postgres import valeur
from meridian.tests.conftest import besoin_pg


def _valeur(**extra):
    return {
        "id": "val-1", "type": "cout_evite", "libelle": "Éviter les rejets",
        "proprietaire": "ops", "statut": "mesuree", "attribution": "contribution",
        "confiance": 0.7, "devise": "EUR",
        "cible": {"valeur": 1000, "unite": "EUR"},
        "observe": {"valeur": 800, "unite": "EUR"},
        **extra,
    }


def test_ecart_comparable_et_non_comparable():
    resultat = valeur.ecart(_valeur())
    assert resultat["comparable"] is True
    assert resultat["delta"] == -200 and resultat["statut"] == "en_ecart"

    autre = valeur.ecart(_valeur(observe={"valeur": 800, "unite": "jours"}))
    assert autre["comparable"] is False and "unités" in autre["raison"]


def test_validation_refuse_type_statut_et_confiance():
    with pytest.raises(valeur.ValeurInvalide):
        valeur.valider(_valeur(type="magique"))
    with pytest.raises(valeur.ValeurInvalide):
        valeur.valider(_valeur(statut="peut_etre"))
    with pytest.raises(valeur.ValeurInvalide):
        valeur.valider(_valeur(confiance=1.5))


@besoin_pg
def test_ledger_persiste_et_resume_sans_melanger_devises(conn):
    cree = valeur.creer(conn, "banque", _valeur())
    assert cree["id"] == "val-1" and cree["ecart"]["delta"] == -200
    valeur.creer(conn, "banque", _valeur(
        id="val-2", devise="CAD",
        cible={"valeur": 500, "unite": "CAD"},
        observe={"valeur": 500, "unite": "CAD"}))
    lu = valeur.lire(conn, "banque", "val-1")
    assert lu["tenant_id"] == "banque"
    resume = valeur.resume(conn, "banque")
    assert resume["entrees"] == 2
    assert set(resume["devises"]) == {"EUR", "CAD"}
    assert resume["devises"]["EUR"]["attendue"] == 1000.0
    assert "limites" in resume and "devises" in resume["limites"][0]


@besoin_pg
def test_isolation_tenant_et_mise_a_jour(conn):
    valeur.creer(conn, "banque", _valeur())
    assert valeur.lire(conn, "autre", "val-1") is None
    mis = valeur.mettre_a_jour(conn, "banque", "val-1", {
        "statut": "realisee", "observe": {"valeur": 1200, "unite": "EUR"}})
    assert mis["statut"] == "realisee" and mis["ecart"]["statut"] == "atteint"
    with pytest.raises(valeur.ValeurInvalide):
        valeur.mettre_a_jour(conn, "banque", "val-1", {"id": "autre"})
