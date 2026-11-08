"""Journal d'épisodes D1 : écriture via enregistrer_boucle, immuabilité, lecture HTTP et fail-soft."""
import psycopg
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from meridian.adapters.inbound.http import boucle as boucle_routes
from meridian.adapters.outbound.postgres import boucle
from meridian.adapters.outbound.postgres import journal_episodes
from meridian.tests.conftest import besoin_pg

TENANT = "banque"
AUTRE_TENANT = "assurance"
DATES = {
    "cree_le": "2026-10-01T08:00:00+00:00",
    "observe_le": "2026-10-02T09:00:00+00:00",
    "valide_depuis": "2026-10-02T09:00:00+00:00",
}


def situation(identifiant="sit-1", tenant=TENANT, titre="Délai de traitement en hausse", **champs):
    valeurs = {**DATES, "id": identifiant, "tenant_id": tenant, "titre": titre,
               "resume": "Le délai dépasse la cible"}
    valeurs.update(champs)
    return boucle.Situation(**valeurs)


def chaine(prefixe="je", tenant=TENANT):
    sit = situation(f"sit-{prefixe}", tenant=tenant)
    investigation = boucle.ouvrir_investigation(
        sit, id=f"inv-{prefixe}", titre="Comprendre le délai", question="Pourquoi 12 jours ?")
    proposition = boucle.proposer_decision(
        investigation, ["Automatiser", "Réorganiser"], id=f"dec-{prefixe}")
    decision = boucle.trancher_decision(proposition, "comité-cartes", "Automatiser")
    initiative = boucle.lancer_initiative(decision, id=f"ini-{prefixe}")
    outcome = boucle.mesurer_outcome(
        initiative, {"metrique": "delai", "valeur": 4.2}, id=f"out-{prefixe}")
    learning = boucle.capitaliser_learning(
        outcome, id=f"lea-{prefixe}", enonce="Automatiser réduit le délai")
    return sit, investigation, decision, initiative, outcome, learning


class _ConnexionPartagee:
    """Rend la connexion du test sans la fermer à la sortie du ``with`` de la route."""

    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *_):
        return False


def _client(monkeypatch, conn):
    monkeypatch.setenv("JUMEAU_PG_DSN", "postgresql://test/test")
    monkeypatch.setattr(
        boucle_routes.psycopg, "connect", lambda *_, **__: _ConnexionPartagee(conn))
    app = FastAPI()
    api = APIRouter(prefix="/api")
    api.include_router(boucle_routes.router)
    app.include_router(api)
    return TestClient(app)


@besoin_pg
def test_enregistrer_boucle_consigne_les_evenements_dans_l_ordre(conn):
    *objets, learning = chaine()
    boucle.enregistrer_boucle(conn, TENANT, [*objets, learning])

    evenements = journal_episodes.lire_episode(conn, TENANT, f"sit-je")
    assert [e["objet_type"] for e in evenements] == [
        "SITUATION", "INVESTIGATION", "DECISION", "INITIATIVE", "OUTCOME", "LEARNING"]
    assert {e["episode_id"] for e in evenements} == {"sit-je"}
    assert {e["action"] for e in evenements} == {"cree"}
    assert all(e["tenant_id"] == TENANT for e in evenements)
    # le lien causal de chaque événement pointe la source de l'objet
    par_type = {e["objet_type"]: e for e in evenements}
    assert par_type["INVESTIGATION"]["donnees"]["lien_cause"] == "sit-je"
    assert par_type["OUTCOME"]["donnees"]["lien_cause"] == "ini-je"
    assert par_type["DECISION"]["acteur"] == "comité-cartes"


@besoin_pg
def test_re_ecriture_dun_objet_consigne_une_transition(conn):
    sit = situation("sit-tr")
    boucle.enregistrer_boucle(conn, TENANT, sit)
    revue = situation("sit-tr", titre="Délai revu")
    boucle.enregistrer_boucle(conn, TENANT, revue)

    evenements = journal_episodes.lire_episode(conn, TENANT, "sit-tr")
    assert [e["action"] for e in evenements] == ["cree", "transition"]
    assert {e["objet_id"] for e in evenements} == {"sit-tr"}


@besoin_pg
def test_episode_id_explicite_est_repris(conn):
    sit = situation("sit-ep")
    investigation = boucle.ouvrir_investigation(
        sit, id="inv-ep", question="Pourquoi ?", episode_id="ep-9")
    boucle.enregistrer_boucle(conn, TENANT, [sit, investigation])

    assert [e["objet_id"] for e in journal_episodes.lire_episode(conn, TENANT, "ep-9")] == ["inv-ep"]
    assert [e["objet_id"] for e in journal_episodes.lire_episode(conn, TENANT, "sit-ep")] == ["sit-ep"]


