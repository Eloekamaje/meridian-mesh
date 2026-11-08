"""C5d — Signaux canoniques, globaux ou rattachés à une Situation.

Les tests de commande utilisent un magasin en mémoire qui satisfait la surface utile du
port ``BoucleStore`` et simule le lien inverse ``Situation.signal_ids``. Les tests HTTP
remplacent les commandes et la connexion : ils vérifient le contrat public et les
traductions d'erreurs sans dépendre d'un serveur. Les tests Postgres sont opt-in via
``JUMEAU_PG_DSN`` et prouvent la chaîne réelle, l'empreinte, la concurrence, l'atomicité
et l'isolation tenant.

Règle d'empreinte : SHA-256 versionné de ``source + type_signal + libelle + detecte_le``.
Les textes sont normalisés NFKC, espaces compactés et casse repliée ; une date absente
vaut la chaîne vide, jamais l'heure serveur.
"""
from __future__ import annotations

import copy
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
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
from meridian.domain.modele_entreprise import ModeleInvalide
from meridian.domain.objets_exploitation import (
    ObjetsExploitationInvalide,
    empreinte_signal,
)
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
    ligne.setdefault("famille", "emergence")
    ligne.setdefault("mode", "OBSERVED")
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
    valeurs = {
        "titre": "Latence des paiements",
        "description": "",
        "signal_ids": [],
        "expression_id": None,
        "confidence": 0.5,
    }
    valeurs.update(donnees)
    return {
        "id": identifiant,
        "tenant_id": tenant,
        "famille": "emergence",
        "type": "SITUATION",
        "mode": "OBSERVED",
        "titre": valeurs["titre"],
        "donnees": valeurs,
        "version": 1,
        **DATES,
    }


def _signal_row(
    identifiant: str = "signal-1", *, tenant: str = TENANT,
    situation_ids=None, **donnees,
) -> dict:
    valeurs = {
        "titre": "Dépendance nouvelle",
        "libelle": "Dépendance nouvelle",
        "description": "",
        "type_signal": "OBSERVATION",
        "source": "git://depot",
        "statut": "DETECTED",
        "intensite": None,
        "fingerprint": "empreinte-1",
        "detecte_le": "2026-11-07T00:00:00+00:00",
        "situation_ids": list(situation_ids or []),
        "entite_ids": [],
        "liens": {},
        "preuves": [],
        "source_ids": [],
        "confiance": 0.5,
    }
    valeurs.update(donnees)
    return {
        "id": identifiant,
        "tenant_id": tenant,
        "famille": "emergence",
        "type": "SIGNAL",
        "mode": "OBSERVED",
        "titre": valeurs["titre"],
        "donnees": valeurs,
        "version": 1,
        **DATES,
    }


class _Store:
    """Port Boucle minimal, transaction annulable, empreinte et lien inverse réels."""

    def __init__(self, objets=None):
        self.objets = {objet["id"]: copy.deepcopy(objet) for objet in (objets or [])}
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
            if type_objet == "SIGNAL":
                situations = list(donnees.get("situation_ids") or [])
                parent_id = situations[0] if len(situations) == 1 else None
            elif type_objet == "HYPOTHESIS":
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

    def nouveau_signal(self, **champs):
        return construction_objets_exploitation.nouveau_signal(**champs)

    def enregistrer_boucle(self, conn, tenant_id=None, objets=None, **kwargs):
        objets = list(objets or [])
        self.enregistres_boucle.extend(copy.deepcopy(objets))
        for objet in objets:
            if str(getattr(objet, "type", "")).upper() == "SIGNAL":
                raise AssertionError(
                    "enregistrer_boucle ne doit pas persister un SIGNAL")
        return objets

    def enregistrer_objets(
        self, conn, tenant_id=None, objets=None, *, historique=False, as_dict=True,
    ):
        objets = list(objets or [])
        self.enregistres_objets.extend(copy.deepcopy(objets))
        for objet in objets:
            ligne = _ligne(objet)
            if ligne["type"] == "SIGNAL":
                empreinte = (ligne.get("donnees") or {}).get("fingerprint")
                for existant in self.objets.values():
                    if (
                        existant.get("type") == "SIGNAL"
                        and existant.get("tenant_id") == ligne["tenant_id"]
                        and existant.get("id") != ligne["id"]
                        and (existant.get("donnees") or {}).get("fingerprint") == empreinte
                    ):
                        raise ObjetsExploitationInvalide(
                            f"empreinte de Signal déjà connue : {empreinte!r}")
            self.objets[ligne["id"]] = ligne
            if self.echec_lien:
                raise RuntimeError("échec simulé du lien inverse")
            if ligne["type"] != "SIGNAL":
                continue
            for situation_id in (ligne.get("donnees") or {}).get("situation_ids") or []:
                parent = self.objets.get(situation_id)
                if parent is None:
                    raise RuntimeError(f"situation introuvable : {situation_id}")
                ids = parent.setdefault("donnees", {}).setdefault("signal_ids", [])
                if ligne["id"] not in ids:
                    ids.append(ligne["id"])
        return objets if not as_dict else [_ligne(objet) for objet in objets]

    def lister_objets_exploitation(
        self, conn, tenant_id, *, type_=None, situation_id=None, investigation_id=None,
        decision_id=None, expression_id=None, type_signal=None, statut=None,
        limite=100, as_dict=True,
    ):
        resultat = []
        for objet in self.objets.values():
            if objet.get("tenant_id") != tenant_id:
                continue
            if type_ is not None and objet.get("type") != type_:
                continue
            donnees = objet.get("donnees") or {}
            if situation_id is not None:
                if objet.get("type") == "SIGNAL":
                    if situation_id not in (donnees.get("situation_ids") or []):
                        continue
                elif donnees.get("situation_id") != situation_id:
                    continue
            if type_signal is not None and donnees.get("type_signal") != type_signal:
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
# Domaine : empreinte déterministe
# --------------------------------------------------------------------------- #


