"""Scénarios canoniques : orchestration applicative, API HTTP et comparaison.

Les tests de commande utilisent un magasin en mémoire qui satisfait la surface du port
``BoucleStore``. Les tests HTTP remplacent uniquement les commandes et la connexion
Postgres : ils vérifient le contrat public, les validations et les traductions d'erreurs.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass

import psycopg
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from meridian.adapters.inbound.http import boucle as boucle_routes
from meridian.adapters.outbound.postgres import boucle
from meridian.application import commandes_boucle
from meridian.domain import construction_objets_exploitation
from meridian.domain.objets_exploitation import ObjetsExploitationInvalide
from meridian.ports.boucle import ObjetInvalide

TENANT = "local"
AUTRE_TENANT = "banque"
BASE = "/api/boucle"
CHAMPS = {
    "id", "tenant_id", "famille", "type", "mode", "titre", "version",
    "observe_le", "valide_depuis", "valide_jusqua", "cree_le", "maj_le",
}


def _ligne(objet) -> dict:
    donn = asdict(objet) if is_dataclass(objet) else dict(objet)
    ligne = {cle: copy.deepcopy(donn[cle]) for cle in CHAMPS if cle in donn}
    ligne.setdefault("famille", "decision")
    ligne.setdefault("mode", "PROPOSED")
    ligne.setdefault("version", 1)
    ligne["donnees"] = {
        cle: copy.deepcopy(valeur)
        for cle, valeur in donn.items()
        if cle not in CHAMPS
    }
    return ligne


def _parent(type_: str, identifiant: str, *, tenant: str = TENANT, **donnees) -> dict:
    famille = {
        "INVESTIGATION": "investigation",
        "DECISION": "decision",
    }[type_]
    if type_ == "INVESTIGATION":
        donnees.setdefault("situation_id", "sit-1")
    if type_ == "DECISION":
        donnees.setdefault("investigation_id", "inv-1")
    return {
        "id": identifiant,
        "tenant_id": tenant,
        "famille": famille,
        "type": type_,
        "mode": "DECLARED",
        "titre": f"{type_.capitalize()} {identifiant}",
        "donnees": copy.deepcopy(donnees),
        "version": 1,
    }


def _scenario_row(
    identifiant: str = "scenario-1",
    *,
    investigation_id: str | None = "inv-1",
    decision_id: str | None = None,
    titre: str = "Scénario",
    **donnees,
) -> dict:
    valeurs = {
        "investigation_id": investigation_id,
        "decision_id": decision_id,
        "titre": titre,
        "description": "",
        "statut": "DRAFT",
        "valeur_estimee": None,
        "cout_estime": None,
        "delai_jours": None,
        "risque": None,
        "reversibilite": "REVERSIBLE",
        "complexite": None,
    }
    valeurs.update(donnees)
    return {
        "id": identifiant,
        "tenant_id": TENANT,
        "famille": "decision",
        "type": "SCENARIO",
        "mode": "PROPOSED",
        "titre": titre,
        "donnees": valeurs,
        "version": 1,
    }


class _Store:
    """Port Boucle minimal, avec les liens inverses que l'adaptateur réel maintient."""

    def __init__(self, objets=None):
        self.objets = {
            objet["id"]: copy.deepcopy(objet) for objet in (objets or [])
        }
        self.enregistres = []
        self.derniere_liste = None

    @contextmanager
    def transaction(self, conn):
        yield

    def lire_boucle(
        self, conn, tenant_id, objet_id, *, historique=False, as_dict=True,
        for_update=False,
    ):
        objet = self.objets.get(objet_id)
        if objet is None or objet.get("tenant_id") != tenant_id:
            return None
        resultat = copy.deepcopy(objet)
        if historique:
            chaine = []
            if resultat.get("type") == "SCENARIO":
                for cle in ("investigation_id", "decision_id"):
                    parent_id = (resultat.get("donnees") or {}).get(cle)
                    parent = self.objets.get(parent_id)
                    if parent is not None:
                        chaine.append(copy.deepcopy(parent))
            chaine.append(resultat)
            resultat["chaine"] = chaine
            resultat["historique"] = []
        return resultat

    def nouveau_scenario(self, **champs):
        return construction_objets_exploitation.nouveau_scenario(**champs)

    def enregistrer_objets(
        self, conn, tenant_id=None, objets=None, *, historique=False, as_dict=True,
    ):
        objets = list(objets or [])
        self.enregistres.extend(copy.deepcopy(objets))
        for objet in objets:
            ligne = _ligne(objet)
            self.objets[ligne["id"]] = ligne
            if ligne["type"] == "SCENARIO":
                investigation_id = ligne["donnees"].get("investigation_id")
                decision_id = ligne["donnees"].get("decision_id")
                if investigation_id and investigation_id in self.objets:
                    donnees = self.objets[investigation_id].setdefault("donnees", {})
                    ids = list(donnees.get("scenario_ids") or [])
                    if ligne["id"] not in ids:
                        ids.append(ligne["id"])
                    donnees["scenario_ids"] = ids
                if decision_id and decision_id in self.objets:
                    donnees = self.objets[decision_id].setdefault("donnees", {})
                    ids = list(donnees.get("scenario_ids") or [])
                    if ligne["id"] not in ids:
                        ids.append(ligne["id"])
                    donnees["scenario_ids"] = ids
                    donnees.setdefault("scenario_id", ligne["id"])
        return objets if not as_dict else [_ligne(objet) for objet in objets]

    def lister_objets_exploitation(
        self, conn, tenant_id, *, type_=None, investigation_id=None,
        decision_id=None, limite=100, as_dict=True,
    ):
        self.derniere_liste = {
            "tenant_id": tenant_id,
            "type_": type_,
            "investigation_id": investigation_id,
            "decision_id": decision_id,
            "limite": limite,
        }
        resultat = []
        for objet in self.objets.values():
            if objet.get("tenant_id") != tenant_id:
                continue
            if type_ and objet.get("type") != type_:
                continue
            donnees = objet.get("donnees") or {}
            if investigation_id and donnees.get("investigation_id") != investigation_id:
                continue
            if decision_id and donnees.get("decision_id") != decision_id:
                continue
            resultat.append(copy.deepcopy(objet))
        return resultat[:limite]


