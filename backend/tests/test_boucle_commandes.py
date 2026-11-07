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

from auth import acteur as acteur_courant
from meridian.adapters.inbound.http import boucle as boucle_routes
from meridian.adapters.outbound.postgres import boucle, rls
from meridian.application import commandes_boucle
from meridian.ports.boucle import ObjetInvalide

TENANT = "local"
BASE = "/api/boucle"
MAINTENANT = "2026-10-01T08:00:00+00:00"
CHAMPS_LEGACY = {
    "niveau": "strategique",
    "genre": "a_confirmer",
    "raison": "migré du legacy",
    "quand": "2026-10-01T08:00:00+00:00",
    "travail_id": "case-1",
    "jumeau_cible": "paiements",
    "urgence": "haute",
    "reponse": {"par": "paiements"},
}


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

    def execute(self, sql, params=()):
        """Utilisé par ``rls.contexte_tenant`` pour poser le tenant local."""
        self.requetes.append((" ".join(str(sql).split()), tuple(params)))
        return None

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
            if "ON CONFLICT" in sql and (tenant, identifiant) in self.magasin.objets:
                return []
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

        if sql.startswith("UPDATE objet_entreprise SET donnees = %s"):
            donnees, mode, tenant, identifiant = params[:4]
            version_attendue = params[4] if "AND version = %s" in sql else None
            ancien = self.magasin.objets.get((tenant, identifiant))
            if ancien is None:
                return []
            if version_attendue is not None and ancien["version"] != version_attendue:
                return []
            ligne = copy.deepcopy(ancien)
            ligne["donnees"] = _donnees(donnees)
            if mode:
                ligne["mode"] = mode
            ligne["version"] = ancien["version"] + 1
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


def _app(acteur: str = "demo") -> TestClient:
    app = FastAPI()
    app.dependency_overrides[acteur_courant] = lambda: acteur
    api = APIRouter(prefix="/api")
    api.include_router(boucle_routes.router)
    app.include_router(api)
    return TestClient(app)


