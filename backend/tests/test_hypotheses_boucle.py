"""C5c — Hypothèses canoniques depuis une Investigation.

Les tests de commande utilisent un magasin en mémoire qui satisfait la surface utile du
port ``BoucleStore`` et simule le lien inverse ``Investigation.hypothesis_ids``. Les tests
HTTP remplacent les commandes et la connexion : ils vérifient le contrat public et les
traductions d'erreurs sans dépendre d'un serveur. Les tests Postgres sont opt-in via
``JUMEAU_PG_DSN`` et prouvent la chaîne réelle
Situation → Investigation → Hypothèse, l'atomicité, l'isolation tenant et les transitions.
"""
from __future__ import annotations

import copy
import os
import uuid
from contextlib import contextmanager, nullcontext
from dataclasses import asdict, is_dataclass

import psycopg
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from meridian.adapters.inbound.http import boucle as boucle_routes
from meridian.adapters.outbound.postgres import boucle, depot, objets_exploitation, rls
from meridian.application import commandes_boucle
from meridian.domain import construction_objets_exploitation
from meridian.domain import objets_exploitation as domaine
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
DATES = {
    "cree_le": "2026-11-07T00:00:00+00:00",
    "observe_le": "2026-11-07T00:00:00+00:00",
    "valide_depuis": "2026-11-07T00:00:00+00:00",
}
DSN = os.environ.get("JUMEAU_PG_DSN")
besoin_pg = pytest.mark.skipif(not DSN, reason="JUMEAU_PG_DSN non défini")


def _ligne(objet) -> dict:
    donnees = asdict(objet) if is_dataclass(objet) else dict(objet)
    ligne = {cle: copy.deepcopy(donnees[cle]) for cle in CHAMPS if cle in donnees}
    ligne.setdefault("famille", "investigation")
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


def _investigation_row(
    identifiant: str = "inv-1", *, situation_id: str = "sit-1",
    tenant: str = TENANT, **donnees,
) -> dict:
    valeurs = {
        "titre": "Comprendre la latence",
        "question": "Pourquoi les paiements ralentissent-ils ?",
        "resume": "",
        "situation_id": situation_id,
        "statut": "OPEN",
        "perimetre": "",
        "proprietaire": None,
        "twin_ids": [],
        "hypothesis_ids": [],
        "expert_ids": [],
        "scenario_ids": [],
        "preuves": [],
        "confiance": 0.5,
    }
    valeurs.update(donnees)
    return {
        "id": identifiant,
        "tenant_id": tenant,
        "famille": "investigation",
        "type": "INVESTIGATION",
        "mode": "DECLARED",
        "titre": valeurs["titre"],
        "donnees": valeurs,
        "version": 1,
        "cree_le": "2026-11-07T00:00:00+00:00",
        "observe_le": "2026-11-07T00:00:00+00:00",
        "valide_depuis": "2026-11-07T00:00:00+00:00",
    }


def _hypothesis_row(
    identifiant: str = "hypothesis-1", *, investigation_id: str = "inv-1",
    tenant: str = TENANT, **donnees,
) -> dict:
    valeurs = {
        "titre": "Le contrôle synchrone bloque les paiements",
        "investigation_id": investigation_id,
        "enonce": "Le contrôle synchrone bloque les paiements",
        "statut": "OPEN",
        "conditions_test": ["mesurer le p95 sur trois flux"],
        "claim_ids_soutenants": [],
        "claim_ids_opposants": [],
        "expert_id": None,
        "motif": "",
        "preuves": [],
        "confiance": 0.5,
    }
    valeurs.update(donnees)
    return {
        "id": identifiant,
        "tenant_id": tenant,
        "famille": "investigation",
        "type": "HYPOTHESIS",
        "mode": "PROPOSED",
        "titre": valeurs["titre"],
        "donnees": valeurs,
        "version": 1,
        "cree_le": "2026-11-07T00:00:00+00:00",
        "observe_le": "2026-11-07T00:00:00+00:00",
        "valide_depuis": "2026-11-07T00:00:00+00:00",
    }


class _Store:
    """Port Boucle minimal, transaction annulable et lien inverse réel."""

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
            resultat["chaine"] = self._chaine(tenant_id, resultat)
            resultat["historique"] = copy.deepcopy(
                (resultat.get("donnees") or {}).get("_historique") or [])
        return resultat

    def _chaine(self, tenant_id, ligne):
        chaine = []
        vus = set()
        courant = ligne
        while courant is not None:
            identifiant = courant.get("id")
            if not identifiant or identifiant in vus:
                break
            vus.add(identifiant)
            chaine.append(copy.deepcopy(courant))
            donnees = courant.get("donnees") or {}
            type_objet = str(courant.get("type") or "").upper()
            parent_id = None
            if type_objet == "HYPOTHESIS":
                parent_id = donnees.get("investigation_id")
            elif type_objet == "INVESTIGATION":
                parent_id = donnees.get("situation_id")
            if not parent_id:
                break
            parent = self.objets.get(parent_id)
            if parent is None or parent.get("tenant_id") != tenant_id:
                break
            courant = parent
        return list(reversed(chaine))

    def nouvelle_hypothese(self, **champs):
        investigation = champs.pop("investigation", None)
        return construction_objets_exploitation.nouvelle_hypothese(
            investigation, **champs)

    def muer_hypothese(self, hypothese, vers, **champs):
        return construction_objets_exploitation.muer_hypothese(
            hypothese, vers, **champs)

    def enregistrer_boucle(self, conn, tenant_id=None, objets=None, **kwargs):
        objets = list(objets or [])
        self.enregistres_boucle.extend(copy.deepcopy(objets))
        for objet in objets:
            type_objet = str(getattr(objet, "type", "")).upper()
            if type_objet == "HYPOTHESIS":
                raise AssertionError(
                    "enregistrer_boucle ne doit pas persister une HYPOTHESIS")
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
            ancien = self.objets.get(ligne["id"])
            if ancien is not None and historique:
                versions = list((ancien.get("donnees") or {}).get("_historique") or [])
                versions.append({
                    "version": ancien.get("version"),
                    "titre": ancien.get("titre", ""),
                    "donnees": copy.deepcopy(ancien.get("donnees") or {}),
                })
                ligne["donnees"]["_historique"] = versions[-50:]
            self.objets[ligne["id"]] = ligne
            if self.echec_lien:
                raise RuntimeError("échec simulé du lien inverse")
            if ligne["type"] != "HYPOTHESIS":
                continue
            investigation_id = (ligne.get("donnees") or {}).get("investigation_id")
            if not investigation_id:
                continue
            parent = self.objets.get(investigation_id)
            if parent is None:
                raise RuntimeError(f"investigation introuvable : {investigation_id}")
            donnees = parent.setdefault("donnees", {})
            actuels = list(donnees.get("hypothesis_ids") or [])
            if ligne["id"] not in actuels:
                actuels.append(ligne["id"])
            donnees["hypothesis_ids"] = actuels
        return objets if not as_dict else [_ligne(objet) for objet in objets]

    def lister_objets_exploitation(
        self, conn, tenant_id, *, type_=None, investigation_id=None,
        decision_id=None, expression_id=None, statut=None, limite=100, as_dict=True,
    ):
        resultat = []
        for objet in self.objets.values():
            if objet.get("tenant_id") != tenant_id:
                continue
            if type_ is not None and objet.get("type") != type_:
                continue
            donnees = objet.get("donnees") or {}
            if investigation_id is not None and donnees.get("investigation_id") != investigation_id:
                continue
            if statut is not None and donnees.get("statut") != statut:
                continue
            resultat.append(copy.deepcopy(objet))
        resultat.sort(key=lambda objet: (objet.get("type"), objet.get("id")))
        return resultat[:max(1, min(int(limite), 1000))]


