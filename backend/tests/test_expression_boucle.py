"""C5a — Expression canonique : domaine, commande, routes et Postgres réel.

Les tests de commande utilisent un magasin en mémoire qui satisfait la surface utile du
port ``BoucleStore`` et simule le lien inverse ``situation.expression_id``. Les tests HTTP
remplacent la commande et la connexion : ils vérifient le contrat public et les
traductions d'erreurs sans dépendre d'un serveur. Le test Postgres est opt-in via
``JUMEAU_PG_DSN`` et prouve la chaîne réelle Situation → Expression.
"""
from __future__ import annotations

import copy
import json
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
from dataclasses import asdict, is_dataclass
from types import SimpleNamespace

import psycopg
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from meridian.adapters.inbound.http import boucle as boucle_routes
from meridian.adapters.outbound.postgres import boucle, depot, objets_exploitation, rls
from meridian.application import commandes_boucle
from meridian.domain import construction_objets_exploitation
from meridian.domain.modele_entreprise import ModeleInvalide
from meridian.domain.objets_exploitation import ObjetsExploitationInvalide
from meridian.ports.boucle import ObjetInvalide

TENANT = "local"
AUTRE_TENANT = "banque"
BASE = "/api/boucle"
CHAMPS = {
    "id", "tenant_id", "famille", "type", "mode", "titre", "version",
    "observe_le", "valide_depuis", "valide_jusqua", "cree_le", "maj_le",
}
DSN = os.environ.get("JUMEAU_PG_DSN")
besoin_pg = pytest.mark.skipif(not DSN, reason="JUMEAU_PG_DSN non défini")


def _ligne(objet) -> dict:
    donnees = asdict(objet) if is_dataclass(objet) else dict(objet)
    ligne = {cle: copy.deepcopy(donnees[cle]) for cle in CHAMPS if cle in donnees}
    ligne.setdefault("famille", "emergence")
    ligne.setdefault("mode", "DECLARED")
    ligne.setdefault("version", 1)
    ligne["donnees"] = {
        cle: copy.deepcopy(valeur)
        for cle, valeur in donnees.items()
        if cle not in CHAMPS
    }
    return ligne


def _situation_row(
    identifiant: str = "sit-1", *, tenant: str = TENANT, **donnees,
) -> dict:
    return {
        "id": identifiant,
        "tenant_id": tenant,
        "famille": "emergence",
        "type": "SITUATION",
        "mode": "OBSERVED",
        "titre": "Latence des paiements",
        "donnees": copy.deepcopy(donnees),
        "version": 1,
    }


def _expression_row(
    identifiant: str = "expression-1", *, situation_id: str = "sit-1",
    tenant: str = TENANT, **donnees,
) -> dict:
    valeurs = {
        "situation_id": situation_id,
        "type_expression": "IDEE",
        "formulation": "Les paiements ralentissent.",
        "canal": "",
        "auteur": None,
        "statut": "PROPOSED",
        "claim_ids": [],
        "hypothesis_ids": [],
        "inconnues": [],
        "confiance": 0.5,
    }
    valeurs.update(donnees)
    return {
        "id": identifiant,
        "tenant_id": tenant,
        "famille": "emergence",
        "type": "EXPRESSION",
        "mode": "DECLARED",
        "titre": valeurs["formulation"],
        "donnees": valeurs,
        "version": 1,
    }


