"""Transitions canoniques HTTP et orchestration applicative de la boucle.

La base Postgres est remplacée par un magasin en mémoire qui répond aux quelques requêtes
utilisées par :mod:`meridian.adapters.outbound.postgres.entreprise_depot`. Ces tests ne
dépendent donc ni d'un serveur Postgres ni d'un ``JUMEAU_PG_DSN`` réel.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager, nullcontext
from unittest.mock import Mock

import psycopg
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from meridian.adapters.inbound.http import boucle as boucle_routes
from meridian.adapters.outbound.postgres import boucle
from meridian.application import commandes_boucle

TENANT = "local"
BASE = "/api/boucle"
MAINTENANT = "2026-10-01T08:00:00+00:00"


def _objet(
    identifiant: str,
    *,
    tenant: str = TENANT,
    famille: str = "emergence",
    type_: str = "SITUATION",
    mode: str = "OBSERVED",
    titre: str | None = None,
    donnees: dict | None = None,
    version: int = 1,
) -> dict:
    return {
        "id": identifiant,
        "tenant_id": tenant,
        "famille": famille,
        "type": type_,
        "mode": mode,
        "titre": titre or identifiant,
        "donnees": copy.deepcopy(donnees or {}),
        "version": version,
        "observe_le": MAINTENANT,
        "valide_depuis": MAINTENANT,
        "valide_jusqua": None,
        "cree_le": MAINTENANT,
        "maj_le": MAINTENANT,
    }


def _situation(identifiant: str = "sit-1", *, tenant: str = TENANT, **champs):
    valeurs = {
        "id": identifiant,
        "tenant_id": tenant,
        "titre": "Délai de traitement en hausse",
        "description": "Le délai dépasse la cible",
    }
    valeurs.update(champs)
    return boucle.Situation(**valeurs)


# --------------------------------------------------------------------------- #
# Faux magasin Postgres : uniquement les requêtes de la boucle.
# --------------------------------------------------------------------------- #


def _donnees(valeur):
    return copy.deepcopy(getattr(valeur, "obj", valeur))


class _Curseur:
    def __init__(self, connexion: "_Connexion"):
        self.connexion = connexion
        self.lignes: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=()):
        self.connexion.requetes.append((" ".join(sql.split()), tuple(params)))
        self.lignes = self.connexion.repondre(" ".join(sql.split()), tuple(params))
        return self

    def fetchall(self):
        return list(self.lignes)

    def fetchone(self):
        return self.lignes[0] if self.lignes else None


class _Connexion:
    def __init__(self, magasin: "_Magasin"):
        self.magasin = magasin
        self.requetes: list[tuple[str, tuple]] = []
        self.transactions = 0
        self.ferme = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.ferme = True
        return False

    @contextmanager
    def transaction(self):
        """Transaction simulée : restaure l'instantané si le bloc échoue."""
        self.transactions += 1
        instantane = copy.deepcopy(self.magasin.objets)
        try:
            yield
        except Exception:
            self.magasin.objets = instantane
            raise

    def cursor(self, row_factory=None):
        return _Curseur(self)

    def repondre(self, sql: str, params: tuple) -> list[dict]:
        if "GROUP BY famille, type, mode" in sql:
            tenant = params[0]
            comptes: dict[tuple[str, str, str], int] = {}
            for (tenant_ligne, _), ligne in self.magasin.objets.items():
                if tenant_ligne != tenant:
                    continue
                cle = (ligne["famille"], ligne["type"], ligne["mode"])
                comptes[cle] = comptes.get(cle, 0) + 1
            return [
                {"famille": famille, "type": type_, "mode": mode, "nombre": nombre}
                for (famille, type_, mode), nombre in sorted(comptes.items())
            ]

        if sql.startswith("INSERT INTO objet_entreprise"):
            identifiant, tenant, famille, type_, mode, titre, donnees, version = params[:8]
            observe_le, valide_depuis, valide_jusqua, _, cree_le = params[8:]
            observe_le = observe_le or MAINTENANT
            ligne = _objet(
                identifiant, tenant=tenant, famille=famille, type_=type_, mode=mode,
                titre=titre, donnees=_donnees(donnees), version=int(version or 1),
            )
            ligne["observe_le"] = observe_le
            ligne["valide_depuis"] = valide_depuis or observe_le
            ligne["valide_jusqua"] = valide_jusqua
            ligne["cree_le"] = cree_le or observe_le
            self.magasin.objets[(tenant, identifiant)] = ligne
            return [copy.deepcopy(ligne)]

        if sql.startswith("UPDATE objet_entreprise SET"):
            (famille, type_, mode, titre, donnees, version, observe_le, valide_depuis,
             valide_jusqua, tenant, identifiant) = params
            ancien = self.magasin.objets[(tenant, identifiant)]
            ligne = copy.deepcopy(ancien)
            ligne.update({
                "famille": famille,
                "type": type_,
                "mode": mode,
                "titre": titre,
                "donnees": _donnees(donnees),
                "version": int(version),
                "observe_le": observe_le or ancien["observe_le"],
                "valide_depuis": valide_depuis or ancien["valide_depuis"],
                "valide_jusqua": valide_jusqua,
            })
            self.magasin.objets[(tenant, identifiant)] = ligne
            return [copy.deepcopy(ligne)]

        if "FOR UPDATE" in sql:
            tenant, identifiant = params[:2]
            ligne = self.magasin.objets.get((tenant, identifiant))
            return [copy.deepcopy(ligne)] if ligne is not None else []

        if "WHERE tenant_id = %s AND id = %s" in sql:
            tenant, identifiant = params[:2]
            ligne = self.magasin.objets.get((tenant, identifiant))
            return [copy.deepcopy(ligne)] if ligne is not None else []

        if sql.startswith("SELECT * FROM objet_entreprise WHERE"):
            tenant = params[0]
            lignes = [
                copy.deepcopy(ligne)
                for (tenant_ligne, _), ligne in self.magasin.objets.items()
                if tenant_ligne == tenant
            ]
            rang = 1
            for colonne in ("famille", "type", "mode"):
                if f"{colonne} = %s" in sql:
                    valeur = params[rang]
                    rang += 1
                    lignes = [ligne for ligne in lignes if ligne[colonne] == valeur]
            lignes.sort(key=lambda ligne: (ligne["famille"], ligne["type"], ligne["id"]))
            return lignes[: params[-1]]

        return []