def test_empreinte_signal_est_deterministe_et_normalisee():
    premier = empreinte_signal(
        source=" Git://Depot ", type_signal="changement",
        libelle="  Dépendance   nouvelle ", detecte_le=None)
    second = empreinte_signal(
        source="git://depot", type_signal="CHANGEMENT",
        libelle="dépendance nouvelle", detecte_le="")

    assert premier == second
    assert len(premier) == 64
    assert all(caractere in "0123456789abcdef" for caractere in premier)


def test_empreinte_signal_sans_date_ne_depend_pas_de_l_horloge():
    arguments = {
        "source": "git://depot",
        "type_signal": "OBSERVATION",
        "libelle": "Dépendance nouvelle",
    }
    assert empreinte_signal(**arguments, detecte_le=None) == empreinte_signal(
        **arguments, detecte_le=None)
    assert empreinte_signal(**arguments, detecte_le=None) != empreinte_signal(
        **arguments, detecte_le="2026-11-07T00:00:00+00:00")


def test_empreinte_signal_change_avec_chaque_composante():
    base = empreinte_signal(
        source="source", type_signal="OBSERVATION", libelle="Libellé")
    for variation in (
        {"source": "autre source", "type_signal": "OBSERVATION", "libelle": "Libellé"},
        {"source": "source", "type_signal": "ANOMALIE", "libelle": "Libellé"},
        {"source": "source", "type_signal": "OBSERVATION", "libelle": "Autre libellé"},
    ):
        assert empreinte_signal(**variation) != base


# --------------------------------------------------------------------------- #
# Commandes
# --------------------------------------------------------------------------- #


def test_creer_signal_global_persiste_statut_mode_et_empreinte():
    store = _Store()

    resultat = commandes_boucle.creer_signal(
        store, _Connexion(), TENANT,
        libelle="  Dépendance   nouvelle  ",
        source="  git://depot  ",
        type_signal="changement",
        description="Le dépôt dépend d'un paquet non maintenu.",
        intensite=0.7,
        confiance=0.6,
    )

    assert resultat.objet["type"] == "SIGNAL"
    assert resultat.objet["titre"] == "Dépendance   nouvelle"
    assert resultat.objet["donnees"]["libelle"] == "Dépendance   nouvelle"
    assert resultat.objet["donnees"]["source"] == "git://depot"
    assert resultat.objet["donnees"]["type_signal"] == "CHANGEMENT"
    assert resultat.objet["donnees"]["statut"] == "DETECTED"
    assert resultat.objet["mode"] == "OBSERVED"
    assert resultat.objet["donnees"]["fingerprint"] == empreinte_signal(
        source="git://depot", type_signal="CHANGEMENT", libelle="Dépendance nouvelle")
    assert resultat.objet["donnees"]["situation_ids"] == []
    assert [element["type"] for element in resultat.chaine] == ["SIGNAL"]
    assert len(store.enregistres_objets) == 1
    assert store.enregistres_boucle == []


def test_creer_signal_depuis_une_situation_pose_le_lien_inverse_et_la_chaine():
    store = _Store([_situation_row()])

    resultat = commandes_boucle.creer_signal(
        store, _Connexion(), TENANT, situation_id="sit-1",
        libelle="Latence en hausse", source="suivi-cartes")

    assert resultat.objet["donnees"]["situation_ids"] == ["sit-1"]
    assert [element["type"] for element in resultat.chaine] == ["SITUATION", "SIGNAL"]
    assert store.objets["sit-1"]["donnees"]["signal_ids"] == [resultat.objet["id"]]
    assert store.appels_lire[0] == {
        "tenant_id": TENANT, "objet_id": "sit-1",
        "historique": False, "for_update": True,
    }


