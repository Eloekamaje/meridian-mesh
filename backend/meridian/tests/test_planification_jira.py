"""Adapter Jira de travail : normalisation sans réseau."""
from meridian.adapters.outbound.travail import jira


def _reponse():
    return {"issues": [{
        "key": "PAY-1",
        "fields": {
            "summary": "Ajouter une route", "issuetype": {"name": "Story"},
            "status": {"statusCategory": {"key": "new"}}, "priority": {"name": "High"},
            "updated": "2026-01-10T10:00:00.000+0000", "created": "2026-01-01T10:00:00.000+0000",
            "timeoriginalestimate": 7200, "customfield_10016": 3,
            "fixVersions": [{"id": "10", "name": "R1"}],
            "parent": {"key": "PAY-0"},
            "components": [{"name": "API"}], "labels": ["paiement"],
            "issuelinks": [{"type": {"name": "Blocks"}, "outwardIssue": {"key": "PAY-2"}}],
        },
    }]}


def test_jira_normalise_points_heures_liens_et_releases(monkeypatch):
    monkeypatch.setattr(jira.lecture, "_get", lambda *a, **k: _reponse())
    source = jira.JiraTravail({"projet": "PAY", "champ_points": "customfield_10016",
                               "champ_cycle": "customfield_10020"}, secret_ref="vault:jira")
    elements = source.lister_elements()
    element = elements[0]
    assert element["external_id"] == "PAY-1"
    assert element["estimation"] == {"valeur": 3.0, "unite": "points", "methode": "story_points"}
    assert element["release_id"] == "10"
    assert element["parent_id"] == "PAY-0"
    assert element["categorie_charge"] == "planifiee"
    assert element["donnees"]["liens"][0]["outwardIssue"]["key"] == "PAY-2"
    assert source.capacites()["points"] is True
    assert source.capacites()["sprints"] is False


def test_jira_utilise_les_heures_si_aucun_point(monkeypatch):
    reponse = _reponse()
    reponse["issues"][0]["fields"].pop("customfield_10016")
    monkeypatch.setattr(jira.lecture, "_get", lambda *a, **k: reponse)
    source = jira.JiraTravail({"projet": "PAY"}, secret_ref="vault:jira")
    element = source.lister_elements()[0]
    assert element["estimation"]["unite"] == "heures"
    assert element["estimation"]["valeur"] == 2.0


def test_jira_worklogs_optionnels(monkeypatch):
    def fake(self, chemin, **params):
        if chemin == "/rest/api/3/search/jql":
            return {"issues": [{"key": "PAY-1", "fields": {"summary": "A", "issuetype": {"name": "Story"},
                                                           "status": {"statusCategory": {"key": "new"}},
                                                           "updated": "2026-01-10T10:00:00Z"}}]}
        return {"worklogs": [{"id": "w1", "started": "2026-01-10T09:00:00Z",
                              "timeSpentSeconds": 5400}]}
    monkeypatch.setattr(jira.JiraTravail, "_get", fake)
    source = jira.JiraTravail({"projet": "PAY", "worklogs": True}, secret_ref="vault:jira")
    temps = source.lister_temps()
    assert temps[0]["id"] == "PAY-1:w1"
    assert temps[0]["valeur"] == 1.5 and temps[0]["unite"] == "heures"
    assert source.capacites()["worklogs"] is True
