"""Adapter Azure DevOps : WIQL, champs, points et liens, sans réseau."""
from meridian.adapters.outbound.travail import azure


def _element():
    return {"value": [{
        "id": 42,
        "fields": {"System.Title": "Paiement", "System.WorkItemType": "User Story",
                   "System.State": "Active", "System.Priority": 2,
                   "System.IterationPath": "PAY\\Sprint 1",
                   "System.ChangedDate": "2026-01-10T10:00:00Z",
                   "Microsoft.VSTS.Scheduling.StoryPoints": 5},
        "relations": [
            {"rel": "System.LinkTypes.Hierarchy-Reverse", "url": "https://dev.azure.com/o/p/_apis/wit/workItems/10"},
            {"rel": "System.LinkTypes.Dependency-Forward", "url": "https://dev.azure.com/o/p/_apis/wit/workItems/43"},
        ],
    }]}


def test_azure_normalise_work_items_et_relations(monkeypatch):
    appels = []

    def fake(self, methode, chemin, **kwargs):
        appels.append((methode, chemin, kwargs))
        if chemin.endswith("wiql"):
            return {"workItems": [{"id": 42}]}
        return _element()

    monkeypatch.setattr(azure.AzureDevOpsTravail, "_appeler", fake)
    source = azure.AzureDevOpsTravail({"organisation": "o", "projet": "p", "equipe_id": "p"}, secret_ref="env:PAT")
    element = source.lister_elements()[0]
    assert element["external_id"] == "42"
    assert element["estimation"] == {"valeur": 5.0, "unite": "points", "methode": "story_points"}
    assert element["parent_id"] == "10"
    assert element["donnees"]["liens"][0]["target_id"] == "43"
    assert appels[0][0] == "POST" and appels[1][0] == "GET"
