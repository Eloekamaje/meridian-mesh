"""Situations d'interface : priorité, identifiant stable, textes métier et aucune preuve brute."""
import pytest

from jumeau import impacts_situations

SECRET = "tok_live_9f3c2b7a"


def _impact(**champs):
    impact = {
        "application": "portail",
        "operation": "DELETE /comptes/{id}",
        "change_type": "operation_removed",
        "severity": "breaking",
        "evidence": [{"locator": f"application.properties?token={SECRET}", "token": SECRET}],
        "raison": f"portail consomme DELETE /comptes/{{id}} (Authorization: Bearer {SECRET})",
    }
    impact.update(champs)
    return impact


def _run(impacts, run_id="run-abc", **champs):
    run = {
        "id": run_id,
        "application_id": "comptes",
        "status": "ok",
        "stats": {"changements": 1, "impacts": len(impacts)},
        "changes": [],
        "impacts": impacts,
        "started_at": "2026-10-30T10:00:00+00:00",
        "ended_at": "2026-10-30T10:01:00+00:00",
    }
    run.update(champs)
    return run


def test_breaking_produit_une_situation_haute_et_actionnable():
    sit = impacts_situations.situation_depuis_run(_run([_impact()]), {"id": "tbt", "nom": "TBT"})

    assert sit["id"] == "sit-interfaces-tbt-run-abc"
    assert sit["verbe"] == "a_comprendre" and sit["nature"] == "changement" and sit["type"] == "interface"
    assert sit["jumeaux"] == ["tbt"] and sit["priorite"] == "haute"
    assert sit["score"] == impacts_situations.SCORES["haute"]
    assert sit["statut"] == "active" and sit["detectee"] == "2026-10-30T10:01:00+00:00"
    assert "DELETE /comptes/{id}" in sit["titre"] and "portail" in sit["titre"].lower()
    assert "opération retirée" in sit["resume"] and "rupture" in sit["resume"]
    assert "portail" in sit["decouverte_quoi"] and "operation_removed" in sit["decouverte_quoi"]
    assert sit["question"].startswith("Qui doit adapter portail") and sit["question"].endswith("?")


def test_warning_seul_reste_une_situation_normale():
    sit = impacts_situations.situation_depuis_run(
        _run([_impact(severity="warning", change_type="operation_changed")]), "tbt")

    assert sit["priorite"] == "normale" and sit["score"] == impacts_situations.SCORES["normale"]
    assert "opération modifiée" in sit["resume"] and "avertissement" in sit["resume"]
    assert sit["question"].startswith("Quel effet")


@pytest.mark.parametrize("impacts", [[], [_impact(severity="info")]])
def test_sans_impact_breaking_ou_warning_aucune_situation(impacts):
    assert impacts_situations.situation_depuis_run(_run(impacts), {"id": "tbt"}) is None


def test_l_identifiant_depend_du_run_et_les_informations_ne_sont_pas_des_impacts():
    premier = impacts_situations.situation_depuis_run(
        _run([_impact(), _impact(application="interne", severity="info")], run_id="run-1"), {"id": "tbt"})
    second = impacts_situations.situation_depuis_run(_run([_impact()], run_id="run-2"), {"id": "tbt"})

    assert premier["id"] == "sit-interfaces-tbt-run-1"
    assert second["id"] == "sit-interfaces-tbt-run-2" and premier["id"] != second["id"]
    assert "interne" not in str(premier)


def test_aucun_secret_de_preuve_dans_la_situation():
    sit = impacts_situations.situation_depuis_run(_run([_impact()]), {"id": "tbt"})

    assert SECRET not in str(sit)
    assert "evidence" not in sit and "raison" not in sit
    assert "application.properties" not in str(sit)


def test_plusieurs_impacts_sont_resumes_sans_en_inventer():
    sit = impacts_situations.situation_depuis_run(
        _run([_impact(), _impact(application="crm", operation="GET /clients", change_type="operation_changed",
                                 severity="warning")]), {"id": "tbt"})

    assert sit["priorite"] == "haute" and "(+1 autre impact)" in sit["titre"]
    assert "portail" in sit["resume"] and "crm" in sit["resume"]
    assert "DELETE /comptes/{id}" in sit["resume"] and "GET /clients" in sit["resume"]


def test_un_resultat_de_decouverte_complet_est_accepte():
    resultat = {"run": _run([_impact()]), "changements": [], "impacts": [_impact()], "graphe": {}}

    sit = impacts_situations.situation_depuis_run(resultat, {"id": "tbt"})

    assert sit["id"] == "sit-interfaces-tbt-run-abc"