class _Connexion:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


# --------------------------------------------------------------------------- #
# Domaine : cycle de vie canonique et construction
# --------------------------------------------------------------------------- #


def test_le_cycle_canonique_des_hypotheses_est_explicite():
    assert domaine.STATUTS_HYPOTHESIS == (
        "OPEN", "STRENGTHENED", "WEAKENED", "REJECTED", "CONFIRMED")
    assert domaine.TRANSITIONS_HYPOTHESIS == {
        "OPEN": ("STRENGTHENED", "WEAKENED", "REJECTED", "CONFIRMED"),
        "STRENGTHENED": ("WEAKENED", "REJECTED", "CONFIRMED"),
        "WEAKENED": ("STRENGTHENED", "REJECTED", "CONFIRMED"),
        "CONFIRMED": (),
        "REJECTED": (),
    }


def test_nouvelle_hypothese_expose_les_champs_c5c():
    investigation = _investigation_row()
    hypothese = construction_objets_exploitation.nouvelle_hypothese(
        investigation,
        enonce="  Le contrôle synchrone bloque les paiements  ",
        conditions_test=["mesurer le p95"],
        claim_ids_soutenants=["claim-1"],
        claim_ids_opposants=["claim-2"],
        preuves=["preuve-1"],
        confiance=0.6,
    )

    assert hypothese.type == "HYPOTHESIS"
    assert hypothese.statut == "OPEN"
    assert hypothese.mode == "PROPOSED"
    assert hypothese.investigation_id == "inv-1"
    assert hypothese.enonce == "Le contrôle synchrone bloque les paiements"
    assert hypothese.conditions_test == ["mesurer le p95"]
    assert hypothese.claim_ids_soutenants == ["claim-1"]
    assert hypothese.claim_ids_opposants == ["claim-2"]
    assert hypothese.preuves == ["preuve-1"]
    assert hypothese.confiance == 0.6


def test_muer_hypothese_refuse_une_transition_non_autorisee():
    hypothese = construction_objets_exploitation.nouvelle_hypothese(
        _investigation_row(), enonce="Hypothèse", statut="CONFIRMED",
        preuves=["preuve-1"])

    with pytest.raises(ObjetsExploitationInvalide):
        construction_objets_exploitation.muer_hypothese(hypothese, "OPEN")
    assert hypothese.statut == "CONFIRMED"


def test_muer_hypothese_confirme_sans_preuve_est_refuse():
    hypothese = construction_objets_exploitation.nouvelle_hypothese(
        _investigation_row(), enonce="Hypothèse")

    with pytest.raises(ObjetsExploitationInvalide) as levee:
        construction_objets_exploitation.muer_hypothese(hypothese, "CONFIRMED")
    assert "preuve" in str(levee.value)
    assert hypothese.statut == "OPEN"


def test_muer_hypothese_rend_un_nouvel_objet_avec_motif_et_preuve():
    hypothese = construction_objets_exploitation.nouvelle_hypothese(
        _investigation_row(), enonce="Hypothèse")
    changee = construction_objets_exploitation.muer_hypothese(
        hypothese, "CONFIRMED",
        motif="  Trois mesures concordantes  ", preuves=["preuve-1"])

    assert changee is not hypothese
    assert changee.statut == "CONFIRMED"
    assert changee.motif == "Trois mesures concordantes"
    assert changee.preuves == ["preuve-1"]
    assert hypothese.statut == "OPEN"


@pytest.mark.parametrize(("champs", "erreur"), [
    ({"claim_ids_soutenants": ["   "]}, "claim_ids_soutenants"),
    ({"confiance": 1.2}, "confiance"),
])
def test_nouvelle_hypothese_refuse_les_champs_invalides(champs, erreur):
    with pytest.raises(ModeleInvalide) as levee:
        construction_objets_exploitation.nouvelle_hypothese(
            _investigation_row(), enonce="Hypothèse", **champs)
    assert erreur in str(levee.value)


def test_nouvelle_hypothese_ignore_les_conditions_vides():
    hypothese = construction_objets_exploitation.nouvelle_hypothese(
        _investigation_row(), enonce="Hypothèse",
        conditions_test=["", "  ", "mesurer le p95"])
    assert hypothese.conditions_test == ["mesurer le p95"]


# --------------------------------------------------------------------------- #
# Commandes
# --------------------------------------------------------------------------- #


def test_creer_hypothese_persiste_et_relie_l_investigation():
    store = _Store([_situation_row(), _investigation_row()])

    resultat = commandes_boucle.creer_hypothese(
        store, _Connexion(), TENANT, "inv-1",
        enonce="  Le contrôle synchrone bloque les paiements  ",
        conditions_test=["mesurer le p95"],
        claim_ids_soutenants=["claim-1"],
        claim_ids_opposants=["claim-2"],
        preuves=["preuve-1"],
        confiance=0.6,
        mode="OBSERVED",
    )

    assert resultat.objet["type"] == "HYPOTHESIS"
    assert resultat.objet["donnees"]["statut"] == "OPEN"
    assert resultat.objet["mode"] == "PROPOSED"
    assert resultat.objet["donnees"]["investigation_id"] == "inv-1"
    assert resultat.objet["titre"] == "Le contrôle synchrone bloque les paiements"
    assert resultat.objet["donnees"]["conditions_test"] == ["mesurer le p95"]
    assert resultat.objet["donnees"]["claim_ids_soutenants"] == ["claim-1"]
    assert resultat.objet["donnees"]["claim_ids_opposants"] == ["claim-2"]
    assert resultat.objet["donnees"]["confiance"] == 0.6
    assert store.objets["inv-1"]["donnees"]["hypothesis_ids"] == [resultat.objet["id"]]
    assert [element["type"] for element in resultat.chaine] == [
        "SITUATION", "INVESTIGATION", "HYPOTHESIS"]
    assert store.appels_lire[0] == {
        "tenant_id": TENANT, "objet_id": "inv-1",
        "historique": False, "for_update": True,
    }
    assert len(store.enregistres_objets) == 1
    assert store.enregistres_boucle == []