class _Store:
    """Port Boucle minimal, avec transaction annulable et lien inverse réel."""

    def __init__(self, objets=None):
        self.objets = {
            objet["id"]: copy.deepcopy(objet) for objet in (objets or [])
        }
        self.enregistres_boucle = []
        self.enregistres_objets = []
        self.appels_lire = []
        self.echec_lien = False

    @contextmanager
    def transaction(self, conn):
        instantane = copy.deepcopy(self.objets)
        try:
            yield
        except Exception:
            self.objets = instantane
            raise

    def lire_boucle(
        self, conn, tenant_id, objet_id, *, historique=False, as_dict=True,
        for_update=False,
    ):
        self.appels_lire.append({
            "tenant_id": tenant_id, "objet_id": objet_id,
            "historique": historique, "for_update": for_update,
        })
        objet = self.objets.get(objet_id)
        if objet is None or objet.get("tenant_id") != tenant_id:
            return None
        resultat = copy.deepcopy(objet)
        if historique:
            chaine = []
            if resultat.get("type") == "EXPRESSION":
                parent_id = (resultat.get("donnees") or {}).get("situation_id")
                parent = self.objets.get(parent_id)
                if parent is not None and parent.get("tenant_id") == tenant_id:
                    chaine.append(copy.deepcopy(parent))
            chaine.append(resultat)
            resultat["chaine"] = chaine
            resultat["historique"] = []
        return resultat

    def nouvelle_expression(self, **champs):
        situation = champs.pop("situation")
        return construction_objets_exploitation.nouvelle_expression(situation, **champs)

    def nouvelle_situation(self, **champs):
        return boucle.Situation(**champs)

    def enregistrer_boucle(self, conn, tenant_id=None, objets=None, **kwargs):
        objets = list(objets or [])
        self.enregistres_boucle.extend(copy.deepcopy(objets))
        liees = [
            objet for objet in objets
            if str(getattr(objet, "type", objet.get("type") if isinstance(objet, dict) else ""))
            .upper() == "EXPRESSION"
        ]
        if liees:
            raise AssertionError("enregistrer_boucle ne doit pas persister une Expression")
        for objet in objets:
            ligne = _ligne(objet)
            self.objets[ligne["id"]] = ligne
        return objets

    def enregistrer_objets(
        self, conn, tenant_id=None, objets=None, *, historique=False, as_dict=True,
    ):
        objets = list(objets or [])
        self.enregistres_objets.extend(copy.deepcopy(objets))
        for objet in objets:
            ligne = _ligne(objet)
            self.objets[ligne["id"]] = ligne
            if self.echec_lien:
                raise RuntimeError("échec simulé du lien inverse")
            situation_id = (ligne.get("donnees") or {}).get("situation_id")
            if not situation_id:
                continue
            parent = self.objets.get(situation_id)
            if parent is None:
                raise RuntimeError(f"situation introuvable : {situation_id}")
            donnees = parent.setdefault("donnees", {})
            existante = donnees.get("expression_id")
            if existante and existante != ligne["id"]:
                raise RuntimeError("situation déjà reliée à une expression")
            donnees["expression_id"] = ligne["id"]
        return objets if not as_dict else [_ligne(objet) for objet in objets]


class _Connexion:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


# --------------------------------------------------------------------------- #
# Domaine : champs C5a
# --------------------------------------------------------------------------- #


def test_nouvelle_expression_expose_les_champs_c5a_et_les_defauts():
    situation = _situation_row()
    expression = construction_objets_exploitation.nouvelle_expression(
        situation,
        type_expression="OPPORTUNITE",
        formulation="  Automatiser la ressaisie  ",
        canal="entretien",
        auteur="Alice",
        exprime_le="2026-11-02T09:30:00+00:00",
        claim_ids=["claim-1"],
        hypothesis_ids=["hyp-1"],
        inconnues=["volume réel", "charge de fin de mois"],
        preuves=["preuve-1"],
        confiance=0.8,
    )

    assert expression.type == "EXPRESSION"
    assert expression.famille == "emergence"
    assert expression.situation_id == "sit-1"
    assert expression.type_expression == "OPPORTUNITE"
    assert expression.formulation == "Automatiser la ressaisie"
    assert expression.titre == "Automatiser la ressaisie"
    assert expression.canal == "entretien"
    assert expression.auteur == "Alice"
    assert expression.exprime_le == "2026-11-02T09:30:00+00:00"
    assert expression.claim_ids == ["claim-1"]
    assert expression.hypothesis_ids == ["hyp-1"]
    assert expression.inconnues == ["volume réel", "charge de fin de mois"]
    assert expression.preuves == ["preuve-1"]
    assert expression.confiance == 0.8
    assert expression.statut == "PROPOSED"
    assert expression.mode == "DECLARED"


def test_nouvelle_expression_prend_idee_et_proposed_par_defaut():
    expression = construction_objets_exploitation.nouvelle_expression(
        _situation_row(), formulation="Une intuition à confirmer")

    assert expression.type_expression == "IDEE"
    assert expression.statut == "PROPOSED"
    assert expression.mode == "DECLARED"
    assert expression.exprime_le


@pytest.mark.parametrize(("champs", "erreur"), [
    ({"formulation": "   "}, "formulation"),
    ({"type_expression": "MAGIQUE"}, "type_expression"),
    ({"confiance": 1.5}, "confiance"),
    ({"confiance": -0.1}, "confiance"),
])
def test_nouvelle_expression_refuse_les_champs_c5a_invalides(champs, erreur):
    with pytest.raises(ModeleInvalide) as levee:
        construction_objets_exploitation.nouvelle_expression(
            _situation_row(), **{"formulation": "Valide", **champs})
    assert erreur in str(levee.value)