def test_creer_signal_multi_situations_reste_sans_chaine_amont():
    store = _Store([_situation_row("sit-1"), _situation_row("sit-2")])

    resultat = commandes_boucle.creer_signal(
        store, _Connexion(), TENANT,
        libelle="Phénomène transversal",
        source="observation",
        situation_ids=["sit-1", "sit-2"],
    )

    assert resultat.objet["donnees"]["situation_ids"] == ["sit-1", "sit-2"]
    assert [element["type"] for element in resultat.chaine] == ["SIGNAL"]
    assert store.objets["sit-1"]["donnees"]["signal_ids"] == [resultat.objet["id"]]
    assert store.objets["sit-2"]["donnees"]["signal_ids"] == [resultat.objet["id"]]


@pytest.mark.parametrize("detecte_le", [None, "2026-11-07T00:00:00+00:00"])
def test_deux_creations_identiques_produisent_un_doublon(detecte_le):
    store = _Store()
    champs = {
        "libelle": "Dépendance nouvelle",
        "source": "git://depot",
        "type_signal": "CHANGEMENT",
        "detecte_le": detecte_le,
    }

    commandes_boucle.creer_signal(store, _Connexion(), TENANT, **champs)
    with pytest.raises(commandes_boucle.DoublonExploitation):
        commandes_boucle.creer_signal(store, _Connexion(), TENANT, **champs)

    assert len([objet for objet in store.objets.values()
                if objet["type"] == "SIGNAL"]) == 1


def test_deux_signaux_differents_par_la_source_ne_sont_pas_des_doublons():
    store = _Store()
    commandes_boucle.creer_signal(
        store, _Connexion(), TENANT, libelle="Même libellé", source="source-a")
    commandes_boucle.creer_signal(
        store, _Connexion(), TENANT, libelle="Même libellé", source="source-b")

    assert len([objet for objet in store.objets.values()
                if objet["type"] == "SIGNAL"]) == 2


@pytest.mark.parametrize("champs", [
    {"statut": "MATURE"},
    {"mode": "DECLARED"},
    {"id": "client-id"},
    {"fingerprint": "client-fingerprint"},
])
def test_creer_signal_refuse_les_champs_serveur(champs):
    store = _Store()
    with pytest.raises(ObjetsExploitationInvalide) as levee:
        commandes_boucle.creer_signal(
            store, _Connexion(), TENANT,
            libelle="Signal", source="source", **champs)
    assert next(iter(champs)) in str(levee.value)
    assert store.enregistres_objets == []


@pytest.mark.parametrize(("champs", "erreur"), [
    ({"libelle": "   ", "source": "source"}, "libelle"),
    ({"libelle": "Signal", "source": "   "}, "source"),
    ({"libelle": "Signal", "source": "source", "type_signal": "MAGIQUE"}, "type_signal"),
    ({"libelle": "Signal", "source": "source", "intensite": 1.5}, "intensite"),
    ({"libelle": "Signal", "source": "source", "confiance": 1.5}, "confiance"),
])
def test_creer_signal_refuse_les_valeurs_invalides_sans_ecriture(champs, erreur):
    store = _Store()
    with pytest.raises(ModeleInvalide) as levee:
        commandes_boucle.creer_signal(
            store, _Connexion(), TENANT, **champs)
    assert erreur in str(levee.value)
    assert store.enregistres_objets == []


def test_creer_signal_situation_absente_ou_hors_tenant_est_404():
    store = _Store()
    with pytest.raises(commandes_boucle.SourceIntrouvable) as levee:
        commandes_boucle.creer_signal(
            store, _Connexion(), TENANT, situation_id="sit-absent",
            libelle="Signal", source="source")
    assert levee.value.role == "situation"

    store = _Store([_situation_row(tenant=AUTRE_TENANT)])
    with pytest.raises(commandes_boucle.SourceIntrouvable):
        commandes_boucle.creer_signal(
            store, _Connexion(), TENANT, situation_id="sit-1",
            libelle="Signal", source="source")
    assert store.enregistres_objets == []


def test_creer_signal_refuse_une_source_qui_n_est_pas_une_situation():
    source = {
        "id": "inv-1", "tenant_id": TENANT, "famille": "investigation",
        "type": "INVESTIGATION", "mode": "DECLARED", "titre": "",
        "donnees": {}, "version": 1,
    }
    store = _Store([source])
    with pytest.raises(ObjetsExploitationInvalide) as levee:
        commandes_boucle.creer_signal(
            store, _Connexion(), TENANT, situation_id="inv-1",
            libelle="Signal", source="source")
    assert "SITUATION" in str(levee.value)
    assert store.enregistres_objets == []