@pytest.mark.parametrize("champs", [
    {"statut": "CONFIRMED"},
    {"id": "client-id"},
])
def test_creer_hypothese_refuse_les_champs_serveur_du_client(champs):
    store = _Store([_investigation_row()])

    with pytest.raises(ObjetsExploitationInvalide) as levee:
        commandes_boucle.creer_hypothese(
            store, _Connexion(), TENANT, "inv-1",
            enonce="Hypothèse", **champs)

    assert next(iter(champs)) in str(levee.value)
    assert store.enregistres_objets == []
    assert not [objet for objet in store.objets.values()
                if objet["type"] == "HYPOTHESIS"]


def test_creer_hypothese_refuse_un_enonce_vide_before_persistence():
    store = _Store([_investigation_row()])
    with pytest.raises(ModeleInvalide) as levee:
        commandes_boucle.creer_hypothese(
            store, _Connexion(), TENANT, "inv-1", enonce="   ")
    assert "enonce" in str(levee.value)
    assert store.enregistres_objets == []


def test_creer_hypothese_investigation_absente_ou_hors_tenant_est_404():
    store = _Store()
    with pytest.raises(commandes_boucle.SourceIntrouvable) as levee:
        commandes_boucle.creer_hypothese(
            store, _Connexion(), TENANT, "inv-absent", enonce="Hypothèse")
    assert levee.value.role == "investigation"

    store = _Store([_investigation_row(tenant=AUTRE_TENANT)])
    with pytest.raises(commandes_boucle.SourceIntrouvable):
        commandes_boucle.creer_hypothese(
            store, _Connexion(), TENANT, "inv-1", enonce="Hors tenant")
    assert store.enregistres_objets == []


def test_creer_hypothese_refuse_une_source_qui_n_est_pas_une_investigation():
    source = {"id": "sit-1", "tenant_id": TENANT, "type": "SITUATION",
              "famille": "emergence", "mode": "OBSERVED", "titre": "",
              "donnees": {}, "version": 1}
    store = _Store([source])
    with pytest.raises(ObjetsExploitationInvalide) as levee:
        commandes_boucle.creer_hypothese(
            store, _Connexion(), TENANT, "sit-1", enonce="Mauvaise source")
    assert "INVESTIGATION" in str(levee.value)
    assert store.enregistres_objets == []


@pytest.mark.parametrize("statut", [
    "CLOSED", "CLOSE", "CLOTUREE", "FERMEE", "ARCHIVED", "ARCHIVEE", "closed",
    "COMPLETED", "COMPLETED_WITH_GAPS", "BUDGET_EXHAUSTED", "FAILED", "CANCELLED",
])
def test_creer_hypothese_refuse_une_investigation_fermee(statut):
    store = _Store([_investigation_row(statut=statut)])

    with pytest.raises(commandes_boucle.TransitionRefusee) as levee:
        commandes_boucle.creer_hypothese(
            store, _Connexion(), TENANT, "inv-1", enonce="Hypothèse")

    assert "fermée" in str(levee.value)
    assert statut.upper() in str(levee.value)
    assert store.enregistres_objets == []
    assert not [objet for objet in store.objets.values()
                if objet["type"] == "HYPOTHESIS"]
    assert store.objets["inv-1"]["donnees"]["hypothesis_ids"] == []


def test_creer_hypothese_accepte_une_investigation_ouverte():
    store = _Store([_investigation_row(statut="open")])

    resultat = commandes_boucle.creer_hypothese(
        store, _Connexion(), TENANT, "inv-1", enonce="Hypothèse")

    assert resultat.objet["donnees"]["statut"] == "OPEN"
    assert store.objets["inv-1"]["donnees"]["hypothesis_ids"] == [
        resultat.objet["id"]]


def test_creer_hypothese_annule_tout_si_le_lien_inverse_echoue():
    store = _Store([_situation_row(), _investigation_row()])
    store.echec_lien = True

    with pytest.raises(RuntimeError):
        commandes_boucle.creer_hypothese(
            store, _Connexion(), TENANT, "inv-1", enonce="Hypothèse partielle")

    assert not [objet for objet in store.objets.values()
                if objet["type"] == "HYPOTHESIS"]
    assert store.objets["inv-1"]["donnees"]["hypothesis_ids"] == []


def test_creer_hypothese_genere_un_identifiant_avec_le_prefixe_du_domaine():
    store = _Store([_investigation_row()])
    resultat = commandes_boucle.creer_hypothese(
        store, _Connexion(), TENANT, "inv-1", enonce="Préfixe serveur")
    assert resultat.objet["id"].startswith("hypothesis-")


def test_changer_statut_hypothese_valide_puis_refuse_une_transition_invalide():
    store = _Store([_situation_row(), _investigation_row(), _hypothesis_row()])

    resultat = commandes_boucle.changer_statut_hypothese(
        store, _Connexion(), TENANT, "hypothesis-1",
        "STRENGTHENED", motif="Trois mesures concordantes")

    assert resultat.objet["donnees"]["statut"] == "STRENGTHENED"
    assert resultat.objet["donnees"]["motif"] == "Trois mesures concordantes"
    assert resultat.historique[-1]["donnees"]["statut"] == "OPEN"

    with pytest.raises(commandes_boucle.TransitionRefusee):
        commandes_boucle.changer_statut_hypothese(
            store, _Connexion(), TENANT, "hypothesis-1", "OPEN")

    assert store.objets["hypothesis-1"]["donnees"]["statut"] == "STRENGTHENED"


