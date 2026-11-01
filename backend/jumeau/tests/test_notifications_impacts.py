"""Notifications d'impact d'interface : tenant-wide, texte métier, identifiant stable, aucun secret."""
import asyncio

import pytest

from jumeau import impacts_situations, notifications_impacts

SECRET = "tok_live_9f3c2b7a"
JUMEAU = {"id": "tbt", "nom": "TBT", "equipe": "equipe-paiements", "domaine": "Paiements",
          "mission": "Traiter les paiements"}


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


def test_breaking_notifie_avec_un_identifiant_stable():
    notification = notifications_impacts.notification_depuis_run(_run([_impact()]), JUMEAU)

    assert notification["id"] == "notif-interface-tbt-run-abc"
    assert notification["type"] == "interface_impact"
    assert notification["lien"] == "/atlas?focus=tbt"
    assert notification["lu"] is False
    assert notification["quand"] == "2026-10-30T10:01:00+00:00"
    assert "rupture" in notification["texte"] and "haute" in notification["texte"]
    assert "DELETE /comptes/{id}" in notification["texte"] and "portail" in notification["texte"]


def test_warning_notifie_avec_la_severite_avertissement():
    notification = notifications_impacts.notification_depuis_run(
        _run([_impact(severity="warning", change_type="operation_changed")]), JUMEAU)

    assert "avertissement" in notification["texte"] and "normale" in notification["texte"]
    assert "DELETE /comptes/{id}" in notification["texte"]


@pytest.mark.parametrize("impacts", [[], [_impact(severity="info")]])
def test_sans_impact_breaking_ou_warning_aucune_notification(impacts):
    assert notifications_impacts.notification_depuis_run(_run(impacts), JUMEAU) is None


def test_aucun_secret_ni_html_dans_le_texte():
    notification = notifications_impacts.notification_depuis_run(
        _run([_impact(application="<b>portail</b>", operation="DELETE <script>alert(1)</script> /comptes")]),
        JUMEAU)

    assert SECRET not in str(notification)
    assert "application.properties" not in str(notification)
    assert "evidence" not in notification and "raison" not in notification
    assert "<" not in notification["texte"] and ">" not in notification["texte"]


def test_deux_runs_produisent_deux_identifiants():
    premier = notifications_impacts.notification_depuis_run(_run([_impact()], run_id="run-1"), JUMEAU)
    second = notifications_impacts.notification_depuis_run(_run([_impact()], run_id="run-2"), JUMEAU)

    assert premier["id"] == "notif-interface-tbt-run-1"
    assert second["id"] == "notif-interface-tbt-run-2"
    assert premier["id"] != second["id"]


def test_une_situation_fournie_ne_change_pas_l_identifiant():
    run = _run([_impact()])
    situation = impacts_situations.situation_depuis_run(run, JUMEAU)

    notification = notifications_impacts.notification_depuis_run(run, JUMEAU, situation=situation)

    assert notification["id"] == situation["id"].replace("sit-interfaces-", "notif-interface-")


class _Notifications:
    def __init__(self):
        self.docs = {}

    async def update_one(self, filtre, mise_a_jour, upsert=False):
        if filtre["id"] in self.docs:
            return type("Resultat", (), {"upserted_id": None, "matched_count": 1})()
        self.docs[filtre["id"]] = dict(mise_a_jour["$setOnInsert"])
        return type("Resultat", (), {"upserted_id": filtre["id"], "matched_count": 0})()


class _Db:
    def __init__(self):
        self.notifications = _Notifications()


def test_publier_notification_est_idempotent_et_publie_le_sse(monkeypatch):
    recus = []
    monkeypatch.setattr(notifications_impacts.evenements, "publier",
                        lambda acteur, type_, **champs: recus.append((acteur, type_, champs)))
    db = _Db()

    async def scenario():
        premier = await notifications_impacts.publier_notification(db, JUMEAU, _run([_impact()]))
        second = await notifications_impacts.publier_notification(db, JUMEAU, _run([_impact()]))
        return premier, second

    premier, second = asyncio.run(scenario())

    assert premier and second is None
    assert list(db.notifications.docs) == ["notif-interface-tbt-run-abc"]
    assert recus == [("*", "notification.creee", {"notification": premier})]