class _Connexion:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


# --------------------------------------------------------------------------- #
# Commandes
# --------------------------------------------------------------------------- #


def test_creer_scenario_lie_a_une_investigation_et_met_a_jour_le_parent():
    store = _Store([
        _parent("INVESTIGATION", "inv-1"),
        {
            "id": "hyp-1", "tenant_id": TENANT, "famille": "investigation",
            "type": "HYPOTHESIS", "mode": "PROPOSED", "titre": "Hypothèse",
            "donnees": {"investigation_id": "inv-1"}, "version": 1,
        },
    ])

    resultat = commandes_boucle.creer_scenario(
        store, _Connexion(), TENANT,
        titre="Automatiser la pièce",
        description="Supprimer la ressaisie",
        investigation_id="inv-1",
        valeur_estimee=12000,
        cout_estime=4500,
        delai_jours=30,
        risque=0.2,
        hypothesis_ids=["hyp-1"],
        actions=["Automatiser", "Contrôler"],
    )

    assert resultat.objet["type"] == "SCENARIO"
    assert resultat.objet["titre"] == "Automatiser la pièce"
    assert resultat.objet["donnees"]["investigation_id"] == "inv-1"
    assert resultat.objet["donnees"]["valeur_estimee"] == 12000.0
    assert store.objets["inv-1"]["donnees"]["scenario_ids"] == [resultat.objet["id"]]
    assert [element["type"] for element in resultat.chaine] == ["INVESTIGATION", "SCENARIO"]
    assert resultat.chaine[0]["donnees"]["scenario_ids"] == [resultat.objet["id"]]


def test_creer_scenario_lie_a_une_decision_et_pose_le_lien_inverse():
    store = _Store([_parent("DECISION", "dec-1")])

    resultat = commandes_boucle.creer_scenario(
        store, _Connexion(), TENANT,
        titre="Réorganiser",
        decision_id="dec-1",
        reversibilite="PARTIELLE",
    )

    assert resultat.objet["donnees"]["decision_id"] == "dec-1"
    assert store.objets["dec-1"]["donnees"]["scenario_id"] == resultat.objet["id"]
    assert store.objets["dec-1"]["donnees"]["scenario_ids"] == [resultat.objet["id"]]
    assert [element["type"] for element in resultat.chaine] == ["DECISION", "SCENARIO"]