class _Magasin:
    def __init__(self):
        self.objets: dict[tuple[str, str], dict] = {}


def _app() -> TestClient:
    app = FastAPI()
    api = APIRouter(prefix="/api")
    api.include_router(boucle_routes.router)
    app.include_router(api)
    return TestClient(app)


def _client(monkeypatch, magasin: _Magasin | None = None) -> tuple[TestClient, _Magasin]:
    magasin = magasin or _Magasin()
    monkeypatch.delenv("AUTH_MODE", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("JUMEAU_PG_DSN", "postgresql://test/test")
    monkeypatch.setattr(boucle_routes.psycopg, "connect", lambda *_, **__: _Connexion(magasin))
    return _app(), magasin


def _post(client: TestClient, chemin: str, corps: dict | None = None, **kwargs):
    return client.post(f"{BASE}{chemin}", json=corps if corps is not None else {}, **kwargs)


def _chaine(client: TestClient) -> dict[str, str]:
    """Déroule la boucle canonique complète et rend les identifiants créés."""
    assert _post(client, "/situations", {
        "id": "sit-1", "titre": "Délai de traitement", "description": "Le délai dépasse la cible",
    }).status_code == 201
    assert _post(client, "/situations/sit-1/investigations", {
        "id": "inv-1", "question": "Pourquoi 12 jours ?",
    }).status_code == 201
    assert _post(client, "/investigations/inv-1/decisions", {
        "id": "dec-1", "options": ["Automatiser", "Réorganiser"], "criteres": ["coût", "délai"],
    }).status_code == 201
    assert _post(client, "/decisions/dec-1/trancher", {
        "acteur": "comité-cartes", "choix": "Automatiser", "rationale": "Réduire le délai",
    }).status_code == 200
    assert _post(client, "/decisions/dec-1/initiatives", {
        "id": "ini-1", "titre": "Automatiser la pièce",
    }).status_code == 201
    assert _post(client, "/initiatives/ini-1/outcomes", {
        "id": "out-1",
        "mesure": {"metrique": "delai_moyen_jours", "valeur": 4.2},
        "valeur_attendue": 5,
    }).status_code == 201
    assert _post(client, "/outcomes/out-1/learnings", {
        "id": "lea-1", "enonce": "Automatiser la pièce réduit le délai",
    }).status_code == 201
    return {"situation": "sit-1", "investigation": "inv-1", "decision": "dec-1",
            "initiative": "ini-1", "outcome": "out-1", "learning": "lea-1"}


# --------------------------------------------------------------------------- #
# Orchestration applicative : chargement, transition pure, persistance.
# --------------------------------------------------------------------------- #


def _lire_resultat(identifiant: str, type_: str, chaine: list[dict] | None = None) -> dict:
    return {
        "id": identifiant,
        "tenant_id": TENANT,
        "famille": "resultat_apprentissage",
        "type": type_,
        "mode": "INFERRED",
        "titre": identifiant,
        "donnees": {},
        "version": 1,
        "observe_le": MAINTENANT,
        "valide_depuis": MAINTENANT,
        "valide_jusqua": None,
        "cree_le": MAINTENANT,
        "maj_le": MAINTENANT,
        "chaine": chaine if chaine is not None else [],
        "historique": [],
    }


class _ConnexionFactice:
    """Connexion minimale : l'orchestration doit ouvrir une transaction englobante."""

    def __init__(self):
        self.transactions = 0

    def transaction(self):
        self.transactions += 1
        return nullcontext()


def test_ouvrir_investigation_charge_la_source_puis_persiste(monkeypatch):
    situation = _situation()
    lire = Mock(side_effect=[situation, _lire_resultat(
        "inv-1", "INVESTIGATION", [_objet("sit-1")])])
    enregistrer = Mock(return_value=[])
    monkeypatch.setattr(boucle, "lire_boucle", lire)
    monkeypatch.setattr(boucle, "enregistrer_boucle", enregistrer)
    conn = _ConnexionFactice()

    resultat = commandes_boucle.ouvrir_investigation(
        boucle, conn, TENANT, "sit-1", id="inv-1", question="Pourquoi 12 jours ?")

    assert resultat.objet["id"] == "inv-1"
    assert [element["type"] for element in resultat.chaine] == ["SITUATION"]
    assert resultat.historique == []
    assert conn.transactions == 1
    assert lire.call_args_list[0].kwargs["as_dict"] is False
    objets = enregistrer.call_args.kwargs["objets"]
    assert enregistrer.call_args.kwargs["historique"] is True
    assert [objet.id for objet in objets] == ["inv-1"]
    assert objets[0].situation_id == "sit-1"


@pytest.mark.parametrize(("appel", "role"), [
    (lambda conn: commandes_boucle.ouvrir_investigation(boucle, conn, TENANT, "sit-x"), "situation"),
    (lambda conn: commandes_boucle.proposer_decision(boucle, conn, TENANT, "inv-x", ["A"]), "investigation"),
    (lambda conn: commandes_boucle.trancher_decision(boucle, conn, TENANT, "dec-x", acteur="a", choix="A"),
     "decision"),
    (lambda conn: commandes_boucle.lancer_initiative(boucle, conn, TENANT, "dec-x"), "decision"),
    (lambda conn: commandes_boucle.mesurer_outcome(boucle, conn, TENANT, "ini-x", {"valeur": 1}),
     "initiative"),
    (lambda conn: commandes_boucle.capitaliser_learning_depuis_outcome(
        boucle, conn, TENANT, "out-x", enonce="Leçon"), "outcome"),
    (lambda conn: commandes_boucle.capitaliser_learning_depuis_investigation(
        boucle, conn, TENANT, "inv-x", enonce="Leçon"), "investigation"),
])
def test_une_source_absente_leve_source_introuvable_sans_persister(monkeypatch, appel, role):
    monkeypatch.setattr(boucle, "lire_boucle", Mock(return_value=None))
    enregistrer = Mock()
    monkeypatch.setattr(boucle, "enregistrer_boucle", enregistrer)

    with pytest.raises(commandes_boucle.SourceIntrouvable) as erreur:
        appel(None)

    assert erreur.value.role == role
    enregistrer.assert_not_called()


def test_trancher_une_decision_deja_tranchee_est_refuse(monkeypatch):
    decision = boucle.Decision(
        id="dec-1", tenant_id=TENANT, investigation_id="inv-1", options=["A"],
        statut="DECIDED", acteur="comité", choix="A")
    monkeypatch.setattr(boucle, "lire_boucle", Mock(return_value=decision))
    enregistrer = Mock()
    monkeypatch.setattr(boucle, "enregistrer_boucle", enregistrer)

    with pytest.raises(boucle.BoucleInvalide):
        commandes_boucle.trancher_decision(boucle, None, TENANT, "dec-1", acteur="autre", choix="A")

    enregistrer.assert_not_called()


def test_trancher_strippe_la_version_pour_incrementer_l_historique(monkeypatch):
    decision = boucle.Decision(
        id="dec-1", tenant_id=TENANT, investigation_id="inv-1", options=["A"], version=5)
    monkeypatch.setattr(boucle, "lire_boucle", Mock(
        side_effect=[decision, _lire_resultat("dec-1", "DECISION")]))
    enregistrer = Mock(return_value=[])
    monkeypatch.setattr(boucle, "enregistrer_boucle", enregistrer)
    conn = _ConnexionFactice()

    commandes_boucle.trancher_decision(
        boucle, conn, TENANT, "dec-1", acteur="comité", choix="A")

    assert conn.transactions == 1
    objets = enregistrer.call_args.kwargs["objets"]
    assert len(objets) == 1
    assert objets[0].version == 1
    assert objets[0].statut == "DECIDED"


def test_lancer_initiative_persiste_aussi_la_decision_pour_le_lien_inverse(monkeypatch):
    decision = boucle.Decision(
        id="dec-1", tenant_id=TENANT, investigation_id="inv-1", options=["A"],
        statut="DECIDED", acteur="comité", choix="A", version=2)
    monkeypatch.setattr(boucle, "lire_boucle", Mock(
        side_effect=[decision, _lire_resultat("ini-1", "INITIATIVE")]))
    enregistrer = Mock(return_value=[])
    monkeypatch.setattr(boucle, "enregistrer_boucle", enregistrer)
    conn = _ConnexionFactice()

    commandes_boucle.lancer_initiative(boucle, conn, TENANT, "dec-1", id="ini-1")

    assert conn.transactions == 1
    objets = enregistrer.call_args.kwargs["objets"]
    assert [objet.type for objet in objets] == ["DECISION", "INITIATIVE"]
    assert objets[0].version == 1
    assert objets[1].decision_id == "dec-1"


def test_mesurer_outcome_refuse_une_mesure_vide(monkeypatch):
    initiative = boucle.Initiative(
        id="ini-1", tenant_id=TENANT, decision_id="dec-1", titre="Automatiser")
    monkeypatch.setattr(boucle, "lire_boucle", Mock(return_value=initiative))
    enregistrer = Mock()
    monkeypatch.setattr(boucle, "enregistrer_boucle", enregistrer)

    with pytest.raises(boucle.BoucleInvalide):
        commandes_boucle.mesurer_outcome(boucle, None, TENANT, "ini-1", {})
    enregistrer.assert_not_called()


def test_capitaliser_depuis_investigation_relie_la_source(monkeypatch):
    investigation = boucle.Investigation(
        id="inv-1", tenant_id=TENANT, situation_id="sit-1", titre="Comprendre")
    monkeypatch.setattr(boucle, "lire_boucle", Mock(
        side_effect=[investigation, _lire_resultat("lea-1", "LEARNING")]))
    enregistrer = Mock(return_value=[])
    monkeypatch.setattr(boucle, "enregistrer_boucle", enregistrer)
    conn = _ConnexionFactice()

    resultat = commandes_boucle.capitaliser_learning_depuis_investigation(
        boucle, conn, TENANT, "inv-1", id="lea-1", enonce="L'enquête est réutilisable")

    assert resultat.objet["id"] == "lea-1"
    assert conn.transactions == 1
    objets = enregistrer.call_args.kwargs["objets"]
    assert objets[0].investigation_ids == ["inv-1"]
    assert objets[0].outcome_ids == []


def test_une_source_d_un_autre_tenant_est_refusee(monkeypatch):
    situation = _situation(tenant="banque")
    monkeypatch.setattr(boucle, "lire_boucle", Mock(return_value=situation))
    enregistrer = Mock()
    monkeypatch.setattr(boucle, "enregistrer_boucle", enregistrer)

    with pytest.raises(commandes_boucle.TransitionRefusee):
        commandes_boucle.ouvrir_investigation(
            boucle, _ConnexionFactice(), TENANT, "sit-1")

    enregistrer.assert_not_called()


def test_une_source_de_mauvais_type_est_refusee(monkeypatch):
    investigation = boucle.Investigation(
        id="inv-1", tenant_id=TENANT, situation_id="sit-1", titre="Comprendre")
    monkeypatch.setattr(boucle, "lire_boucle", Mock(return_value=investigation))
    enregistrer = Mock()
    monkeypatch.setattr(boucle, "enregistrer_boucle", enregistrer)

    with pytest.raises(commandes_boucle.TransitionRefusee):
        commandes_boucle.ouvrir_investigation(
            boucle, _ConnexionFactice(), TENANT, "inv-1")

    enregistrer.assert_not_called()


def test_une_source_sans_identifiant_est_introuvable(monkeypatch):
    lire = Mock()
    monkeypatch.setattr(boucle, "lire_boucle", lire)

    with pytest.raises(commandes_boucle.SourceIntrouvable):
        commandes_boucle.ouvrir_investigation(boucle, None, TENANT, "   ")

    lire.assert_not_called()


# --------------------------------------------------------------------------- #
# Routes HTTP : chaîne complète, codes d'erreur, idempotence et non-régression.
# --------------------------------------------------------------------------- #


def test_la_chaine_complete_est_operationnelle(monkeypatch):
    client, _ = _client(monkeypatch)
    identifiants = _chaine(client)

    situation = client.get(f"{BASE}/objets/{identifiants['situation']}").json()["objet"]
    assert situation["type"] == "SITUATION"

    investigation = client.get(f"{BASE}/objets/{identifiants['investigation']}").json()["objet"]
    assert investigation["donnees"]["situation_id"] == "sit-1"

    decision = client.get(f"{BASE}/objets/{identifiants['decision']}").json()["objet"]
    assert decision["donnees"]["statut"] == "DECIDED"
    assert decision["donnees"]["acteur"] == "comité-cartes"
    assert decision["donnees"]["choix"] == "Automatiser"
    assert decision["donnees"]["initiative_id"] == "ini-1"

    initiative = client.get(f"{BASE}/objets/{identifiants['initiative']}").json()["objet"]
    assert initiative["donnees"]["decision_id"] == "dec-1"
    assert initiative["donnees"]["outcome_ids"] == ["out-1"]

    outcome = client.get(f"{BASE}/objets/{identifiants['outcome']}").json()["objet"]
    assert outcome["donnees"]["initiative_id"] == "ini-1"
    assert outcome["donnees"]["mesure"]["valeur"] == 4.2

    learning = client.get(f"{BASE}/objets/{identifiants['learning']}").json()["objet"]
    assert learning["donnees"]["outcome_ids"] == ["out-1"]

    parcours = client.get(
        f"{BASE}/objets/{identifiants['learning']}", params={"historique": "true"}).json()
    assert [objet["type"] for objet in parcours["chaine"]] == [
        "SITUATION", "INVESTIGATION", "DECISION", "INITIATIVE", "OUTCOME", "LEARNING"]


def test_chaine_retournee_par_chaque_transition(monkeypatch):
    client, _ = _client(monkeypatch)

    situation = _post(client, "/situations", {
        "id": "sit-1", "titre": "Délai", "description": "Le délai dépasse la cible"})
    assert situation.status_code == 201
    assert [objet["type"] for objet in situation.json()["chaine"]] == ["SITUATION"]
    assert situation.json()["objet"] == situation.json()["situation"]

    investigation = _post(client, "/situations/sit-1/investigations", {"id": "inv-1"})
    assert investigation.status_code == 201
    assert [objet["type"] for objet in investigation.json()["chaine"]] == [
        "SITUATION", "INVESTIGATION"]

    decision = _post(client, "/investigations/inv-1/decisions", {
        "id": "dec-1", "options": ["Automatiser"]})
    assert decision.status_code == 201
    assert [objet["type"] for objet in decision.json()["chaine"]] == [
        "SITUATION", "INVESTIGATION", "DECISION"]

    tranchee = _post(client, "/decisions/dec-1/trancher", {
        "acteur": "comité", "choix": "Automatiser"})
    assert tranchee.status_code == 200
    assert [objet["type"] for objet in tranchee.json()["chaine"]] == [
        "SITUATION", "INVESTIGATION", "DECISION"]
    assert tranchee.json()["decision"]["version"] == 2
    assert len(tranchee.json()["historique"]) == 1
    assert tranchee.json()["historique"][0]["version"] == 1
    assert tranchee.json()["historique"][0]["donnees"]["statut"] == "PROPOSED"

    initiative = _post(client, "/decisions/dec-1/initiatives", {"id": "ini-1"})
    assert initiative.status_code == 201
    assert [objet["type"] for objet in initiative.json()["chaine"]] == [
        "SITUATION", "INVESTIGATION", "DECISION", "INITIATIVE"]

    outcome = _post(client, "/initiatives/ini-1/outcomes", {
        "id": "out-1", "mesure": {"valeur": 4.2}})
    assert outcome.status_code == 201
    assert [objet["type"] for objet in outcome.json()["chaine"]] == [
        "SITUATION", "INVESTIGATION", "DECISION", "INITIATIVE", "OUTCOME"]

    learning = _post(client, "/outcomes/out-1/learnings", {
        "id": "lea-1", "enonce": "Automatiser réduit le délai"})
    assert learning.status_code == 201
    assert [objet["type"] for objet in learning.json()["chaine"]] == [
        "SITUATION", "INVESTIGATION", "DECISION", "INITIATIVE", "OUTCOME", "LEARNING"]

    learning_investigation = _post(client, "/investigations/inv-1/learnings", {
        "id": "lea-2", "enonce": "L'enquête est réutilisable"})
    assert learning_investigation.status_code == 201
    assert [objet["type"] for objet in learning_investigation.json()["chaine"]] == [
        "SITUATION", "INVESTIGATION", "LEARNING"]


@pytest.mark.parametrize(("chemin", "corps"), [
    ("/situations/sit-x/investigations", {}),
    ("/investigations/inv-x/decisions", {"options": ["A"]}),
    ("/decisions/dec-x/trancher", {"acteur": "a", "choix": "A"}),
    ("/decisions/dec-x/initiatives", {}),
    ("/initiatives/ini-x/outcomes", {"mesure": {"valeur": 1}}),
    ("/outcomes/out-x/learnings", {"enonce": "Leçon"}),
    ("/investigations/inv-x/learnings", {"enonce": "Leçon"}),
])
def test_une_source_absente_est_404(monkeypatch, chemin, corps):
    client, _ = _client(monkeypatch)

    reponse = _post(client, chemin, corps)

    assert reponse.status_code == 404


def test_un_objet_d_un_autre_tenant_est_404(monkeypatch):
    client, _ = _client(monkeypatch)
    assert _post(client, "/situations", {
        "id": "sit-1", "titre": "Délai", "description": "Le délai dépasse la cible"}).status_code == 201

    reponse = _post(client, "/situations/sit-1/investigations", {},
                    headers={"X-Tenant": "banque"})

    assert reponse.status_code == 404


def test_une_situation_dupliquee_est_409(monkeypatch):
    client, _ = _client(monkeypatch)
    corps = {"id": "sit-1", "titre": "Délai"}
    assert _post(client, "/situations", corps).status_code == 201

    reponse = _post(client, "/situations", corps)

    assert reponse.status_code == 409


def test_une_situation_sans_titre_prend_la_description(monkeypatch):
    client, _ = _client(monkeypatch)

    reponse = _post(client, "/situations", {
        "id": "sit-1", "description": "Le délai dépasse la cible"})

    assert reponse.status_code == 201
    assert reponse.json()["situation"]["titre"] == "Le délai dépasse la cible"


def test_une_erreur_de_persistance_ne_laisse_pas_de_chaine_partielle(monkeypatch):
    client, magasin = _client(monkeypatch)
    assert _post(client, "/situations", {
        "id": "sit-1", "titre": "Délai", "description": "Le délai dépasse la cible"}).status_code == 201
    assert _post(client, "/situations/sit-1/investigations", {"id": "inv-1"}).status_code == 201
    assert _post(client, "/investigations/inv-1/decisions", {
        "id": "dec-1", "options": ["Automatiser"]}).status_code == 201
    assert _post(client, "/decisions/dec-1/trancher", {
        "acteur": "comité", "choix": "Automatiser"}).status_code == 200
    avant = copy.deepcopy(magasin.objets[(TENANT, "dec-1")])
    vrai = boucle.entreprise_depot.enregistrer_objet

    def enregistrer_avec_echec(conn, tenant, payload):
        if payload.get("type") == "INITIATIVE":
            raise psycopg.OperationalError("échec simulé")
        return vrai(conn, tenant, payload)

    monkeypatch.setattr(boucle.entreprise_depot, "enregistrer_objet", enregistrer_avec_echec)

    reponse = _post(client, "/decisions/dec-1/initiatives", {"id": "ini-1"})

    assert reponse.status_code == 503
    assert magasin.objets[(TENANT, "dec-1")] == avant
    assert (TENANT, "ini-1") not in magasin.objets


def test_une_decision_deja_tranchee_est_409(monkeypatch):
    client, _ = _client(monkeypatch)
    _chaine(client)

    reponse = _post(client, "/decisions/dec-1/trancher", {
        "acteur": "autre-comité", "choix": "Automatiser"})

    assert reponse.status_code == 409


@pytest.mark.parametrize(("chemin", "corps"), [
    ("/decisions/dec-1/initiatives", {"id": "ini-refusee"}),
    ("/decisions/dec-1/trancher", {"acteur": "comité", "choix": "Option absente"}),
])
def test_une_transition_invalide_est_409(monkeypatch, chemin, corps):
    client, _ = _client(monkeypatch)
    assert _post(client, "/situations", {
        "id": "sit-1", "titre": "Délai", "description": "Le délai dépasse la cible"}).status_code == 201
    assert _post(client, "/situations/sit-1/investigations", {"id": "inv-1"}).status_code == 201
    assert _post(client, "/investigations/inv-1/decisions", {
        "id": "dec-1", "options": ["Automatiser"]}).status_code == 201

    reponse = _post(client, chemin, corps)

    assert reponse.status_code == 409


@pytest.mark.parametrize(("chemin", "corps"), [
    ("/situations/sit-x/investigations", {"mode": "MAGIQUE"}),
    ("/situations/sit-x/investigations", {"champ_inconnu": "x"}),
    ("/investigations/inv-x/decisions", {"options": []}),
    ("/investigations/inv-x/decisions", {"options": ["  "]}),
    ("/decisions/dec-x/trancher", {"acteur": "   ", "choix": "A"}),
    ("/decisions/dec-x/trancher", {"acteur": "a", "choix": ""}),
    ("/initiatives/ini-x/outcomes", {}),
    ("/initiatives/ini-x/outcomes", {"mesure": {}}),
    ("/outcomes/out-x/learnings", {"enonce": "   "}),
    ("/investigations/inv-x/learnings", {}),
    ("/situations", {"statut": "CANDIDATE"}),
    ("/situations", {"titre": "Délai", "mode": "INCONNU"}),
])
def test_une_validation_invalide_est_422(monkeypatch, chemin, corps):
    client, _ = _client(monkeypatch)

    reponse = _post(client, chemin, corps)

    assert reponse.status_code == 422


def test_sans_dsn_les_post_repondent_503(monkeypatch):
    monkeypatch.delenv("AUTH_MODE", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("JUMEAU_PG_DSN", raising=False)
    client = _app()

    assert _post(client, "/situations", {
        "titre": "Délai", "description": "Le délai dépasse la cible"}).status_code == 503
    assert _post(client, "/situations/sit-1/investigations", {}).status_code == 503


def test_postgres_indisponible_est_503(monkeypatch):
    monkeypatch.delenv("AUTH_MODE", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("JUMEAU_PG_DSN", "postgresql://test/test")

    def indisponible(*_, **__):
        raise psycopg.OperationalError("connexion refusée")

    monkeypatch.setattr(boucle_routes.psycopg, "connect", indisponible)
    client = _app()

    reponse = _post(client, "/situations", {
        "titre": "Délai", "description": "Le délai dépasse la cible"})

    assert reponse.status_code == 503


def test_idempotency_key_est_acceptee_et_renvoyee(monkeypatch):
    client, _ = _client(monkeypatch)
    assert _post(client, "/situations", {
        "id": "sit-1", "titre": "Délai", "description": "Le délai dépasse la cible"}).status_code == 201

    reponse = _post(client, "/situations/sit-1/investigations", {"id": "inv-1"},
                    headers={"Idempotency-Key": "cle-inv-1"})

    assert reponse.status_code == 201
    assert reponse.json()["idempotency_key"] == "cle-inv-1"
    assert reponse.json()["investigation"]["id"] == "inv-1"


def test_les_lectures_existantes_restent_disponibles(monkeypatch):
    client, _ = _client(monkeypatch)
    _chaine(client)
    assert _post(client, "/investigations/inv-1/learnings", {
        "id": "lea-2", "enonce": "L'enquête est réutilisable"}).status_code == 201

    liste = client.get(f"{BASE}/objets", params={"type": "LEARNING"})
    assert liste.status_code == 200
    assert {objet["id"] for objet in liste.json()["objets"]} == {"lea-1", "lea-2"}

    detail = client.get(f"{BASE}/objets/out-1", params={"historique": "true"})
    assert detail.status_code == 200
    assert [objet["type"] for objet in detail.json()["chaine"]] == [
        "SITUATION", "INVESTIGATION", "DECISION", "INITIATIVE", "OUTCOME"]

    synthese = client.get(f"{BASE}/synthese")
    assert synthese.status_code == 200
    assert synthese.json()["total"] == 7
    assert synthese.json()["types"]["LEARNING"] == 2