def test_nouvelle_expression_refuse_une_situation_d_un_autre_type():
    with pytest.raises(ObjetsExploitationInvalide):
        construction_objets_exploitation.nouvelle_expression(
            {"id": "inv-1", "tenant_id": TENANT, "type": "INVESTIGATION"},
            formulation="Mauvaise source")


# --------------------------------------------------------------------------- #
# Commande
# --------------------------------------------------------------------------- #


def test_creer_situation_ignore_expression_id_direct():
    store = _Store()

    resultat = commandes_boucle.creer_situation(
        store, _Connexion(), TENANT,
        titre="Situation non exprimable",
        expression_id="expr-client",
    )

    assert resultat.objet["type"] == "SITUATION"
    assert not resultat.objet["donnees"].get("expression_id")


def test_creer_expression_persiste_l_expression_et_le_lien_inverse():
    store = _Store([_situation_row()])

    resultat = commandes_boucle.creer_expression(
        store, _Connexion(), TENANT, "sit-1",
        type_expression="OPPORTUNITE",
        formulation="  Automatiser la ressaisie  ",
        canal="entretien",
        auteur="Alice",
        inconnues=["volume réel"],
        confiance=0.8,
    )

    assert resultat.objet["type"] == "EXPRESSION"
    assert resultat.objet["donnees"]["statut"] == "PROPOSED"
    assert resultat.objet["donnees"]["formulation"] == "Automatiser la ressaisie"
    assert resultat.objet["donnees"]["situation_id"] == "sit-1"
    assert resultat.objet["donnees"]["canal"] == "entretien"
    assert resultat.objet["donnees"]["auteur"] == "Alice"
    assert resultat.objet["donnees"]["inconnues"] == ["volume réel"]
    assert resultat.objet["donnees"]["confiance"] == 0.8
    assert store.objets["sit-1"]["donnees"]["expression_id"] == resultat.objet["id"]
    assert [element["type"] for element in resultat.chaine] == ["SITUATION", "EXPRESSION"]
    assert store.appels_lire[0] == {
        "tenant_id": TENANT, "objet_id": "sit-1",
        "historique": False, "for_update": True,
    }
    assert len(store.enregistres_objets) == 1
    assert store.enregistres_boucle == []


def test_creer_expression_sans_situation_est_introuvable():
    store = _Store()

    with pytest.raises(commandes_boucle.SourceIntrouvable) as levee:
        commandes_boucle.creer_expression(
            store, _Connexion(), TENANT, "sit-absent", formulation="Introuvable")

    assert levee.value.role == "situation"
    assert store.enregistres_objets == []


def test_creer_expression_hors_tenant_est_introuvable():
    store = _Store([_situation_row(tenant=AUTRE_TENANT)])

    with pytest.raises(commandes_boucle.SourceIntrouvable):
        commandes_boucle.creer_expression(
            store, _Connexion(), TENANT, "sit-1", formulation="Hors tenant")

    assert store.enregistres_objets == []


def test_creer_expression_refuse_une_situation_deja_exploitee_en_409():
    store = _Store([_situation_row(expression_id="expression-existante")])

    with pytest.raises(commandes_boucle.DoublonExploitation) as levee:
        commandes_boucle.creer_expression(
            store, _Connexion(), TENANT, "sit-1", formulation="Doublon")

    assert "expression-existante" in str(levee.value)
    assert store.enregistres_objets == []
    assert store.objets["sit-1"]["donnees"]["expression_id"] == "expression-existante"


def test_creer_expression_force_proposed_meme_si_le_client_envoie_un_statut():
    store = _Store([_situation_row()])

    resultat = commandes_boucle.creer_expression(
        store, _Connexion(), TENANT, "sit-1",
        formulation="Forcée proposée", statut="CONFIRMED")

    assert resultat.objet["donnees"]["statut"] == "PROPOSED"


@pytest.mark.parametrize(("champs", "erreur"), [
    ({"formulation": "Valide", "type_expression": "MAGIQUE"}, "type_expression"),
    ({"formulation": "   "}, "formulation"),
    ({"formulation": "Valide", "confiance": 2}, "confiance"),
])
def test_creer_expression_refuse_les_champs_invalides_avant_persistance(champs, erreur):
    store = _Store([_situation_row()])

    with pytest.raises(ModeleInvalide) as levee:
        commandes_boucle.creer_expression(
            store, _Connexion(), TENANT, "sit-1", **champs)

    assert erreur in str(levee.value)
    assert store.enregistres_objets == []
    assert "expression_id" not in store.objets["sit-1"]["donnees"]