def test_creer_scenario_avec_les_deux_parents_met_a_jour_les_deux_liens():
    store = _Store([
        _parent("INVESTIGATION", "inv-1"),
        _parent("DECISION", "dec-1", investigation_id="inv-1"),
    ])

    resultat = commandes_boucle.creer_scenario(
        store, _Connexion(), TENANT,
        titre="Scénario complet",
        investigation_id="inv-1",
        decision_id="dec-1",
        statut="PROPOSED",
        complexite=0.4,
    )

    assert store.objets["inv-1"]["donnees"]["scenario_ids"] == [resultat.objet["id"]]
    assert store.objets["dec-1"]["donnees"]["scenario_id"] == resultat.objet["id"]
    assert store.objets["dec-1"]["donnees"]["scenario_ids"] == [resultat.objet["id"]]
    assert [element["type"] for element in resultat.chaine] == [
        "INVESTIGATION", "DECISION", "SCENARIO",
    ]


def test_plusieurs_scenarios_peuvent_comparer_une_meme_decision():
    store = _Store([_parent("DECISION", "dec-1")])

    premier = commandes_boucle.creer_scenario(
        store, _Connexion(), TENANT, titre="Automatiser", decision_id="dec-1")
    second = commandes_boucle.creer_scenario(
        store, _Connexion(), TENANT, titre="Réorganiser", decision_id="dec-1")

    assert store.objets["dec-1"]["donnees"]["scenario_ids"] == [
        premier.objet["id"], second.objet["id"],
    ]
    assert store.objets["dec-1"]["donnees"]["scenario_id"] == premier.objet["id"]
    comparison = commandes_boucle.comparer_scenarios(
        store, _Connexion(), TENANT,
        [premier.objet["id"], second.objet["id"]],
    )
    assert [scenario["titre"] for scenario in comparison["scenarios"]] == [
        "Automatiser", "Réorganiser",
    ]


def test_scenario_est_un_type_canonique_de_la_famille_decision():
    from meridian.domain import modele_entreprise as modele

    assert "SCENARIO" in modele.TYPES_OBJET
    assert modele.famille_de("SCENARIO") == "decision"


def test_decision_canonique_porte_scenario_ids_et_scenario_id():
    decision = boucle.Decision(
        id="dec-1", tenant_id=TENANT, investigation_id="inv-1",
        statut="PROPOSED", scenario_id="s1", scenario_ids=["s2"],
    )
    assert decision.scenario_ids == ["s2", "s1"]
    assert decision.scenario_id == "s1"
    assert decision.liens["scenario_ids"] == ["s2", "s1"]


def test_creer_scenario_refuse_une_decision_d_un_autre_investigation():
    store = _Store([
        _parent("INVESTIGATION", "inv-1"),
        _parent("INVESTIGATION", "inv-2"),
        _parent("DECISION", "dec-2", investigation_id="inv-2"),
    ])

    with pytest.raises(commandes_boucle.TransitionRefusee):
        commandes_boucle.creer_scenario(
            store, _Connexion(), TENANT, titre="Incohérent",
            investigation_id="inv-1", decision_id="dec-2")

    assert all(
        objet.get("type") != "SCENARIO" for objet in store.objets.values())
    assert store.objets["inv-1"]["donnees"].get("scenario_ids") is None
    assert store.objets["dec-2"]["donnees"].get("scenario_id") is None


def test_nouveau_scenario_refuse_la_meme_incoherence_au_domaine():
    with pytest.raises(ObjetsExploitationInvalide):
        construction_objets_exploitation.nouveau_scenario(
            investigation=_parent("INVESTIGATION", "inv-1"),
            decision=_parent("DECISION", "dec-2", investigation_id="inv-2"),
            titre="Incohérent",
        )


def test_creer_scenario_refuse_une_hypothese_d_une_autre_investigation():
    store = _Store([
        _parent("INVESTIGATION", "inv-1"),
        {
            "id": "hyp-autre",
            "tenant_id": TENANT,
            "famille": "investigation",
            "type": "HYPOTHESIS",
            "mode": "PROPOSED",
            "titre": "Hypothèse",
            "donnees": {"investigation_id": "inv-2"},
            "version": 1,
        },
    ])

    with pytest.raises(commandes_boucle.TransitionRefusee):
        commandes_boucle.creer_scenario(
            store, _Connexion(), TENANT, titre="Hypothèse invalide",
            investigation_id="inv-1", hypothesis_ids=["hyp-autre"])