def test_creer_signal_depuis_une_situation_refuse_une_autre_situation_dans_le_corps():
    store = _Store([_situation_row("sit-1"), _situation_row("sit-2")])
    with pytest.raises(ObjetsExploitationInvalide):
        commandes_boucle.creer_signal(
            store, _Connexion(), TENANT, situation_id="sit-1",
            libelle="Signal", source="source", situation_ids=["sit-2"])
    assert store.enregistres_objets == []


def test_creer_signal_depuis_une_situation_accepte_le_meme_id_dans_le_corps():
    store = _Store([_situation_row("sit-1")])
    resultat = commandes_boucle.creer_signal(
        store, _Connexion(), TENANT, situation_id="sit-1",
        libelle="Signal", source="source", situation_ids=["sit-1"])
    assert resultat.objet["donnees"]["situation_ids"] == ["sit-1"]


def test_creer_signal_multi_situations_refuse_une_situation_hors_tenant():
    store = _Store([_situation_row("sit-1"), _situation_row("sit-2", tenant=AUTRE_TENANT)])
    with pytest.raises(commandes_boucle.SourceIntrouvable):
        commandes_boucle.creer_signal(
            store, _Connexion(), TENANT,
            libelle="Signal", source="source", situation_ids=["sit-1", "sit-2"])
    assert store.enregistres_objets == []


def test_creer_signal_annule_tout_si_le_lien_inverse_echoue():
    store = _Store([_situation_row()])
    store.echec_lien = True

    with pytest.raises(RuntimeError):
        commandes_boucle.creer_signal(
            store, _Connexion(), TENANT, situation_id="sit-1",
            libelle="Signal partiel", source="source")

    assert not [objet for objet in store.objets.values() if objet["type"] == "SIGNAL"]
    assert store.objets["sit-1"]["donnees"]["signal_ids"] == []


def test_creer_signal_genere_un_identifiant_avec_le_prefixe_du_domaine():
    store = _Store()
    resultat = commandes_boucle.creer_signal(
        store, _Connexion(), TENANT, libelle="Signal", source="source")
    assert resultat.objet["id"].startswith("signal-")


def test_lister_signaux_filtre_par_situation_type_statut_et_tenant():
    store = _Store([
        _situation_row("sit-1"),
        _situation_row("sit-2"),
        _signal_row("signal-1", situation_ids=["sit-1"], type_signal="ANOMALIE"),
        _signal_row("signal-2", situation_ids=["sit-2"], type_signal="CHANGEMENT"),
        _signal_row("signal-3", type_signal="ANOMALIE", statut="MATURE"),
        _signal_row("signal-autre", tenant=AUTRE_TENANT, type_signal="ANOMALIE"),
    ])

    tous = commandes_boucle.lister_signaux(store, _Connexion(), TENANT)
    assert {objet["id"] for objet in tous} == {
        "signal-1", "signal-2", "signal-3"}

    par_situation = commandes_boucle.lister_signaux(
        store, _Connexion(), TENANT, situation_id="sit-1")
    assert [objet["id"] for objet in par_situation] == ["signal-1"]

    par_type = commandes_boucle.lister_signaux(
        store, _Connexion(), TENANT, type_signal="anomalie")
    assert {objet["id"] for objet in par_type} == {"signal-1", "signal-3"}

    par_statut = commandes_boucle.lister_signaux(
        store, _Connexion(), TENANT, statut="MATURE")
    assert [objet["id"] for objet in par_statut] == ["signal-3"]

    limites = commandes_boucle.lister_signaux(
        store, _Connexion(), TENANT, limite=1)
    assert len(limites) == 1


def test_lister_signaux_situation_absente_est_404_et_filtres_invalides_422():
    store = _Store()
    with pytest.raises(commandes_boucle.SourceIntrouvable):
        commandes_boucle.lister_signaux(
            store, _Connexion(), TENANT, situation_id="sit-absent")
    with pytest.raises(ObjetsExploitationInvalide):
        commandes_boucle.lister_signaux(
            store, _Connexion(), TENANT, type_signal="INCONNU")
    with pytest.raises(ObjetsExploitationInvalide):
        commandes_boucle.lister_signaux(
            store, _Connexion(), TENANT, statut="INCONNU")


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


def _resultat(identifiant: str = "signal-1") -> commandes_boucle.ResultatTransition:
    situation = _situation_row()
    signal = _signal_row(identifiant, situation_ids=["sit-1"])
    return commandes_boucle.ResultatTransition(
        objet=signal,
        chaine=[situation, signal],
        historique=[],
    )


