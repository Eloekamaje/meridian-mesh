"""Discriminant D7 : preuves qui départagent les rivales, question par NEED.

Deux modes : READ sans base (besoins, hypothèses et assertions injectés) et
persistance réelle (sautée sans ``JUMEAU_PG_DSN``, comme les autres tests Postgres).
"""
from datetime import datetime, timezone

from meridian.adapters.outbound.postgres import discriminant
from meridian.application import abduction
from meridian.tests.conftest import besoin_pg

TENANT = "banque"
MAINTENANT = datetime(2026, 11, 16, 9, 0, tzinfo=timezone.utc)


def hypothese(identifiant, enonce, preuve, rival_ids, need_id="need-1", statut="EMISE"):
    return {"id": identifiant, "tenant_id": TENANT, "famille": "investigation",
            "type": "HYPOTHESIS", "mode": "PROPOSED", "titre": identifiant,
            "donnees": {"enonce": enonce, "statut": statut,
                        "rival_ids": list(rival_ids),
                        "preuve_discriminante": preuve, "need_id": need_id}}


def need(identifiant="need-1", hypothese_ids=("h1", "h2", "h3"), **donnees):
    charge = {"statut": "OUVERT", "signature": "contournement",
              "sujet_detection": "app-cartes|CONSOMME",
              "hypothese_ids": list(hypothese_ids),
              "refutable_par": "réconcilié 30 jours",
              "preuves": [{"source": "interface_assertion",
                           "subject": "app-cartes", "predicate": "CONSOMME",
                           "declared": ["GET /v1/payments"],
                           "observed": ["GET /v1/payments", "POST /legacy/pay"]}]}
    charge.update(donnees)
    return {"id": identifiant, "tenant_id": TENANT, "famille": "emergence",
            "type": "NEED", "mode": "PROPOSED", "titre": identifiant,
            "donnees": charge}


def assertion(subject, predicate, object_, mode):
    return {"subject": subject, "predicate": predicate, "object": object_,
            "mode": mode, "source": "test", "environment": "prod"}


def lot_rivales():
    return [
        hypothese("h1",
                  "L'usage observé (POST /legacy/pay) est un besoin réel non déclaré.",
                  "POST /legacy/pay reste utilisé dans les flux réels pendant 30 jours",
                  ["h2", "h3"]),
        hypothese("h2",
                  "Le déclaré GET /v1/payments est obsolète, le contrat a changé.",
                  "une révision du contrat fait reparaître POST /legacy/pay dans le déclaré",
                  ["h1", "h3"]),
        hypothese("h3",
                  "La mesure observée est défaillante, hors périmètre.",
                  "une observation manuelle confirme l'absence de POST /legacy/pay des flux réels",
                  ["h1", "h2"]),
    ]


# --- READ sans base ---


def test_preuves_discriminantes_attribue_les_objets_a_la_rivale_qui_tranche():
    metrologie = {"source": "metrologie",
                  "constat": "POST /legacy/pay reste utilisé dans les flux réels "
                             "pendant 32 jours glissants"}
    res = discriminant.preuves_discriminantes(
        None, TENANT, ["h1", "h2", "h3"],
        hypotheses=lot_rivales(),
        besoins=[need(preuves=[{
            "source": "interface_assertion", "subject": "app-cartes",
            "predicate": "CONSOMME", "declared": ["GET /v1/payments"],
            "observed": ["GET /v1/payments", "POST /legacy/pay"]}, metrologie])],
        assertions=[
            assertion("app-cartes", "CONSOMME", "GET /v1/payments", "declared"),
            assertion("app-cartes", "CONSOMME", "POST /legacy/pay", "observed"),
            assertion("app-cartes", "CONSOMME", "audit manuel des flux", "observed"),
        ])

    assert set(res["hypotheses"]) == {"h1", "h2", "h3"}
    # La mesure datée appuie l'usage réel (vocabulaire signature : jours/flux).
    appuis_h1 = {m["objet"].get("constat") for m in res["hypotheses"]["h1"]["appuie"]}
    assert metrologie["constat"] in appuis_h1
    # Le contrat déclaré appuie la rivale « référence obsolète ».
    appuis_h2 = {m["objet"].get("objet") for m in res["hypotheses"]["h2"]["appuie"]}
    assert "GET /v1/payments" in appuis_h2
    # L'audit manuel appuie la rivale « mesure défaillante ».
    appuis_h3 = {m["objet"].get("objet") for m in res["hypotheses"]["h3"]["appuie"]}
    assert "audit manuel des flux" in appuis_h3
    # Le fait déclencheur (l'observé hors déclaré) est mutualisé : il ne
    # discrimine aucune rivale à lui seul.
    partagees = {m["objet"].get("objet") for m in res["partagees"]}
    assert "POST /legacy/pay" in partagees
    for entree in res["hypotheses"].values():
        assert "appuie" in entree and "rival_ids" in entree