def test_creer_scenario_exige_au_moins_un_parent():
    with pytest.raises(commandes_boucle.TransitionRefusee):
        commandes_boucle.creer_scenario(
            _Store(), _Connexion(), TENANT, titre="Sans parent")


def test_creer_scenario_parent_absent_ou_hors_tenant_est_introuvable():
    store = _Store([
        _parent("INVESTIGATION", "inv-autre", tenant=AUTRE_TENANT),
        _parent("DECISION", "dec-1"),
    ])

    for champs in (
        {"investigation_id": "inv-absent"},
        {"investigation_id": "inv-autre"},
        {"decision_id": "dec-absent"},
    ):
        with pytest.raises(commandes_boucle.SourceIntrouvable):
            commandes_boucle.creer_scenario(
                store, _Connexion(), TENANT, titre="Introuvable", **champs)


def test_lister_scenarios_filtre_par_parent_et_normalise_les_metriques():
    store = _Store([
        _scenario_row("s1", investigation_id="inv-1", valeur_estimee=10, cout_estime=5),
        _scenario_row("s2", investigation_id="inv-2"),
        _parent("DECISION", "dec-1"),
        _scenario_row("s3", investigation_id=None, decision_id="dec-1", risque=0.3),
    ])

    resultat = commandes_boucle.lister_scenarios(
        store, _Connexion(), TENANT, investigation_id="inv-1", limite=10)

    assert store.derniere_liste == {
        "tenant_id": TENANT,
        "type_": "SCENARIO",
        "investigation_id": "inv-1",
        "decision_id": None,
        "limite": 10,
    }
    assert [scenario["id"] for scenario in resultat] == ["s1"]
    assert resultat[0]["valeur_estimee"] == 10.0
    assert resultat[0]["cout_estime"] == 5.0
    assert resultat[0]["reversibilite"] == "REVERSIBLE"


def _store_comparaison():
    return _Store([
        _scenario_row(
            "s1", valeur_estimee=100, cout_estime=50, delai_jours=10,
            risque=0.2, complexite=0.4, reversibilite="REVERSIBLE"),
        _scenario_row(
            "s2", valeur_estimee=120, cout_estime=None, delai_jours=8,
            risque=0.3, complexite=0.5, reversibilite="PARTIELLE"),
        _scenario_row(
            "s3", valeur_estimee=80, cout_estime=70, delai_jours=15,
            risque=None, complexite=0.2, reversibilite="IRREVERSIBLE"),
    ])


def test_comparer_deux_scenarios_calcule_les_ecarts_et_les_none():
    resultat = commandes_boucle.comparer_scenarios(
        _store_comparaison(), _Connexion(), TENANT, ["s1", "s2"])

    assert resultat["reference"]["id"] == "s1"
    assert [scenario["id"] for scenario in resultat["scenarios"]] == ["s1", "s2"]
    reference, compare = resultat["scenarios"]
    assert reference["ecarts"]["valeur_estimee"] == {
        "delta": 0.0, "delta_pct": 0.0, "sens": "identique",
    }
    assert compare["ecarts"]["valeur_estimee"] == {
        "delta": 20.0, "delta_pct": 20.0, "sens": "hausse",
    }
    assert compare["ecarts"]["delai_jours"] == {
        "delta": -2.0, "delta_pct": -20.0, "sens": "baisse",
    }
    assert compare["ecarts"]["cout_estime"] == {
        "delta": None, "delta_pct": None, "sens": None,
    }
    assert compare["ecarts"]["reversibilite"] == {
        "reference": "REVERSIBLE", "scenario": "PARTIELLE", "identique": False,
    }


def test_comparer_trois_scenarios_et_reference_explicite():
    resultat = commandes_boucle.comparer_scenarios(
        _store_comparaison(), _Connexion(), TENANT, ["s1", "s2", "s3"],
        reference_id="s2")

    assert resultat["reference"]["id"] == "s2"
    assert [scenario["id"] for scenario in resultat["scenarios"]] == ["s1", "s2", "s3"]
    assert resultat["scenarios"][0]["ecarts"]["valeur_estimee"]["delta"] == -20.0
    assert resultat["scenarios"][2]["ecarts"]["risque"] == {
        "delta": None, "delta_pct": None, "sens": None,
    }