def test_changer_statut_hypothese_confirme_sans_preuve_est_422():
    store = _Store([_situation_row(), _investigation_row(), _hypothesis_row()])

    with pytest.raises(ObjetsExploitationInvalide) as levee:
        commandes_boucle.changer_statut_hypothese(
            store, _Connexion(), TENANT, "hypothesis-1", "CONFIRMED")

    assert "preuve" in str(levee.value)
    assert store.objets["hypothesis-1"]["donnees"]["statut"] == "OPEN"


def test_changer_statut_hypothese_confirme_avec_preuve_ou_preuve_existante():
    store = _Store([_situation_row(), _investigation_row(), _hypothesis_row()])
    resultat = commandes_boucle.changer_statut_hypothese(
        store, _Connexion(), TENANT, "hypothesis-1", "CONFIRMED",
        preuves=["preuve-1"])
    assert resultat.objet["donnees"]["statut"] == "CONFIRMED"
    assert resultat.objet["donnees"]["preuves"] == ["preuve-1"]

    store = _Store([
        _situation_row(), _investigation_row(),
        _hypothesis_row("hypothesis-2", preuves=["preuve-existante"]),
    ])
    resultat = commandes_boucle.changer_statut_hypothese(
        store, _Connexion(), TENANT, "hypothesis-2", "CONFIRMED")
    assert resultat.objet["donnees"]["statut"] == "CONFIRMED"
    assert resultat.objet["donnees"]["preuves"] == ["preuve-existante"]


def test_changement_de_statut_refuse_un_statut_inconnu():
    store = _Store([_situation_row(), _investigation_row(), _hypothesis_row()])
    with pytest.raises(ObjetsExploitationInvalide) as levee:
        commandes_boucle.changer_statut_hypothese(
            store, _Connexion(), TENANT, "hypothesis-1", "MAGIQUE")
    assert "statut" in str(levee.value)
    assert store.enregistres_objets == []


def test_changement_de_statut_inconnu_ou_hors_tenant_est_404():
    store = _Store()
    with pytest.raises(commandes_boucle.SourceIntrouvable):
        commandes_boucle.changer_statut_hypothese(
            store, _Connexion(), TENANT, "absente", "STRENGTHENED")

    store = _Store([_hypothesis_row(tenant=AUTRE_TENANT)])
    with pytest.raises(commandes_boucle.SourceIntrouvable):
        commandes_boucle.changer_statut_hypothese(
            store, _Connexion(), TENANT, "hypothesis-1", "STRENGTHENED")


def test_changement_de_statut_refuse_un_mauvais_type_en_422():
    store = _Store([_situation_row(), _investigation_row(), _hypothesis_row()])

    with pytest.raises(ObjetsExploitationInvalide) as levee:
        commandes_boucle.changer_statut_hypothese(
            store, _Connexion(), TENANT, "inv-1", "STRENGTHENED")

    assert "HYPOTHESIS" in str(levee.value)
    assert store.enregistres_objets == []


def test_lister_hypotheses_filtre_investigation_statut_et_tenant():
    store = _Store([
        _situation_row(), _investigation_row("inv-1"), _investigation_row("inv-2"),
        _investigation_row("inv-autre", tenant=AUTRE_TENANT),
        _hypothesis_row("hypothesis-1", investigation_id="inv-1"),
        _hypothesis_row("hypothesis-2", investigation_id="inv-1",
                        statut="STRENGTHENED"),
        _hypothesis_row("hypothesis-3", investigation_id="inv-2"),
        _hypothesis_row("hypothesis-autre", investigation_id="inv-1",
                        tenant=AUTRE_TENANT),
    ])

    liste = commandes_boucle.lister_hypotheses(
        store, _Connexion(), TENANT, investigation_id="inv-1")
    assert [objet["id"] for objet in liste] == ["hypothesis-1", "hypothesis-2"]

    filtrees = commandes_boucle.lister_hypotheses(
        store, _Connexion(), TENANT, investigation_id="inv-1",
        statut="STRENGTHENED")
    assert [objet["id"] for objet in filtrees] == ["hypothesis-2"]

    toutes = commandes_boucle.lister_hypotheses(store, _Connexion(), TENANT)
    assert [objet["id"] for objet in toutes] == [
        "hypothesis-1", "hypothesis-2", "hypothesis-3"]

    assert len(commandes_boucle.lister_hypotheses(
        store, _Connexion(), TENANT, investigation_id="inv-1", limite=1)) == 1


def test_lister_hypotheses_refuse_un_statut_inconnu():
    store = _Store([_investigation_row()])
    with pytest.raises(ObjetsExploitationInvalide) as levee:
        commandes_boucle.lister_hypotheses(
            store, _Connexion(), TENANT, statut="MAGIQUE")
    assert "statut" in str(levee.value)


def test_lister_hypotheses_investigation_absente_est_404():
    store = _Store()
    with pytest.raises(commandes_boucle.SourceIntrouvable):
        commandes_boucle.lister_hypotheses(
            store, _Connexion(), TENANT, investigation_id="inv-absent")


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


def _resultat(identifiant: str = "hypothesis-1") -> commandes_boucle.ResultatTransition:
    situation = _situation_row()
    investigation = _investigation_row()
    hypothese = _hypothesis_row(identifiant)
    return commandes_boucle.ResultatTransition(
        objet=hypothese,
        chaine=[situation, investigation, hypothese],
        historique=[],
    )


def test_post_hypothese_retourne_le_contrat_c5c(monkeypatch):
    client = _client(monkeypatch)
    appels = []

    def creer(depot, conn, tenant, investigation_id, **champs):
        appels.append((tenant, investigation_id, champs))
        return _resultat()

    monkeypatch.setattr(boucle_routes.commandes_boucle, "creer_hypothese", creer)

    reponse = client.post(f"{BASE}/investigations/inv-1/hypotheses", json={
        "enonce": "  Le contrôle synchrone bloque les paiements  ",
        "conditions_test": ["mesurer le p95"],
        "claim_ids_soutenants": ["claim-1"],
        "claim_ids_opposants": ["claim-2"],
        "preuves": ["preuve-1"],
        "confiance": 0.6,
    })

    assert reponse.status_code == 201, reponse.text
    corps = reponse.json()
    assert corps["tenant"] == TENANT
    assert corps["objet"]["type"] == "HYPOTHESIS"
    assert corps["type"] == "HYPOTHESIS"
    assert corps["role"] == "hypothese"
    assert [element["type"] for element in corps["chaine"]] == [
        "SITUATION", "INVESTIGATION", "HYPOTHESIS"]
    assert corps["historique"] == []
    assert corps["idempotency_key"] is None
    assert appels[0][0] == TENANT
    assert appels[0][1] == "inv-1"
    assert appels[0][2]["enonce"] == "Le contrôle synchrone bloque les paiements"
    assert appels[0][2]["conditions_test"] == ["mesurer le p95"]
    assert appels[0][2]["claim_ids_soutenants"] == ["claim-1"]
    assert appels[0][2]["claim_ids_opposants"] == ["claim-2"]
    assert appels[0][2]["preuves"] == ["preuve-1"]
    assert appels[0][2]["confiance"] == 0.6
    assert "statut" not in appels[0][2]
    assert "mode" not in appels[0][2]
    assert "id" not in appels[0][2]
    assert "investigation_id" not in appels[0][2]