@besoin_pg
def test_evenement_episode_est_append_only(conn):
    statut = journal_episodes.consigner(conn, TENANT, {
        "episode_id": "ep-1", "objet_type": "SITUATION", "objet_id": "sit-1", "action": "cree"})
    assert statut["statut"] == "ok" and statut["insere"] is True

    with pytest.raises(psycopg.Error):
        conn.execute("UPDATE evenement_episode SET action = 'modifie'")
    with pytest.raises(psycopg.Error):
        conn.execute("DELETE FROM evenement_episode")
    # la ligne est intacte et la connexion reste saine (autocommit : chaque ordre est borné)
    assert len(journal_episodes.lire_episode(conn, TENANT, "ep-1")) == 1


@besoin_pg
def test_consigner_refuse_un_evenement_invalide(conn):
    assert journal_episodes.consigner(conn, TENANT, {"objet_id": "x"})["statut"] == "refuse"
    assert journal_episodes.consigner(
        conn, TENANT, "pas-un-mapping")["statut"] == "refuse"
    assert journal_episodes.consigner(conn, "  ", {
        "episode_id": "ep", "objet_type": "SITUATION", "objet_id": "s", "action": "cree"
    })["statut"] == "refuse"


@besoin_pg
def test_erreur_insert_ne_casse_ni_connexion_ni_boucle(conn, monkeypatch):
    # une erreur de base est contenue : la connexion reste saine
    conn.execute("ALTER TABLE evenement_episode DROP COLUMN objet_type")
    statut = journal_episodes.consigner(conn, TENANT, {
        "episode_id": "ep-1", "objet_type": "SITUATION", "objet_id": "sit-1", "action": "cree"})
    assert statut["statut"] == "erreur" and statut["insere"] is False
    assert conn.execute("SELECT 1").fetchone() == (1,)

    # et une défaillance du journal ne bloque jamais enregistrer_boucle
    def exploser(*_args, **_kwargs):
        raise RuntimeError("journal en panne")

    monkeypatch.setattr(journal_episodes, "consigner", exploser)
    sit = situation("sit-fail")
    stocke = boucle.enregistrer_boucle(conn, TENANT, sit)
    assert stocke["id"] == "sit-fail"
    assert boucle.lire_boucle(conn, TENANT, "sit-fail") is not None


@besoin_pg
def test_episodes_groupes_et_bornes_au_tenant(conn):
    sit_a, inv_a, *_ = chaine(prefixe="ga", tenant=TENANT)
    boucle.enregistrer_boucle(conn, TENANT, [sit_a, inv_a])
    sit_b = situation("sit-gb", tenant=AUTRE_TENANT)
    boucle.enregistrer_boucle(conn, AUTRE_TENANT, sit_b)

    groupes = journal_episodes.episodes(conn, TENANT)
    assert [g["episode_id"] for g in groupes] == ["sit-ga"]
    assert groupes[0]["evenements"] == 2
    assert groupes[0]["premier"] <= groupes[0]["dernier"]
    assert journal_episodes.lire_episode(conn, AUTRE_TENANT, "sit-ga") == []


@besoin_pg
def test_get_episodes_est_borne_au_tenant(conn, monkeypatch):
    client = _client(monkeypatch, conn)
    sit_a, inv_a, *_ = chaine(prefixe="ha", tenant=TENANT)
    boucle.enregistrer_boucle(conn, TENANT, [sit_a, inv_a])
    boucle.enregistrer_boucle(conn, AUTRE_TENANT, situation("sit-hb", tenant=AUTRE_TENANT))

    reponse = client.get("/api/boucle/episodes", headers={"X-Tenant": TENANT})
    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["tenant"] == TENANT
    assert [g["episode_id"] for g in corps["episodes"]] == ["sit-ha"]

    reponse = client.get("/api/boucle/episodes/sit-ha", headers={"X-Tenant": TENANT})
    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["episode"] == "sit-ha"
    assert [e["objet_type"] for e in corps["evenements"]] == ["SITUATION", "INVESTIGATION"]

    # un épisode d'un autre tenant est invisible : 404, jamais de fuite
    assert client.get(
        "/api/boucle/episodes/sit-hb", headers={"X-Tenant": TENANT}).status_code == 404
    assert client.get("/api/boucle/episodes/inconnu", headers={"X-Tenant": TENANT}).status_code == 404
