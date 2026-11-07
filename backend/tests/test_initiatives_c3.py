"""Lot C3 — la réponse d'initiative enfile son état canonique.

Ces tests n'ouvrent ni Mongo réel ni Postgres : ils fixent le contrat du builder pur
``pont_travail.evenement_initiative_maj`` et de la route ``POST /initiatives/{iid}/repondre``
(outbox best-effort, tenant, idempotence, collision).
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
import time
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from aides_pont import CollectionPont, ConnexionPont
from test_conversation_routes import Collection

from meridian.adapters.inbound.http import initiatives as initiatives_module
from meridian.adapters.outbound.mongo import pont_canonique as pont_mongo
from meridian.adapters.outbound.postgres import boucle as pg_boucle
from meridian.adapters.outbound.postgres import entreprise_depot
from meridian.adapters.outbound.postgres import pont_canonique as pont_pg
from meridian.application import pont_canonique as pont
from meridian.application import pont_travail
from meridian.application import tenant_context

TENANT = "banque"
AUTRE = "assurance"
DATE = "2026-11-07T09:00:00+00:00"
REPONSE_LE = "2026-11-07T09:05:00+00:00"
IID = "init-c3"
SID = "sit-c3"
INI_CANONIQUE = pont.initiative_id(pont.decision_initiative_id(IID))


@pytest.fixture(autouse=True)
def _cles_pont(monkeypatch):
    monkeypatch.setenv(pont.PONT_KEY_ENV, "cle-de-test-pont-canonique-32")


def un_situation(**champs):
    base = {
        "id": SID,
        "tenant_id": TENANT,
        "titre": "Latence des paiements",
        "resume": "Le délai dépasse la cible.",
        "statut": "active",
        "priorite": "haute",
        "jumeaux": [],
        "cree_le": DATE,
        "detectee": DATE,
    }
    base.update(champs)
    return base


def un_initiative(**champs):
    base = {
        "id": IID,
        "tenant_id": TENANT,
        "titre": "Traiter la latence",
        "raison": "Le délai monte",
        "statut": "en_attente",
        "genre": "a_confirmer",
        "jumeaux": [],
        "confiance": 70,
        "situation_id": SID,
        "reponse": {"choix": "Créer un nouveau travail", "par": "demo",
                    "quand": REPONSE_LE},
        "quand": DATE,
        "cree_le": DATE,
        "maj_le": REPONSE_LE,
    }
    base.update(champs)
    return base


def _objets(evenement):
    return pont.objets_depuis_evenement(
        evenement, tenant_id=evenement["tenant_id"], maintenant=REPONSE_LE)


# ---------------------------------------------------------------------------
# Builder pur : la réponse porte l'Initiative et les ancres parentes
# ---------------------------------------------------------------------------


def test_evenement_initiative_maj_porte_l_initiative_et_les_ancres():
    situation = un_situation()
    investigation = pont_travail.snapshot_investigation(
        situation, tenant_id=TENANT)

    evenement = pont_travail.evenement_initiative_maj(
        un_initiative(statut="acceptee"), tenant_id=TENANT, situation=situation,
        investigation=investigation, maintenant=REPONSE_LE)

    assert evenement["operation"] == pont.OPERATION_INITIATIVE
    assert evenement["canonical_id"] == IID
    assert evenement["tenant_id"] == TENANT
    assert evenement["payload"]["initiative"]["statut"] == "acceptee"
    assert evenement["payload"]["initiative"]["reponse"]["choix"] == (
        "Créer un nouveau travail")
    assert evenement["payload"]["situation"]["id"] == SID
    assert evenement["payload"]["investigation"]["id"] == pont.investigation_id(SID)
    assert evenement["payload"]["investigation"]["situation_id"] == SID
    assert evenement["source"]["collection"] == "initiatives"
    assert evenement["source"]["id"] == IID

    objets = _objets(evenement)
    assert [objet["type"] for objet in objets] == [
        "SITUATION", "INVESTIGATION", "DECISION", "INITIATIVE"]
    initiative = next(objet for objet in objets if objet["type"] == "INITIATIVE")
    assert initiative["id"] == INI_CANONIQUE
    assert initiative["donnees"]["decision_id"] == pont.decision_initiative_id(IID)


def test_evenement_initiative_maj_est_idempotent_et_une_vraie_modification_change_la_cle():
    situation = un_situation()
    initiative = un_initiative(statut="acceptee")

    premier = pont_travail.evenement_initiative_maj(
        initiative, tenant_id=TENANT, situation=situation, maintenant=REPONSE_LE)
    rejeu = pont_travail.evenement_initiative_maj(
        initiative, tenant_id=TENANT, situation=situation,
        maintenant="2026-11-07T20:00:00+00:00")
    modifie = pont_travail.evenement_initiative_maj(
        un_initiative(reponse={"choix": "Ignorer", "par": "demo", "quand": REPONSE_LE},
                      statut="refusee"),
        tenant_id=TENANT, situation=situation, maintenant=REPONSE_LE)

    assert premier["_id"] == rejeu["_id"]
    assert premier["_id"] != modifie["_id"]


def test_evenement_initiative_maj_canonise_demo_vers_local():
    situation = un_situation(tenant_id="demo")
    initiative = un_initiative(tenant_id="demo", situation_id=SID, statut="acceptee")

    evenement = pont_travail.evenement_initiative_maj(
        initiative, tenant_id="local", situation=situation, maintenant=REPONSE_LE)

    assert evenement["tenant_id"] == "local"
    assert evenement["payload"]["initiative"]["tenant_id"] == "local"
    assert evenement["payload"]["situation"]["tenant_id"] == "local"
    assert all(objet["tenant_id"] == "local" for objet in _objets(evenement))


def test_evenement_initiative_maj_refuse_un_document_non_mapping():
    with pytest.raises(pont.PontInvalide):
        pont_travail.evenement_initiative_maj(
            "initiative", tenant_id=TENANT, situation=un_situation())


def test_evenement_initiative_maj_refuse_un_tenant_divergent():
    with pytest.raises(pont.TenantMismatch):
        pont_travail.evenement_initiative_maj(
            un_initiative(tenant_id=AUTRE), tenant_id=TENANT,
            situation=un_situation())


def test_snapshot_investigation_suit_le_statut_de_la_situation():
    ouverte = pont_travail.snapshot_investigation(
        un_situation(statut="active"), tenant_id=TENANT)
    close = pont_travail.snapshot_investigation(
        un_situation(statut="classée"), tenant_id=TENANT)

    assert ouverte == {"id": pont.investigation_id(SID), "tenant_id": TENANT,
                       "situation_id": SID, "titre": "Latence des paiements",
                       "statut": "OPEN"}
    assert close["statut"] == "CLOSED"


def test_snapshot_investigation_refuse_un_document_non_mapping():
    with pytest.raises(pont.PontInvalide):
        pont_travail.snapshot_investigation("situation", tenant_id=TENANT)


# ---------------------------------------------------------------------------
# Route /initiatives/{iid}/repondre : écriture Mongo puis outbox best-effort
# ---------------------------------------------------------------------------


def _db(initiative=None, situation=None, cases=None):
    return SimpleNamespace(
        jumeaux=Collection([]),
        situations=Collection([situation or un_situation()]),
        cases=Collection(cases or []),
        initiatives=Collection([initiative or un_initiative()]),
        pont_canonique=CollectionPont(),
    )


def _client(db):
    async def journaler(*args, **kwargs):
        return None

    deps = {
        "db": db,
        "resoudre_perimetre": lambda acteur, espace: (acteur, {"id": "perso"}),
        "autorisations": lambda espace, ids: set(ids),
        "journaler": journaler,
        "slugify": lambda texte: texte.lower().replace(" ", "-"),
        "NO_ID": {"_id": 0},
    }
    api = APIRouter(prefix="/api")
    api.include_router(initiatives_module.build_initiatives_router(deps))
    app = FastAPI()
    app.include_router(api)
    return TestClient(app)


@contextmanager
def _tenant(valeur):
    jeton = tenant_context.definir(valeur)
    try:
        yield
    finally:
        tenant_context.reinitialiser(jeton)


def _repondre(client, choix="Créer un nouveau travail", **kwargs):
    with _tenant(TENANT):
        return client.post(f"/api/initiatives/{IID}/repondre",
                           json={"choix": choix, **kwargs})


def test_repondre_enfile_initiative_maj_avec_le_snapshot_de_la_situation():
    db = _db()
    client = _client(db)

    r = _repondre(client)

    assert r.status_code == 200, r.text
    initiatives = db.pont_canonique.documents
    assert len(initiatives) == 1
    evenement = initiatives[0]
    assert evenement["operation"] == pont.OPERATION_INITIATIVE
    assert evenement["canonical_id"] == IID
    assert evenement["tenant_id"] == TENANT
    assert evenement["payload"]["initiative"]["id"] == IID
    assert evenement["payload"]["initiative"]["statut"] == "acceptee"
    assert evenement["payload"]["initiative"]["tenant_id"] == TENANT
    assert evenement["payload"]["situation"]["id"] == SID
    assert evenement["payload"]["investigation"]["id"] == pont.investigation_id(SID)
    assert evenement["payload"]["initiative"]["maj_le"] == db.initiatives.docs[0]["maj_le"]


def test_repondre_refus_enfile_aussi_l_initiative_maj():
    db = _db()
    client = _client(db)

    r = _repondre(client, "Ignorer")

    assert r.status_code == 200, r.text
    evenement = db.pont_canonique.documents[0]
    assert evenement["payload"]["initiative"]["statut"] == "refusee"
    assert [objet["type"] for objet in _objets(evenement)] == [
        "SITUATION", "INVESTIGATION", "DECISION"]


def test_repondre_cree_l_initiative_canonique_et_sa_chaine_parente():
    db = _db()
    client = _client(db)

    r = _repondre(client)
    assert r.status_code == 200, r.text
    evenement = db.pont_canonique.documents[0]

    conn = ConnexionPont()
    resultat = pont_pg.appliquer_evenement(conn, evenement)

    assert INI_CANONIQUE in resultat["ecrits"]
    initiative = entreprise_depot.lire_objet(conn, TENANT, INI_CANONIQUE)
    assert initiative is not None
    assert initiative["donnees"]["decision_id"] == pont.decision_initiative_id(IID)
    ligne = pg_boucle.lire_boucle(conn, TENANT, INI_CANONIQUE, historique=True)
    assert [etape["type"] for etape in ligne["chaine"]] == [
        "SITUATION", "INVESTIGATION", "DECISION", "INITIATIVE"]


def test_un_rejeu_du_meme_evenement_ne_duplique_ni_l_outbox_ni_le_canonique():
    db = _db()
    client = _client(db)
    assert _repondre(client).status_code == 200
    evenement = db.pont_canonique.documents[0]

    depot = pont_mongo.DepotPontCanonique(CollectionPont())
    premier = asyncio.run(depot.enfiler(evenement))
    second = asyncio.run(depot.enfiler(evenement))

    assert premier["cree"] is True
    assert second["cree"] is False
    assert len(depot.collection.documents) == 1
    assert len(db.pont_canonique.documents) == 1

    conn = ConnexionPont()
    pont_pg.appliquer_evenement(conn, evenement)
    rejeu = pont_pg.appliquer_evenement(conn, evenement)

    assert rejeu["ecrits"] == []
    assert set(conn.stock) == {
        (TENANT, identifiant) for identifiant in evenement["canonical_ids"]}


def test_repondre_avec_un_autre_tenant_ne_lit_pas_l_initiative_et_n_enfile_rien():
    db = _db(initiative=un_initiative(tenant_id=AUTRE))
    client = _client(db)

    with _tenant(TENANT):
        r = client.post(f"/api/initiatives/{IID}/repondre",
                        json={"choix": "Créer un nouveau travail"})

    assert r.status_code == 404
    assert db.pont_canonique.documents == []
    assert db.initiatives.docs[0]["statut"] == "en_attente"


def test_repondre_avec_demo_ne_cree_qu_un_objet_local():
    db = _db(initiative=un_initiative(tenant_id="demo"),
             situation=un_situation(tenant_id="demo"))
    client = _client(db)

    with _tenant("demo"):
        r = client.post(f"/api/initiatives/{IID}/repondre",
                        json={"choix": "Créer un nouveau travail"})

    assert r.status_code == 200, r.text
    assert db.initiatives.docs[0]["tenant_id"] == "local"
    evenement = db.pont_canonique.documents[0]
    assert evenement["tenant_id"] == "local"
    assert evenement["payload"]["initiative"]["tenant_id"] == "local"
    conn = ConnexionPont()
    pont_pg.appliquer_evenement(conn, evenement, tenant_id="local")
    assert {tenant for tenant, _ in conn.stock} == {"local"}


def test_repondre_reste_best_effort_si_la_construction_leve(monkeypatch):
    db = _db()
    client = _client(db)

    def _construction_impossible(*args, **kwargs):
        raise RuntimeError("construction impossible")

    monkeypatch.setattr(
        initiatives_module.pont_travail, "evenement_initiative_maj",
        _construction_impossible)

    r = _repondre(client, "Ignorer")

    assert r.status_code == 200, r.text
    assert db.initiatives.docs[0]["statut"] == "refusee"
    assert db.initiatives.docs[0]["tenant_id"] == TENANT
    assert db.pont_canonique.documents == []


def test_repondre_avec_cle_absente_reste_best_effort(monkeypatch):
    db = _db()
    client = _client(db)
    monkeypatch.delenv(pont.PONT_KEY_ENV, raising=False)

    r = _repondre(client)

    assert r.status_code == 200, r.text
    assert db.initiatives.docs[0]["statut"] == "acceptee"
    assert db.pont_canonique.documents == []


def test_repondre_ne_bloque_pas_sur_une_outbox_lente(monkeypatch):
    db = _db()
    client = _client(db)

    async def _outbox_lente(*args, **kwargs):
        await asyncio.sleep(5)
        return []

    monkeypatch.setattr(
        initiatives_module.pont_outbox, "enfiler_lot_best_effort", _outbox_lente)

    debut = time.monotonic()
    r = _repondre(client)
    duree = time.monotonic() - debut

    assert r.status_code == 200, r.text
    assert duree < 3.5
    assert db.initiatives.docs[0]["statut"] == "acceptee"
    assert db.pont_canonique.documents == []


def test_repondre_ne_perd_pas_l_ecriture_si_l_outbox_leve_une_collision(monkeypatch, caplog):
    db = _db()
    client = _client(db)

    async def _collision(*args, **kwargs):
        raise pont.PontInvalide(
            "collision d'idempotence sur _id 'abc' : contenu différent")

    monkeypatch.setattr(
        initiatives_module.pont_outbox, "enfiler_lot_best_effort", _collision)

    with caplog.at_level("WARNING", logger="meridian.initiatives"):
        r = _repondre(client)

    assert r.status_code == 200, r.text
    assert db.initiatives.docs[0]["statut"] == "acceptee"
    assert db.pont_canonique.documents == []
    assert "collision d'idempotence" in caplog.text
    assert "contenu différent" in caplog.text


def test_les_logs_du_pont_expurgent_les_urls_a_secret(monkeypatch, caplog):
    db = _db()
    client = _client(db)

    def _construction_impossible(*args, **kwargs):
        raise RuntimeError("panne mongodb://alice:motdepasse@mongo/db")

    monkeypatch.setattr(
        initiatives_module.pont_travail, "evenement_initiative_maj",
        _construction_impossible)

    with caplog.at_level("WARNING", logger="meridian.initiatives"):
        r = _repondre(client)

    assert r.status_code == 200, r.text
    assert "motdepasse" not in caplog.text
    assert "[redacted]" in caplog.text
    assert db.initiatives.docs[0]["statut"] == "acceptee"