@pytest.mark.parametrize("corps", [
    {},
    {"enonce": "   "},
    {"enonce": "Valide", "statut": "CONFIRMED"},
    {"enonce": "Valide", "id": "client-id"},
    {"enonce": "Valide", "investigation_id": "inv-1"},
    {"enonce": "Valide", "mode": "OBSERVED"},
    {"enonce": "Valide", "expert_id": "expert-1"},
    {"enonce": "Valide", "confiance": 1.2},
    {"enonce": "Valide", "conditions_test": ["   "]},
    {"enonce": "Valide", "champ_inconnu": True},
])
def test_post_hypothese_valide_le_corps_avant_la_commande(monkeypatch, corps):
    client = _client(monkeypatch)
    monkeypatch.setattr(
        boucle_routes.commandes_boucle, "creer_hypothese",
        lambda *_, **__: pytest.fail("la commande ne doit pas être appelée"),
    )
    assert client.post(f"{BASE}/investigations/inv-1/hypotheses", json=corps).status_code == 422


def test_post_hypothese_expert_id_refuse_sans_ecriture(monkeypatch):
    """``expert_id`` reste hors du corps : C5e rattache les experts par contribution."""
    client = _client(monkeypatch)
    monkeypatch.setattr(
        boucle_routes.commandes_boucle, "creer_hypothese",
        lambda *_, **__: pytest.fail("aucune écriture ne doit être tentée"),
    )

    reponse = client.post(
        f"{BASE}/investigations/inv-1/hypotheses",
        json={"enonce": "Hypothèse", "expert_id": "expert-1"},
    )

    assert reponse.status_code == 422


def test_post_hypothese_traduit_les_erreurs(monkeypatch):
    client = _client(monkeypatch)

    @contextmanager
    def contexte(conn, tenant):
        yield tenant

    monkeypatch.setattr(boucle_routes.rls, "est_actif", lambda: True)
    monkeypatch.setattr(boucle_routes.rls, "contexte_tenant", contexte)

    for erreur, statut in [
        (commandes_boucle.SourceIntrouvable("investigation", "inv-x"), 404),
        (commandes_boucle.TransitionRefusee("transition refusée"), 409),
        (ObjetsExploitationInvalide("source invalide"), 422),
        (ObjetInvalide("secret refusé"), 400),
        (psycopg.OperationalError("panne"), 503),
    ]:
        def echouer(*_, _erreur=erreur, **__):
            raise _erreur

        monkeypatch.setattr(boucle_routes.commandes_boucle, "creer_hypothese", echouer)
        reponse = client.post(
            f"{BASE}/investigations/inv-1/hypotheses", json={"enonce": "Valide"})
        assert reponse.status_code == statut
        assert "Traceback" not in reponse.text


def test_post_hypothese_refuse_une_cle_d_idempotence(monkeypatch):
    client = _client(monkeypatch)
    reponse = client.post(
        f"{BASE}/investigations/inv-1/hypotheses",
        json={"enonce": "Valide"},
        headers={"Idempotency-Key": "cle-1"},
    )
    assert reponse.status_code == 501


def test_post_hypothese_pose_le_tenant_rls_et_transmet_x_tenant(monkeypatch):
    client = _client(monkeypatch)
    contextes = []

    @contextmanager
    def contexte(conn, tenant):
        contextes.append(tenant)
        yield tenant

    monkeypatch.setattr(boucle_routes.rls, "est_actif", lambda: True)
    monkeypatch.setattr(boucle_routes.rls, "contexte_tenant", contexte)
    appels = []

    def creer(depot, conn, tenant, investigation_id, **champs):
        appels.append((tenant, investigation_id))
        return _resultat()

    monkeypatch.setattr(boucle_routes.commandes_boucle, "creer_hypothese", creer)
    reponse = client.post(
        f"{BASE}/investigations/inv-1/hypotheses",
        json={"enonce": "Valide"},
        headers={"X-Tenant": "banque"},
    )

    assert reponse.status_code == 201
    assert reponse.json()["tenant"] == "banque"
    assert contextes == ["banque"]
    assert appels == [("banque", "inv-1")]


def test_la_reponse_creation_ne_laisse_pas_passer_un_secret(monkeypatch):
    client = _client(monkeypatch)
    resultat = _resultat()
    resultat.objet["donnees"]["preuves"] = [{"password": "s3cr3t"}]
    monkeypatch.setattr(
        boucle_routes.commandes_boucle, "creer_hypothese",
        lambda *_, **__: resultat)

    reponse = client.post(
        f"{BASE}/investigations/inv-1/hypotheses", json={"enonce": "Valide"})

    assert reponse.status_code == 201
    assert "s3cr3t" not in reponse.text
    assert reponse.json()["objet"]["donnees"]["preuves"] == [{"password": "***"}]