def test_post_signal_global_retourne_le_contrat_c5d(monkeypatch):
    client = _client(monkeypatch)
    appels = []

    def creer(depot_, conn, tenant, *, situation_id=None, **champs):
        appels.append((tenant, situation_id, champs))
        return _resultat()

    monkeypatch.setattr(boucle_routes.commandes_boucle, "creer_signal", creer)

    reponse = client.post(f"{BASE}/signals", json={
        "libelle": "  Dépendance   nouvelle  ",
        "source": "  git://depot  ",
        "type_signal": "changement",
        "description": "Paquet non maintenu",
        "intensite": 0.7,
        "detecte_le": "2026-11-08T10:00:00+00:00",
        "situation_ids": ["sit-1"],
        "entite_ids": ["app-paiement"],
        "liens": {"depends_on": ["app-cartes"]},
        "preuves": ["preuve-1"],
        "confiance": 0.6,
    })

    assert reponse.status_code == 201, reponse.text
    corps = reponse.json()
    assert corps["tenant"] == TENANT
    assert corps["objet"]["type"] == "SIGNAL"
    assert corps["type"] == "SIGNAL"
    assert corps["role"] == "signal"
    assert [element["type"] for element in corps["chaine"]] == ["SITUATION", "SIGNAL"]
    assert corps["historique"] == []
    assert corps["idempotency_key"] is None
    assert appels[0][0] == TENANT
    assert appels[0][1] is None
    assert appels[0][2]["libelle"] == "Dépendance   nouvelle"
    assert appels[0][2]["source"] == "git://depot"
    assert appels[0][2]["type_signal"] == "CHANGEMENT"
    assert appels[0][2]["description"] == "Paquet non maintenu"
    assert appels[0][2]["intensite"] == 0.7
    assert appels[0][2]["detecte_le"] == "2026-11-08T10:00:00+00:00"
    assert appels[0][2]["situation_ids"] == ["sit-1"]
    assert appels[0][2]["entite_ids"] == ["app-paiement"]
    assert appels[0][2]["liens"] == {"depends_on": ["app-cartes"]}
    assert appels[0][2]["preuves"] == ["preuve-1"]
    assert appels[0][2]["confiance"] == 0.6
    for interdit in ("statut", "mode", "id", "tenant_id", "fingerprint"):
        assert interdit not in appels[0][2]


def test_post_signal_depuis_situation_force_la_situation(monkeypatch):
    client = _client(monkeypatch)
    appels = []

    def creer(depot_, conn, tenant, *, situation_id=None, **champs):
        appels.append((tenant, situation_id, champs))
        return _resultat()

    monkeypatch.setattr(boucle_routes.commandes_boucle, "creer_signal", creer)

    reponse = client.post(f"{BASE}/situations/sit-1/signals", json={
        "libelle": "Latence en hausse",
        "source": "suivi-cartes",
        "situation_ids": ["sit-1"],
    })

    assert reponse.status_code == 201, reponse.text
    assert appels[0][0] == TENANT
    assert appels[0][1] == "sit-1"
    assert appels[0][2]["situation_ids"] == ["sit-1"]


@pytest.mark.parametrize("corps", [
    {},
    {"libelle": "   ", "source": "source"},
    {"libelle": "Signal", "source": "   "},
    {"libelle": "Signal", "source": "source", "type_signal": "MAGIQUE"},
    {"libelle": "Signal", "source": "source", "statut": "DETECTED"},
    {"libelle": "Signal", "source": "source", "mode": "OBSERVED"},
    {"libelle": "Signal", "source": "source", "id": "client-id"},
    {"libelle": "Signal", "source": "source", "tenant_id": "banque"},
    {"libelle": "Signal", "source": "source", "fingerprint": "client-fingerprint"},
    {"libelle": "Signal", "source": "source", "confiance": 1.2},
    {"libelle": "Signal", "source": "source", "intensite": 1.2},
    {"libelle": "Signal", "source": "source", "champ_inconnu": True},
])
def test_post_signal_valide_le_corps_avant_la_commande(monkeypatch, corps):
    client = _client(monkeypatch)
    monkeypatch.setattr(
        boucle_routes.commandes_boucle, "creer_signal",
        lambda *_, **__: pytest.fail("la commande ne doit pas être appelée"),
    )
    assert client.post(f"{BASE}/signals", json=corps).status_code == 422


def test_post_signal_traduit_les_erreurs(monkeypatch):
    client = _client(monkeypatch)

    @contextmanager
    def contexte(conn, tenant):
        yield tenant

    monkeypatch.setattr(boucle_routes.rls, "est_actif", lambda: True)
    monkeypatch.setattr(boucle_routes.rls, "contexte_tenant", contexte)

    for erreur, statut in [
        (commandes_boucle.SourceIntrouvable("situation", "sit-x"), 404),
        (commandes_boucle.DoublonExploitation("empreinte de Signal déjà connue"), 409),
        (ObjetsExploitationInvalide("source invalide"), 422),
        (ObjetInvalide("secret refusé"), 400),
        (psycopg.OperationalError("panne"), 503),
    ]:
        def echouer(*_, _erreur=erreur, **__):
            raise _erreur

        monkeypatch.setattr(boucle_routes.commandes_boucle, "creer_signal", echouer)
        reponse = client.post(
            f"{BASE}/signals", json={"libelle": "Signal", "source": "source"})
        assert reponse.status_code == statut
        assert "Traceback" not in reponse.text