def _client(
    monkeypatch, magasin: _Magasin | None = None, *, acteur: str = "demo",
) -> tuple[TestClient, _Magasin]:
    magasin = magasin or _Magasin()
    monkeypatch.delenv("AUTH_MODE", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("JUMEAU_PG_DSN", "postgresql://test/test")
    monkeypatch.setattr(boucle_routes.psycopg, "connect", lambda *_, **__: _Connexion(magasin))
    return _app(acteur), magasin


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
    source = _objet("sit-1", type_="SITUATION", famille="emergence", mode="OBSERVED")
    lire = Mock(side_effect=[source, _lire_resultat(
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
    assert conn.transactions == 2
    assert lire.call_args_list[0].kwargs["as_dict"] is True
    assert lire.call_args_list[0].kwargs["for_update"] is True
    objets = enregistrer.call_args.kwargs["objets"]
    assert enregistrer.call_args.kwargs["historique"] is True
    assert enregistrer.call_args.kwargs["creer"] is True
    assert [objet["id"] for objet in objets] == ["inv-1"]
    assert objets[0]["situation_id"] == "sit-1"


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
        appel(_ConnexionFactice())

    assert erreur.value.role == role
    enregistrer.assert_not_called()


def test_trancher_une_decision_deja_tranchee_est_refuse(monkeypatch):
    decision = _objet(
        "dec-1", type_="DECISION", famille="decision", mode="DECLARED",
        donnees={"investigation_id": "inv-1", "options": ["A"],
                 "statut": "DECIDED", "acteur": "comité", "choix": "A"})
    monkeypatch.setattr(boucle, "lire_boucle", Mock(return_value=decision))
    enregistrer = Mock()
    monkeypatch.setattr(boucle, "enregistrer_boucle", enregistrer)

    with pytest.raises(boucle.BoucleInvalide):
        commandes_boucle.trancher_decision(
            boucle, _ConnexionFactice(), TENANT, "dec-1", acteur="autre", choix="A")

    enregistrer.assert_not_called()


def test_trancher_utilise_la_version_lue_pour_l_ecriture_optimiste(monkeypatch):
    source = _objet(
        "dec-1", type_="DECISION", famille="decision", mode="DECLARED", version=5,
        donnees={"investigation_id": "inv-1", "options": ["A"], "statut": "PROPOSED"})
    monkeypatch.setattr(boucle, "lire_boucle", Mock(
        side_effect=[source, _lire_resultat("dec-1", "DECISION")]))
    patch = {"statut": "DECIDED", "acteur": "comité", "choix": "A"}
    monkeypatch.setattr(boucle, "donnees_de", Mock(return_value=patch))
    fusionner = Mock(return_value={})
    monkeypatch.setattr(boucle, "fusionner_donnees", fusionner)
    conn = _ConnexionFactice()

    commandes_boucle.trancher_decision(
        boucle, conn, TENANT, "dec-1", acteur="comité", choix="A")

    assert conn.transactions == 1
    assert fusionner.call_args.args[2] == "dec-1"
    assert fusionner.call_args.args[3] == patch
    assert fusionner.call_args.kwargs["historique"] is True
    assert fusionner.call_args.kwargs["version_attendue"] == 5


def test_lancer_initiative_persiste_uniquement_l_initiative_et_le_lien(monkeypatch):
    source = _objet(
        "dec-1", type_="DECISION", famille="decision", mode="DECLARED", version=2,
        donnees={"investigation_id": "inv-1", "options": ["A"],
                 "statut": "DECIDED", "acteur": "comité", "choix": "A"})
    monkeypatch.setattr(boucle, "lire_boucle", Mock(
        side_effect=[source, _lire_resultat("ini-1", "INITIATIVE")]))
    enregistrer = Mock(return_value=[])
    monkeypatch.setattr(boucle, "enregistrer_boucle", enregistrer)
    fusionner = Mock(return_value={})
    monkeypatch.setattr(boucle, "fusionner_donnees", fusionner)
    conn = _ConnexionFactice()

    commandes_boucle.lancer_initiative(boucle, conn, TENANT, "dec-1", id="ini-1")

    assert conn.transactions == 2
    objets = enregistrer.call_args.kwargs["objets"]
    assert enregistrer.call_args.kwargs["creer"] is True
    assert [objet["type"] for objet in objets] == ["INITIATIVE"]
    assert objets[0]["decision_id"] == "dec-1"
    assert fusionner.call_args.args[3] == {"initiative_id": "ini-1"}
    assert fusionner.call_args.kwargs["version_attendue"] == 2


def test_mesurer_outcome_refuse_une_mesure_vide(monkeypatch):
    initiative = _objet(
        "ini-1", type_="INITIATIVE", famille="decision", mode="DECLARED",
        donnees={"decision_id": "dec-1"})
    monkeypatch.setattr(boucle, "lire_boucle", Mock(return_value=initiative))
    enregistrer = Mock()
    monkeypatch.setattr(boucle, "enregistrer_boucle", enregistrer)

    with pytest.raises(boucle.BoucleInvalide):
        commandes_boucle.mesurer_outcome(
            boucle, _ConnexionFactice(), TENANT, "ini-1", {})
    enregistrer.assert_not_called()


def test_capitaliser_depuis_investigation_relie_la_source(monkeypatch):
    investigation = _objet(
        "inv-1", type_="INVESTIGATION", famille="investigation", mode="DECLARED",
        donnees={"situation_id": "sit-1"})
    monkeypatch.setattr(boucle, "lire_boucle", Mock(
        side_effect=[investigation, _lire_resultat("lea-1", "LEARNING")]))
    enregistrer = Mock(return_value=[])
    monkeypatch.setattr(boucle, "enregistrer_boucle", enregistrer)
    conn = _ConnexionFactice()

    resultat = commandes_boucle.capitaliser_learning_depuis_investigation(
        boucle, conn, TENANT, "inv-1", id="lea-1", enonce="L'enquête est réutilisable")

    assert resultat.objet["id"] == "lea-1"
    assert conn.transactions == 2
    objets = enregistrer.call_args.kwargs["objets"]
    assert enregistrer.call_args.kwargs["creer"] is True
    assert objets[0]["investigation_ids"] == ["inv-1"]
    assert objets[0]["outcome_ids"] == []


def test_une_source_d_un_autre_tenant_est_refusee(monkeypatch):
    situation = _objet("sit-1", tenant="banque")
    monkeypatch.setattr(boucle, "lire_boucle", Mock(return_value=situation))
    enregistrer = Mock()
    monkeypatch.setattr(boucle, "enregistrer_boucle", enregistrer)

    with pytest.raises(commandes_boucle.TransitionRefusee):
        commandes_boucle.ouvrir_investigation(
            boucle, _ConnexionFactice(), TENANT, "sit-1")

    enregistrer.assert_not_called()


def test_une_source_de_mauvais_type_est_refusee(monkeypatch):
    investigation = _objet(
        "inv-1", type_="INVESTIGATION", famille="investigation", mode="DECLARED",
        donnees={"situation_id": "sit-1"})
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
        commandes_boucle.ouvrir_investigation(
            boucle, _ConnexionFactice(), TENANT, "   ")

    lire.assert_not_called()


# --------------------------------------------------------------------------- #
# Routes HTTP : chaîne complète, codes d'erreur, idempotence et non-régression.
# --------------------------------------------------------------------------- #


def test_la_chaine_complete_est_operationnelle(monkeypatch):
    client, _ = _client(monkeypatch, acteur="comité-cartes")
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
    assert situation.json()["type"] == "SITUATION"
    assert situation.json()["role"] == "situation"
    assert situation.json()["objet"]["id"] == "sit-1"
    assert situation.json()["idempotency_key"] is None

    investigation = _post(client, "/situations/sit-1/investigations", {"id": "inv-1"})
    assert investigation.status_code == 201
    assert [objet["type"] for objet in investigation.json()["chaine"]] == [
        "SITUATION", "INVESTIGATION"]
    assert investigation.json()["objet"]["type"] == "INVESTIGATION"

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
    assert tranchee.json()["objet"]["version"] == 2
    assert "_historique" not in tranchee.json()["objet"]["donnees"]
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


def test_la_reponse_de_transition_a_un_contrat_stable(monkeypatch):
    client, _ = _client(monkeypatch)

    reponse = _post(client, "/situations", {"titre": "Délai"})

    assert reponse.status_code == 201
    assert set(reponse.json()) == {
        "tenant", "objet", "type", "role", "chaine", "historique", "idempotency_key",
    }


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
    assert reponse.json()["objet"]["titre"] == "Le délai dépasse la cible"


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

    def enregistrer_avec_echec(conn, tenant, payload, *, creer=False):
        if payload.get("type") == "INITIATIVE":
            raise psycopg.OperationalError("échec simulé")
        return vrai(conn, tenant, payload, creer=creer)

    monkeypatch.setattr(boucle.entreprise_depot, "enregistrer_objet", enregistrer_avec_echec)

    reponse = _post(client, "/decisions/dec-1/initiatives", {"id": "ini-1"})

    assert reponse.status_code == 503
    assert magasin.objets[(TENANT, "dec-1")] == avant
    assert (TENANT, "ini-1") not in magasin.objets


def test_une_erreur_de_lien_annule_la_creation(monkeypatch):
    client, magasin = _client(monkeypatch)
    assert _post(client, "/situations", {
        "id": "sit-1", "titre": "Délai"}).status_code == 201
    assert _post(client, "/situations/sit-1/investigations", {"id": "inv-1"}).status_code == 201
    assert _post(client, "/investigations/inv-1/decisions", {
        "id": "dec-1", "options": ["Automatiser"]}).status_code == 201
    assert _post(client, "/decisions/dec-1/trancher", {
        "choix": "Automatiser"}).status_code == 200
    avant = copy.deepcopy(magasin.objets[(TENANT, "dec-1")])
    monkeypatch.setattr(boucle, "fusionner_donnees", Mock(
        side_effect=psycopg.OperationalError("échec du lien")))

    reponse = _post(client, "/decisions/dec-1/initiatives", {"id": "ini-1"})

    assert reponse.status_code == 503
    assert (TENANT, "ini-1") not in magasin.objets
    assert magasin.objets[(TENANT, "dec-1")] == avant


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
    ("/situations/sit-x/investigations", {"question": "x" * 2001}),
    ("/investigations/inv-x/decisions", {"options": []}),
    ("/investigations/inv-x/decisions", {"options": ["  "]}),
    ("/decisions/dec-x/trancher", {"choix": "   "}),
    ("/decisions/dec-x/trancher", {"acteur": "a", "choix": ""}),
    ("/decisions/dec-x/trancher", {"choix": "A", "decide_le": "pas-une-date"}),
    ("/initiatives/ini-x/outcomes", {}),
    ("/initiatives/ini-x/outcomes", {"mesure": {}}),
    ("/initiatives/ini-x/outcomes", {"mesure": {"valeur": 1}, "mesure_le": "pas-une-date"}),
    ("/outcomes/out-x/learnings", {"enonce": "   "}),
    ("/outcomes/out-x/learnings", {"enonce": "x" * 5001}),
    ("/investigations/inv-x/learnings", {}),
    ("/situations", {"statut": "CANDIDATE"}),
    ("/situations", {"titre": "Délai", "mode": "INCONNU"}),
    ("/situations", {"id": "   ", "titre": "Délai"}),
    ("/situations", {"titre": "Délai", "description": "x" * 10001}),
])
def test_une_validation_invalide_est_422(monkeypatch, chemin, corps):
    client, _ = _client(monkeypatch)

    reponse = _post(client, chemin, corps)

    assert reponse.status_code == 422


def test_x_espace_est_valide_puis_ignore_sur_les_post(monkeypatch):
    client, _ = _client(monkeypatch)

    reponse = _post(client, "/situations", {"titre": "Délai"},
                    headers={"X-Espace": "espace-paiements"})
    assert reponse.status_code == 201

    inconnu = _post(client, "/situations", {"titre": "Autre"},
                    headers={"X-Espace": "espace-inconnu"})
    assert inconnu.status_code == 400


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


def test_un_id_existant_ne_surcharge_pas_un_objet(monkeypatch):
    client, magasin = _client(monkeypatch)
    assert _post(client, "/situations", {
        "id": "sit-victime", "titre": "Victime"}).status_code == 201
    avant = copy.deepcopy(magasin.objets[(TENANT, "sit-victime")])
    assert _post(client, "/situations", {
        "id": "sit-source", "titre": "Source"}).status_code == 201

    reponse = _post(client, "/situations/sit-source/investigations", {
        "id": "sit-victime", "titre": "Écrasement"})

    assert reponse.status_code == 409
    assert magasin.objets[(TENANT, "sit-victime")] == avant


def test_les_donnees_legacy_survivent_aux_transitions(monkeypatch):
    client, magasin = _client(monkeypatch)
    _chaine(client)
    magasin.objets[(TENANT, "ini-1")]["donnees"].update(copy.deepcopy(CHAMPS_LEGACY))

    assert _post(client, "/initiatives/ini-1/outcomes", {
        "id": "out-2", "mesure": {"valeur": 3}}).status_code == 201
    initiative = client.get(f"{BASE}/objets/ini-1").json()["objet"]
    assert initiative["donnees"]["outcome_ids"] == ["out-1", "out-2"]
    for cle, valeur in CHAMPS_LEGACY.items():
        assert initiative["donnees"][cle] == valeur

    assert _post(client, "/investigations/inv-1/decisions", {
        "id": "dec-2", "options": ["A"]}).status_code == 201
    magasin.objets[(TENANT, "dec-2")]["donnees"].update(copy.deepcopy(CHAMPS_LEGACY))
    assert _post(client, "/decisions/dec-2/trancher", {"choix": "A"}).status_code == 200
    decision = client.get(f"{BASE}/objets/dec-2").json()["objet"]
    assert decision["donnees"]["statut"] == "DECIDED"
    for cle, valeur in CHAMPS_LEGACY.items():
        assert decision["donnees"][cle] == valeur


def test_une_lecture_perimee_est_refusee_en_409(monkeypatch):
    client, magasin = _client(monkeypatch)
    _chaine(client)
    assert _post(client, "/investigations/inv-1/decisions", {
        "id": "dec-2", "options": ["A"]}).status_code == 201
    perime = copy.deepcopy(magasin.objets[(TENANT, "dec-2")])
    assert _post(client, "/decisions/dec-2/trancher", {"choix": "A"}).status_code == 200
    etat = copy.deepcopy(magasin.objets[(TENANT, "dec-2")])
    vrai_lire = boucle.lire_boucle

    def lire_perime(conn, tenant, objet_id, **kwargs):
        if objet_id == "dec-2" and not kwargs.get("historique"):
            return copy.deepcopy(perime)
        return vrai_lire(conn, tenant, objet_id, **kwargs)

    monkeypatch.setattr(boucle, "lire_boucle", lire_perime)

    reponse = _post(client, "/decisions/dec-2/trancher", {"choix": "A"})

    assert reponse.status_code == 409
    assert magasin.objets[(TENANT, "dec-2")] == etat


def test_les_outcomes_sont_ajoutes_sans_perte_de_lien(monkeypatch):
    client, _ = _client(monkeypatch)
    _chaine(client)

    assert _post(client, "/initiatives/ini-1/outcomes", {
        "id": "out-2", "mesure": {"valeur": 3}}).status_code == 201

    initiative = client.get(f"{BASE}/objets/ini-1").json()["objet"]
    assert initiative["donnees"]["outcome_ids"] == ["out-1", "out-2"]


def test_une_decision_ne_peut_avoir_deux_initiatives(monkeypatch):
    client, _ = _client(monkeypatch)
    _chaine(client)

    reponse = _post(client, "/decisions/dec-1/initiatives", {"id": "ini-2"})

    assert reponse.status_code == 409


def test_l_acteur_authentifie_prime_sur_le_corps(monkeypatch):
    client, _ = _client(monkeypatch, acteur="alice")
    assert _post(client, "/situations", {"id": "sit-1", "titre": "Délai"}).status_code == 201
    assert _post(client, "/situations/sit-1/investigations", {"id": "inv-1"}).status_code == 201
    assert _post(client, "/investigations/inv-1/decisions", {
        "id": "dec-1", "options": ["A"]}).status_code == 201

    reponse = _post(client, "/decisions/dec-1/trancher", {
        "acteur": "pirate", "choix": "A"})

    assert reponse.status_code == 200
    decision = client.get(f"{BASE}/objets/dec-1").json()["objet"]
    assert decision["donnees"]["acteur"] == "alice"


def test_un_learning_force_statut_et_mode(monkeypatch):
    client, _ = _client(monkeypatch)
    _chaine(client)

    reponse = _post(client, "/outcomes/out-1/learnings", {
        "id": "lea-force", "enonce": "Leçon",
        "statut": "CONFIRMED", "mode": "DECLARED"})

    assert reponse.status_code == 201
    learning = client.get(f"{BASE}/objets/lea-force").json()["objet"]
    assert learning["donnees"]["statut"] == "PROPOSED"
    assert learning["mode"] == "INFERRED"


def test_une_decision_incomplete_est_409_pas_422(monkeypatch):
    client, magasin = _client(monkeypatch)
    _chaine(client)
    assert _post(client, "/investigations/inv-1/decisions", {
        "id": "dec-2", "options": ["A"]}).status_code == 201
    del magasin.objets[(TENANT, "dec-2")]["donnees"]["investigation_id"]

    reponse = _post(client, "/decisions/dec-2/trancher", {"choix": "A"})

    assert reponse.status_code == 409


def test_une_decision_sans_options_est_409(monkeypatch):
    client, magasin = _client(monkeypatch)
    _chaine(client)
    assert _post(client, "/investigations/inv-1/decisions", {
        "id": "dec-2", "options": ["A"]}).status_code == 201
    magasin.objets[(TENANT, "dec-2")]["donnees"]["options"] = []

    reponse = _post(client, "/decisions/dec-2/trancher", {"choix": "A"})

    assert reponse.status_code == 409


def test_une_initiative_incomplete_est_409_pas_422(monkeypatch):
    client, magasin = _client(monkeypatch)
    _chaine(client)
    del magasin.objets[(TENANT, "ini-1")]["donnees"]["decision_id"]

    reponse = _post(client, "/initiatives/ini-1/outcomes", {
        "id": "out-x", "mesure": {"valeur": 1}})

    assert reponse.status_code == 409


def test_une_initiative_avec_decision_ref_seul_est_acceptee(monkeypatch):
    client, magasin = _client(monkeypatch)
    _chaine(client)
    donnees = magasin.objets[(TENANT, "ini-1")]["donnees"]
    donnees.pop("decision_id", None)
    donnees["decision_ref"] = "dec-1"

    canonique = boucle.lire_boucle(_Connexion(magasin), TENANT, "ini-1", as_dict=False)
    assert isinstance(canonique, boucle.Initiative)
    assert canonique.decision_id == "dec-1"

    reponse = _post(client, "/initiatives/ini-1/outcomes", {
        "id": "out-ref", "mesure": {"valeur": 2}})

    assert reponse.status_code == 201
    assert [objet["type"] for objet in reponse.json()["chaine"]] == [
        "SITUATION", "INVESTIGATION", "DECISION", "INITIATIVE", "OUTCOME"]
    assert reponse.json()["objet"]["donnees"]["initiative_id"] == "ini-1"


def test_une_decision_avec_investigation_ref_seul_est_acceptee(monkeypatch):
    client, magasin = _client(monkeypatch)
    assert _post(client, "/situations", {"id": "sit-1", "titre": "Délai"}).status_code == 201
    assert _post(client, "/situations/sit-1/investigations", {"id": "inv-1"}).status_code == 201
    assert _post(client, "/investigations/inv-1/decisions", {
        "id": "dec-1", "options": ["A"]}).status_code == 201
    donnees = magasin.objets[(TENANT, "dec-1")]["donnees"]
    donnees.pop("investigation_id", None)
    donnees["investigation_ref"] = "inv-1"

    reponse = _post(client, "/decisions/dec-1/trancher", {"choix": "A"})

    assert reponse.status_code == 200
    assert reponse.json()["objet"]["donnees"]["investigation_id"] == "inv-1"


def test_lancer_initiative_accepte_une_decision_decidee_sans_options(monkeypatch):
    client, magasin = _client(monkeypatch)
    assert _post(client, "/situations", {"id": "sit-1", "titre": "Délai"}).status_code == 201
    assert _post(client, "/situations/sit-1/investigations", {"id": "inv-1"}).status_code == 201
    assert _post(client, "/investigations/inv-1/decisions", {
        "id": "dec-1", "options": ["A"]}).status_code == 201
    assert _post(client, "/decisions/dec-1/trancher", {"choix": "A"}).status_code == 200
    magasin.objets[(TENANT, "dec-1")]["donnees"].pop("options", None)

    reponse = _post(client, "/decisions/dec-1/initiatives", {"id": "ini-1"})

    assert reponse.status_code == 201
    assert reponse.json()["objet"]["donnees"]["decision_id"] == "dec-1"


def test_un_acteur_declare_non_textuel_est_ignore(monkeypatch):
    client, _ = _client(monkeypatch)
    assert _post(client, "/situations", {"id": "sit-1", "titre": "Délai"}).status_code == 201
    assert _post(client, "/situations/sit-1/investigations", {"id": "inv-1"}).status_code == 201
    assert _post(client, "/investigations/inv-1/decisions", {
        "id": "dec-1", "options": ["A"]}).status_code == 201

    reponse = _post(client, "/decisions/dec-1/trancher", {
        "acteur": {"x": 1}, "choix": "A"})

    assert reponse.status_code == 200
    assert reponse.json()["objet"]["donnees"]["acteur"] == "demo"


def test_lancer_initiative_sur_decision_avec_investigation_ref_seul(monkeypatch):
    client, magasin = _client(monkeypatch)
    assert _post(client, "/situations", {"id": "sit-1", "titre": "Délai"}).status_code == 201
    assert _post(client, "/situations/sit-1/investigations", {"id": "inv-1"}).status_code == 201
    assert _post(client, "/investigations/inv-1/decisions", {
        "id": "dec-1", "options": ["A"]}).status_code == 201
    assert _post(client, "/decisions/dec-1/trancher", {"choix": "A"}).status_code == 200
    donnees = magasin.objets[(TENANT, "dec-1")]["donnees"]
    donnees.pop("investigation_id", None)
    donnees["investigation_ref"] = "inv-1"

    reponse = _post(client, "/decisions/dec-1/initiatives", {"id": "ini-1"})

    assert reponse.status_code == 201
    assert [objet["type"] for objet in reponse.json()["chaine"]] == [
        "SITUATION", "INVESTIGATION", "DECISION", "INITIATIVE"]


def test_capitaliser_learning_sur_outcome_avec_initiative_ref_seul(monkeypatch):
    client, magasin = _client(monkeypatch)
    _chaine(client)
    donnees = magasin.objets[(TENANT, "out-1")]["donnees"]
    donnees.pop("initiative_id", None)
    donnees["initiative_ref"] = "ini-1"

    reponse = _post(client, "/outcomes/out-1/learnings", {
        "id": "lea-ref", "enonce": "Leçon"})

    assert reponse.status_code == 201
    assert [objet["type"] for objet in reponse.json()["chaine"]] == [
        "SITUATION", "INVESTIGATION", "DECISION", "INITIATIVE", "OUTCOME", "LEARNING"]


def test_des_liens_decision_contradictoires_sont_409(monkeypatch):
    client, magasin = _client(monkeypatch)
    _chaine(client)
    donnees = magasin.objets[(TENANT, "ini-1")]["donnees"]
    donnees["decision_id"] = "dec-1"
    donnees["decision_ref"] = "dec-2"

    reponse = _post(client, "/initiatives/ini-1/outcomes", {
        "id": "out-x", "mesure": {"valeur": 1}})

    assert reponse.status_code == 409


def test_des_liens_investigation_contradictoires_sont_409(monkeypatch):
    client, magasin = _client(monkeypatch)
    assert _post(client, "/situations", {"id": "sit-1", "titre": "Délai"}).status_code == 201
    assert _post(client, "/situations/sit-1/investigations", {"id": "inv-1"}).status_code == 201
    assert _post(client, "/investigations/inv-1/decisions", {
        "id": "dec-1", "options": ["A"]}).status_code == 201
    donnees = magasin.objets[(TENANT, "dec-1")]["donnees"]
    donnees["investigation_id"] = "inv-1"
    donnees["investigation_ref"] = "inv-2"

    reponse = _post(client, "/decisions/dec-1/trancher", {"choix": "A"})

    assert reponse.status_code == 409


def test_des_liens_initiative_contradictoires_sont_409(monkeypatch):
    client, magasin = _client(monkeypatch)
    _chaine(client)
    donnees = magasin.objets[(TENANT, "out-1")]["donnees"]
    donnees["initiative_id"] = "ini-1"
    donnees["initiative_ref"] = "ini-2"

    reponse = _post(client, "/outcomes/out-1/learnings", {"enonce": "Leçon"})

    assert reponse.status_code == 409


def test_enregistrer_boucle_fusionne_les_donnees_existantes():
    magasin = _Magasin()
    magasin.objets[(TENANT, "sit-fusion")] = _objet(
        "sit-fusion", type_="SITUATION", famille="emergence", mode="OBSERVED",
        titre="Avant", version=1,
        donnees={
            "legacy": "conservé",
            "signal_ids": ["sig-1"],
            "expression_id": "expr-1",
            "opportunity_ids": ["opp-1"],
            "risk_ids": ["risk-1"],
            "_historique": [{"version": 1, "titre": "Ancienne"}],
        })
    conn = _Connexion(magasin)
    situation = boucle.Situation(
        id="sit-fusion", tenant_id=TENANT, titre="Après",
        description="Nouvelle description")

    boucle.enregistrer_boucle(conn, TENANT, situation, historique=True)

    relu = magasin.objets[(TENANT, "sit-fusion")]
    assert relu["titre"] == "Après"
    assert relu["donnees"]["description"] == "Nouvelle description"
    assert relu["donnees"]["legacy"] == "conservé"
    assert relu["donnees"]["signal_ids"] == ["sig-1"]
    assert relu["donnees"]["expression_id"] == "expr-1"
    assert relu["donnees"]["opportunity_ids"] == ["opp-1"]
    assert relu["donnees"]["risk_ids"] == ["risk-1"]
    assert [entree["titre"] for entree in relu["donnees"]["_historique"]] == [
        "Ancienne", "Avant"]
    assert relu["version"] == 2


def test_fusionner_donnees_preserve_une_cle_legacy_sensible():
    magasin = _Magasin()
    magasin.objets[(TENANT, "ini-legacy")] = _objet(
        "ini-legacy", type_="INITIATIVE", famille="decision", mode="DECLARED",
        donnees={"decision_id": "dec-1", "token": "legacy-valeur"}, version=1)
    conn = _Connexion(magasin)

    boucle.fusionner_donnees(
        conn, TENANT, "ini-legacy", {"outcome_ids": ["out-1"]},
        historique=True, ajouter=("outcome_ids",), version_attendue=1)

    relu = magasin.objets[(TENANT, "ini-legacy")]
    assert relu["donnees"]["token"] == "legacy-valeur"
    assert relu["donnees"]["outcome_ids"] == ["out-1"]


def test_fusionner_donnees_refuse_un_secret_nouveau():
    magasin = _Magasin()
    magasin.objets[(TENANT, "ini-legacy")] = _objet(
        "ini-legacy", type_="INITIATIVE", famille="decision", mode="DECLARED",
        donnees={"decision_id": "dec-1"}, version=1)
    conn = _Connexion(magasin)

    with pytest.raises(ObjetInvalide):
        boucle.fusionner_donnees(
            conn, TENANT, "ini-legacy", {"token": "nouveau"}, version_attendue=1)


def _semer_parents(magasin: "_Magasin", *, decision: bool = False) -> None:
    magasin.objets[(TENANT, "sit-1")] = _objet(
        "sit-1", type_="SITUATION", famille="emergence", mode="OBSERVED",
        titre="Situation")
    magasin.objets[(TENANT, "inv-1")] = _objet(
        "inv-1", type_="INVESTIGATION", famille="investigation", mode="DECLARED",
        titre="Investigation", donnees={"situation_id": "sit-1"})
    if decision:
        magasin.objets[(TENANT, "dec-1")] = _objet(
            "dec-1", type_="DECISION", famille="decision", mode="DECLARED",
            titre="Décision",
            donnees={"investigation_id": "inv-1", "options": ["A"],
                     "statut": "DECIDED", "acteur": "comité", "choix": "A"})


def test_enregistrer_boucle_preserve_scenario_et_liens_inverses():
    magasin = _Magasin()
    _semer_parents(magasin)
    magasin.objets[(TENANT, "dec-liens")] = _objet(
        "dec-liens", type_="DECISION", famille="decision", mode="DECLARED",
        titre="Décision", version=1,
        donnees={
            "investigation_id": "inv-1", "options": ["A"], "statut": "DECIDED",
            "acteur": "comité", "choix": "A",
            "scenario_id": "scn-1", "initiative_id": "ini-1",
            "scenarios_rejetes": ["scn-0"],
            "hypothesis_ids": ["hyp-1"], "expert_ids": ["exp-1"],
            "scenario_ids": ["scn-1"], "signal_ids": ["sig-1"],
            "expression_id": "expr-1", "opportunity_ids": ["opp-1"],
            "risk_ids": ["risk-1"],
            "_historique": [{"version": 1, "titre": "Ancienne"}],
        })
    conn = _Connexion(magasin)
    decision = boucle.Decision(
        id="dec-liens", tenant_id=TENANT, investigation_id="inv-1",
        options=["A"], statut="DECIDED", acteur="comité", choix="A")

    boucle.enregistrer_boucle(conn, TENANT, decision, historique=True)

    relu = magasin.objets[(TENANT, "dec-liens")]
    assert relu["donnees"]["scenario_id"] == "scn-1"
    assert relu["donnees"]["initiative_id"] == "ini-1"
    assert relu["donnees"]["scenarios_rejetes"] == ["scn-0"]
    assert relu["donnees"]["hypothesis_ids"] == ["hyp-1"]
    assert relu["donnees"]["expert_ids"] == ["exp-1"]
    assert relu["donnees"]["scenario_ids"] == ["scn-1"]
    assert relu["donnees"]["signal_ids"] == ["sig-1"]
    assert relu["donnees"]["expression_id"] == "expr-1"
    assert relu["donnees"]["opportunity_ids"] == ["opp-1"]
    assert relu["donnees"]["risk_ids"] == ["risk-1"]
    assert [entree["titre"] for entree in relu["donnees"]["_historique"]] == [
        "Ancienne", "Décision"]


def test_enregistrer_boucle_preserve_outcome_ids_et_liens_b():
    magasin = _Magasin()
    _semer_parents(magasin, decision=True)
    magasin.objets[(TENANT, "ini-liens")] = _objet(
        "ini-liens", type_="INITIATIVE", famille="decision", mode="DECLARED",
        titre="Initiative", version=1,
        donnees={
            "decision_id": "dec-1", "outcome_ids": ["out-1"],
            "scenario_ids": ["scn-1"], "hypothesis_ids": ["hyp-1"],
            "expert_ids": ["exp-1"],
            "_historique": [{"version": 1, "titre": "Ancienne"}],
        })
    conn = _Connexion(magasin)
    initiative = boucle.Initiative(
        id="ini-liens", tenant_id=TENANT, decision_id="dec-1", titre="Initiative")

    boucle.enregistrer_boucle(conn, TENANT, initiative, historique=True)

    relu = magasin.objets[(TENANT, "ini-liens")]
    assert relu["donnees"]["outcome_ids"] == ["out-1"]
    assert relu["donnees"]["scenario_ids"] == ["scn-1"]
    assert relu["donnees"]["hypothesis_ids"] == ["hyp-1"]
    assert relu["donnees"]["expert_ids"] == ["exp-1"]
    assert [entree["titre"] for entree in relu["donnees"]["_historique"]] == [
        "Ancienne", "Initiative"]


def test_enregistrer_boucle_laisse_gagner_un_initiative_id_explicite():
    magasin = _Magasin()
    _semer_parents(magasin)
    magasin.objets[(TENANT, "dec-liens")] = _objet(
        "dec-liens", type_="DECISION", famille="decision", mode="DECLARED",
        titre="Décision", version=1,
        donnees={
            "investigation_id": "inv-1", "options": ["A"], "statut": "DECIDED",
            "acteur": "comité", "choix": "A",
            "scenario_id": "scn-1", "initiative_id": "ini-1",
        })
    conn = _Connexion(magasin)
    decision = boucle.Decision(
        id="dec-liens", tenant_id=TENANT, investigation_id="inv-1",
        options=["A"], statut="DECIDED", acteur="comité", choix="A",
        initiative_id="ini-2")

    boucle.enregistrer_boucle(conn, TENANT, decision)

    relu = magasin.objets[(TENANT, "dec-liens")]
    assert relu["donnees"]["initiative_id"] == "ini-2"
    assert relu["donnees"]["scenario_id"] == "scn-1"


def test_les_conflits_sont_declares_par_le_port():
    from meridian.adapters.outbound.postgres import entreprise_depot
    from meridian.ports.boucle import (ObjetExistant, ObjetInvalide,
                                       VersionRefusee)

    assert issubclass(ObjetExistant, ObjetInvalide)
    assert issubclass(VersionRefusee, ObjetInvalide)
    assert entreprise_depot.ObjetExistant is ObjetExistant
    assert entreprise_depot.VersionRefusee is VersionRefusee


def test_la_chaine_application_est_nettoyee_de_l_historique(monkeypatch):
    source = _objet(
        "dec-1", type_="DECISION", famille="decision", mode="DECLARED",
        donnees={"investigation_id": "inv-1", "options": ["A"], "statut": "PROPOSED"})
    chaine = [_objet(
        "dec-1", type_="DECISION", famille="decision", mode="DECLARED",
        donnees={"_historique": [{"version": 1}]})]
    monkeypatch.setattr(boucle, "lire_boucle", Mock(
        side_effect=[source, _lire_resultat("dec-1", "DECISION", chaine)]))
    monkeypatch.setattr(boucle, "donnees_de", Mock(return_value={"statut": "DECIDED"}))
    monkeypatch.setattr(boucle, "fusionner_donnees", Mock(return_value={}))

    resultat = commandes_boucle.trancher_decision(
        boucle, _ConnexionFactice(), TENANT, "dec-1", acteur="a", choix="A")

    assert "_historique" not in resultat.chaine[0]["donnees"]


def test_sans_version_supprime_la_cle_sans_forcer_un():
    decision = boucle.Decision(
        id="dec-1", tenant_id=TENANT, investigation_id="inv-1", options=["A"], version=7)

    charge = commandes_boucle._sans_version(decision)

    assert "version" not in charge


def test_le_contexte_rls_est_applique(monkeypatch):
    client, _ = _client(monkeypatch)
    monkeypatch.setenv("JUMEAU_RLS", "1")
    appels = []
    vrai = rls.contexte_tenant

    @contextmanager
    def espion(conn, tenant):
        appels.append(tenant)
        with vrai(conn, tenant) as identifiant:
            yield identifiant

    monkeypatch.setattr(boucle_routes.rls, "contexte_tenant", espion)

    reponse = _post(client, "/situations", {"titre": "Délai"})

    assert reponse.status_code == 201
    assert appels == [TENANT]


def test_trancher_sans_motif_conserve_le_rationale(monkeypatch):
    client, _ = _client(monkeypatch)
    assert _post(client, "/situations", {"id": "sit-1", "titre": "Délai"}).status_code == 201
    assert _post(client, "/situations/sit-1/investigations", {"id": "inv-1"}).status_code == 201
    assert _post(client, "/investigations/inv-1/decisions", {
        "id": "dec-1", "options": ["A"], "rationale": "raison initiale"}).status_code == 201

    assert _post(client, "/decisions/dec-1/trancher", {"choix": "A"}).status_code == 200

    decision = client.get(f"{BASE}/objets/dec-1").json()["objet"]
    assert decision["donnees"]["rationale"] == "raison initiale"


def test_trancher_avec_un_motif_vide_conserve_le_rationale(monkeypatch):
    client, _ = _client(monkeypatch)
    assert _post(client, "/situations", {"id": "sit-1", "titre": "Délai"}).status_code == 201
    assert _post(client, "/situations/sit-1/investigations", {"id": "inv-1"}).status_code == 201
    assert _post(client, "/investigations/inv-1/decisions", {
        "id": "dec-1", "options": ["A"], "rationale": "raison initiale"}).status_code == 201

    assert _post(client, "/decisions/dec-1/trancher", {
        "choix": "A", "motif": "   "}).status_code == 200

    decision = client.get(f"{BASE}/objets/dec-1").json()["objet"]
    assert decision["donnees"]["rationale"] == "raison initiale"


def test_une_unique_violation_est_409(monkeypatch):
    client, _ = _client(monkeypatch)

    def echec(*_, **__):
        raise psycopg.errors.UniqueViolation("doublon")

    monkeypatch.setattr(boucle.entreprise_depot, "enregistrer_objet", echec)

    reponse = _post(client, "/situations", {"titre": "Délai"})

    assert reponse.status_code == 409


def test_idempotency_key_est_refusee_explicitement(monkeypatch):
    client, magasin = _client(monkeypatch)

    reponse = _post(client, "/situations", {"titre": "Délai"},
                    headers={"Idempotency-Key": "cle-inv-1"})

    assert reponse.status_code == 501
    assert not magasin.objets


@pytest.mark.parametrize("valeur", ["", "   "])
def test_idempotency_key_blanche_est_aussi_refusee(monkeypatch, valeur):
    client, magasin = _client(monkeypatch)

    reponse = _post(client, "/situations", {"titre": "Délai"},
                    headers={"Idempotency-Key": valeur})

    assert reponse.status_code == 501
    assert not magasin.objets


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
