"""B3 : une décision prise dans l'interface Travail (Mongo) écrit l'objet canonique `DECISION`.

Deux niveaux : `enregistrer_decision_travail` avec un dépôt `objet_entreprise` simulé en mémoire,
et la route `POST /cases/{cid}/decisions` pour le drapeau `JUMEAU_TRAVAIL_DUAL_WRITE` et le
fail-soft Postgres.
"""
from __future__ import annotations

import asyncio
import copy
import datetime as dt
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from meridian.adapters.inbound.http import cases as cases_routes
from meridian.adapters.outbound.postgres import decision_travail
from meridian.adapters.outbound.postgres import boucle
from seed_data import ESPACES

TENANT = "local"


class DepotFaux:
    """Simule `objet_entreprise` : `{(tenant, id): ligne}` ; la connexion n'est pas utilisée."""

    def __init__(self, lignes=()):
        self.lignes = {(l["tenant_id"], l["id"]): dict(l) for l in lignes}
        self.ecrits = []

    def lire_objet(self, conn, tenant, objet_id):
        ligne = self.lignes.get((tenant, objet_id))
        return dict(ligne) if ligne is not None else None

    def lister_objets(self, conn, tenant, famille=None, type_=None, mode=None, limite=100):
        resultat = [dict(ligne) for ligne in self.lignes.values()
                    if ligne["tenant_id"] == tenant
                    and (type_ is None or ligne.get("type") == type_)]
        return resultat[:limite]

    def enregistrer_objet(self, conn, tenant, objet):
        ligne = dict(objet)
        ligne["tenant_id"] = tenant
        ligne.setdefault("donnees", {})
        self.lignes[(tenant, ligne["id"])] = ligne
        self.ecrits.append(ligne)
        return ligne


@pytest.fixture
def depot_faux(monkeypatch):
    depot = DepotFaux()
    monkeypatch.setattr(decision_travail.entreprise_depot, "lire_objet", depot.lire_objet)
    monkeypatch.setattr(decision_travail.entreprise_depot, "lister_objets", depot.lister_objets)
    monkeypatch.setattr(decision_travail.entreprise_depot, "enregistrer_objet", depot.enregistrer_objet)
    return depot


def _ligne(objet_id, type_, tenant=TENANT, donnees=None, **champs):
    familles = {"SITUATION": "emergence", "INVESTIGATION": "investigation", "DECISION": "decision"}
    return {"id": objet_id, "tenant_id": tenant, "type": type_,
            "famille": familles.get(type_, "decision"), "mode": "DECLARED",
            "titre": objet_id, "donnees": dict(donnees or {}), **champs}


def _dec(texte="Aller de l'avant", par="demo", quand="2026-02-01T10:00:00+00:00"):
    return {"texte": texte, "type": "arbitrage", "quand": quand, "par": par}


def test_sans_parent_canonique_la_decision_est_persistee_tranchee(depot_faux):
    case = {"id": "trav-1", "titre": "Refonte socle"}
    ligne = decision_travail.enregistrer_decision_travail(object(), TENANT, case, _dec())

    assert ligne["type"] == "DECISION" and ligne["famille"] == "decision"
    assert ligne["mode"] == "DECLARED"  # jamais auto-confirmée
    donnees = ligne["donnees"]
    assert donnees["statut"] == "DECIDED"
    assert donnees["acteur"] == "demo" and donnees["choix"] == "Aller de l'avant"
    assert donnees["decide_le"] == "2026-02-01T10:00:00+00:00"
    assert donnees["episode_id"] == "trav-1" and donnees["travail_id"] == "trav-1"


def test_decision_chainee_a_l_investigation_de_l_episode(depot_faux):
    depot_faux.lignes[(TENANT, "inv-1")] = _ligne(
        "inv-1", "INVESTIGATION", donnees={"episode_id": "ep-9", "situation_id": "sit-1"})
    case = {"id": "trav-1", "episode_id": "ep-9"}
    ligne = decision_travail.enregistrer_decision_travail(object(), TENANT, case, _dec())

    donnees = ligne["donnees"]
    assert donnees["investigation_id"] == "inv-1"
    assert donnees["situation_id"] == "sit-1"
    assert donnees["episode_id"] == "ep-9"  # le même identifiant que la chaîne amont
    assert donnees["travail_id"] == "trav-1"
    assert donnees["statut"] == "DECIDED" and donnees["acteur"] == "demo"
    assert donnees["choix"] == "Aller de l'avant" and "Aller de l'avant" in donnees["options"]


