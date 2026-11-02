"""Adapter Linear : GraphQL normalisé sans réseau."""
from meridian.adapters.outbound.travail import linear


def test_linear_normalise_issues_et_relations(monkeypatch):
    def fake(self, requete, variables):
        if "Issues" in requete:
            return {"issues": {"nodes": [{
                "id": "uuid", "identifier": "PAY-1", "title": "Paiement",
                "priority": 2, "estimate": 3, "state": {"name": "In Progress", "type": "started"},
                "cycle": {"id": "c1", "name": "Sprint"}, "parent": {"identifier": "PAY-0"},
                "relations": {"nodes": [{"type": "blocks", "relatedIssue": {"identifier": "PAY-2"}}]},
                "updatedAt": "2026-01-10T10:00:00Z", "createdAt": "2026-01-01T10:00:00Z",
            }]}}
        return {"team": {"cycles": {"nodes": [{"id": "c1", "name": "Sprint",
                                              "startsAt": "2026-01-01", "endsAt": "2026-01-14",
                                              "completedAt": "2026-01-14"}]}}}
    monkeypatch.setattr(linear.LinearTravail, "_appeler", fake)
    source = linear.LinearTravail({"equipe_id": "t1"}, secret_ref="env:LINEAR")
    element = source.lister_elements()[0]
    assert element["external_id"] == "PAY-1"
    assert element["estimation"]["valeur"] == 3
    assert element["statut"] == "en_cours"
    assert element["parent_id"] == "PAY-0"
    assert source.lister_cycles()[0]["termine"] is True