def test_comparer_une_reference_nulle_ne_divisionne_pas_par_zero():
    store = _Store([
        _scenario_row("s1", valeur_estimee=0),
        _scenario_row("s2", valeur_estimee=10),
    ])

    resultat = commandes_boucle.comparer_scenarios(
        store, _Connexion(), TENANT, ["s1", "s2"])

    ecart = resultat["scenarios"][1]["ecarts"]["valeur_estimee"]
    assert ecart["delta"] == 10.0
    assert ecart["delta_pct"] is None
    assert ecart["sens"] == "hausse"


def test_lister_et_comparer_ne_traversent_pas_le_tenant():
    store = _Store([
        {**_scenario_row("s-autre"), "tenant_id": AUTRE_TENANT},
        _scenario_row("s-local"),
    ])

    assert [scenario["id"] for scenario in commandes_boucle.lister_scenarios(
        store, _Connexion(), TENANT)] == ["s-local"]
    with pytest.raises(commandes_boucle.SourceIntrouvable):
        commandes_boucle.comparer_scenarios(
            store, _Connexion(), TENANT, ["s-local", "s-autre"])


def test_resume_scenario_ne_fabrique_pas_de_valeurs_categoriques_absentes():
    row = {"id": "s1", "titre": "Sans catégories", "donnees": {}}
    resume = commandes_boucle._resume_scenario(row)
    assert resume["statut"] is None
    assert resume["reversibilite"] is None

    store = _Store([
        {**row, "tenant_id": TENANT, "famille": "decision", "type": "SCENARIO", "version": 1},
        {"id": "s2", "titre": "Autre", "tenant_id": TENANT, "famille": "decision",
         "type": "SCENARIO", "donnees": {}, "version": 1},
    ])
    resultat = commandes_boucle.comparer_scenarios(
        store, _Connexion(), TENANT, ["s1", "s2"])
    assert resultat["scenarios"][1]["ecarts"]["statut"]["identique"] is None
    assert resultat["scenarios"][1]["ecarts"]["reversibilite"]["identique"] is None


def test_comparer_refuse_moins_de_deux_ids_les_doublons_et_les_absents():
    store = _store_comparaison()
    for ids in (["s1"], []):
        with pytest.raises(commandes_boucle.TransitionRefusee):
            commandes_boucle.comparer_scenarios(store, _Connexion(), TENANT, ids)
    with pytest.raises(commandes_boucle.TransitionRefusee):
        commandes_boucle.comparer_scenarios(
            store, _Connexion(), TENANT, ["s1", "s1"])
    with pytest.raises(commandes_boucle.SourceIntrouvable):
        commandes_boucle.comparer_scenarios(
            store, _Connexion(), TENANT, ["s1", "absent"])


def test_comparer_refuse_un_objet_qui_n_est_pas_un_scenario():
    store = _Store([
        _scenario_row("s1"),
        _parent("DECISION", "dec-1"),
    ])
    with pytest.raises(commandes_boucle.SourceIntrouvable):
        commandes_boucle.comparer_scenarios(
            store, _Connexion(), TENANT, ["s1", "dec-1"])


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #


def _app() -> TestClient:
    app = FastAPI()
    api = APIRouter(prefix="/api")
    api.include_router(boucle_routes.router)
    app.include_router(api)
    return TestClient(app)