def test_situation_seule_ouvre_l_investigation_de_l_episode(depot_faux):
    depot_faux.lignes[(TENANT, "sit-1")] = _ligne("sit-1", "SITUATION")
    case = {"id": "trav-1", "titre": "Doublon applicatif", "situations": ["sit-1"],
            "objectif": "Comprendre le doublon"}
    ligne = decision_travail.enregistrer_decision_travail(object(), TENANT, case, _dec())

    investigation = next(l for l in depot_faux.ecrits if l["type"] == "INVESTIGATION")
    assert investigation["donnees"]["situation_id"] == "sit-1"
    assert investigation["donnees"]["episode_id"] == "trav-1"
    assert ligne["donnees"]["investigation_id"] == investigation["id"]
    assert ligne["donnees"]["episode_id"] == "trav-1"


def test_reference_explicite_dans_le_case(depot_faux):
    depot_faux.lignes[(TENANT, "inv-2")] = _ligne(
        "inv-2", "INVESTIGATION", donnees={"episode_id": "ep-2", "situation_id": "sit-9"})
    case = {"id": "trav-1", "boucle": {"investigation_id": "inv-2"}}
    ligne = decision_travail.enregistrer_decision_travail(object(), TENANT, case, _dec())

    assert ligne["donnees"]["investigation_id"] == "inv-2"
    assert ligne["donnees"]["episode_id"] == "ep-2"  # repris de l'objet canonique lié


def test_episode_id_explicite_du_case_est_repris(depot_faux):
    case = {"id": "trav-1", "episode_id": "ep-7"}
    ligne = decision_travail.enregistrer_decision_travail(object(), TENANT, case, _dec())
    assert ligne["donnees"]["episode_id"] == "ep-7"


def test_investigation_reliee_via_les_situations_du_case(depot_faux):
    depot_faux.lignes[(TENANT, "sit-1")] = _ligne("sit-1", "SITUATION")
    depot_faux.lignes[(TENANT, "inv-1")] = _ligne(
        "inv-1", "INVESTIGATION", donnees={"situation_id": "sit-1"})
    case = {"id": "trav-1", "situations": ["sit-1"]}
    ligne = decision_travail.enregistrer_decision_travail(object(), TENANT, case, _dec())

    assert ligne["donnees"]["investigation_id"] == "inv-1"
    # Aucune investigation dupliquée : seuls la décision est écrite en plus.
    assert sum(1 for l in depot_faux.ecrits if l["type"] == "INVESTIGATION") == 0


def test_les_options_du_case_nourrissent_la_decision(depot_faux):
    case = {"id": "trav-1", "options": [{"titre": "Option A"}, {"titre": "Option B"}]}
    ligne = decision_travail.enregistrer_decision_travail(
        object(), TENANT, case, _dec(texte="Option A"))
    assert ligne["donnees"]["options"] == ["Option A", "Option B"]
    assert ligne["donnees"]["choix"] == "Option A"


# --- Route POST /cases/{cid}/decisions : drapeau et fail-soft ---

class CollectionFaux:
    """Collection Mongo minimale : `find_one`, `find` et `update_one` ($set/$push)."""

    def __init__(self, docs=()):
        self.docs = [copy.deepcopy(d) for d in docs]

    def _ok(self, d, f):
        return all(d.get(k) == v for k, v in (f or {}).items())

    async def find_one(self, filtre, projection=None):
        return next((copy.deepcopy(d) for d in self.docs if self._ok(d, filtre)), None)

    def find(self, filtre, projection=None):
        lot = [d for d in self.docs if self._ok(d, filtre)]

        class Curseur:
            async def to_list(self, n):
                return lot[:n]

            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration

        return Curseur()

    async def update_one(self, filtre, maj):
        d = next((d for d in self.docs if self._ok(d, filtre)), None)
        resultat = SimpleNamespace(matched_count=0, modified_count=0, upserted_id=None)
        if d is None:
            return resultat
        for k, v in (maj.get("$set") or {}).items():
            d[k] = copy.deepcopy(v)
        for k, v in (maj.get("$push") or {}).items():
            lot = v["$each"] if isinstance(v, dict) and "$each" in v else [v]
            d.setdefault(k, []).extend(copy.deepcopy(lot))
        resultat.matched_count = resultat.modified_count = 1
        return resultat