def test_post_signal_refuse_une_cle_d_idempotence(monkeypatch):
    client = _client(monkeypatch)
    reponse = client.post(
        f"{BASE}/signals",
        json={"libelle": "Signal", "source": "source"},
        headers={"Idempotency-Key": "cle-1"},
    )
    assert reponse.status_code == 501


def test_post_signal_refuse_un_json_non_valide_en_400(monkeypatch):
    client = _client(monkeypatch)
    reponse = client.post(
        f"{BASE}/signals",
        content=b"{",
        headers={"content-type": "application/json"},
    )
    assert reponse.status_code == 400


def test_la_reponse_creation_signal_ne_laisse_pas_passer_un_secret(monkeypatch):
    client = _client(monkeypatch)
    resultat = _resultat()
    resultat.objet["donnees"]["preuves"] = [{"password": "s3cr3t"}]
    monkeypatch.setattr(
        boucle_routes.commandes_boucle, "creer_signal",
        lambda *_, **__: resultat)

    reponse = client.post(
        f"{BASE}/signals", json={"libelle": "Signal", "source": "source"})

    assert reponse.status_code == 201
    assert "s3cr3t" not in reponse.text
    assert reponse.json()["objet"]["donnees"]["preuves"] == [{"password": "***"}]


def test_sans_dsn_la_route_signal_repond_503(monkeypatch):
    monkeypatch.delenv("AUTH_MODE", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("JUMEAU_PG_DSN", raising=False)
    reponse = _app().post(
        f"{BASE}/signals", json={"libelle": "Signal", "source": "source"})
    assert reponse.status_code == 503
    assert "JUMEAU_PG_DSN" in reponse.json()["detail"]


def test_get_signaux_retourne_la_liste_filtree(monkeypatch):
    client = _client(monkeypatch)
    appels = []

    def lister(depot_, conn, tenant, *, situation_id=None, type_signal=None,
               statut=None, limite=100):
        appels.append((tenant, situation_id, type_signal, statut, limite))
        return [_signal_row("signal-1", situation_ids=["sit-1"])]

    monkeypatch.setattr(boucle_routes.commandes_boucle, "lister_signaux", lister)
    reponse = client.get(
        f"{BASE}/signals",
        params={
            "situation_id": "sit-1",
            "type_signal": "anomalie",
            "statut": "DETECTED",
            "limite": 25,
        },
        headers={"X-Tenant": "banque"},
    )

    assert reponse.status_code == 200
    assert reponse.json()["tenant"] == "banque"
    assert [objet["id"] for objet in reponse.json()["signaux"]] == ["signal-1"]
    assert appels == [("banque", "sit-1", "ANOMALIE", "DETECTED", 25)]


def test_get_signaux_situation_absente_repond_404(monkeypatch):
    client = _client(monkeypatch)

    def echouer(*_, **__):
        raise commandes_boucle.SourceIntrouvable("situation", "sit-x")

    monkeypatch.setattr(boucle_routes.commandes_boucle, "lister_signaux", echouer)
    reponse = client.get(f"{BASE}/signals", params={"situation_id": "sit-x"})
    assert reponse.status_code == 404


def test_get_signaux_filtre_inconnu_repond_422(monkeypatch):
    client = _client(monkeypatch)

    def echouer(*_, **__):
        raise ObjetsExploitationInvalide("type_signal inconnu")

    monkeypatch.setattr(boucle_routes.commandes_boucle, "lister_signaux", echouer)
    reponse = client.get(f"{BASE}/signals", params={"type_signal": "INCONNU"})
    assert reponse.status_code == 422


# --------------------------------------------------------------------------- #
# Postgres réel : chaînes, liens inverses, doublons, concurrence et atomicité
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


@besoin_pg
def test_pg_creation_signal_chaine_lien_inverse_et_lecture(monkeypatch):
    tenant = f"c5d-{uuid.uuid4().hex[:10]}"
    client = _client_pg(monkeypatch)
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)

        situation = client.post(
            f"{BASE}/situations",
            json={"id": "sit-c5d", "titre": "Latence des paiements"},
            headers={"X-Tenant": tenant},
        )
        assert situation.status_code == 201, situation.text

        creation = client.post(
            f"{BASE}/situations/sit-c5d/signals",
            json={
                "libelle": "Latence en hausse",
                "source": "suivi-cartes",
                "type_signal": "ANOMALIE",
                "description": "Le p95 dépasse la cible.",
                "intensite": 0.8,
                "preuves": ["preuve-1"],
                "confiance": 0.7,
            },
            headers={"X-Tenant": tenant},
        )
        assert creation.status_code == 201, creation.text
        corps = creation.json()
        signal_id = corps["objet"]["id"]
        assert corps["objet"]["donnees"]["statut"] == "DETECTED"
        assert corps["objet"]["mode"] == "OBSERVED"
        assert corps["objet"]["donnees"]["situation_ids"] == ["sit-c5d"]
        assert corps["objet"]["donnees"]["fingerprint"]
        assert [element["type"] for element in corps["chaine"]] == [
            "SITUATION", "SIGNAL"]

        situation_lue = client.get(
            f"{BASE}/objets/sit-c5d", headers={"X-Tenant": tenant}
        ).json()["objet"]
        assert situation_lue["donnees"]["signal_ids"] == [signal_id]

        lecture = client.get(
            f"{BASE}/objets/{signal_id}",
            params={"historique": True},
            headers={"X-Tenant": tenant},
        )
        assert lecture.status_code == 200, lecture.text
        assert [element["type"] for element in lecture.json()["chaine"]] == [
            "SITUATION", "SIGNAL"]

        liste = client.get(
            f"{BASE}/signals",
            params={"situation_id": "sit-c5d", "type_signal": "ANOMALIE"},
            headers={"X-Tenant": tenant},
        )
        assert liste.status_code == 200, liste.text
        assert [objet["id"] for objet in liste.json()["signaux"]] == [signal_id]

        with psycopg.connect(DSN) as conn:
            assert "SIGNAL" in boucle.TYPES_LECTURE
            assert "SIGNAL" not in boucle.TYPES_BOUCLE
            objet = boucle.lire_boucle(conn, tenant, signal_id, as_dict=False)
            assert objet.type == "SIGNAL"
            assert objet.situation_ids == ["sit-c5d"]
            with pytest.raises(boucle.BoucleInvalide):
                boucle.enregistrer_boucle(conn, tenant, objets=[objet])
    finally:
        _nettoyer(tenant)