def test_sans_dsn_la_route_creation_repond_503(monkeypatch):
    monkeypatch.delenv("AUTH_MODE", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("JUMEAU_PG_DSN", raising=False)
    reponse = _app().post(
        f"{BASE}/investigations/inv-1/hypotheses", json={"enonce": "Valide"})
    assert reponse.status_code == 503
    assert "JUMEAU_PG_DSN" in reponse.json()["detail"]


def test_get_hypotheses_retourne_la_liste_filtree(monkeypatch):
    client = _client(monkeypatch)
    appels = []

    def lister(depot, conn, tenant, *, investigation_id=None, statut=None, limite=100):
        appels.append((tenant, investigation_id, statut, limite))
        return [_hypothesis_row()]

    monkeypatch.setattr(boucle_routes.commandes_boucle, "lister_hypotheses", lister)
    reponse = client.get(
        f"{BASE}/hypotheses",
        params={"investigation_id": "inv-1", "statut": "OPEN", "limite": 25},
        headers={"X-Tenant": "banque"},
    )

    assert reponse.status_code == 200
    assert reponse.json()["tenant"] == "banque"
    assert [objet["id"] for objet in reponse.json()["hypotheses"]] == ["hypothesis-1"]
    assert appels == [("banque", "inv-1", "OPEN", 25)]


def test_get_hypotheses_investigation_absente_repond_404(monkeypatch):
    client = _client(monkeypatch)

    def echouer(*_, **__):
        raise commandes_boucle.SourceIntrouvable("investigation", "inv-x")

    monkeypatch.setattr(boucle_routes.commandes_boucle, "lister_hypotheses", echouer)
    reponse = client.get(f"{BASE}/hypotheses", params={"investigation_id": "inv-x"})
    assert reponse.status_code == 404


def test_post_statut_hypothese_retourne_le_contrat(monkeypatch):
    client = _client(monkeypatch)
    appels = []

    def changer(depot, conn, tenant, hypothese_id, vers, **champs):
        appels.append((tenant, hypothese_id, vers, champs))
        return _resultat()

    monkeypatch.setattr(boucle_routes.commandes_boucle, "changer_statut_hypothese", changer)
    reponse = client.post(f"{BASE}/hypotheses/hypothesis-1/statut", json={
        "vers": "STRENGTHENED",
        "motif": "  Trois mesures concordantes  ",
        "preuves": ["preuve-1"],
    })

    assert reponse.status_code == 200, reponse.text
    corps = reponse.json()
    assert corps["objet"]["type"] == "HYPOTHESIS"
    assert corps["type"] == "HYPOTHESIS"
    assert corps["role"] == "hypothese"
    assert appels[0][0] == TENANT
    assert appels[0][1] == "hypothesis-1"
    assert appels[0][2] == "STRENGTHENED"
    assert appels[0][3]["motif"] == "Trois mesures concordantes"
    assert appels[0][3]["preuves"] == ["preuve-1"]


@pytest.mark.parametrize("corps", [
    {},
    {"vers": "   "},
    {"vers": "STRENGTHENED", "statut": "CONFIRMED"},
    {"vers": "STRENGTHENED", "champ_inconnu": True},
])
def test_post_statut_hypothese_valide_le_corps(monkeypatch, corps):
    client = _client(monkeypatch)
    monkeypatch.setattr(
        boucle_routes.commandes_boucle, "changer_statut_hypothese",
        lambda *_, **__: pytest.fail("la commande ne doit pas être appelée"))
    assert client.post(
        f"{BASE}/hypotheses/hypothesis-1/statut", json=corps).status_code == 422


def test_post_statut_hypothese_traduit_404_409_422_400_503(monkeypatch):
    client = _client(monkeypatch)
    for erreur, statut in [
        (commandes_boucle.SourceIntrouvable("hypothèse", "x"), 404),
        (commandes_boucle.TransitionRefusee("transition refusée"), 409),
        (ObjetsExploitationInvalide("statut inconnu"), 422),
        (ObjetInvalide("secret refusé"), 400),
        (psycopg.OperationalError("panne"), 503),
    ]:
        def echouer(*_, _erreur=erreur, **__):
            raise _erreur

        monkeypatch.setattr(
            boucle_routes.commandes_boucle, "changer_statut_hypothese", echouer)
        reponse = client.post(
            f"{BASE}/hypotheses/hypothesis-1/statut", json={"vers": "STRENGTHENED"})
        assert reponse.status_code == statut


def test_post_statut_hypothese_confirme_sans_preuve_repond_422(monkeypatch):
    client = _client(monkeypatch)

    def echouer(*_, **__):
        raise ObjetsExploitationInvalide(
            "une hypothèse CONFIRMED exige au moins une preuve")

    monkeypatch.setattr(
        boucle_routes.commandes_boucle, "changer_statut_hypothese", echouer)
    reponse = client.post(
        f"{BASE}/hypotheses/hypothesis-1/statut", json={"vers": "CONFIRMED"})
    assert reponse.status_code == 422
    assert "preuve" in reponse.json()["detail"]


def test_post_statut_hypothese_refuse_une_cle_d_idempotence(monkeypatch):
    client = _client(monkeypatch)
    reponse = client.post(
        f"{BASE}/hypotheses/hypothesis-1/statut",
        json={"vers": "STRENGTHENED"},
        headers={"Idempotency-Key": "cle-1"},
    )
    assert reponse.status_code == 501


# --------------------------------------------------------------------------- #
# Postgres réel : chaînes, liens inverses, transitions et atomicité
# --------------------------------------------------------------------------- #


def _client_pg(monkeypatch) -> TestClient:
    monkeypatch.delenv("AUTH_MODE", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("JUMEAU_PG_DSN", DSN)
    return _app()


def _nettoyer(tenant: str) -> None:
    with psycopg.connect(DSN, autocommit=True) as conn, \
            rls.contexte_tenant(conn, tenant):
        conn.execute(
            "DELETE FROM objet_entreprise WHERE tenant_id = %s", (tenant,))


def _pg_investigation(
    tenant: str, *, situation_id: str = "sit-c5c", investigation_id: str = "inv-c5c",
):
    with psycopg.connect(DSN) as conn:
        situation = {**_situation_row(situation_id), "tenant_id": tenant}
        boucle.enregistrer_boucle(conn, tenant, objets=[situation], historique=True)
        situation_lue = boucle.lire_boucle(
            conn, tenant, situation_id, as_dict=False)
        investigation_obj = boucle.ouvrir_investigation(
            situation_lue, id=investigation_id, tenant_id=tenant,
            titre="Comprendre la latence", question="Pourquoi ?")
        boucle.enregistrer_boucle(
            conn, tenant, objets=[investigation_obj], historique=True)
        return investigation_obj


@besoin_pg
def test_pg_creation_hypothese_chaine_liens_et_transitions(monkeypatch):
    tenant = f"c5c-{uuid.uuid4().hex[:10]}"
    client = _client_pg(monkeypatch)
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)

        assert client.post(
            f"{BASE}/situations",
            json={"id": "sit-c5c", "titre": "Latence des paiements"},
            headers={"X-Tenant": tenant},
        ).status_code == 201
        investigation = client.post(
            f"{BASE}/situations/sit-c5c/investigations",
            json={"id": "inv-c5c", "titre": "Comprendre",
                  "question": "Pourquoi les paiements ralentissent-ils ?"},
            headers={"X-Tenant": tenant},
        )
        assert investigation.status_code == 201, investigation.text
        investigation_id = investigation.json()["objet"]["id"]

        creation = client.post(
            f"{BASE}/investigations/{investigation_id}/hypotheses",
            json={
                "enonce": "Le contrôle synchrone bloque les paiements",
                "conditions_test": ["mesurer le p95"],
                "claim_ids_soutenants": ["claim-1"],
                "claim_ids_opposants": ["claim-2"],
                "confiance": 0.6,
            },
            headers={"X-Tenant": tenant},
        )
        assert creation.status_code == 201, creation.text
        hypothese_id = creation.json()["objet"]["id"]
        assert creation.json()["objet"]["donnees"]["statut"] == "OPEN"
        assert creation.json()["objet"]["mode"] == "PROPOSED"
        assert [element["type"] for element in creation.json()["chaine"]] == [
            "SITUATION", "INVESTIGATION", "HYPOTHESIS"]

        investigation_lue = client.get(
            f"{BASE}/objets/{investigation_id}", headers={"X-Tenant": tenant}
        ).json()["objet"]
        assert sorted(investigation_lue["donnees"]["hypothesis_ids"]) == [hypothese_id]

        lecture = client.get(
            f"{BASE}/objets/{hypothese_id}",
            params={"historique": True},
            headers={"X-Tenant": tenant},
        )
        assert lecture.status_code == 200
        assert [element["type"] for element in lecture.json()["chaine"]] == [
            "SITUATION", "INVESTIGATION", "HYPOTHESIS"]

        liste = client.get(
            f"{BASE}/hypotheses",
            params={"investigation_id": investigation_id, "statut": "OPEN"},
            headers={"X-Tenant": tenant},
        )
        assert liste.status_code == 200
        assert [objet["id"] for objet in liste.json()["hypotheses"]] == [hypothese_id]

        mauvais_type = client.post(
            f"{BASE}/hypotheses/{investigation_id}/statut",
            json={"vers": "STRENGTHENED"},
            headers={"X-Tenant": tenant},
        )
        assert mauvais_type.status_code == 422, mauvais_type.text

        secret = client.post(
            f"{BASE}/hypotheses/{hypothese_id}/statut",
            json={"vers": "STRENGTHENED", "preuves": [{"password": "s3cr3t"}]},
            headers={"X-Tenant": tenant},
        )
        assert secret.status_code == 400, secret.text
        with psycopg.connect(DSN) as conn:
            assert boucle.lire_boucle(
                conn, tenant, hypothese_id, as_dict=True
            )["donnees"]["statut"] == "OPEN"

        confirme_sans_preuve = client.post(
            f"{BASE}/hypotheses/{hypothese_id}/statut",
            json={"vers": "CONFIRMED"},
            headers={"X-Tenant": tenant},
        )
        assert confirme_sans_preuve.status_code == 422, confirme_sans_preuve.text

        renforcee = client.post(
            f"{BASE}/hypotheses/{hypothese_id}/statut",
            json={"vers": "STRENGTHENED", "motif": "Trois mesures concordantes"},
            headers={"X-Tenant": tenant},
        )
        assert renforcee.status_code == 200, renforcee.text
        assert renforcee.json()["objet"]["donnees"]["statut"] == "STRENGTHENED"
        assert renforcee.json()["historique"][-1]["donnees"]["statut"] == "OPEN"

        retour_invalide = client.post(
            f"{BASE}/hypotheses/{hypothese_id}/statut",
            json={"vers": "OPEN"},
            headers={"X-Tenant": tenant},
        )
        assert retour_invalide.status_code == 409

        confirmee = client.post(
            f"{BASE}/hypotheses/{hypothese_id}/statut",
            json={"vers": "CONFIRMED", "preuves": ["preuve-2"]},
            headers={"X-Tenant": tenant},
        )
        assert confirmee.status_code == 200, confirmee.text
        assert confirmee.json()["objet"]["donnees"]["statut"] == "CONFIRMED"
        assert "preuve-2" in confirmee.json()["objet"]["donnees"]["preuves"]

        terminale = client.post(
            f"{BASE}/hypotheses/{hypothese_id}/statut",
            json={"vers": "WEAKENED"},
            headers={"X-Tenant": tenant},
        )
        assert terminale.status_code == 409

        with psycopg.connect(DSN) as conn:
            assert "HYPOTHESIS" in boucle.TYPES_LECTURE
            assert "HYPOTHESIS" not in boucle.TYPES_BOUCLE
            objet = boucle.lire_boucle(conn, tenant, hypothese_id, as_dict=False)
            assert objet.type == "HYPOTHESIS"
            assert objet.investigation_id == investigation_id
            with pytest.raises(boucle.BoucleInvalide):
                boucle.enregistrer_boucle(conn, tenant, objets=[objet], historique=True)
    finally:
        _nettoyer(tenant)


@besoin_pg
def test_pg_http_investigation_fermee_refusee_et_ouverte_acceptee(monkeypatch):
    tenant = f"c5c-{uuid.uuid4().hex[:10]}"
    client = _client_pg(monkeypatch)
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)

        assert client.post(
            f"{BASE}/situations",
            json={"id": "sit-c5c", "titre": "Latence des paiements"},
            headers={"X-Tenant": tenant},
        ).status_code == 201
        investigation_fermee = client.post(
            f"{BASE}/situations/sit-c5c/investigations",
            json={
                "id": "inv-fermee",
                "titre": "Investigation fermée",
                "question": "Pourquoi les paiements ralentissent-ils ?",
                "statut": "CLOSED",
            },
            headers={"X-Tenant": tenant},
        )
        assert investigation_fermee.status_code == 201, investigation_fermee.text

        refusee = client.post(
            f"{BASE}/investigations/inv-fermee/hypotheses",
            json={"enonce": "Hypothèse interdite"},
            headers={"X-Tenant": tenant},
        )
        assert refusee.status_code == 409, refusee.text

        with psycopg.connect(DSN) as conn:
            nombre = conn.execute(
                "SELECT count(*) FROM objet_entreprise "
                "WHERE tenant_id = %s AND type = 'HYPOTHESIS'",
                (tenant,),
            ).fetchone()[0]
            investigation = boucle.lire_boucle(
                conn, tenant, "inv-fermee", as_dict=True)
        assert nombre == 0
        assert investigation["donnees"]["hypothesis_ids"] == []

        investigation_ouverte = client.post(
            f"{BASE}/situations/sit-c5c/investigations",
            json={
                "id": "inv-ouverte",
                "titre": "Investigation ouverte",
                "question": "Quel contrôle bloque les paiements ?",
                "statut": "OPEN",
            },
            headers={"X-Tenant": tenant},
        )
        assert investigation_ouverte.status_code == 201, investigation_ouverte.text

        acceptee = client.post(
            f"{BASE}/investigations/inv-ouverte/hypotheses",
            json={"enonce": "Le contrôle synchrone bloque les paiements"},
            headers={"X-Tenant": tenant},
        )
        assert acceptee.status_code == 201, acceptee.text
        identifiant = acceptee.json()["objet"]["id"]

        with psycopg.connect(DSN) as conn:
            investigation = boucle.lire_boucle(
                conn, tenant, "inv-ouverte", as_dict=True)
        assert investigation["donnees"]["hypothesis_ids"] == [identifiant]
    finally:
        _nettoyer(tenant)