class DbFaux:
    def __init__(self, cases):
        self.cases = CollectionFaux(cases)
        self.jumeaux = CollectionFaux()


CASE = {"id": "t1", "titre": "Socle Kafka", "responsable": "demo", "jumeaux": [],
        "conversation": [], "historique": [], "decisions": [], "maj_le": "2026-01-01"}


def resoudre_perimetre(acteur, espace_id):
    espace = next((e for e in ESPACES if e["id"] == espace_id), None) \
        or next(e for e in ESPACES if e.get("global"))
    return acteur, espace


def _client(db):
    async def rien(*a, **k):
        return None
    router = cases_routes.build_cases_router({
        "db": db, "resoudre_perimetre": resoudre_perimetre,
        "autorisations": lambda espace, ids: {},
        "journaler": rien, "notifier": rien,
        "generer_reponse_flore": rien, "slugify": lambda s: s, "NO_ID": {"_id": 0},
        "datetime": dt.datetime, "timezone": dt.timezone})
    api = APIRouter(prefix="/api")
    api.include_router(router)
    app = FastAPI()
    app.include_router(api)
    return TestClient(app)


def test_drapeau_inactif_aucune_ecriture_canonique(monkeypatch):
    monkeypatch.delenv("JUMEAU_TRAVAIL_DUAL_WRITE", raising=False)
    monkeypatch.delenv("JUMEAU_TRAVAIL_WRITE", raising=False)
    monkeypatch.setenv("JUMEAU_PG_DSN", "postgresql://x/y")
    db = DbFaux([CASE])
    import psycopg
    connexions = []
    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: connexions.append(k) or nullcontext(object()))

    rep = _client(db).post("/api/cases/t1/decisions", json={"texte": "Aller de l'avant"})

    assert rep.status_code == 201
    assert len(db.cases.docs[0]["decisions"]) == 1
    assert connexions == []


def test_drapeau_actif_ecrit_la_decision_canonique(monkeypatch, depot_faux):
    monkeypatch.setenv("JUMEAU_TRAVAIL_DUAL_WRITE", "1")
    monkeypatch.delenv("JUMEAU_TRAVAIL_WRITE", raising=False)
    monkeypatch.setenv("JUMEAU_PG_DSN", "postgresql://x/y")
    monkeypatch.delenv("JUMEAU_RLS", raising=False)
    db = DbFaux([CASE])
    import psycopg
    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: nullcontext(object()))

    rep = _client(db).post("/api/cases/t1/decisions", json={"texte": "Aller de l'avant"})

    assert rep.status_code == 201
    assert rep.json()["texte"] == "Aller de l'avant"
    assert len(depot_faux.ecrits) == 1
    ligne = depot_faux.ecrits[0]
    assert ligne["type"] == "DECISION" and ligne["donnees"]["statut"] == "DECIDED"
    assert ligne["donnees"]["episode_id"] == "t1"
    assert ligne["donnees"]["acteur"] == "demo" and ligne["donnees"]["choix"] == "Aller de l'avant"


def test_une_panne_postgres_ne_fait_pas_echouer_la_decision(monkeypatch):
    monkeypatch.setenv("JUMEAU_TRAVAIL_DUAL_WRITE", "1")
    monkeypatch.setenv("JUMEAU_PG_DSN", "postgresql://x/y")
    db = DbFaux([CASE])
    monkeypatch.setattr(
        decision_travail, "enregistrer_decision_travail",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("Postgres indisponible")))
    import psycopg
    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: nullcontext(object()))

    rep = _client(db).post("/api/cases/t1/decisions", json={"texte": "Aller de l'avant"})

    assert rep.status_code == 201
    assert db.cases.docs[0]["decisions"][-1]["texte"] == "Aller de l'avant"