def test_creer_expression_annule_tout_si_le_lien_inverse_echoue():
    store = _Store([_situation_row()])
    store.echec_lien = True

    with pytest.raises(RuntimeError):
        commandes_boucle.creer_expression(
            store, _Connexion(), TENANT, "sit-1",
            formulation="Expression partielle")

    assert [objet for objet in store.objets.values() if objet["type"] == "EXPRESSION"] == []
    assert "expression_id" not in store.objets["sit-1"]["donnees"]


def test_enregistrer_boucle_refuse_toujours_expression_et_types_lecture_l_accepte():
    situation = _situation_row()
    expression = construction_objets_exploitation.nouvelle_expression(
        situation, formulation="Lecture seule")

    assert "EXPRESSION" not in boucle.TYPES_BOUCLE
    assert "EXPRESSION" in boucle.TYPES_LECTURE
    assert set(boucle.TYPES_BOUCLE) <= set(boucle.TYPES_LECTURE)
    with pytest.raises(boucle.BoucleInvalide):
        boucle.enregistrer_boucle(
            None, TENANT, objets=[expression], as_dict=False)


def test_types_boucle_et_lecture_ont_une_source_unique_et_un_ordre_exact():
    assert boucle.TYPES_BOUCLE == (
        "SITUATION", "INVESTIGATION", "DECISION", "INITIATIVE",
        "OUTCOME", "LEARNING", "SCENARIO",
    )
    assert boucle.TYPES_LECTURE == (
        *boucle.TYPES_BOUCLE, "SIGNAL", "EXPRESSION", "HYPOTHESIS", "OPPORTUNITY", "RISK")
    assert set(boucle._CLASSES_LECTURE) == set(boucle.TYPES_LECTURE)
    assert boucle._CLASSES_LECTURE["SIGNAL"].__name__ == "Signal"
    assert boucle._CLASSES_LECTURE["EXPRESSION"].__name__ == "Expression"
    assert boucle._CLASSES_LECTURE["HYPOTHESIS"].__name__ == "Hypothesis"
    assert boucle._CLASSES_LECTURE["OPPORTUNITY"].__name__ == "Opportunity"
    assert boucle._CLASSES_LECTURE["RISK"].__name__ == "Risk"
    assert boucle._CLASSES_LECTURE["SCENARIO"].__name__ == "Scenario"


# --------------------------------------------------------------------------- #
# Routes HTTP
# --------------------------------------------------------------------------- #


class _ConnexionRoute(_Connexion):
    def transaction(self):
        return nullcontext()


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
    monkeypatch.setattr(boucle_routes.psycopg, "connect", lambda *_, **__: _ConnexionRoute())
    return _app()


def _resultat_expression(identifiant: str = "expression-1") -> commandes_boucle.ResultatTransition:
    situation = _situation_row()
    expression = _expression_row(identifiant)
    return commandes_boucle.ResultatTransition(
        objet=expression,
        chaine=[situation, expression],
        historique=[],
    )


def test_post_expression_retourne_le_contrat_c5a(monkeypatch):
    client = _client(monkeypatch)
    appels = []

    def creer(depot, conn, tenant, situation_id, **champs):
        appels.append((tenant, situation_id, champs))
        return _resultat_expression()

    monkeypatch.setattr(boucle_routes.commandes_boucle, "creer_expression", creer)

    reponse = client.post(f"{BASE}/situations/sit-1/expressions", json={
        "type_expression": "OPPORTUNITE",
        "formulation": "  Automatiser la ressaisie  ",
        "canal": "entretien",
        "auteur": "Alice",
        "exprime_le": "2026-11-02T09:30:00+00:00",
        "claim_ids": ["claim-1"],
        "hypothesis_ids": ["hyp-1"],
        "inconnues": ["volume réel"],
        "preuves": ["preuve-1"],
        "confiance": 0.8,
        "mode": "DECLARED",
    })

    assert reponse.status_code == 201
    corps = reponse.json()
    assert corps["tenant"] == TENANT
    assert corps["objet"]["type"] == "EXPRESSION"
    assert corps["type"] == "EXPRESSION"
    assert corps["role"] == "expression"
    assert [element["type"] for element in corps["chaine"]] == ["SITUATION", "EXPRESSION"]
    assert corps["historique"] == []
    assert corps["idempotency_key"] is None
    assert appels[0][0] == TENANT
    assert appels[0][1] == "sit-1"
    assert appels[0][2]["formulation"] == "Automatiser la ressaisie"
    assert appels[0][2]["type_expression"] == "OPPORTUNITE"
    assert appels[0][2]["confiance"] == 0.8