def _client(monkeypatch) -> TestClient:
    monkeypatch.delenv("AUTH_MODE", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("JUMEAU_PG_DSN", "postgresql://test/test")
    monkeypatch.setattr(boucle_routes.psycopg, "connect", lambda *_, **__: _Connexion())
    return _app()


def _resultat_scenario(identifiant="scenario-1") -> commandes_boucle.ResultatTransition:
    objet = _scenario_row(identifiant)
    situation = {
        "id": "sit-1", "tenant_id": TENANT, "famille": "emergence",
        "type": "SITUATION", "mode": "OBSERVED", "titre": "Situation",
        "donnees": {}, "version": 1,
    }
    return commandes_boucle.ResultatTransition(
        objet=objet,
        chaine=[
            situation,
            _parent("INVESTIGATION", "inv-1"),
            _parent("DECISION", "dec-1"),
            objet,
        ],
        historique=[],
    )


def test_post_scenario_retourne_le_contrat_de_creation(monkeypatch):
    client = _client(monkeypatch)
    appels = []

    def creer(depot, conn, tenant, **champs):
        appels.append((tenant, champs))
        return _resultat_scenario()

    monkeypatch.setattr(boucle_routes.commandes_boucle, "creer_scenario", creer)

    reponse = client.post(f"{BASE}/scenarios", json={
        "titre": "Automatiser la pièce",
        "description": "Supprimer la ressaisie",
        "investigation_id": "inv-1",
        "hypothesis_ids": ["hyp-1"],
        "actions": ["Automatiser"],
        "valeur_estimee": 12000,
        "cout_estime": 4500,
        "delai_jours": 30,
        "risque": 0.2,
        "reversibilite": "PARTIELLE",
        "statut": "PROPOSED",
        "preuves": ["preuve-1"],
        "confiance": 0.8,
    })

    assert reponse.status_code == 201
    corps = reponse.json()
    assert corps["tenant"] == TENANT
    assert corps["objet"]["type"] == "SCENARIO"
    assert corps["type"] == "SCENARIO"
    assert corps["role"] == "scenario"
    assert [element["type"] for element in corps["chaine"]] == [
        "SITUATION", "INVESTIGATION", "DECISION", "SCENARIO",
    ]
    assert corps["idempotency_key"] is None
    assert appels[0][0] == TENANT
    assert appels[0][1]["investigation_id"] == "inv-1"
    assert appels[0][1]["valeur_estimee"] == 12000


@pytest.mark.parametrize("corps", [
    {"titre": "Sans parent"},
    {"titre": ""},
    {"description": "Description seule"},
    {"titre": "Parent vide", "investigation_id": "   "},
    {"titre": "Nombre invalide", "investigation_id": "inv-1", "risque": 2},
    {"titre": "Délai négatif", "investigation_id": "inv-1", "delai_jours": -1},
])
def test_post_scenario_valide_le_corps_avant_la_base(monkeypatch, corps):
    client = _client(monkeypatch)
    monkeypatch.setattr(
        boucle_routes.commandes_boucle, "creer_scenario",
        lambda *_, **__: pytest.fail("la commande ne doit pas être appelée"),
    )
    assert client.post(f"{BASE}/scenarios", json=corps).status_code == 422


def test_post_scenario_incoherent_est_refuse_en_409(monkeypatch):
    client = _client(monkeypatch)

    def refuser(*_, **__):
        raise commandes_boucle.TransitionRefusee(
            "la décision appartient à une autre investigation")

    monkeypatch.setattr(boucle_routes.commandes_boucle, "creer_scenario", refuser)
    reponse = client.post(f"{BASE}/scenarios", json={
        "titre": "Incohérent", "investigation_id": "inv-1", "decision_id": "dec-2"})
    assert reponse.status_code == 409
    assert "autre investigation" in reponse.json()["detail"]


def test_post_scenario_refuse_une_cle_d_idempotence(monkeypatch):
    client = _client(monkeypatch)
    reponse = client.post(
        f"{BASE}/scenarios",
        json={"titre": "Scénario", "investigation_id": "inv-1"},
        headers={"Idempotency-Key": "cle-1"},
    )
    assert reponse.status_code == 501


def test_post_comparer_refuse_une_cle_d_idempotence(monkeypatch):
    client = _client(monkeypatch)
    reponse = client.post(
        f"{BASE}/scenarios/comparer",
        json={"scenario_ids": ["s1", "s2"]},
        headers={"Idempotency-Key": "cle-1"},
    )
    assert reponse.status_code == 501


def test_get_scenarios_accepte_un_filtre_vide(monkeypatch):
    client = _client(monkeypatch)
    appels = []

    def lister(depot, conn, tenant, **champs):
        appels.append(champs)
        return []

    monkeypatch.setattr(boucle_routes.commandes_boucle, "lister_scenarios", lister)
    reponse = client.get(f"{BASE}/scenarios", params={
        "investigation_id": "  ", "decision_id": ""})

    assert reponse.status_code == 200
    assert reponse.json()["scenarios"] == []
    assert appels == [{"investigation_id": "  ", "decision_id": "", "limite": 100}]


@pytest.mark.parametrize(("erreur", "statut"), [
    (commandes_boucle.SourceIntrouvable("investigation", "inv-x"), 404),
    (commandes_boucle.TransitionRefusee("transition refusée"), 409),
    (ObjetsExploitationInvalide("scénario invalide"), 422),
    (ObjetInvalide("objet invalide"), 400),
    (psycopg.OperationalError("panne"), 503),
])
def test_post_scenario_traduit_les_erreurs(monkeypatch, erreur, statut):
    client = _client(monkeypatch)

    def echouer(*_, **__):
        raise erreur

    monkeypatch.setattr(boucle_routes.commandes_boucle, "creer_scenario", echouer)
    reponse = client.post(f"{BASE}/scenarios", json={
        "titre": "Scénario", "investigation_id": "inv-1"})
    assert reponse.status_code == statut


def test_get_scenarios_filtre_et_serialise(monkeypatch):
    client = _client(monkeypatch)
    appels = []

    def lister(depot, conn, tenant, **champs):
        appels.append((tenant, champs))
        return [commandes_boucle._resume_scenario(_scenario_row(
            "s1", valeur_estimee=10, cout_estime=5))]

    monkeypatch.setattr(boucle_routes.commandes_boucle, "lister_scenarios", lister)
    reponse = client.get(
        f"{BASE}/scenarios",
        params={"investigation_id": "inv-1", "limite": 25},
    )

    assert reponse.status_code == 200
    assert reponse.json()["tenant"] == TENANT
    assert [scenario["id"] for scenario in reponse.json()["scenarios"]] == ["s1"]
    assert reponse.json()["scenarios"][0]["valeur_estimee"] == 10.0
    assert appels[0][1] == {
        "investigation_id": "inv-1", "decision_id": None, "limite": 25,
    }


def test_post_comparer_scenarios_retourne_la_reference_et_les_ecarts(monkeypatch):
    client = _client(monkeypatch)
    appels = []
    resultat = commandes_boucle.comparer_scenarios(
        _store_comparaison(), _Connexion(), TENANT, ["s1", "s2"], reference_id="s2")

    def comparer(depot, conn, tenant, scenario_ids, reference_id=None):
        appels.append((tenant, scenario_ids, reference_id))
        return resultat

    monkeypatch.setattr(boucle_routes.commandes_boucle, "comparer_scenarios", comparer)
    reponse = client.post(f"{BASE}/scenarios/comparer", json={
        "scenario_ids": ["s1", "s2"], "reference_id": "s2"})

    assert reponse.status_code == 200
    assert reponse.json()["reference"]["id"] == "s2"
    assert [scenario["id"] for scenario in reponse.json()["scenarios"]] == ["s1", "s2"]
    assert appels == [(TENANT, ["s1", "s2"], "s2")]


def test_post_comparer_traduit_un_scenario_absent_en_404(monkeypatch):
    client = _client(monkeypatch)

    def echouer(*_, **__):
        raise commandes_boucle.SourceIntrouvable("scénario", "absent")

    monkeypatch.setattr(boucle_routes.commandes_boucle, "comparer_scenarios", echouer)
    reponse = client.post(f"{BASE}/scenarios/comparer", json={
        "scenario_ids": ["s1", "absent"]})
    assert reponse.status_code == 404


@pytest.mark.parametrize("corps", [
    {"scenario_ids": ["s1"]},
    {"scenario_ids": []},
    {"scenario_ids": ["s1", "s1"]},
    {"scenario_ids": ["s1", "s2"], "reference_id": "s3"},
    {"scenario_ids": ["s1", "s2"], "reference_id": "s1", "inconnu": True},
])
def test_post_comparer_valide_le_corps(monkeypatch, corps):
    client = _client(monkeypatch)
    monkeypatch.setattr(
        boucle_routes.commandes_boucle, "comparer_scenarios",
        lambda *_, **__: pytest.fail("la commande ne doit pas être appelée"),
    )
    assert client.post(f"{BASE}/scenarios/comparer", json=corps).status_code == 422


@pytest.mark.parametrize(("methode", "chemin", "corps"), [
    ("get", f"{BASE}/scenarios", None),
    ("post", f"{BASE}/scenarios", {"titre": "Scénario", "investigation_id": "inv-1"}),
    ("post", f"{BASE}/scenarios/comparer", {"scenario_ids": ["s1", "s2"]}),
])
def test_sans_dsn_les_routes_scenarios_repondent_503(monkeypatch, methode, chemin, corps):
    monkeypatch.delenv("JUMEAU_PG_DSN", raising=False)
    client = _app()
    reponse = (
        client.post(chemin, json=corps) if methode == "post" else client.get(chemin)
    )
    assert reponse.status_code == 503
    assert "JUMEAU_PG_DSN" in reponse.json()["detail"]