def test_suggestions_need_contournement_question_non_vide_liee_aux_rivales():
    res = discriminant.suggestions(
        None, TENANT, "need-1", need=need(), hypotheses=lot_rivales())

    assert res["need_id"] == "need-1"
    assert res["signature"] == "contournement"
    assert res["question"] and "?" in res["question"]
    assert set(res["rivales"]) == {"h1", "h2", "h3"}
    assert set(res["couvre"]) <= set(res["rivales"])
    assert res["couvre"]  # la question départage au moins une rivale
    assert "Hypothèses rivales" in res["question_socratique"]


def test_suggestions_need_introuvable_rend_none(monkeypatch):
    monkeypatch.setattr(discriminant.entreprise_depot, "lire_objet",
                        lambda conn, tenant, objet_id: None)
    assert discriminant.suggestions(None, TENANT, "need-inconnu") is None


def test_suggestions_need_sans_rivale_question_vide():
    res = discriminant.suggestions(
        None, TENANT, "need-1",
        need=need(hypothese_ids=[]), hypotheses=[])
    assert res["question"] == ""
    assert res["rivales"] == []


# --- Persistance réelle ---


@besoin_pg
def test_discriminant_sur_hypotheses_persistees(conn):
    """Le détecteur contournement (B7) persiste 3 rivales + 1 NEED ; le
    discriminant les relit et attribue les assertions aux bonnes rivales."""
    from meridian.domain.interfaces import Assertion, InterfaceGraph
    from meridian.adapters.outbound.postgres import (
        boucle, detecteurs_besoins, interfaces_depot)

    graphe = InterfaceGraph(assertions=[
        Assertion(subject="app-cartes", predicate="CONSOMME",
                  object="GET /v1/payments", mode="declared", source="code",
                  locator="spec", environment="prod", confidence=0.9,
                  evidence="contrat"),
        Assertion(subject="app-cartes", predicate="CONSOMME",
                  object="POST /legacy/pay", mode="observed", source="runtime",
                  locator="otlp", environment="prod", confidence=0.8,
                  evidence="trace"),
    ])
    interfaces_depot.enregistrer(conn, TENANT, graphe)
    rapport = detecteurs_besoins.detecter(
        conn, TENANT, signature="contournement", maintenant=MAINTENANT)
    assert rapport["erreurs"] == []
    [cree] = rapport["crees"]
    hyp_ids = cree["hypothese_ids"]
    assert len(hyp_ids) == 3

    res = discriminant.preuves_discriminantes(conn, TENANT, hyp_ids)
    assert set(res["hypotheses"]) == set(hyp_ids)
    for hyp_id, entree in res["hypotheses"].items():
        assert entree["statut"] == "EMISE"
        assert entree["preuve_discriminante"]
        assert set(entree["rival_ids"]) == set(hyp_ids) - {hyp_id}
    # Au moins un objet de preuve a été lu depuis la base.
    assert res["preuves"]

    sug = discriminant.suggestions(conn, TENANT, cree["id"])
    assert sug["need_id"] == cree["id"]
    assert sug["signature"] == "contournement"
    assert sug["question"] and "?" in sug["question"]
    assert set(sug["rivales"]) == set(hyp_ids)
    # La question est liée aux rivales : elle reprend une preuve discriminante.
    preuves = " ".join(
        res["hypotheses"][h]["preuve_discriminante"] for h in hyp_ids)
    assert any(
        mot in preuves for mot in abduction._tokens(sug["question"]))
    assert "Hypothèses rivales" in sug["question_socratique"]

    # La ligne relue reste compatible avec le modèle persisté.
    relue = boucle.lire_boucle(conn, TENANT, hyp_ids[0], as_dict=False)
    assert relue.statut == "EMISE"
    assert set(relue.rival_ids) == set(hyp_ids) - {hyp_ids[0]}