def test_post_situation_refuse_expression_id_client(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(
        boucle_routes.commandes_boucle, "creer_situation",
        lambda *_, **__: pytest.fail("la situation ne doit pas être créée"),
    )

    reponse = client.post(f"{BASE}/situations", json={
        "titre": "Situation non exprimable",
        "expression_id": "expr-client",
    })

    assert reponse.status_code == 422
    detail = json.dumps(reponse.json())
    assert "expression_id" in detail


def test_post_expression_utilise_idee_par_defaut(monkeypatch):
    client = _client(monkeypatch)
    appels = []

    def creer(depot, conn, tenant, situation_id, **champs):
        appels.append(champs)
        return _resultat_expression()

    monkeypatch.setattr(boucle_routes.commandes_boucle, "creer_expression", creer)
    reponse = client.post(
        f"{BASE}/situations/sit-1/expressions", json={"formulation": "Une idée"})

    assert reponse.status_code == 201
    assert appels[0]["type_expression"] == "IDEE"


@pytest.mark.parametrize("corps", [
    {},
    {"formulation": "   "},
    {"formulation": "Valide", "type_expression": "MAGIQUE"},
    {"formulation": "Valide", "confiance": 1.2},
    {"formulation": "Valide", "confiance": -0.1},
    {"formulation": "Valide", "statut": "CONFIRMED"},
    {"formulation": "Valide", "champ_inconnu": True},
    {"formulation": "Valide", "exprime_le": "pas-une-date"},
    {"formulation": "Valide", "hypothesis_ids": ["   "]},
])
def test_post_expression_valide_le_corps_avant_la_commande(monkeypatch, corps):
    client = _client(monkeypatch)
    monkeypatch.setattr(
        boucle_routes.commandes_boucle, "creer_expression",
        lambda *_, **__: pytest.fail("la commande ne doit pas être appelée"),
    )
    assert client.post(f"{BASE}/situations/sit-1/expressions", json=corps).status_code == 422


def test_post_expression_traduit_les_erreurs(monkeypatch):
    client = _client(monkeypatch)

    @contextmanager
    def contexte(conn, tenant):
        yield tenant

    monkeypatch.setattr(boucle_routes.rls, "est_actif", lambda: True)
    monkeypatch.setattr(boucle_routes.rls, "contexte_tenant", contexte)

    for erreur, statut in [
        (commandes_boucle.SourceIntrouvable("situation", "sit-x"), 404),
        (commandes_boucle.DoublonExploitation("Expression déjà existante"), 409),
        (commandes_boucle.TransitionRefusee("transition refusée"), 409),
        (ObjetsExploitationInvalide("expression invalide"), 422),
        (ObjetInvalide("secret refusé"), 400),
        (psycopg.OperationalError("panne"), 503),
    ]:
        def echouer(*_, _erreur=erreur, **__):
            raise _erreur

        monkeypatch.setattr(boucle_routes.commandes_boucle, "creer_expression", echouer)
        reponse = client.post(
            f"{BASE}/situations/sit-x/expressions", json={"formulation": "Valide"})
        assert reponse.status_code == statut
        assert "Traceback" not in reponse.text


def test_unique_violation_expression_a_un_message_409_dedie():
    dedie = SimpleNamespace(
        diag=SimpleNamespace(constraint_name="objet_entreprise_expression_situation_unique"))
    generique = SimpleNamespace(diag=SimpleNamespace(constraint_name="autre_contrainte"))

    assert "Situation déjà exprimée" in boucle_routes._detail_unique_violation(dedie)
    assert boucle_routes._detail_unique_violation(generique) == "objet déjà existant"


def test_post_expression_mappe_unique_violation_expression_en_409(monkeypatch):
    client = _client(monkeypatch)

    class DoublonUnique(psycopg.errors.UniqueViolation):
        diag = SimpleNamespace(
            constraint_name="objet_entreprise_expression_situation_unique")

    def echouer(*_, **__):
        raise DoublonUnique("doublon")

    monkeypatch.setattr(boucle_routes.commandes_boucle, "creer_expression", echouer)
    reponse = client.post(
        f"{BASE}/situations/sit-1/expressions", json={"formulation": "Valide"})

    assert reponse.status_code == 409
    assert "Situation déjà exprimée" in reponse.json()["detail"]


def test_post_expression_refuse_une_cle_d_idempotence(monkeypatch):
    client = _client(monkeypatch)
    reponse = client.post(
        f"{BASE}/situations/sit-1/expressions",
        json={"formulation": "Valide"},
        headers={"Idempotency-Key": "cle-1"},
    )
    assert reponse.status_code == 501


def test_post_expression_pose_le_tenant_rls_et_transmet_x_tenant(monkeypatch):
    client = _client(monkeypatch)
    contextes = []

    @contextmanager
    def contexte(conn, tenant):
        contextes.append(tenant)
        yield tenant

    monkeypatch.setattr(boucle_routes.rls, "est_actif", lambda: True)
    monkeypatch.setattr(boucle_routes.rls, "contexte_tenant", contexte)
    appels = []

    def creer(depot, conn, tenant, situation_id, **champs):
        appels.append((tenant, situation_id))
        return _resultat_expression()

    monkeypatch.setattr(boucle_routes.commandes_boucle, "creer_expression", creer)
    reponse = client.post(
        f"{BASE}/situations/sit-1/expressions",
        json={"formulation": "Valide"},
        headers={"X-Tenant": "banque"},
    )

    assert reponse.status_code == 201
    assert reponse.json()["tenant"] == "banque"
    assert contextes == ["banque"]
    assert appels == [("banque", "sit-1")]


def test_la_reponse_expression_ne_laisse_pas_passer_un_secret(monkeypatch):
    client = _client(monkeypatch)
    resultat = _resultat_expression()
    resultat.objet["donnees"]["preuves"] = [{"password": "s3cr3t"}]
    resultat.objet["donnees"]["auteur"] = "Bearer abcdefghijklmnop"
    monkeypatch.setattr(
        boucle_routes.commandes_boucle, "creer_expression",
        lambda *_, **__: resultat)

    reponse = client.post(
        f"{BASE}/situations/sit-1/expressions", json={"formulation": "Valide"})

    assert reponse.status_code == 201
    assert "s3cr3t" not in reponse.text
    assert "abcdefghijklmnop" not in reponse.text
    assert reponse.json()["objet"]["donnees"]["preuves"] == [{"password": "***"}]


def test_sans_dsn_la_route_expression_repond_503(monkeypatch):
    monkeypatch.delenv("AUTH_MODE", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("JUMEAU_PG_DSN", raising=False)
    reponse = _app().post(
        f"{BASE}/situations/sit-1/expressions", json={"formulation": "Valide"})
    assert reponse.status_code == 503
    assert "JUMEAU_PG_DSN" in reponse.json()["detail"]


# --------------------------------------------------------------------------- #
# Postgres réel : chaîne, doublon, refus canonique et atomicité
# --------------------------------------------------------------------------- #


def _client_pg(monkeypatch) -> TestClient:
    monkeypatch.delenv("AUTH_MODE", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("JUMEAU_PG_DSN", DSN)
    return _app()


def _nettoyer(tenant: str) -> None:
    with psycopg.connect(DSN, autocommit=True) as conn:
        with rls.contexte_tenant(conn, tenant):
            conn.execute(
                "DELETE FROM objet_entreprise WHERE tenant_id = %s", (tenant,))


@besoin_pg
def test_pg_creation_expression_et_lecture_de_la_chaine_situation_expression(monkeypatch):
    tenant = f"c5a-{uuid.uuid4().hex[:10]}"
    client = _client_pg(monkeypatch)
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)

        situation = client.post(
            f"{BASE}/situations",
            json={"id": "sit-c5a", "titre": "Latence des paiements"},
            headers={"X-Tenant": tenant},
        )
        assert situation.status_code == 201

        creation = client.post(
            f"{BASE}/situations/sit-c5a/expressions",
            json={
                "type_expression": "OPPORTUNITE",
                "formulation": "Automatiser la ressaisie",
                "canal": "entretien",
                "auteur": "Alice",
                "inconnues": ["volume réel"],
                "preuves": ["preuve-1"],
                "confiance": 0.8,
            },
            headers={"X-Tenant": tenant},
        )
        assert creation.status_code == 201, creation.text
        corps = creation.json()
        expression_id = corps["objet"]["id"]
        assert corps["type"] == "EXPRESSION"
        assert corps["role"] == "expression"
        assert corps["objet"]["donnees"]["statut"] == "PROPOSED"
        assert corps["objet"]["donnees"]["situation_id"] == "sit-c5a"
        assert [element["type"] for element in corps["chaine"]] == [
            "SITUATION", "EXPRESSION",
        ]

        lecture = client.get(
            f"{BASE}/objets/{expression_id}",
            params={"historique": True},
            headers={"X-Tenant": tenant},
        )
        assert lecture.status_code == 200
        assert [element["type"] for element in lecture.json()["chaine"]] == [
            "SITUATION", "EXPRESSION",
        ]
        assert lecture.json()["objet"]["donnees"]["formulation"] == "Automatiser la ressaisie"

        situation_lue = client.get(
            f"{BASE}/objets/sit-c5a", headers={"X-Tenant": tenant}).json()["objet"]
        assert situation_lue["donnees"]["expression_id"] == expression_id

        with psycopg.connect(DSN) as conn:
            objet = boucle.lire_boucle(
                conn, tenant, expression_id, as_dict=False)
        assert objet.type == "EXPRESSION"
        assert objet.formulation == "Automatiser la ressaisie"
        assert objet.situation_id == "sit-c5a"

        doublon = client.post(
            f"{BASE}/situations/sit-c5a/expressions",
            json={"formulation": "Deuxième expression"},
            headers={"X-Tenant": tenant},
        )
        assert doublon.status_code == 409
        assert "Situation déjà exprimée" in doublon.json()["detail"]
        with psycopg.connect(DSN) as conn:
            nombre = conn.execute(
                "SELECT count(*) FROM objet_entreprise "
                "WHERE tenant_id = %s AND type = 'EXPRESSION'",
                (tenant,),
            ).fetchone()[0]
        assert nombre == 1

        hors_tenant = client.post(
            f"{BASE}/situations/sit-c5a/expressions",
            json={"formulation": "Hors tenant"},
            headers={"X-Tenant": f"{tenant}-autre"},
        )
        assert hors_tenant.status_code == 404
    finally:
        _nettoyer(tenant)


@besoin_pg
def test_pg_migration_index_unique_expression_situation(monkeypatch):
    tenant = f"c5a-{uuid.uuid4().hex[:10]}"
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            unique = conn.execute(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = current_schema() AND indexname = %s",
                ("objet_entreprise_expression_situation_unique",),
            ).fetchone()
            filtre = conn.execute(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = current_schema() AND indexname = %s",
                ("objet_entreprise_exploitation_expression",),
            ).fetchone()
            situation = {**_situation_row(), "tenant_id": tenant}
            boucle.enregistrer_boucle(conn, tenant, objets=[situation], historique=True)

        assert unique is not None and "UNIQUE" in unique[0]
        assert "donnees ->> 'situation_id'::text" in unique[0]
        assert filtre is not None and "UNIQUE" not in filtre[0]

        with psycopg.connect(DSN) as conn:
            commandes_boucle.creer_expression(
                boucle, conn, tenant, "sit-1", formulation="Première expression")

        with psycopg.connect(DSN) as conn:
            with pytest.raises(psycopg.errors.UniqueViolation) as levee:
                conn.execute(
                    "INSERT INTO objet_entreprise "
                    "(id, tenant_id, famille, type, mode, titre, donnees) "
                    "VALUES (%s, %s, 'emergence', 'EXPRESSION', 'DECLARED', '', %s::jsonb)",
                    (
                        "expr-doublon-direct",
                        tenant,
                        json.dumps({
                            "situation_id": "sit-1",
                            "type_expression": "IDEE",
                            "formulation": "Deuxième expression directe",
                        }),
                    ),
                )
        assert levee.value.diag.constraint_name == (
            "objet_entreprise_expression_situation_unique")
    finally:
        _nettoyer(tenant)


@besoin_pg
def test_pg_deux_creations_concurrentes_laissent_une_seule_expression():
    tenant = f"c5a-{uuid.uuid4().hex[:10]}"
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            situation = {**_situation_row(), "tenant_id": tenant}
            boucle.enregistrer_boucle(conn, tenant, objets=[situation], historique=True)

        barriere = threading.Barrier(2)

        def tenter(formulation: str):
            barriere.wait(timeout=10)
            with psycopg.connect(DSN) as conn:
                try:
                    resultat = commandes_boucle.creer_expression(
                        boucle, conn, tenant, "sit-1", formulation=formulation)
                except commandes_boucle.DoublonExploitation as exc:
                    return ("doublon", str(exc))
                return ("succes", resultat.objet["id"])

        with ThreadPoolExecutor(max_workers=2) as executeur:
            futurs = [
                executeur.submit(tenter, "Expression A"),
                executeur.submit(tenter, "Expression B"),
            ]
            resultats = [futur.result(timeout=30) for futur in futurs]

        succes = [resultat for resultat in resultats if resultat[0] == "succes"]
        doublons = [resultat for resultat in resultats if resultat[0] == "doublon"]
        assert len(succes) == 1
        assert len(doublons) == 1
        assert "Situation déjà exprimée" in doublons[0][1]
        gagnante = succes[0][1]

        with psycopg.connect(DSN) as conn:
            nombre = conn.execute(
                "SELECT count(*) FROM objet_entreprise "
                "WHERE tenant_id = %s AND type = 'EXPRESSION'",
                (tenant,),
            ).fetchone()[0]
            situation_lue = boucle.lire_boucle(conn, tenant, "sit-1", as_dict=True)
        assert nombre == 1
        assert situation_lue["donnees"]["expression_id"] == gagnante
    finally:
        _nettoyer(tenant)


@besoin_pg
def test_pg_un_secret_refuse_ne_laisse_aucune_expression_partielle(monkeypatch):
    tenant = f"c5a-{uuid.uuid4().hex[:10]}"
    client = _client_pg(monkeypatch)
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)

        assert client.post(
            f"{BASE}/situations",
            json={"id": "sit-secret", "titre": "Situation avec preuve sensible"},
            headers={"X-Tenant": tenant},
        ).status_code == 201

        reponse = client.post(
            f"{BASE}/situations/sit-secret/expressions",
            json={
                "formulation": "Expression refusée",
                "preuves": [{"password": "s3cr3t"}],
            },
            headers={"X-Tenant": tenant},
        )
        assert reponse.status_code == 400

        situation = client.get(
            f"{BASE}/objets/sit-secret", headers={"X-Tenant": tenant}).json()["objet"]
        assert not situation["donnees"].get("expression_id")
        with psycopg.connect(DSN) as conn:
            lignes = conn.execute(
                "SELECT count(*) FROM objet_entreprise "
                "WHERE tenant_id = %s AND type = 'EXPRESSION'",
                (tenant,),
            ).fetchone()
        assert lignes[0] == 0
    finally:
        _nettoyer(tenant)


@besoin_pg
def test_pg_un_echec_du_lien_inverse_annule_l_expression(monkeypatch):
    tenant = f"c5a-{uuid.uuid4().hex[:10]}"
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            situation = {**_situation_row(), "tenant_id": tenant}
            boucle.enregistrer_boucle(conn, tenant, objets=[situation], historique=True)

        def echouer(*_, **__):
            raise RuntimeError("échec simulé du lien inverse")

        monkeypatch.setattr(objets_exploitation, "_persister_parent", echouer)
        with psycopg.connect(DSN) as conn:
            with pytest.raises(RuntimeError):
                commandes_boucle.creer_expression(
                    boucle, conn, tenant, "sit-1",
                    formulation="Expression partielle")

        with psycopg.connect(DSN) as conn:
            nombre = conn.execute(
                "SELECT count(*) FROM objet_entreprise "
                "WHERE tenant_id = %s AND type = 'EXPRESSION'",
                (tenant,),
            ).fetchone()[0]
            situation_lue = boucle.lire_boucle(conn, tenant, "sit-1", as_dict=True)
        assert nombre == 0
        assert not situation_lue["donnees"].get("expression_id")
    finally:
        _nettoyer(tenant)


@besoin_pg
def test_pg_enregistrer_boucle_refuse_expression_apres_creation_reelle(monkeypatch):
    tenant = f"c5a-{uuid.uuid4().hex[:10]}"
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            situation = {**_situation_row(), "tenant_id": tenant}
            boucle.enregistrer_boucle(conn, tenant, objets=[situation], historique=True)
            expression = construction_objets_exploitation.nouvelle_expression(
                {**situation, "tenant_id": tenant}, formulation="Expression B")

            with pytest.raises(boucle.BoucleInvalide):
                boucle.enregistrer_boucle(conn, tenant, objets=[expression], historique=True)

            assert boucle.lire_boucle(
                conn, tenant, expression.id, historique=True) is None
    finally:
        _nettoyer(tenant)