@besoin_pg
def test_pg_signal_global_et_multi_situation_sans_chaine(monkeypatch):
    tenant = f"c5d-{uuid.uuid4().hex[:10]}"
    client = _client_pg(monkeypatch)
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)

        for identifiant in ("sit-a", "sit-b"):
            assert client.post(
                f"{BASE}/situations",
                json={"id": identifiant, "titre": f"Situation {identifiant}"},
                headers={"X-Tenant": tenant},
            ).status_code == 201

        multi = client.post(
            f"{BASE}/signals",
            json={
                "libelle": "Phénomène transversal",
                "source": "observation",
                "situation_ids": ["sit-a", "sit-b"],
            },
            headers={"X-Tenant": tenant},
        )
        assert multi.status_code == 201, multi.text
        multi_id = multi.json()["objet"]["id"]
        assert [element["type"] for element in multi.json()["chaine"]] == ["SIGNAL"]

        lecture = client.get(
            f"{BASE}/objets/{multi_id}",
            params={"historique": True},
            headers={"X-Tenant": tenant},
        )
        assert lecture.status_code == 200
        assert [element["type"] for element in lecture.json()["chaine"]] == ["SIGNAL"]

        for identifiant in ("sit-a", "sit-b"):
            situation = client.get(
                f"{BASE}/objets/{identifiant}", headers={"X-Tenant": tenant}
            ).json()["objet"]
            assert situation["donnees"]["signal_ids"] == [multi_id]

        global_ = client.post(
            f"{BASE}/signals",
            json={"libelle": "Signal autonome", "source": "veille"},
            headers={"X-Tenant": tenant},
        )
        assert global_.status_code == 201, global_.text
        assert global_.json()["objet"]["donnees"]["situation_ids"] == []
        assert [element["type"] for element in global_.json()["chaine"]] == ["SIGNAL"]
    finally:
        _nettoyer(tenant)


@besoin_pg
def test_pg_doublon_empreinte_409_puis_concurrence_sans_doublon(monkeypatch):
    tenant = f"c5d-{uuid.uuid4().hex[:10]}"
    client = _client_pg(monkeypatch)
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)

        charge = {
            "libelle": "Dépendance nouvelle",
            "source": "git://depot",
            "type_signal": "CHANGEMENT",
        }
        premier = client.post(
            f"{BASE}/signals", json=charge, headers={"X-Tenant": tenant})
        assert premier.status_code == 201, premier.text

        doublon = client.post(
            f"{BASE}/signals", json=charge, headers={"X-Tenant": tenant})
        assert doublon.status_code == 409, doublon.text
        assert "empreinte" in doublon.json()["detail"].lower()

        with psycopg.connect(DSN) as conn:
            nombre = conn.execute(
                "SELECT count(*) FROM objet_entreprise "
                "WHERE tenant_id = %s AND type = 'SIGNAL'",
                (tenant,),
            ).fetchone()[0]
        assert nombre == 1
    finally:
        _nettoyer(tenant)