@besoin_pg
def test_pg_creation_hypothese_secret_refusee_sans_ecriture(monkeypatch):
    tenant = f"c5c-{uuid.uuid4().hex[:10]}"
    client = _client_pg(monkeypatch)
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            _pg_investigation(tenant)

        reponse = client.post(
            f"{BASE}/investigations/inv-c5c/hypotheses",
            json={
                "enonce": "Hypothèse avec secret",
                "preuves": [{"password": "s3cr3t"}],
            },
            headers={"X-Tenant": tenant},
        )
        assert reponse.status_code == 400, reponse.text

        with psycopg.connect(DSN) as conn:
            nombre = conn.execute(
                "SELECT count(*) FROM objet_entreprise "
                "WHERE tenant_id = %s AND type = 'HYPOTHESIS'",
                (tenant,),
            ).fetchone()[0]
            investigation = boucle.lire_boucle(
                conn, tenant, "inv-c5c", as_dict=True)
        assert nombre == 0
        assert investigation["donnees"]["hypothesis_ids"] == []
    finally:
        _nettoyer(tenant)


@besoin_pg
def test_pg_http_expert_id_refuse_sans_ecriture(monkeypatch):
    tenant = f"c5c-{uuid.uuid4().hex[:10]}"
    client = _client_pg(monkeypatch)
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            _pg_investigation(tenant)

        reponse = client.post(
            f"{BASE}/investigations/inv-c5c/hypotheses",
            json={"enonce": "Hypothèse C5e", "expert_id": "expert-1"},
            headers={"X-Tenant": tenant},
        )
        assert reponse.status_code == 422, reponse.text

        with psycopg.connect(DSN) as conn:
            nombre = conn.execute(
                "SELECT count(*) FROM objet_entreprise "
                "WHERE tenant_id = %s AND type = 'HYPOTHESIS'",
                (tenant,),
            ).fetchone()[0]
            investigation = boucle.lire_boucle(
                conn, tenant, "inv-c5c", as_dict=True)
        assert nombre == 0
        assert investigation["donnees"]["hypothesis_ids"] == []
    finally:
        _nettoyer(tenant)