@besoin_pg
def test_pg_concurrence_reelle_meme_empreinte_un_seul_signal(monkeypatch):
    tenant = f"c5d-{uuid.uuid4().hex[:10]}"
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)

        barriere = threading.Barrier(4)
        resultats = []

        def creer(_):
            with psycopg.connect(DSN) as conn:
                barriere.wait()
                try:
                    resultat = commandes_boucle.creer_signal(
                        boucle, conn, tenant,
                        libelle="Signal concurrent", source="git://depot",
                        type_signal="CHANGEMENT")
                    return ("ok", resultat.objet["id"])
                except commandes_boucle.DoublonExploitation:
                    return ("doublon", None)

        with ThreadPoolExecutor(max_workers=4) as executeur:
            resultats = list(executeur.map(creer, range(4)))

        assert [statut for statut, _ in resultats].count("ok") == 1
        assert [statut for statut, _ in resultats].count("doublon") == 3
        with psycopg.connect(DSN) as conn:
            nombre = conn.execute(
                "SELECT count(*) FROM objet_entreprise "
                "WHERE tenant_id = %s AND type = 'SIGNAL'",
                (tenant,),
            ).fetchone()[0]
        assert nombre == 1
    finally:
        _nettoyer(tenant)


@besoin_pg
def test_pg_signal_secret_refuse_sans_ecriture(monkeypatch):
    tenant = f"c5d-{uuid.uuid4().hex[:10]}"
    client = _client_pg(monkeypatch)
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)

        reponse = client.post(
            f"{BASE}/signals",
            json={
                "libelle": "Signal avec secret",
                "source": "source",
                "preuves": [{"password": "s3cr3t"}],
            },
            headers={"X-Tenant": tenant},
        )
        assert reponse.status_code == 400, reponse.text

        with psycopg.connect(DSN) as conn:
            nombre = conn.execute(
                "SELECT count(*) FROM objet_entreprise "
                "WHERE tenant_id = %s AND type = 'SIGNAL'",
                (tenant,),
            ).fetchone()[0]
        assert nombre == 0
    finally:
        _nettoyer(tenant)


@besoin_pg
def test_pg_creation_signal_atomique_si_le_lien_inverse_echoue(monkeypatch):
    tenant = f"c5d-{uuid.uuid4().hex[:10]}"
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            situation = boucle.Situation(
                **DATES, id="sit-c5d", tenant_id=tenant, titre="Latence")
            boucle.enregistrer_boucle(conn, tenant, objets=[situation])

        def echouer(*_, **__):
            raise RuntimeError("échec simulé du lien inverse")

        monkeypatch.setattr(objets_exploitation, "_persister_parent", echouer)
        with psycopg.connect(DSN) as conn, pytest.raises(RuntimeError):
            commandes_boucle.creer_signal(
                boucle, conn, tenant, situation_id="sit-c5d",
                libelle="Signal partiel", source="source")

        with psycopg.connect(DSN) as conn:
            nombre = conn.execute(
                "SELECT count(*) FROM objet_entreprise "
                "WHERE tenant_id = %s AND type = 'SIGNAL'",
                (tenant,),
            ).fetchone()[0]
            situation_lue = boucle.lire_boucle(
                conn, tenant, "sit-c5d", as_dict=True)
        assert nombre == 0
        assert situation_lue["donnees"]["signal_ids"] == []
    finally:
        _nettoyer(tenant)


@besoin_pg
def test_pg_second_tenant_ne_voit_ni_ne_relie_les_signaux(monkeypatch):
    tenant = f"c5d-{uuid.uuid4().hex[:10]}"
    autre = f"{tenant}-autre"
    client = _client_pg(monkeypatch)
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            situation = boucle.Situation(
                **DATES, id="sit-c5d", tenant_id=tenant, titre="Latence")
            boucle.enregistrer_boucle(conn, tenant, objets=[situation])
            with psycopg.connect(DSN) as conn:
                commandes_boucle.creer_signal(
                    boucle, conn, tenant, situation_id="sit-c5d",
                    libelle="Signal tenant A", source="source")

        reponse = client.post(
            f"{BASE}/situations/sit-c5d/signals",
            json={"libelle": "Signal tenant B", "source": "source"},
            headers={"X-Tenant": autre},
        )
        assert reponse.status_code == 404

        liste = client.get(
            f"{BASE}/signals",
            params={"situation_id": "sit-c5d"},
            headers={"X-Tenant": autre},
        )
        assert liste.status_code == 404

        liste_autre = client.get(
            f"{BASE}/signals", headers={"X-Tenant": autre})
        assert liste_autre.status_code == 200
        assert liste_autre.json()["signaux"] == []

        with psycopg.connect(DSN) as conn:
            assert boucle.lire_boucle(conn, autre, "sit-c5d") is None
            assert objets_exploitation.lister_objets_exploitation(
                conn, autre, type_="SIGNAL") == []
    finally:
        _nettoyer(tenant)
        _nettoyer(autre)