@besoin_pg
def test_pg_creation_est_atomique_si_le_lien_inverse_echoue(monkeypatch):
    tenant = f"c5c-{uuid.uuid4().hex[:10]}"
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            _pg_investigation(tenant)

        def echouer(*_, **__):
            raise RuntimeError("échec simulé du lien inverse")

        monkeypatch.setattr(objets_exploitation, "_persister_parent", echouer)
        with psycopg.connect(DSN) as conn, pytest.raises(RuntimeError):
            commandes_boucle.creer_hypothese(
                boucle, conn, tenant, "inv-c5c",
                enonce="Hypothèse partielle", confiance=0.5)

        with psycopg.connect(DSN) as conn:
            nombre = conn.execute(
                "SELECT count(*) FROM objet_entreprise "
                "WHERE tenant_id = %s AND type = 'HYPOTHESIS'",
                (tenant,),
            ).fetchone()[0]
            investigation = boucle.lire_boucle(
                conn, tenant, "inv-c5c", as_dict=True)
        assert nombre == 0
        assert investigation["donnees"]["hypothesis_ids"] == []
    finally:
        _nettoyer(tenant)


@besoin_pg
def test_pg_second_tenant_ne_voit_ni_ne_relie_les_hypotheses(monkeypatch):
    tenant = f"c5c-{uuid.uuid4().hex[:10]}"
    autre = f"{tenant}-autre"
    client = _client_pg(monkeypatch)
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            _pg_investigation(tenant)
            with psycopg.connect(DSN) as conn:
                commandes_boucle.creer_hypothese(
                    boucle, conn, tenant, "inv-c5c",
                    enonce="Hypothèse tenant A", confiance=0.5)

        reponse = client.post(
            f"{BASE}/investigations/inv-c5c/hypotheses",
            json={"enonce": "Hypothèse tenant B"},
            headers={"X-Tenant": autre},
        )
        assert reponse.status_code == 404

        liste = client.get(
            f"{BASE}/hypotheses",
            params={"investigation_id": "inv-c5c"},
            headers={"X-Tenant": autre},
        )
        assert liste.status_code == 404

        with psycopg.connect(DSN) as conn:
            assert boucle.lire_boucle(conn, autre, "inv-c5c") is None
            assert objets_exploitation.lister_objets_exploitation(
                conn, autre, type_="HYPOTHESIS") == []
    finally:
        _nettoyer(tenant)
        _nettoyer(autre)


@besoin_pg
def test_pg_liste_filtre_par_investigation_statut_et_limite(monkeypatch):
    tenant = f"c5c-{uuid.uuid4().hex[:10]}"
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            _pg_investigation(tenant)
            with psycopg.connect(DSN) as conn:
                premiere = commandes_boucle.creer_hypothese(
                    boucle, conn, tenant, "inv-c5c", enonce="Hypothèse 1")
                seconde = commandes_boucle.creer_hypothese(
                    boucle, conn, tenant, "inv-c5c", enonce="Hypothèse 2")
                commandes_boucle.changer_statut_hypothese(
                    boucle, conn, tenant, seconde.objet["id"], "STRENGTHENED")

        with psycopg.connect(DSN) as conn:
            liste = commandes_boucle.lister_hypotheses(
                boucle, conn, tenant, investigation_id="inv-c5c")
            assert {objet["id"] for objet in liste} == {
                premiere.objet["id"], seconde.objet["id"]}

            filtrees = commandes_boucle.lister_hypotheses(
                boucle, conn, tenant, investigation_id="inv-c5c",
                statut="STRENGTHENED")
            assert [objet["id"] for objet in filtrees] == [seconde.objet["id"]]

            assert len(commandes_boucle.lister_hypotheses(
                boucle, conn, tenant, investigation_id="inv-c5c", limite=1)) == 1
    finally:
        _nettoyer(tenant)
