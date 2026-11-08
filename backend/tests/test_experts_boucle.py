"""C5e — Experts canoniques et contributions depuis Investigation ou Hypothesis.

Les tests de commande utilisent un magasin en mémoire qui satisfait la surface utile du
port ``BoucleStore`` et simule le lien inverse ``Investigation.expert_ids``. Les tests
HTTP remplacent les commandes et la connexion : ils vérifient le contrat public et les
traductions d'erreurs sans dépendre d'un serveur. Les tests Postgres sont opt-in via
``JUMEAU_PG_DSN`` et prouvent la chaîne réelle, l'invariant hypothèse/investigation,
l'atomicité et l'isolation tenant.
"""
from __future__ import annotations

import copy
import os
import threading
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from meridian.adapters.inbound.http import boucle as boucle_routes
from meridian.adapters.outbound.postgres import (
    boucle,
    depot,
    objets_exploitation,
    rls,
)
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
    "cree_le": "2026-11-08T00:00:00+00:00",
    "observe_le": "2026-11-08T00:00:00+00:00",
    "valide_depuis": "2026-11-08T00:00:00+00:00",
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
        **DATES,
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
        "conditions_test": [],
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
        **DATES,
    }


def _expert_row(
    identifiant: str = "expert-1", *, tenant: str = TENANT, **donnees,
) -> dict:
    valeurs = {
        "titre": "Camille Martin",
        "nom": "Camille Martin",
        "domaine": "Cartes bancaires",
        "role": "Expert métier",
        "methodes": ["Entretien"],
        "responsabilites": ["Valider les règles de gestion"],
        "perimetre": "Équipe cartes",
        "sources_autorisees": ["Confluence"],
        "outils_autorises": ["lecture"],
        "limites": ["Pas d'accès aux données clients"],
        "statut": "ACTIVE",
        "preuves": [],
        "confiance": 0.5,
    }
    valeurs.update(donnees)
    return {
        "id": identifiant,
        "tenant_id": tenant,
        "famille": "investigation",
        "type": "EXPERT",
        "mode": "DECLARED",
        "titre": valeurs["nom"],
        "donnees": valeurs,
        "version": 1,
        **DATES,
    }


def _contribution_row(
    identifiant: str = "contribution-1", *, expert_id: str = "expert-1",
    investigation_id: str | None = "inv-1", hypothesis_id: str | None = None,
    tenant: str = TENANT, **donnees,
) -> dict:
    valeurs = {
        "titre": "La règle de gestion est contournée par le canal agence",
        "expert_id": expert_id,
        "investigation_id": investigation_id,
        "hypothesis_id": hypothesis_id,
        "contenu": "La règle de gestion est contournée par le canal agence",
        "contribution_le": "2026-11-08T00:00:00+00:00",
        "statut": "PROPOSED",
        "constats": [],
        "claim_ids_proposes": [],
        "hypothesis_ids_soutenues": [],
        "hypothesis_ids_contestees": [],
        "inconnues": [],
        "motif": "",
        "preuves": [],
        "confiance": 0.5,
    }
    valeurs.update(donnees)
    return {
        "id": identifiant,
        "tenant_id": tenant,
        "famille": "investigation",
        "type": "EXPERT_CONTRIBUTION",
        "mode": "DECLARED",
        "titre": valeurs["titre"],
        "donnees": valeurs,
        "version": 1,
        **DATES,
    }


class _Store:
    """Port Boucle minimal, transaction annulable et liens inverses réels."""

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
            elif type_objet == "EXPERT_CONTRIBUTION":
                parent_id = donnees.get("hypothesis_id") or donnees.get("investigation_id")
            elif type_objet == "INVESTIGATION":
                parent_id = donnees.get("situation_id")
            if not parent_id:
                break
            parent = self.objets.get(parent_id)
            if parent is None or parent.get("tenant_id") != tenant_id:
                break
            courant = parent
        return list(reversed(chaine))

    def nouvel_expert(self, **champs):
        return construction_objets_exploitation.nouvel_expert(**champs)

    def nouvelle_contribution(self, expert=None, **champs):
        return construction_objets_exploitation.nouvelle_contribution(expert, **champs)

    def muer_contribution(self, contribution, vers, **champs):
        return construction_objets_exploitation.muer_contribution(
            contribution, vers, **champs)

    def muer_expert(self, expert, vers, **champs):
        return construction_objets_exploitation.muer_expert(
            expert, vers, **champs)

    def muer_hypothese(self, hypothese, vers, **champs):
        return construction_objets_exploitation.muer_hypothese(
            hypothese, vers, **champs)

    def enregistrer_boucle(self, conn, tenant_id=None, objets=None, **kwargs):
        objets = list(objets or [])
        self.enregistres_boucle.extend(copy.deepcopy(objets))
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
            if ligne["type"] != "EXPERT_CONTRIBUTION":
                continue
            donnees = ligne.get("donnees") or {}
            investigation_id = donnees.get("investigation_id")
            expert_id = donnees.get("expert_id")
            if not investigation_id or not expert_id:
                continue
            parent = self.objets.get(investigation_id)
            if parent is None:
                raise RuntimeError(f"investigation introuvable : {investigation_id}")
            parent_donnees = parent.setdefault("donnees", {})
            actuels = list(parent_donnees.get("expert_ids") or [])
            if expert_id not in actuels:
                actuels.append(expert_id)
            parent_donnees["expert_ids"] = actuels
        return objets if not as_dict else [_ligne(objet) for objet in objets]

    def lister_objets_exploitation(
        self, conn, tenant_id, *, type_=None, investigation_id=None,
        hypothesis_id=None, expert_id=None, domaine=None, statut=None,
        limite=100, as_dict=True,
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
            if hypothesis_id is not None and donnees.get("hypothesis_id") != hypothesis_id:
                continue
            if expert_id is not None and donnees.get("expert_id") != expert_id:
                continue
            if domaine is not None and donnees.get("domaine") != domaine:
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
# Domaine : cycle de vie et invariant hypothèse/investigation
# --------------------------------------------------------------------------- #


def test_le_cycle_canonique_des_contributions_est_explicite():
    assert domaine.STATUTS_EXPERT_CONTRIBUTION == (
        "PROPOSED", "ACCEPTED", "REJECTED", "ARCHIVED")
    assert domaine.TRANSITIONS_EXPERT_CONTRIBUTION == {
        "PROPOSED": ("ACCEPTED", "REJECTED", "ARCHIVED"),
        "ACCEPTED": ("ARCHIVED",),
        "REJECTED": ("ARCHIVED",),
        "ARCHIVED": (),
    }


def test_muer_contribution_refuse_une_transition_non_autorisee():
    contribution = construction_objets_exploitation.nouvelle_contribution(
        _expert_row(), investigation=_investigation_row(),
        contenu="Contribution", statut="ACCEPTED")
    with pytest.raises(ObjetsExploitationInvalide):
        construction_objets_exploitation.muer_contribution(contribution, "PROPOSED")
    assert contribution.statut == "ACCEPTED"


def test_muer_contribution_rend_un_nouvel_objet_avec_motif_et_preuve():
    contribution = construction_objets_exploitation.nouvelle_contribution(
        _expert_row(), investigation=_investigation_row(), contenu="Contribution")
    changee = construction_objets_exploitation.muer_contribution(
        contribution, "ACCEPTED",
        motif="  Relecture métier concordante  ", preuves=["preuve-1"])

    assert changee is not contribution
    assert changee.statut == "ACCEPTED"
    assert changee.motif == "Relecture métier concordante"
    assert changee.preuves == ["preuve-1"]
    assert contribution.statut == "PROPOSED"


def test_muer_contribution_transmet_le_mode_sans_muter_la_source():
    contribution = construction_objets_exploitation.nouvelle_contribution(
        _expert_row(), investigation=_investigation_row(), contenu="Contribution")
    changee = construction_objets_exploitation.muer_contribution(
        contribution, "ACCEPTED", mode="CONFIRMED")

    assert changee.mode == "CONFIRMED"
    assert contribution.mode == "DECLARED"


def test_muer_contribution_valide_les_statuts():
    contribution = construction_objets_exploitation.nouvelle_contribution(
        _expert_row(), investigation=_investigation_row(), contenu="Contribution")
    with pytest.raises(ObjetsExploitationInvalide):
        construction_objets_exploitation.muer_contribution(contribution, "MAGIQUE")


def test_nouvelle_contribution_derive_l_investigation_depuis_l_hypothese():
    contribution = construction_objets_exploitation.nouvelle_contribution(
        _expert_row(),
        hypothesis=_hypothesis_row("hypothesis-1", investigation_id="inv-1"),
        contenu="Contribution sur l'hypothèse",
    )

    assert contribution.hypothesis_id == "hypothesis-1"
    assert contribution.investigation_id == "inv-1"


def test_nouvelle_contribution_refuse_une_hypothese_hors_investigation():
    with pytest.raises(ObjetsExploitationInvalide) as levee:
        construction_objets_exploitation.nouvelle_contribution(
            _expert_row(),
            investigation=_investigation_row("inv-1"),
            hypothesis=_hypothesis_row("hypothesis-1", investigation_id="inv-2"),
            contenu="Contribution incohérente",
        )
    assert "appartient" in str(levee.value)


def test_nouvelle_contribution_refuse_une_hypothese_incoherente_par_tenant():
    with pytest.raises(ObjetsExploitationInvalide):
        construction_objets_exploitation.nouvelle_contribution(
            _expert_row(),
            hypothesis=_hypothesis_row("hypothesis-1", tenant=AUTRE_TENANT),
            contenu="Contribution",
        )


def test_nouvel_expert_exige_nom_et_domaine():
    with pytest.raises(ObjetsExploitationInvalide):
        construction_objets_exploitation.nouvel_expert("", "Domaine", tenant_id=TENANT)
    with pytest.raises(ObjetsExploitationInvalide):
        construction_objets_exploitation.nouvel_expert("Nom", "", tenant_id=TENANT)


def test_enregistrer_boucle_refuse_expert_et_contribution():
    expert = construction_objets_exploitation.nouvel_expert(
        "Expert", "Cartes", tenant_id=TENANT)
    contribution = construction_objets_exploitation.nouvelle_contribution(
        expert, investigation=_investigation_row(), contenu="Contribution")

    for objet in (expert, contribution):
        with pytest.raises(boucle.BoucleInvalide):
            boucle.enregistrer_boucle(
                None, TENANT, objets=[objet], as_dict=False)


# --------------------------------------------------------------------------- #
# Commandes : registre
# --------------------------------------------------------------------------- #


def test_creer_expert_persiste_le_registre_et_force_statut_et_mode():
    store = _Store()

    resultat = commandes_boucle.creer_expert(
        store, _Connexion(), TENANT,
        nom="  Camille Martin  ", domaine="  Cartes bancaires  ",
        role="Expert métier", methodes=["Entretien"],
        responsabilites=["Valider les règles de gestion"],
        perimetre="Équipe cartes", sources_autorisees=["Confluence"],
        outils_autorises=["lecture"], limites=["Pas d'accès aux données clients"],
        preuves=["doc://entretien"], confiance=0.7,
    )

    assert resultat.objet["type"] == "EXPERT"
    assert resultat.objet["mode"] == "DECLARED"
    assert resultat.objet["titre"] == "Camille Martin"
    assert resultat.objet["donnees"]["nom"] == "Camille Martin"
    assert resultat.objet["donnees"]["domaine"] == "Cartes bancaires"
    assert resultat.objet["donnees"]["statut"] == "ACTIVE"
    assert resultat.objet["donnees"]["methodes"] == ["Entretien"]
    assert resultat.objet["donnees"]["confiance"] == 0.7
    assert resultat.objet["id"].startswith("expert-")
    assert [element["type"] for element in resultat.chaine] == ["EXPERT"]
    assert store.enregistres_boucle == []
    assert len(store.enregistres_objets) == 1


@pytest.mark.parametrize("champs", [
    {"statut": "ARCHIVED"},
    {"mode": "OBSERVED"},
    {"id": "client-id"},
])
def test_creer_expert_refuse_les_champs_serveur_du_client(champs):
    store = _Store()
    with pytest.raises(ObjetsExploitationInvalide) as levee:
        commandes_boucle.creer_expert(
            store, _Connexion(), TENANT,
            nom="Camille", domaine="Cartes", **champs)
    assert next(iter(champs)) in str(levee.value)
    assert store.enregistres_objets == []


def test_creer_expert_exige_nom_et_domaine():
    store = _Store()
    with pytest.raises(ModeleInvalide):
        commandes_boucle.creer_expert(
            store, _Connexion(), TENANT, nom="   ", domaine="Cartes")
    with pytest.raises(ModeleInvalide):
        commandes_boucle.creer_expert(
            store, _Connexion(), TENANT, nom="Camille", domaine="   ")
    assert store.enregistres_objets == []


def test_lister_experts_filtre_domaine_statut_et_tenant():
    store = _Store([
        _expert_row("expert-1", domaine="Cartes"),
        _expert_row("expert-2", domaine="Cartes", statut="INACTIVE"),
        _expert_row("expert-3", domaine="Finance"),
        _expert_row("expert-autre", tenant=AUTRE_TENANT),
    ])

    assert [objet["id"] for objet in commandes_boucle.lister_experts(
        store, _Connexion(), TENANT)] == ["expert-1", "expert-2", "expert-3"]
    assert [objet["id"] for objet in commandes_boucle.lister_experts(
        store, _Connexion(), TENANT, domaine="Cartes")] == ["expert-1", "expert-2"]
    assert [objet["id"] for objet in commandes_boucle.lister_experts(
        store, _Connexion(), TENANT, statut="INACTIVE")] == ["expert-2"]
    assert len(commandes_boucle.lister_experts(
        store, _Connexion(), TENANT, limite=1)) == 1


def test_lister_experts_refuse_un_statut_inconnu():
    store = _Store([_expert_row()])
    with pytest.raises(ObjetsExploitationInvalide):
        commandes_boucle.lister_experts(store, _Connexion(), TENANT, statut="MAGIQUE")


def test_changer_statut_expert_persiste_chaque_etape_avec_motif_et_preuves():
    store = _Store([_expert_row("expert-1")])

    inactif = commandes_boucle.changer_statut_expert(
        store, _Connexion(), TENANT, "expert-1", "inactive",
        motif="  Congé longue durée  ", preuves=["doc://rh"])

    assert inactif.objet["donnees"]["statut"] == "INACTIVE"
    assert inactif.objet["donnees"]["motif"] == "Congé longue durée"
    assert inactif.objet["donnees"]["preuves"] == ["doc://rh"]
    assert inactif.historique[-1]["donnees"]["statut"] == "ACTIVE"

    actif = commandes_boucle.changer_statut_expert(
        store, _Connexion(), TENANT, "expert-1", "ACTIVE")
    assert actif.objet["donnees"]["statut"] == "ACTIVE"

    archive = commandes_boucle.changer_statut_expert(
        store, _Connexion(), TENANT, "expert-1", "ARCHIVED")
    assert archive.objet["donnees"]["statut"] == "ARCHIVED"

    with pytest.raises(commandes_boucle.TransitionRefusee):
        commandes_boucle.changer_statut_expert(
            store, _Connexion(), TENANT, "expert-1", "INACTIVE")
    assert store.objets["expert-1"]["donnees"]["statut"] == "ARCHIVED"


def test_changer_statut_expert_refuse_un_statut_inconnu_avant_ecriture():
    store = _Store([_expert_row("expert-1")])

    with pytest.raises(ObjetsExploitationInvalide):
        commandes_boucle.changer_statut_expert(
            store, _Connexion(), TENANT, "expert-1", "MAGIQUE")

    assert store.enregistres_objets == []
    assert store.objets["expert-1"]["donnees"]["statut"] == "ACTIVE"


def test_changer_statut_expert_absent_hors_tenant_ou_mauvais_type():
    store = _Store([
        _expert_row("expert-1"),
        _expert_row("expert-autre", tenant=AUTRE_TENANT),
        _hypothesis_row("hypothesis-1"),
    ])

    with pytest.raises(commandes_boucle.SourceIntrouvable):
        commandes_boucle.changer_statut_expert(
            store, _Connexion(), TENANT, "expert-absent", "INACTIVE")
    with pytest.raises(commandes_boucle.SourceIntrouvable):
        commandes_boucle.changer_statut_expert(
            store, _Connexion(), TENANT, "expert-autre", "INACTIVE")
    with pytest.raises(ObjetsExploitationInvalide):
        commandes_boucle.changer_statut_expert(
            store, _Connexion(), TENANT, "hypothesis-1", "INACTIVE")

    assert store.enregistres_objets == []


@pytest.mark.parametrize("statut", ["ACTIVE", "INACTIVE", "ARCHIVED"])
def test_changer_statut_expert_refuse_une_transition_vers_le_meme_statut(statut):
    store = _Store([_expert_row("expert-1", statut=statut)])

    with pytest.raises(commandes_boucle.TransitionRefusee):
        commandes_boucle.changer_statut_expert(
            store, _Connexion(), TENANT, "expert-1", statut)

    assert store.enregistres_objets == []
    assert store.objets["expert-1"]["donnees"]["statut"] == statut


# --------------------------------------------------------------------------- #
# Commandes : contributions
# --------------------------------------------------------------------------- #


def test_creer_contribution_investigation_persiste_et_relie_expert_et_parent():
    store = _Store([
        _situation_row(), _investigation_row(), _expert_row(),
    ])

    resultat = commandes_boucle.creer_contribution_investigation(
        store, _Connexion(), TENANT, "inv-1",
        expert_id="expert-1",
        contenu="  La règle est contournée par le canal agence  ",
        constats=["La pièce est saisie après validation"],
        claim_ids_proposes=["claim-3"],
        hypothesis_ids_soutenues=["hypothesis-1"],
        hypothesis_ids_contestees=["hypothesis-2"],
        inconnues=["volume réel"],
        contribution_le="2026-11-08T10:00:00+00:00",
        preuves=["doc://entretien"],
        confiance=0.7,
    )

    assert resultat.objet["type"] == "EXPERT_CONTRIBUTION"
    assert resultat.objet["mode"] == "DECLARED"
    assert resultat.objet["donnees"]["statut"] == "PROPOSED"
    assert resultat.objet["donnees"]["expert_id"] == "expert-1"
    assert resultat.objet["donnees"]["investigation_id"] == "inv-1"
    assert resultat.objet["donnees"]["hypothesis_id"] is None
    assert resultat.objet["donnees"]["contenu"] == (
        "La règle est contournée par le canal agence")
    assert resultat.objet["donnees"]["constats"] == [
        "La pièce est saisie après validation"]
    assert resultat.objet["donnees"]["claim_ids_proposes"] == ["claim-3"]
    assert resultat.objet["donnees"]["hypothesis_ids_soutenues"] == ["hypothesis-1"]
    assert resultat.objet["donnees"]["hypothesis_ids_contestees"] == ["hypothesis-2"]
    assert resultat.objet["donnees"]["inconnues"] == ["volume réel"]
    assert resultat.objet["donnees"]["confiance"] == 0.7
    assert resultat.objet["id"].startswith("contribution-")
    assert store.objets["inv-1"]["donnees"]["expert_ids"] == ["expert-1"]
    assert [element["type"] for element in resultat.chaine] == [
        "SITUATION", "INVESTIGATION", "EXPERT_CONTRIBUTION"]
    assert store.appels_lire[0]["for_update"] is True
    assert store.enregistres_boucle == []


def test_creer_contribution_investigation_avec_hypothese_du_parent():
    store = _Store([
        _situation_row(), _investigation_row(),
        _hypothesis_row("hypothesis-1", investigation_id="inv-1"), _expert_row(),
    ])

    resultat = commandes_boucle.creer_contribution_investigation(
        store, _Connexion(), TENANT, "inv-1",
        expert_id="expert-1", hypothesis_id="hypothesis-1",
        contenu="Contribution ciblée",
    )

    assert resultat.objet["donnees"]["hypothesis_id"] == "hypothesis-1"
    assert resultat.objet["donnees"]["investigation_id"] == "inv-1"
    assert [element["type"] for element in resultat.chaine] == [
        "SITUATION", "INVESTIGATION", "HYPOTHESIS", "EXPERT_CONTRIBUTION"]


def test_creer_contribution_refuse_une_hypothese_hors_investigation():
    store = _Store([
        _investigation_row("inv-1"),
        _hypothesis_row("hypothesis-1", investigation_id="inv-2"),
        _expert_row(),
    ])

    with pytest.raises(commandes_boucle.TransitionRefusee) as levee:
        commandes_boucle.creer_contribution_investigation(
            store, _Connexion(), TENANT, "inv-1",
            expert_id="expert-1", hypothesis_id="hypothesis-1",
            contenu="Contribution incohérente")

    assert "appartient" in str(levee.value)
    assert store.enregistres_objets == []
    assert store.objets["inv-1"]["donnees"]["expert_ids"] == []


@pytest.mark.parametrize("statut", [
    "CLOSED", "CLOSE", "CLOTUREE", "FERMEE", "ARCHIVED", "ARCHIVEE", "closed",
    "COMPLETED", "COMPLETED_WITH_GAPS", "BUDGET_EXHAUSTED", "FAILED", "CANCELLED",
])
def test_creer_contribution_refuse_une_investigation_fermee(statut):
    store = _Store([_investigation_row(statut=statut), _expert_row()])

    with pytest.raises(commandes_boucle.TransitionRefusee) as levee:
        commandes_boucle.creer_contribution_investigation(
            store, _Connexion(), TENANT, "inv-1",
            expert_id="expert-1", contenu="Contribution")

    assert "fermée" in str(levee.value)
    assert store.enregistres_objets == []


def test_creer_contribution_investigation_absente_ou_hors_tenant_est_404():
    store = _Store([_expert_row()])
    with pytest.raises(commandes_boucle.SourceIntrouvable):
        commandes_boucle.creer_contribution_investigation(
            store, _Connexion(), TENANT, "inv-absent",
            expert_id="expert-1", contenu="Contribution")

    store = _Store([_investigation_row(tenant=AUTRE_TENANT), _expert_row()])
    with pytest.raises(commandes_boucle.SourceIntrouvable):
        commandes_boucle.creer_contribution_investigation(
            store, _Connexion(), TENANT, "inv-1",
            expert_id="expert-1", contenu="Contribution")
    assert store.enregistres_objets == []


def test_creer_contribution_expert_absent_ou_hors_tenant_est_404():
    store = _Store([_investigation_row()])
    with pytest.raises(commandes_boucle.SourceIntrouvable) as levee:
        commandes_boucle.creer_contribution_investigation(
            store, _Connexion(), TENANT, "inv-1",
            expert_id="expert-absent", contenu="Contribution")
    assert levee.value.role == "expert"

    store = _Store([_investigation_row(), _expert_row(tenant=AUTRE_TENANT)])
    with pytest.raises(commandes_boucle.SourceIntrouvable):
        commandes_boucle.creer_contribution_investigation(
            store, _Connexion(), TENANT, "inv-1",
            expert_id="expert-1", contenu="Contribution")
    assert store.enregistres_objets == []


def test_creer_contribution_refuse_un_mauvais_type_en_422():
    store = _Store([_investigation_row(), _expert_row()])
    with pytest.raises(ObjetsExploitationInvalide) as levee:
        commandes_boucle.creer_contribution_investigation(
            store, _Connexion(), TENANT, "expert-1",
            expert_id="expert-1", contenu="Contribution")
    assert "INVESTIGATION" in str(levee.value)

    store = _Store([_investigation_row(), _hypothesis_row()])
    with pytest.raises(ObjetsExploitationInvalide) as levee:
        commandes_boucle.creer_contribution_investigation(
            store, _Connexion(), TENANT, "inv-1",
            expert_id="hypothesis-1", contenu="Contribution")
    assert "EXPERT" in str(levee.value)


@pytest.mark.parametrize("champs", [
    {"statut": "ACCEPTED"},
    {"mode": "OBSERVED"},
    {"id": "client-id"},
])
def test_creer_contribution_refuse_les_champs_serveur(champs):
    store = _Store([_investigation_row(), _expert_row()])
    with pytest.raises(ObjetsExploitationInvalide) as levee:
        commandes_boucle.creer_contribution_investigation(
            store, _Connexion(), TENANT, "inv-1",
            expert_id="expert-1", contenu="Contribution", **champs)
    assert next(iter(champs)) in str(levee.value)
    assert store.enregistres_objets == []


def test_creer_contribution_exige_contenu_et_expert():
    store = _Store([_investigation_row(), _expert_row()])
    with pytest.raises(ModeleInvalide):
        commandes_boucle.creer_contribution_investigation(
            store, _Connexion(), TENANT, "inv-1",
            expert_id="expert-1", contenu="   ")
    with pytest.raises(ObjetsExploitationInvalide):
        commandes_boucle.creer_contribution_investigation(
            store, _Connexion(), TENANT, "inv-1", contenu="Contribution")
    assert store.enregistres_objets == []


def test_creer_contribution_hypothese_derive_l_investigation():
    store = _Store([
        _situation_row(), _investigation_row(),
        _hypothesis_row("hypothesis-1", investigation_id="inv-1"), _expert_row(),
    ])

    resultat = commandes_boucle.creer_contribution_hypothese(
        store, _Connexion(), TENANT, "hypothesis-1",
        expert_id="expert-1", contenu="Contribution sur l'hypothèse")

    assert resultat.objet["donnees"]["hypothesis_id"] == "hypothesis-1"
    assert resultat.objet["donnees"]["investigation_id"] == "inv-1"
    assert store.objets["inv-1"]["donnees"]["expert_ids"] == ["expert-1"]
    assert [element["type"] for element in resultat.chaine] == [
        "SITUATION", "INVESTIGATION", "HYPOTHESIS", "EXPERT_CONTRIBUTION"]


def test_creer_contribution_hypothese_verrouille_investigation_avant_hypothese():
    """Les deux routes prennent les verrous dans le même ordre pour éviter un deadlock."""
    store = _Store([
        _situation_row(), _investigation_row(),
        _hypothesis_row("hypothesis-1", investigation_id="inv-1"), _expert_row(),
    ])

    commandes_boucle.creer_contribution_hypothese(
        store, _Connexion(), TENANT, "hypothesis-1",
        expert_id="expert-1", contenu="Contribution")

    verrouilles = [
        appel["objet_id"] for appel in store.appels_lire if appel["for_update"]
    ]
    assert verrouilles == ["inv-1", "hypothesis-1", "expert-1"]


def test_changer_statut_hypothese_verrouille_investigation_avant_hypothese():
    """Le statut d'hypothèse suit l'ordre Investigation → Hypothesis."""
    store = _Store([
        _situation_row(), _investigation_row(),
        _hypothesis_row("hypothesis-1", investigation_id="inv-1"),
    ])

    commandes_boucle.changer_statut_hypothese(
        store, _Connexion(), TENANT, "hypothesis-1", "STRENGTHENED")

    verrouilles = [
        appel["objet_id"] for appel in store.appels_lire if appel["for_update"]
    ]
    assert verrouilles == ["inv-1", "hypothesis-1"]


def test_changer_statut_contribution_verrouille_investigation_avant_hypothese():
    """Le statut de contribution verrouille la contribution, puis I1, puis H1."""
    store = _Store([
        _situation_row(), _investigation_row(),
        _hypothesis_row("hypothesis-1", investigation_id="inv-1"), _expert_row(),
        _contribution_row(
            "contribution-1", investigation_id="inv-1",
            hypothesis_id="hypothesis-1"),
    ])

    commandes_boucle.changer_statut_contribution(
        store, _Connexion(), TENANT, "contribution-1", "ACCEPTED")

    verrouilles = [
        appel["objet_id"] for appel in store.appels_lire if appel["for_update"]
    ]
    assert verrouilles == ["contribution-1", "inv-1", "hypothesis-1"]


def test_creer_contribution_hypothese_refuse_hypothesis_id_et_investigation_id():
    store = _Store([_hypothesis_row(), _investigation_row(), _expert_row()])
    with pytest.raises(ObjetsExploitationInvalide) as levee:
        commandes_boucle.creer_contribution_hypothese(
            store, _Connexion(), TENANT, "hypothesis-1",
            expert_id="expert-1", contenu="Contribution", investigation_id="x")
    assert "investigation_id" in str(levee.value)
    assert store.enregistres_objets == []


def test_creer_contribution_hypothese_absente_ou_fermee_est_refusee():
    store = _Store([_investigation_row(), _expert_row()])
    with pytest.raises(commandes_boucle.SourceIntrouvable):
        commandes_boucle.creer_contribution_hypothese(
            store, _Connexion(), TENANT, "hypothesis-absent",
            expert_id="expert-1", contenu="Contribution")

    store = _Store([
        _investigation_row(statut="CLOSED"),
        _hypothesis_row("hypothesis-1", investigation_id="inv-1"), _expert_row(),
    ])
    with pytest.raises(commandes_boucle.TransitionRefusee) as levee:
        commandes_boucle.creer_contribution_hypothese(
            store, _Connexion(), TENANT, "hypothesis-1",
            expert_id="expert-1", contenu="Contribution")
    assert "fermée" in str(levee.value)
    assert store.enregistres_objets == []


def test_creer_contribution_annule_tout_si_le_lien_inverse_echoue():
    store = _Store([_investigation_row(), _expert_row()])
    store.echec_lien = True

    with pytest.raises(RuntimeError):
        commandes_boucle.creer_contribution_investigation(
            store, _Connexion(), TENANT, "inv-1",
            expert_id="expert-1", contenu="Contribution partielle")

    assert not [objet for objet in store.objets.values()
                if objet["type"] == "EXPERT_CONTRIBUTION"]
    assert store.objets["inv-1"]["donnees"]["expert_ids"] == []


def test_lister_contributions_filtre_expert_investigation_hypothese_statut():
    store = _Store([
        _contribution_row("contribution-1", investigation_id="inv-1"),
        _contribution_row("contribution-2", investigation_id="inv-2"),
        _contribution_row("contribution-3", hypothesis_id="hypothesis-1",
                          investigation_id="inv-1", statut="ACCEPTED"),
        _contribution_row("contribution-autre", tenant=AUTRE_TENANT),
    ])

    assert [objet["id"] for objet in commandes_boucle.lister_contributions(
        store, _Connexion(), TENANT)] == [
            "contribution-1", "contribution-2", "contribution-3"]
    assert [objet["id"] for objet in commandes_boucle.lister_contributions(
        store, _Connexion(), TENANT, investigation_id="inv-1")] == [
            "contribution-1", "contribution-3"]
    assert [objet["id"] for objet in commandes_boucle.lister_contributions(
        store, _Connexion(), TENANT, hypothesis_id="hypothesis-1")] == [
            "contribution-3"]
    assert [objet["id"] for objet in commandes_boucle.lister_contributions(
        store, _Connexion(), TENANT, expert_id="expert-1")] == [
            "contribution-1", "contribution-2", "contribution-3"]
    assert [objet["id"] for objet in commandes_boucle.lister_contributions(
        store, _Connexion(), TENANT, statut="ACCEPTED")] == ["contribution-3"]
    assert len(commandes_boucle.lister_contributions(
        store, _Connexion(), TENANT, limite=1)) == 1


def test_lister_contributions_refuse_un_statut_inconnu():
    store = _Store([_contribution_row()])
    with pytest.raises(ObjetsExploitationInvalide):
        commandes_boucle.lister_contributions(
            store, _Connexion(), TENANT, statut="MAGIQUE")


def test_changer_statut_contribution_valide_puis_refuse_une_transition_invalide():
    store = _Store([_situation_row(), _investigation_row(), _contribution_row()])

    resultat = commandes_boucle.changer_statut_contribution(
        store, _Connexion(), TENANT, "contribution-1",
        "ACCEPTED", motif="Relecture métier concordante", preuves=["preuve-1"])

    assert resultat.objet["donnees"]["statut"] == "ACCEPTED"
    assert resultat.objet["donnees"]["motif"] == "Relecture métier concordante"
    assert resultat.objet["donnees"]["preuves"] == ["preuve-1"]
    assert resultat.historique[-1]["donnees"]["statut"] == "PROPOSED"

    with pytest.raises(commandes_boucle.TransitionRefusee):
        commandes_boucle.changer_statut_contribution(
            store, _Connexion(), TENANT, "contribution-1", "PROPOSED")
    assert store.objets["contribution-1"]["donnees"]["statut"] == "ACCEPTED"


def test_changement_de_statut_contribution_refuse_un_statut_inconnu_ou_un_mauvais_type():
    store = _Store([_investigation_row(), _contribution_row()])
    with pytest.raises(ObjetsExploitationInvalide):
        commandes_boucle.changer_statut_contribution(
            store, _Connexion(), TENANT, "contribution-1", "MAGIQUE")

    with pytest.raises(ObjetsExploitationInvalide) as levee:
        commandes_boucle.changer_statut_contribution(
            store, _Connexion(), TENANT, "inv-1", "ACCEPTED")
    assert "EXPERT_CONTRIBUTION" in str(levee.value)


def test_changement_de_statut_contribution_inconnu_ou_hors_tenant_est_404():
    store = _Store()
    with pytest.raises(commandes_boucle.SourceIntrouvable):
        commandes_boucle.changer_statut_contribution(
            store, _Connexion(), TENANT, "absente", "ACCEPTED")

    store = _Store([_contribution_row(tenant=AUTRE_TENANT)])
    with pytest.raises(commandes_boucle.SourceIntrouvable):
        commandes_boucle.changer_statut_contribution(
            store, _Connexion(), TENANT, "contribution-1", "ACCEPTED")


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


def _resultat_expert(identifiant: str = "expert-1") -> commandes_boucle.ResultatTransition:
    expert = _expert_row(identifiant)
    return commandes_boucle.ResultatTransition(
        objet=expert, chaine=[expert], historique=[])


def _resultat_contribution(
    identifiant: str = "contribution-1", *,
    hypothesis_id: str | None = None,
) -> commandes_boucle.ResultatTransition:
    situation = _situation_row()
    investigation = _investigation_row()
    if hypothesis_id:
        hypothesis = _hypothesis_row(hypothesis_id, investigation_id="inv-1")
        contribution = _contribution_row(
            identifiant, hypothesis_id=hypothesis_id, investigation_id="inv-1")
        chaine = [situation, investigation, hypothesis, contribution]
    else:
        contribution = _contribution_row(identifiant)
        chaine = [situation, investigation, contribution]
    return commandes_boucle.ResultatTransition(
        objet=contribution, chaine=chaine, historique=[])


def test_post_expert_retourne_le_contrat_c5e(monkeypatch):
    client = _client(monkeypatch)
    appels = []

    def creer(depot, conn, tenant, **champs):
        appels.append((tenant, champs))
        return _resultat_expert()

    monkeypatch.setattr(boucle_routes.commandes_boucle, "creer_expert", creer)

    reponse = client.post(f"{BASE}/experts", json={
        "nom": "  Camille Martin  ",
        "domaine": "  Cartes bancaires  ",
        "role": "Expert métier",
        "methodes": ["Entretien"],
        "responsabilites": ["Valider les règles de gestion"],
        "perimetre": "Équipe cartes",
        "sources_autorisees": ["Confluence"],
        "outils_autorises": ["lecture"],
        "limites": ["Pas d'accès aux données clients"],
        "preuves": ["doc://entretien"],
        "confiance": 0.7,
    })

    assert reponse.status_code == 201, reponse.text
    corps = reponse.json()
    assert corps["tenant"] == TENANT
    assert corps["objet"]["type"] == "EXPERT"
    assert corps["type"] == "EXPERT"
    assert corps["role"] == "expert"
    assert [element["type"] for element in corps["chaine"]] == ["EXPERT"]
    assert corps["historique"] == []
    assert corps["idempotency_key"] is None
    assert appels[0][0] == TENANT
    assert appels[0][1]["nom"] == "Camille Martin"
    assert appels[0][1]["domaine"] == "Cartes bancaires"
    assert appels[0][1]["methodes"] == ["Entretien"]
    assert appels[0][1]["confiance"] == 0.7
    assert "statut" not in appels[0][1]
    assert "mode" not in appels[0][1]
    assert "id" not in appels[0][1]
    assert "tenant_id" not in appels[0][1]


@pytest.mark.parametrize("corps", [
    {},
    {"domaine": "Cartes"},
    {"nom": "Camille"},
    {"nom": "   ", "domaine": "Cartes"},
    {"nom": "Camille", "domaine": "   "},
    {"nom": "Camille", "domaine": "Cartes", "statut": "ARCHIVED"},
    {"nom": "Camille", "domaine": "Cartes", "mode": "OBSERVED"},
    {"nom": "Camille", "domaine": "Cartes", "id": "client-id"},
    {"nom": "Camille", "domaine": "Cartes", "tenant_id": AUTRE_TENANT},
    {"nom": "Camille", "domaine": "Cartes", "confiance": 1.2},
    {"nom": "Camille", "domaine": "Cartes", "champ_inconnu": True},
])
def test_post_expert_valide_le_corps_avant_la_commande(monkeypatch, corps):
    client = _client(monkeypatch)
    monkeypatch.setattr(
        boucle_routes.commandes_boucle, "creer_expert",
        lambda *_, **__: pytest.fail("la commande ne doit pas être appelée"),
    )
    assert client.post(f"{BASE}/experts", json=corps).status_code == 422


def test_post_expert_traduit_les_erreurs(monkeypatch):
    client = _client(monkeypatch)
    for erreur, statut in [
        (ObjetsExploitationInvalide("nom obligatoire"), 422),
        (ObjetInvalide("secret refusé"), 400),
        (psycopg.OperationalError("panne"), 503),
    ]:
        def echouer(*_, _erreur=erreur, **__):
            raise _erreur

        monkeypatch.setattr(boucle_routes.commandes_boucle, "creer_expert", echouer)
        reponse = client.post(
            f"{BASE}/experts", json={"nom": "Camille", "domaine": "Cartes"})
        assert reponse.status_code == statut
        assert "Traceback" not in reponse.text


def test_post_expert_json_malforme_repond_400(monkeypatch):
    client = _client(monkeypatch)
    reponse = client.post(
        f"{BASE}/experts",
        content=b"{pas du json",
        headers={"Content-Type": "application/json"},
    )
    assert reponse.status_code == 400, reponse.text


def test_post_expert_refuse_un_corps_json_non_objet_en_400(monkeypatch):
    client = _client(monkeypatch)
    reponse = client.post(
        f"{BASE}/experts",
        content=b"[]",
        headers={"Content-Type": "application/json"},
    )
    assert reponse.status_code == 400, reponse.text


def test_post_expert_refuse_une_cle_d_idempotence(monkeypatch):
    client = _client(monkeypatch)
    reponse = client.post(
        f"{BASE}/experts",
        json={"nom": "Camille", "domaine": "Cartes"},
        headers={"Idempotency-Key": "cle-1"},
    )
    assert reponse.status_code == 501


def test_sans_dsn_la_route_expert_repond_503(monkeypatch):
    monkeypatch.delenv("AUTH_MODE", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("JUMEAU_PG_DSN", raising=False)
    reponse = _app().post(
        f"{BASE}/experts", json={"nom": "Camille", "domaine": "Cartes"})
    assert reponse.status_code == 503
    assert "JUMEAU_PG_DSN" in reponse.json()["detail"]


def test_get_experts_retourne_la_liste_filtree(monkeypatch):
    client = _client(monkeypatch)
    appels = []

    def lister(depot, conn, tenant, *, domaine=None, statut=None, limite=100):
        appels.append((tenant, domaine, statut, limite))
        return [_expert_row()]

    monkeypatch.setattr(boucle_routes.commandes_boucle, "lister_experts", lister)
    reponse = client.get(
        f"{BASE}/experts",
        params={"domaine": "Cartes", "statut": "ACTIVE", "limite": 25},
        headers={"X-Tenant": "banque"},
    )

    assert reponse.status_code == 200
    assert reponse.json()["tenant"] == "banque"
    assert [objet["id"] for objet in reponse.json()["experts"]] == ["expert-1"]
    assert appels == [("banque", "Cartes", "ACTIVE", 25)]


def test_get_experts_refuse_un_statut_inconnu(monkeypatch):
    client = _client(monkeypatch)

    def echouer(*_, **__):
        raise ObjetsExploitationInvalide("statut inconnu : 'MAGIQUE'")

    monkeypatch.setattr(boucle_routes.commandes_boucle, "lister_experts", echouer)
    reponse = client.get(f"{BASE}/experts", params={"statut": "MAGIQUE"})
    assert reponse.status_code == 422


def _resultat_expert_statut(statut: str = "INACTIVE", **donnees):
    expert = _expert_row("expert-1", statut=statut, **donnees)
    return commandes_boucle.ResultatTransition(
        objet=expert, chaine=[expert],
        historique=[{"donnees": {"statut": "ACTIVE"}}])


def test_post_statut_expert_retourne_le_contrat_c5f(monkeypatch):
    client = _client(monkeypatch)
    appels = []

    def changer(depot, conn, tenant, expert_id, vers, *, motif=None, preuves=None):
        appels.append((tenant, expert_id, vers, motif, preuves))
        return _resultat_expert_statut(
            motif="Congé longue durée", preuves=["doc://rh"])

    monkeypatch.setattr(
        boucle_routes.commandes_boucle, "changer_statut_expert", changer)
    reponse = client.post(
        f"{BASE}/experts/expert-1/statut",
        json={
            "vers": "  inactive  ",
            "motif": "  Congé longue durée  ",
            "preuves": ["doc://rh"],
        },
        headers={"X-Tenant": "banque"},
    )

    assert reponse.status_code == 200, reponse.text
    corps = reponse.json()
    assert corps["tenant"] == "banque"
    assert corps["objet"]["type"] == "EXPERT"
    assert corps["type"] == "EXPERT"
    assert corps["role"] == "expert"
    assert corps["objet"]["donnees"]["statut"] == "INACTIVE"
    assert appels == [(
        "banque", "expert-1", "inactive", "Congé longue durée", ["doc://rh"])]


@pytest.mark.parametrize("corps", [
    {},
    {"vers": "   "},
    {"vers": "INACTIVE", "statut": "ACTIVE"},
    {"vers": "INACTIVE", "mode": "DECLARED"},
    {"vers": "INACTIVE", "id": "expert-2"},
    {"vers": "INACTIVE", "tenant_id": "autre"},
    {"vers": "INACTIVE", "champ_inconnu": True},
])
def test_post_statut_expert_valide_le_corps(monkeypatch, corps):
    client = _client(monkeypatch)
    monkeypatch.setattr(
        boucle_routes.commandes_boucle, "changer_statut_expert",
        lambda *_, **__: pytest.fail("la commande ne doit pas être appelée"))
    reponse = client.post(f"{BASE}/experts/expert-1/statut", json=corps)
    assert reponse.status_code == 422, reponse.text


def test_post_statut_expert_traduit_404_409_422_400_503(monkeypatch):
    client = _client(monkeypatch)
    for erreur, statut in [
        (commandes_boucle.SourceIntrouvable("expert", "expert-x"), 404),
        (commandes_boucle.TransitionRefusee("transition refusée"), 409),
        (ObjetsExploitationInvalide("statut inconnu"), 422),
        (ObjetInvalide("secret refusé"), 400),
        (psycopg.OperationalError("panne"), 503),
    ]:
        def echouer(*_, _erreur=erreur, **__):
            raise _erreur

        monkeypatch.setattr(
            boucle_routes.commandes_boucle, "changer_statut_expert", echouer)
        reponse = client.post(
            f"{BASE}/experts/expert-1/statut", json={"vers": "INACTIVE"})
        assert reponse.status_code == statut, reponse.text
        assert "Traceback" not in reponse.text


def test_post_statut_expert_json_malforme_ou_non_objet_repond_400(monkeypatch):
    client = _client(monkeypatch)
    for contenu in (b"{pas du json", b"[]"):
        reponse = client.post(
            f"{BASE}/experts/expert-1/statut",
            content=contenu,
            headers={"Content-Type": "application/json"},
        )
        assert reponse.status_code == 400, reponse.text


def test_post_statut_expert_refuse_une_cle_d_idempotence(monkeypatch):
    client = _client(monkeypatch)
    reponse = client.post(
        f"{BASE}/experts/expert-1/statut",
        json={"vers": "INACTIVE"},
        headers={"Idempotency-Key": "cle-1"},
    )
    assert reponse.status_code == 501


def test_post_statut_expert_ne_laisse_pas_passer_un_secret(monkeypatch):
    client = _client(monkeypatch)
    resultat = _resultat_expert_statut()
    resultat.objet["donnees"]["preuves"] = [{"password": "s3cr3t"}]
    monkeypatch.setattr(
        boucle_routes.commandes_boucle, "changer_statut_expert",
        lambda *_, **__: resultat)

    reponse = client.post(
        f"{BASE}/experts/expert-1/statut", json={"vers": "INACTIVE"})

    assert reponse.status_code == 200, reponse.text
    assert "s3cr3t" not in reponse.text
    assert reponse.json()["objet"]["donnees"]["preuves"] == [{"password": "***"}]


def test_openapi_documente_le_changement_de_statut_expert(monkeypatch):
    client = _client(monkeypatch)
    specification = client.get("/openapi.json").json()
    route = specification["paths"][f"{BASE}/experts/{{eid}}/statut"]["post"]
    schema = route["requestBody"]["content"]["application/json"]["schema"]

    assert schema["required"] == ["vers"]
    assert set(schema["properties"]) == {"vers", "motif", "preuves"}
    assert route["responses"]["200"]["content"]["application/json"]["schema"]
    assert "501" in route["responses"]
    assert "503" in route["responses"]


def test_post_contribution_investigation_retourne_le_contrat(monkeypatch):
    client = _client(monkeypatch)
    appels = []

    def creer(depot, conn, tenant, investigation_id, **champs):
        appels.append((tenant, investigation_id, champs))
        return _resultat_contribution()

    monkeypatch.setattr(
        boucle_routes.commandes_boucle, "creer_contribution_investigation", creer)
    reponse = client.post(f"{BASE}/investigations/inv-1/contributions", json={
        "expert_id": "expert-1",
        "contenu": "  La règle est contournée par le canal agence  ",
        "constats": ["La pièce est saisie après validation"],
        "claim_ids_proposes": ["claim-3"],
        "hypothesis_ids_soutenues": ["hypothesis-1"],
        "hypothesis_ids_contestees": ["hypothesis-2"],
        "inconnues": ["volume réel"],
        "contribution_le": "2026-11-08T10:00:00+00:00",
        "preuves": ["doc://entretien"],
        "confiance": 0.7,
    })

    assert reponse.status_code == 201, reponse.text
    corps = reponse.json()
    assert corps["objet"]["type"] == "EXPERT_CONTRIBUTION"
    assert corps["type"] == "EXPERT_CONTRIBUTION"
    assert corps["role"] == "contribution"
    assert [element["type"] for element in corps["chaine"]] == [
        "SITUATION", "INVESTIGATION", "EXPERT_CONTRIBUTION"]
    assert appels[0][0] == TENANT
    assert appels[0][1] == "inv-1"
    assert appels[0][2]["expert_id"] == "expert-1"
    assert appels[0][2]["contenu"] == "La règle est contournée par le canal agence"
    assert appels[0][2]["constats"] == ["La pièce est saisie après validation"]
    assert appels[0][2]["claim_ids_proposes"] == ["claim-3"]
    assert appels[0][2]["hypothesis_ids_soutenues"] == ["hypothesis-1"]
    assert appels[0][2]["hypothesis_ids_contestees"] == ["hypothesis-2"]
    assert appels[0][2]["inconnues"] == ["volume réel"]
    assert appels[0][2]["contribution_le"] == "2026-11-08T10:00:00+00:00"
    assert appels[0][2]["preuves"] == ["doc://entretien"]
    assert appels[0][2]["confiance"] == 0.7
    for interdit in ("statut", "mode", "id", "tenant_id", "investigation_id"):
        assert interdit not in appels[0][2]


def test_post_contribution_investigation_accepte_hypothesis_id(monkeypatch):
    client = _client(monkeypatch)
    appels = []

    def creer(depot, conn, tenant, investigation_id, **champs):
        appels.append((investigation_id, champs))
        return _resultat_contribution("contribution-1", hypothesis_id="hypothesis-1")

    monkeypatch.setattr(
        boucle_routes.commandes_boucle, "creer_contribution_investigation", creer)
    reponse = client.post(f"{BASE}/investigations/inv-1/contributions", json={
        "expert_id": "expert-1",
        "hypothesis_id": "hypothesis-1",
        "contenu": "Contribution ciblée",
    })

    assert reponse.status_code == 201, reponse.text
    assert appels[0][1]["hypothesis_id"] == "hypothesis-1"
    assert [element["type"] for element in reponse.json()["chaine"]] == [
        "SITUATION", "INVESTIGATION", "HYPOTHESIS", "EXPERT_CONTRIBUTION"]


@pytest.mark.parametrize("corps", [
    {},
    {"expert_id": "expert-1"},
    {"contenu": "Contribution"},
    {"expert_id": "expert-1", "contenu": "   "},
    {"expert_id": "   ", "contenu": "Contribution"},
    {"expert_id": "expert-1", "contenu": "Contribution", "statut": "ACCEPTED"},
    {"expert_id": "expert-1", "contenu": "Contribution", "mode": "OBSERVED"},
    {"expert_id": "expert-1", "contenu": "Contribution", "id": "client-id"},
    {"expert_id": "expert-1", "contenu": "Contribution", "tenant_id": "banque"},
    {"expert_id": "expert-1", "contenu": "Contribution", "investigation_id": "inv-1"},
    {"expert_id": "expert-1", "contenu": "Contribution", "confiance": 1.2},
    {"expert_id": "expert-1", "contenu": "Contribution", "constats": ["   "]},
    {"expert_id": "expert-1", "contenu": "Contribution", "champ_inconnu": True},
])
def test_post_contribution_investigation_valide_le_corps(monkeypatch, corps):
    client = _client(monkeypatch)
    monkeypatch.setattr(
        boucle_routes.commandes_boucle, "creer_contribution_investigation",
        lambda *_, **__: pytest.fail("la commande ne doit pas être appelée"),
    )
    assert client.post(
        f"{BASE}/investigations/inv-1/contributions", json=corps).status_code == 422


def test_post_contribution_hypothese_derive_la_route(monkeypatch):
    client = _client(monkeypatch)
    appels = []

    def creer(depot, conn, tenant, hypothesis_id, **champs):
        appels.append((tenant, hypothesis_id, champs))
        return _resultat_contribution("contribution-1", hypothesis_id="hypothesis-1")

    monkeypatch.setattr(
        boucle_routes.commandes_boucle, "creer_contribution_hypothese", creer)
    reponse = client.post(f"{BASE}/hypotheses/hypothesis-1/contributions", json={
        "expert_id": "expert-1",
        "contenu": "Contribution sur l'hypothèse",
        "constats": ["Constat"],
        "confiance": 0.6,
    })

    assert reponse.status_code == 201, reponse.text
    assert appels[0][0] == TENANT
    assert appels[0][1] == "hypothesis-1"
    assert appels[0][2]["expert_id"] == "expert-1"
    assert appels[0][2]["contenu"] == "Contribution sur l'hypothèse"
    assert appels[0][2]["constats"] == ["Constat"]
    assert appels[0][2]["confiance"] == 0.6
    for interdit in ("statut", "mode", "id", "tenant_id",
                     "investigation_id", "hypothesis_id"):
        assert interdit not in appels[0][2]
    assert [element["type"] for element in reponse.json()["chaine"]] == [
        "SITUATION", "INVESTIGATION", "HYPOTHESIS", "EXPERT_CONTRIBUTION"]


@pytest.mark.parametrize("corps", [
    {"expert_id": "expert-1", "contenu": "Contribution", "hypothesis_id": "autre"},
    {"expert_id": "expert-1", "contenu": "Contribution", "investigation_id": "inv-1"},
    {"expert_id": "expert-1", "contenu": "Contribution", "statut": "PROPOSED"},
    {"expert_id": "expert-1", "contenu": "Contribution", "mode": "DECLARED"},
])
def test_post_contribution_hypothese_refuse_les_liens_et_champs_serveur(monkeypatch, corps):
    client = _client(monkeypatch)
    monkeypatch.setattr(
        boucle_routes.commandes_boucle, "creer_contribution_hypothese",
        lambda *_, **__: pytest.fail("la commande ne doit pas être appelée"),
    )
    assert client.post(
        f"{BASE}/hypotheses/hypothesis-1/contributions", json=corps).status_code == 422


def test_post_contribution_investigation_json_malforme_repond_400(monkeypatch):
    client = _client(monkeypatch)
    reponse = client.post(
        f"{BASE}/investigations/inv-1/contributions",
        content=b"{pas du json",
        headers={"Content-Type": "application/json"},
    )
    assert reponse.status_code == 400


def test_post_contribution_hypothese_json_malforme_repond_400(monkeypatch):
    client = _client(monkeypatch)
    reponse = client.post(
        f"{BASE}/hypotheses/hypothesis-1/contributions",
        content=b"[]",
        headers={"Content-Type": "application/json"},
    )
    assert reponse.status_code == 400


@pytest.mark.parametrize("chemin", [
    f"{BASE}/investigations/inv-1/contributions",
    f"{BASE}/hypotheses/hypothesis-1/contributions",
])
def test_post_contribution_traduit_404_409_422_400_503(monkeypatch, chemin):
    client = _client(monkeypatch)
    nom_commande = (
        "creer_contribution_investigation"
        if "/investigations/" in chemin else "creer_contribution_hypothese")
    corps = {"expert_id": "expert-1", "contenu": "Contribution"}
    for erreur, statut in [
        (commandes_boucle.SourceIntrouvable("expert", "expert-x"), 404),
        (commandes_boucle.TransitionRefusee("investigation fermée"), 409),
        (ObjetsExploitationInvalide("validation"), 422),
        (ObjetInvalide("secret refusé"), 400),
        (psycopg.OperationalError("panne"), 503),
    ]:
        def echouer(*_, _erreur=erreur, **__):
            raise _erreur

        monkeypatch.setattr(
            boucle_routes.commandes_boucle, nom_commande, echouer)
        reponse = client.post(chemin, json=corps)
        assert reponse.status_code == statut
        assert "Traceback" not in reponse.text


def test_post_contribution_refuse_une_cle_d_idempotence(monkeypatch):
    client = _client(monkeypatch)
    for chemin in (
        f"{BASE}/investigations/inv-1/contributions",
        f"{BASE}/hypotheses/hypothesis-1/contributions",
    ):
        reponse = client.post(
            chemin,
            json={"expert_id": "expert-1", "contenu": "Contribution"},
            headers={"Idempotency-Key": "cle-1"},
        )
        assert reponse.status_code == 501


def test_get_contributions_retourne_la_liste_filtree(monkeypatch):
    client = _client(monkeypatch)
    appels = []

    def lister(depot, conn, tenant, *, expert_id=None, investigation_id=None,
               hypothesis_id=None, statut=None, limite=100):
        appels.append((tenant, expert_id, investigation_id, hypothesis_id, statut, limite))
        return [_contribution_row()]

    monkeypatch.setattr(
        boucle_routes.commandes_boucle, "lister_contributions", lister)
    reponse = client.get(
        f"{BASE}/contributions",
        params={
            "expert_id": "expert-1",
            "investigation_id": "inv-1",
            "hypothesis_id": "hypothesis-1",
            "statut": "PROPOSED",
            "limite": 25,
        },
        headers={"X-Tenant": "banque"},
    )

    assert reponse.status_code == 200
    assert reponse.json()["tenant"] == "banque"
    assert [objet["id"] for objet in reponse.json()["contributions"]] == [
        "contribution-1"]
    assert appels == [(
        "banque", "expert-1", "inv-1", "hypothesis-1", "PROPOSED", 25)]


def test_get_contributions_refuse_un_statut_inconnu(monkeypatch):
    client = _client(monkeypatch)

    def echouer(*_, **__):
        raise ObjetsExploitationInvalide("statut inconnu : 'MAGIQUE'")

    monkeypatch.setattr(
        boucle_routes.commandes_boucle, "lister_contributions", echouer)
    reponse = client.get(f"{BASE}/contributions", params={"statut": "MAGIQUE"})
    assert reponse.status_code == 422


def test_post_statut_contribution_retourne_le_contrat(monkeypatch):
    client = _client(monkeypatch)
    appels = []

    def changer(depot, conn, tenant, contribution_id, vers, **champs):
        appels.append((tenant, contribution_id, vers, champs))
        return _resultat_contribution()

    monkeypatch.setattr(
        boucle_routes.commandes_boucle, "changer_statut_contribution", changer)
    reponse = client.post(f"{BASE}/contributions/contribution-1/statut", json={
        "vers": "ACCEPTED",
        "motif": "  Relecture métier concordante  ",
        "preuves": ["preuve-1"],
    })

    assert reponse.status_code == 200, reponse.text
    corps = reponse.json()
    assert corps["objet"]["type"] == "EXPERT_CONTRIBUTION"
    assert corps["type"] == "EXPERT_CONTRIBUTION"
    assert corps["role"] == "contribution"
    assert appels[0][0] == TENANT
    assert appels[0][1] == "contribution-1"
    assert appels[0][2] == "ACCEPTED"
    assert appels[0][3]["motif"] == "Relecture métier concordante"
    assert appels[0][3]["preuves"] == ["preuve-1"]


@pytest.mark.parametrize("corps", [
    {},
    {"vers": "   "},
    {"vers": "ACCEPTED", "statut": "ARCHIVED"},
    {"vers": "ACCEPTED", "champ_inconnu": True},
])
def test_post_statut_contribution_valide_le_corps(monkeypatch, corps):
    client = _client(monkeypatch)
    monkeypatch.setattr(
        boucle_routes.commandes_boucle, "changer_statut_contribution",
        lambda *_, **__: pytest.fail("la commande ne doit pas être appelée"))
    assert client.post(
        f"{BASE}/contributions/contribution-1/statut", json=corps).status_code == 422


def test_post_statut_contribution_traduit_404_409_422_400_503(monkeypatch):
    client = _client(monkeypatch)
    for erreur, statut in [
        (commandes_boucle.SourceIntrouvable("contribution", "x"), 404),
        (commandes_boucle.TransitionRefusee("transition refusée"), 409),
        (ObjetsExploitationInvalide("statut inconnu"), 422),
        (ObjetInvalide("secret refusé"), 400),
        (psycopg.OperationalError("panne"), 503),
    ]:
        def echouer(*_, _erreur=erreur, **__):
            raise _erreur

        monkeypatch.setattr(
            boucle_routes.commandes_boucle, "changer_statut_contribution", echouer)
        reponse = client.post(
            f"{BASE}/contributions/contribution-1/statut", json={"vers": "ACCEPTED"})
        assert reponse.status_code == statut


def test_post_statut_contribution_json_malforme_repond_400(monkeypatch):
    client = _client(monkeypatch)
    reponse = client.post(
        f"{BASE}/contributions/contribution-1/statut",
        content=b"{pas du json",
        headers={"Content-Type": "application/json"},
    )
    assert reponse.status_code == 400, reponse.text


def test_post_statut_contribution_refuse_un_corps_json_non_objet_en_400(monkeypatch):
    client = _client(monkeypatch)
    reponse = client.post(
        f"{BASE}/contributions/contribution-1/statut",
        content=b"[]",
        headers={"Content-Type": "application/json"},
    )
    assert reponse.status_code == 400, reponse.text


def test_post_statut_contribution_refuse_une_cle_d_idempotence(monkeypatch):
    client = _client(monkeypatch)
    reponse = client.post(
        f"{BASE}/contributions/contribution-1/statut",
        json={"vers": "ACCEPTED"},
        headers={"Idempotency-Key": "cle-1"},
    )
    assert reponse.status_code == 501


def test_la_reponse_contribution_ne_laisse_pas_passer_un_secret(monkeypatch):
    client = _client(monkeypatch)
    resultat = _resultat_contribution()
    resultat.objet["donnees"]["preuves"] = [{"password": "s3cr3t"}]
    monkeypatch.setattr(
        boucle_routes.commandes_boucle, "creer_contribution_investigation",
        lambda *_, **__: resultat)

    reponse = client.post(f"{BASE}/investigations/inv-1/contributions", json={
        "expert_id": "expert-1", "contenu": "Contribution"})

    assert reponse.status_code == 201
    assert "s3cr3t" not in reponse.text
    assert reponse.json()["objet"]["donnees"]["preuves"] == [{"password": "***"}]


# --------------------------------------------------------------------------- #
# Postgres réel : registre, chaînes, invariant, atomicité et isolation tenant
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


def _pg_situation(tenant: str, *, situation_id: str = "sit-c5e") -> None:
    with psycopg.connect(DSN) as conn:
        situation = {**_situation_row(situation_id), "tenant_id": tenant}
        boucle.enregistrer_boucle(conn, tenant, objets=[situation], historique=True)


def _pg_investigation(
    tenant: str, *, situation_id: str = "sit-c5e",
    investigation_id: str = "inv-c5e", statut: str = "OPEN",
):
    with psycopg.connect(DSN) as conn:
        situation = boucle.lire_boucle(conn, tenant, situation_id, as_dict=False)
        investigation_obj = boucle.ouvrir_investigation(
            situation, id=investigation_id, tenant_id=tenant,
            titre="Comprendre la latence", question="Pourquoi ?", statut=statut)
        boucle.enregistrer_boucle(
            conn, tenant, objets=[investigation_obj], historique=True)
        return investigation_obj


def _pg_expert(tenant: str, *, nom: str = "Camille Martin", domaine: str = "Cartes"):
    with psycopg.connect(DSN) as conn:
        return commandes_boucle.creer_expert(
            boucle, conn, tenant, nom=nom, domaine=domaine)


def _pg_hypothese(tenant: str, investigation_id: str, *, enonce: str = "Hypothèse"):
    with psycopg.connect(DSN) as conn:
        return commandes_boucle.creer_hypothese(
            boucle, conn, tenant, investigation_id, enonce=enonce)


@besoin_pg
def test_pg_registre_experts_et_contribution_depuis_investigation(monkeypatch):
    tenant = f"c5e-{uuid.uuid4().hex[:10]}"
    client = _client_pg(monkeypatch)
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            _pg_situation(tenant)
            _pg_investigation(tenant)
        hypothese = _pg_hypothese(
            tenant, "inv-c5e", enonce="La règle est contournée")

        expert = client.post(
            f"{BASE}/experts",
            json={
                "nom": "  Camille Martin  ",
                "domaine": "  Cartes bancaires  ",
                "role": "Expert métier",
                "methodes": ["Entretien"],
                "responsabilites": ["Valider les règles de gestion"],
                "limites": ["Pas d'accès aux données clients"],
            },
            headers={"X-Tenant": tenant},
        )
        assert expert.status_code == 201, expert.text
        expert_id = expert.json()["objet"]["id"]
        assert expert.json()["objet"]["donnees"]["statut"] == "ACTIVE"
        assert expert.json()["objet"]["mode"] == "DECLARED"
        assert [element["type"] for element in expert.json()["chaine"]] == ["EXPERT"]

        registre = client.get(
            f"{BASE}/experts",
            params={"domaine": "Cartes bancaires", "statut": "ACTIVE"},
            headers={"X-Tenant": tenant},
        )
        assert registre.status_code == 200, registre.text
        assert [objet["id"] for objet in registre.json()["experts"]] == [expert_id]

        creation = client.post(
            f"{BASE}/investigations/inv-c5e/contributions",
            json={
                "expert_id": expert_id,
                "contenu": "La règle est contournée par le canal agence",
                "constats": ["La pièce est saisie après validation"],
                "claim_ids_proposes": ["claim-3"],
                "hypothesis_ids_soutenues": [hypothese.objet["id"]],
                "inconnues": ["volume réel"],
                "confiance": 0.7,
            },
            headers={"X-Tenant": tenant},
        )
        assert creation.status_code == 201, creation.text
        contribution_id = creation.json()["objet"]["id"]
        assert creation.json()["objet"]["donnees"]["statut"] == "PROPOSED"
        assert creation.json()["objet"]["mode"] == "DECLARED"
        assert creation.json()["objet"]["donnees"]["investigation_id"] == "inv-c5e"
        assert [element["type"] for element in creation.json()["chaine"]] == [
            "SITUATION", "INVESTIGATION", "EXPERT_CONTRIBUTION"]

        investigation_lue = client.get(
            f"{BASE}/objets/inv-c5e", headers={"X-Tenant": tenant}
        ).json()["objet"]
        assert investigation_lue["donnees"]["expert_ids"] == [expert_id]

        lecture = client.get(
            f"{BASE}/objets/{contribution_id}",
            params={"historique": True},
            headers={"X-Tenant": tenant},
        )
        assert lecture.status_code == 200
        assert [element["type"] for element in lecture.json()["chaine"]] == [
            "SITUATION", "INVESTIGATION", "EXPERT_CONTRIBUTION"]

        liste = client.get(
            f"{BASE}/contributions",
            params={"expert_id": expert_id, "investigation_id": "inv-c5e",
                    "statut": "PROPOSED"},
            headers={"X-Tenant": tenant},
        )
        assert liste.status_code == 200, liste.text
        assert [objet["id"] for objet in liste.json()["contributions"]] == [
            contribution_id]

        acceptee = client.post(
            f"{BASE}/contributions/{contribution_id}/statut",
            json={"vers": "ACCEPTED", "motif": "Relecture concordante",
                  "preuves": ["preuve-1"]},
            headers={"X-Tenant": tenant},
        )
        assert acceptee.status_code == 200, acceptee.text
        assert acceptee.json()["objet"]["donnees"]["statut"] == "ACCEPTED"
        assert acceptee.json()["objet"]["donnees"]["motif"] == "Relecture concordante"
        assert acceptee.json()["objet"]["donnees"]["preuves"] == ["preuve-1"]
        assert acceptee.json()["historique"][-1]["donnees"]["statut"] == "PROPOSED"

        retour = client.post(
            f"{BASE}/contributions/{contribution_id}/statut",
            json={"vers": "PROPOSED"},
            headers={"X-Tenant": tenant},
        )
        assert retour.status_code == 409, retour.text

        archivee = client.post(
            f"{BASE}/contributions/{contribution_id}/statut",
            json={"vers": "ARCHIVED"},
            headers={"X-Tenant": tenant},
        )
        assert archivee.status_code == 200, archivee.text
        terminale = client.post(
            f"{BASE}/contributions/{contribution_id}/statut",
            json={"vers": "ACCEPTED"},
            headers={"X-Tenant": tenant},
        )
        assert terminale.status_code == 409

        with psycopg.connect(DSN) as conn:
            assert "EXPERT" in boucle.TYPES_LECTURE
            assert "EXPERT_CONTRIBUTION" in boucle.TYPES_LECTURE
            assert "EXPERT" not in boucle.TYPES_BOUCLE
            assert "EXPERT_CONTRIBUTION" not in boucle.TYPES_BOUCLE
            objet = boucle.lire_boucle(
                conn, tenant, contribution_id, as_dict=False)
            assert isinstance(objet, domaine.ExpertContribution)
            assert objet.expert_id == expert_id
            assert objet.investigation_id == "inv-c5e"
            with pytest.raises(boucle.BoucleInvalide):
                boucle.enregistrer_boucle(conn, tenant, objets=[objet], historique=True)
    finally:
        _nettoyer(tenant)


@besoin_pg
def test_pg_contribution_depuis_hypothese_chaine_complete(monkeypatch):
    tenant = f"c5e-{uuid.uuid4().hex[:10]}"
    client = _client_pg(monkeypatch)
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            _pg_situation(tenant)
            _pg_investigation(tenant)
        expert = _pg_expert(tenant)
        hypothese = _pg_hypothese(tenant, "inv-c5e", enonce="Contrôle synchrone")

        creation = client.post(
            f"{BASE}/hypotheses/{hypothese.objet['id']}/contributions",
            json={
                "expert_id": expert.objet["id"],
                "contenu": "Le contournement est confirmé par le canal agence",
                "hypothesis_ids_soutenues": [hypothese.objet["id"]],
                "confiance": 0.8,
            },
            headers={"X-Tenant": tenant},
        )
        assert creation.status_code == 201, creation.text
        corps = creation.json()
        assert corps["objet"]["donnees"]["hypothesis_id"] == hypothese.objet["id"]
        assert corps["objet"]["donnees"]["investigation_id"] == "inv-c5e"
        assert [element["type"] for element in corps["chaine"]] == [
            "SITUATION", "INVESTIGATION", "HYPOTHESIS", "EXPERT_CONTRIBUTION"]

        lecture = client.get(
            f"{BASE}/objets/{corps['objet']['id']}",
            params={"historique": True},
            headers={"X-Tenant": tenant},
        )
        assert [element["type"] for element in lecture.json()["chaine"]] == [
            "SITUATION", "INVESTIGATION", "HYPOTHESIS", "EXPERT_CONTRIBUTION"]

        filtrees = client.get(
            f"{BASE}/contributions",
            params={"hypothesis_id": hypothese.objet["id"]},
            headers={"X-Tenant": tenant},
        )
        assert [objet["id"] for objet in filtrees.json()["contributions"]] == [
            corps["objet"]["id"]]

        with psycopg.connect(DSN) as conn:
            investigation = boucle.lire_boucle(conn, tenant, "inv-c5e", as_dict=True)
        assert investigation["donnees"]["expert_ids"] == [expert.objet["id"]]
    finally:
        _nettoyer(tenant)


@besoin_pg
def test_pg_hypothese_hors_investigation_refusee_sans_ecriture(monkeypatch):
    tenant = f"c5e-{uuid.uuid4().hex[:10]}"
    client = _client_pg(monkeypatch)
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            _pg_situation(tenant)
            _pg_investigation(tenant, investigation_id="inv-1")
            _pg_investigation(tenant, investigation_id="inv-2")
        expert = _pg_expert(tenant)
        hypothese = _pg_hypothese(tenant, "inv-2")

        reponse = client.post(
            f"{BASE}/investigations/inv-1/contributions",
            json={
                "expert_id": expert.objet["id"],
                "hypothesis_id": hypothese.objet["id"],
                "contenu": "Contribution incohérente",
            },
            headers={"X-Tenant": tenant},
        )
        assert reponse.status_code == 409, reponse.text

        with psycopg.connect(DSN) as conn:
            nombre = conn.execute(
                "SELECT count(*) FROM objet_entreprise "
                "WHERE tenant_id = %s AND type = 'EXPERT_CONTRIBUTION'",
                (tenant,),
            ).fetchone()[0]
            investigation = boucle.lire_boucle(conn, tenant, "inv-1", as_dict=True)
        assert nombre == 0
        assert investigation["donnees"]["expert_ids"] == []
    finally:
        _nettoyer(tenant)


@besoin_pg
def test_pg_investigation_fermee_refusee_sans_ecriture(monkeypatch):
    tenant = f"c5e-{uuid.uuid4().hex[:10]}"
    client = _client_pg(monkeypatch)
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            _pg_situation(tenant)
            _pg_investigation(tenant, investigation_id="inv-fermee", statut="CLOSED")
        expert = _pg_expert(tenant)

        reponse = client.post(
            f"{BASE}/investigations/inv-fermee/contributions",
            json={"expert_id": expert.objet["id"], "contenu": "Contribution"},
            headers={"X-Tenant": tenant},
        )
        assert reponse.status_code == 409, reponse.text

        with psycopg.connect(DSN) as conn:
            nombre = conn.execute(
                "SELECT count(*) FROM objet_entreprise "
                "WHERE tenant_id = %s AND type = 'EXPERT_CONTRIBUTION'",
                (tenant,),
            ).fetchone()[0]
            investigation = boucle.lire_boucle(
                conn, tenant, "inv-fermee", as_dict=True)
        assert nombre == 0
        assert investigation["donnees"]["expert_ids"] == []
    finally:
        _nettoyer(tenant)


@besoin_pg
def test_pg_appel_direct_a_la_persistance_refuse_l_invariant():
    tenant = f"c5e-{uuid.uuid4().hex[:10]}"
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            _pg_situation(tenant)
            _pg_investigation(tenant, investigation_id="inv-1")
            _pg_investigation(tenant, investigation_id="inv-2")
        expert = _pg_expert(tenant)
        hypothese_inv2 = _pg_hypothese(tenant, "inv-2")

        contournement = {
            "id": "contribution-contournement",
            "tenant_id": tenant,
            "famille": "investigation",
            "type": "EXPERT_CONTRIBUTION",
            "mode": "DECLARED",
            **DATES,
            "expert_id": expert.objet["id"],
            "investigation_id": "inv-1",
            "hypothesis_id": hypothese_inv2.objet["id"],
            "contenu": "Écriture directe incohérente",
            "statut": "PROPOSED",
        }
        with psycopg.connect(DSN) as conn, \
                pytest.raises(ObjetsExploitationInvalide) as levee:
            objets_exploitation.enregistrer_objets_exploitation(
                conn, tenant, contournement)
        assert "appartient" in str(levee.value)

        with psycopg.connect(DSN) as conn:
            assert boucle.lire_boucle(
                conn, tenant, "contribution-contournement") is None
            investigation = boucle.lire_boucle(conn, tenant, "inv-1", as_dict=True)
        assert investigation["donnees"]["expert_ids"] == []
    finally:
        _nettoyer(tenant)


@besoin_pg
def test_pg_second_tenant_ne_voit_ni_ne_relie_experts_et_contributions(monkeypatch):
    tenant = f"c5e-{uuid.uuid4().hex[:10]}"
    autre = f"{tenant}-autre"
    client = _client_pg(monkeypatch)
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            _pg_situation(tenant)
            _pg_investigation(tenant)
        expert = _pg_expert(tenant)
        with psycopg.connect(DSN) as conn:
            commandes_boucle.creer_contribution_investigation(
                boucle, conn, tenant, "inv-c5e",
                expert_id=expert.objet["id"], contenu="Contribution tenant A")

        for url, methode in (
            (f"{BASE}/experts", "get"),
            (f"{BASE}/contributions", "get"),
        ):
            reponse = getattr(client, methode)(url, headers={"X-Tenant": autre})
            assert reponse.status_code == 200
            cle = "experts" if url.endswith("/experts") else "contributions"
            assert reponse.json()[cle] == []

        reponse = client.post(
            f"{BASE}/investigations/inv-c5e/contributions",
            json={"expert_id": expert.objet["id"], "contenu": "Contribution B"},
            headers={"X-Tenant": autre},
        )
        assert reponse.status_code == 404

        with psycopg.connect(DSN) as conn:
            assert boucle.lire_boucle(conn, autre, "inv-c5e") is None
            assert objets_exploitation.lister_objets_exploitation(
                conn, autre, type_="EXPERT") == []
            assert objets_exploitation.lister_objets_exploitation(
                conn, autre, type_="EXPERT_CONTRIBUTION") == []
    finally:
        _nettoyer(tenant)
        _nettoyer(autre)


@besoin_pg
def test_pg_liste_filtre_et_tri_deterministe():
    tenant = f"c5e-{uuid.uuid4().hex[:10]}"
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            _pg_situation(tenant)
            _pg_investigation(tenant, investigation_id="inv-1")
            _pg_investigation(tenant, investigation_id="inv-2")
        expert_1 = _pg_expert(tenant, nom="Expert 1", domaine="Cartes")
        expert_2 = _pg_expert(tenant, nom="Expert 2", domaine="Finance")
        hypothese = _pg_hypothese(tenant, "inv-1")

        with psycopg.connect(DSN) as conn:
            premiere = commandes_boucle.creer_contribution_investigation(
                boucle, conn, tenant, "inv-1",
                expert_id=expert_1.objet["id"], contenu="Contribution 1")
            seconde = commandes_boucle.creer_contribution_investigation(
                boucle, conn, tenant, "inv-2",
                expert_id=expert_1.objet["id"], contenu="Contribution 2")
            troisieme = commandes_boucle.creer_contribution_hypothese(
                boucle, conn, tenant, hypothese.objet["id"],
                expert_id=expert_2.objet["id"], contenu="Contribution 3")
            commandes_boucle.changer_statut_contribution(
                boucle, conn, tenant, troisieme.objet["id"], "ACCEPTED")

        with psycopg.connect(DSN) as conn:
            toutes = commandes_boucle.lister_contributions(
                boucle, conn, tenant)
            assert [objet["id"] for objet in toutes] == sorted(
                [premiere.objet["id"], seconde.objet["id"], troisieme.objet["id"]])

            par_expert = commandes_boucle.lister_contributions(
                boucle, conn, tenant, expert_id=expert_1.objet["id"])
            assert {objet["id"] for objet in par_expert} == {
                premiere.objet["id"], seconde.objet["id"]}

            par_hypothese = commandes_boucle.lister_contributions(
                boucle, conn, tenant, hypothesis_id=hypothese.objet["id"])
            assert [objet["id"] for objet in par_hypothese] == [troisieme.objet["id"]]

            acceptees = commandes_boucle.lister_contributions(
                boucle, conn, tenant, statut="ACCEPTED")
            assert [objet["id"] for objet in acceptees] == [troisieme.objet["id"]]

            assert len(commandes_boucle.lister_contributions(
                boucle, conn, tenant, limite=1)) == 1

            experts_cartes = commandes_boucle.lister_experts(
                boucle, conn, tenant, domaine="Cartes")
            assert [objet["id"] for objet in experts_cartes] == [expert_1.objet["id"]]
    finally:
        _nettoyer(tenant)


@besoin_pg
def test_pg_derivation_hypothese_seule_a_la_persistance(monkeypatch):
    """Un appel direct avec hypothesis_id seul dérive investigation_id et le lien inverse."""
    tenant = f"c5e-{uuid.uuid4().hex[:10]}"
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            _pg_situation(tenant)
            _pg_investigation(tenant)
        expert = _pg_expert(tenant)
        hypothese = _pg_hypothese(tenant, "inv-c5e")
        appels_verrouillage: list[set[str]] = []
        verrouiller = objets_exploitation._lire_verrouilles

        def espion_verrouillage(conn, tenant_appel, identifiants):
            appels_verrouillage.append(set(identifiants))
            return verrouiller(conn, tenant_appel, identifiants)

        monkeypatch.setattr(
            objets_exploitation, "_lire_verrouilles", espion_verrouillage)

        contribution = {
            "id": "contribution-hypothese-seule",
            "tenant_id": tenant,
            "famille": "investigation",
            "type": "EXPERT_CONTRIBUTION",
            "mode": "DECLARED",
            **DATES,
            "expert_id": expert.objet["id"],
            "hypothesis_id": hypothese.objet["id"],
            "contenu": "Contribution dérivée à la persistance",
            "statut": "PROPOSED",
        }
        with psycopg.connect(DSN) as conn:
            enregistre = objets_exploitation.enregistrer_objets_exploitation(
                conn, tenant, contribution)

        assert enregistre["donnees"]["hypothesis_id"] == hypothese.objet["id"]
        assert enregistre["donnees"]["investigation_id"] == "inv-c5e"
        assert appels_verrouillage, "la persistance doit verrouiller les parents"
        assert "inv-c5e" in appels_verrouillage[0]

        with psycopg.connect(DSN) as conn:
            investigation = boucle.lire_boucle(conn, tenant, "inv-c5e", as_dict=True)
            liste = objets_exploitation.lister_objets_exploitation(
                conn, tenant, type_="EXPERT_CONTRIBUTION",
                investigation_id="inv-c5e")
        assert investigation["donnees"]["expert_ids"] == [expert.objet["id"]]
        assert [objet["id"] for objet in liste] == ["contribution-hypothese-seule"]
    finally:
        _nettoyer(tenant)


@besoin_pg
def test_pg_cycle_de_vie_expert_administrable(monkeypatch):
    tenant = f"c5f-{uuid.uuid4().hex[:10]}"
    autre = f"{tenant}-autre"
    client = _client_pg(monkeypatch)
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            _pg_situation(tenant)
            _pg_investigation(tenant)
        expert = _pg_expert(tenant)
        expert_id = expert.objet["id"]
        expert_autre = _pg_expert(autre)

        actifs = client.get(
            f"{BASE}/experts", params={"statut": "ACTIVE"},
            headers={"X-Tenant": tenant})
        assert [objet["id"] for objet in actifs.json()["experts"]] == [expert_id]

        inactif = client.post(
            f"{BASE}/experts/{expert_id}/statut",
            json={
                "vers": "INACTIVE",
                "motif": "  Congé longue durée  ",
                "preuves": ["doc://rh"],
            },
            headers={"X-Tenant": tenant},
        )
        assert inactif.status_code == 200, inactif.text
        assert inactif.json()["objet"]["donnees"]["statut"] == "INACTIVE"
        assert inactif.json()["objet"]["donnees"]["motif"] == "Congé longue durée"
        assert inactif.json()["objet"]["donnees"]["preuves"] == ["doc://rh"]
        assert inactif.json()["historique"][-1]["donnees"]["statut"] == "ACTIVE"

        inactifs = client.get(
            f"{BASE}/experts", params={"statut": "INACTIVE"},
            headers={"X-Tenant": tenant})
        assert [objet["id"] for objet in inactifs.json()["experts"]] == [expert_id]

        for cible in ("ACTIVE", "ARCHIVED"):
            reponse = client.post(
                f"{BASE}/experts/{expert_id}/statut",
                json={"vers": cible}, headers={"X-Tenant": tenant})
            assert reponse.status_code == 200, reponse.text
            assert reponse.json()["objet"]["donnees"]["statut"] == cible

        terminal = client.post(
            f"{BASE}/experts/{expert_id}/statut",
            json={"vers": "INACTIVE"}, headers={"X-Tenant": tenant})
        assert terminal.status_code == 409, terminal.text

        inconnu = client.post(
            f"{BASE}/experts/{expert_id}/statut",
            json={"vers": "MAGIQUE"}, headers={"X-Tenant": tenant})
        assert inconnu.status_code == 422, inconnu.text

        hypothese = _pg_hypothese(tenant, "inv-c5e")
        mauvais_type = client.post(
            f"{BASE}/experts/{hypothese.objet['id']}/statut",
            json={"vers": "INACTIVE"}, headers={"X-Tenant": tenant})
        assert mauvais_type.status_code == 422, mauvais_type.text

        absent = client.post(
            f"{BASE}/experts/expert-absent/statut",
            json={"vers": "INACTIVE"}, headers={"X-Tenant": tenant})
        assert absent.status_code == 404, absent.text

        hors_tenant = client.post(
            f"{BASE}/experts/{expert_autre.objet['id']}/statut",
            json={"vers": "INACTIVE"}, headers={"X-Tenant": tenant})
        assert hors_tenant.status_code == 404, hors_tenant.text

        with psycopg.connect(DSN) as conn:
            ligne = boucle.lire_boucle(conn, tenant, expert_id, historique=True)
        assert ligne["donnees"]["statut"] == "ARCHIVED"
        assert len(ligne["historique"]) == 3
    finally:
        _nettoyer(tenant)
        _nettoyer(autre)


@pytest.mark.parametrize(("champ", "valeur"), [
    ("motif", "ghp_abcdefghijkl"),
    ("preuves", ["ghp_abcdefghijkl"]),
])
@besoin_pg
def test_pg_secret_dans_statut_expert_refuse_sans_ecriture(
    monkeypatch, champ, valeur,
):
    tenant = f"c5f-{uuid.uuid4().hex[:10]}"
    client = _client_pg(monkeypatch)
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
        expert = _pg_expert(tenant)

        reponse = client.post(
            f"{BASE}/experts/{expert.objet['id']}/statut",
            json={"vers": "INACTIVE", champ: valeur},
            headers={"X-Tenant": tenant},
        )
        assert reponse.status_code == 400, reponse.text
        assert "ghp_abcdefghijkl" not in reponse.text

        with psycopg.connect(DSN) as conn:
            ligne = boucle.lire_boucle(
                conn, tenant, expert.objet["id"], historique=True)
        assert ligne["donnees"]["statut"] == "ACTIVE"
        assert ligne["version"] == 1
        assert ligne["historique"] == []
    finally:
        _nettoyer(tenant)


@besoin_pg
def test_pg_contribution_cite_hypotheses_validees_des_deux_routes(monkeypatch):
    tenant = f"c5f-{uuid.uuid4().hex[:10]}"
    client = _client_pg(monkeypatch)
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            _pg_situation(tenant)
            _pg_investigation(tenant)
        expert = _pg_expert(tenant)
        soutenue = _pg_hypothese(tenant, "inv-c5e", enonce="Soutenue")
        contestee = _pg_hypothese(tenant, "inv-c5e", enonce="Contestée")
        source = _pg_hypothese(tenant, "inv-c5e", enonce="Source")

        depuis_investigation = client.post(
            f"{BASE}/investigations/inv-c5e/contributions",
            json={
                "expert_id": expert.objet["id"],
                "contenu": "Depuis l'investigation",
                "hypothesis_ids_soutenues": [soutenue.objet["id"]],
                "hypothesis_ids_contestees": [contestee.objet["id"]],
            },
            headers={"X-Tenant": tenant},
        )
        assert depuis_investigation.status_code == 201, depuis_investigation.text
        donnees = depuis_investigation.json()["objet"]["donnees"]
        assert donnees["hypothesis_ids_soutenues"] == [soutenue.objet["id"]]
        assert donnees["hypothesis_ids_contestees"] == [contestee.objet["id"]]

        depuis_hypothese = client.post(
            f"{BASE}/hypotheses/{source.objet['id']}/contributions",
            json={
                "expert_id": expert.objet["id"],
                "contenu": "Depuis l'hypothèse",
                "hypothesis_ids_soutenues": [soutenue.objet["id"]],
                "hypothesis_ids_contestees": [contestee.objet["id"]],
            },
            headers={"X-Tenant": tenant},
        )
        assert depuis_hypothese.status_code == 201, depuis_hypothese.text
        donnees = depuis_hypothese.json()["objet"]["donnees"]
        assert donnees["investigation_id"] == "inv-c5e"
        assert donnees["hypothesis_ids_soutenues"] == [soutenue.objet["id"]]
        assert donnees["hypothesis_ids_contestees"] == [contestee.objet["id"]]

        with psycopg.connect(DSN) as conn:
            nombre = conn.execute(
                "SELECT count(*) FROM objet_entreprise "
                "WHERE tenant_id = %s AND type = 'EXPERT_CONTRIBUTION'",
                (tenant,),
            ).fetchone()[0]
        assert nombre == 2
    finally:
        _nettoyer(tenant)


@besoin_pg
def test_pg_statut_expert_refuse_les_transitions_identiques(monkeypatch):
    tenant = f"c5f-{uuid.uuid4().hex[:10]}"
    client = _client_pg(monkeypatch)
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
        expert = _pg_expert(tenant)
        url = f"{BASE}/experts/{expert.objet['id']}/statut"
        headers = {"X-Tenant": tenant}

        for cible in ("ACTIVE", "INACTIVE", "ARCHIVED"):
            if cible != "ACTIVE":
                changement = client.post(
                    url, json={"vers": cible}, headers=headers)
                assert changement.status_code == 200, changement.text
            identique = client.post(url, json={"vers": cible}, headers=headers)
            assert identique.status_code == 409, identique.text

        with psycopg.connect(DSN) as conn:
            ligne = boucle.lire_boucle(
                conn, tenant, expert.objet["id"], historique=True)
        assert ligne["donnees"]["statut"] == "ARCHIVED"
        assert len(ligne["historique"]) == 2
    finally:
        _nettoyer(tenant)


@pytest.mark.parametrize("champ", [
    "hypothesis_ids_soutenues", "hypothesis_ids_contestees",
])
@besoin_pg
def test_pg_contribution_cite_hypothese_inconnue_refusee_sans_ecriture(
    monkeypatch, champ,
):
    tenant = f"c5f-{uuid.uuid4().hex[:10]}"
    client = _client_pg(monkeypatch)
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            _pg_situation(tenant)
            _pg_investigation(tenant)
        expert = _pg_expert(tenant)
        corps = {
            "expert_id": expert.objet["id"],
            "contenu": "Citation inconnue",
            champ: ["hypothesis-inconnue"],
        }

        reponse = client.post(
            f"{BASE}/investigations/inv-c5e/contributions",
            json=corps, headers={"X-Tenant": tenant})
        assert reponse.status_code == 422, reponse.text
        assert "introuvable" in reponse.json()["detail"]

        with psycopg.connect(DSN) as conn:
            nombre = conn.execute(
                "SELECT count(*) FROM objet_entreprise "
                "WHERE tenant_id = %s AND type = 'EXPERT_CONTRIBUTION'",
                (tenant,),
            ).fetchone()[0]
            investigation = boucle.lire_boucle(
                conn, tenant, "inv-c5e", as_dict=True)
        assert nombre == 0
        assert investigation["donnees"]["expert_ids"] == []
    finally:
        _nettoyer(tenant)


@besoin_pg
def test_pg_contribution_cite_hypothese_autre_tenant_refusee(monkeypatch):
    tenant = f"c5f-{uuid.uuid4().hex[:10]}"
    autre = f"{tenant}-autre"
    client = _client_pg(monkeypatch)
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            _pg_situation(tenant)
            _pg_investigation(tenant)
            _pg_situation(autre)
            _pg_investigation(autre, investigation_id="inv-autre")
        expert = _pg_expert(tenant)
        hypothese_autre = _pg_hypothese(autre, "inv-autre")

        reponse = client.post(
            f"{BASE}/investigations/inv-c5e/contributions",
            json={
                "expert_id": expert.objet["id"],
                "contenu": "Contribution inter-tenant",
                "hypothesis_ids_soutenues": [hypothese_autre.objet["id"]],
            },
            headers={"X-Tenant": tenant},
        )
        assert reponse.status_code == 422, reponse.text

        with psycopg.connect(DSN) as conn:
            nombre = conn.execute(
                "SELECT count(*) FROM objet_entreprise "
                "WHERE tenant_id = %s AND type = 'EXPERT_CONTRIBUTION'",
                (tenant,),
            ).fetchone()[0]
            investigation = boucle.lire_boucle(
                conn, tenant, "inv-c5e", as_dict=True)
        assert nombre == 0
        assert investigation["donnees"]["expert_ids"] == []
    finally:
        _nettoyer(tenant)
        _nettoyer(autre)


@besoin_pg
def test_pg_contribution_cite_hypothese_autre_investigation_refusee_des_deux_routes(
    monkeypatch,
):
    tenant = f"c5f-{uuid.uuid4().hex[:10]}"
    client = _client_pg(monkeypatch)
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            _pg_situation(tenant)
            _pg_investigation(tenant, investigation_id="inv-1")
            _pg_investigation(tenant, investigation_id="inv-2")
        expert = _pg_expert(tenant)
        source = _pg_hypothese(tenant, "inv-1", enonce="Source")
        hors_parent = _pg_hypothese(tenant, "inv-2", enonce="Hors parent")

        depuis_investigation = client.post(
            f"{BASE}/investigations/inv-1/contributions",
            json={
                "expert_id": expert.objet["id"],
                "contenu": "Citation hors investigation",
                "hypothesis_ids_soutenues": [hors_parent.objet["id"]],
            },
            headers={"X-Tenant": tenant},
        )
        assert depuis_investigation.status_code == 422, depuis_investigation.text
        assert "appartient" in depuis_investigation.json()["detail"]

        depuis_hypothese = client.post(
            f"{BASE}/hypotheses/{source.objet['id']}/contributions",
            json={
                "expert_id": expert.objet["id"],
                "contenu": "Citation hors investigation depuis hypothèse",
                "hypothesis_ids_contestees": [hors_parent.objet["id"]],
            },
            headers={"X-Tenant": tenant},
        )
        assert depuis_hypothese.status_code == 422, depuis_hypothese.text
        assert "appartient" in depuis_hypothese.json()["detail"]

        with psycopg.connect(DSN) as conn:
            nombre = conn.execute(
                "SELECT count(*) FROM objet_entreprise "
                "WHERE tenant_id = %s AND type = 'EXPERT_CONTRIBUTION'",
                (tenant,),
            ).fetchone()[0]
            investigation = boucle.lire_boucle(
                conn, tenant, "inv-1", as_dict=True)
        assert nombre == 0
        assert investigation["donnees"]["expert_ids"] == []
    finally:
        _nettoyer(tenant)


@besoin_pg
def test_pg_appel_direct_cite_hypothese_invalide_refuse_sans_ecriture():
    tenant = f"c5f-{uuid.uuid4().hex[:10]}"
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            _pg_situation(tenant)
            _pg_investigation(tenant, investigation_id="inv-1")
            _pg_investigation(tenant, investigation_id="inv-2")
        expert = _pg_expert(tenant)
        hors_parent = _pg_hypothese(tenant, "inv-2")

        contournement = {
            "id": "contribution-citation-directe",
            "tenant_id": tenant,
            "famille": "investigation",
            "type": "EXPERT_CONTRIBUTION",
            "mode": "DECLARED",
            **DATES,
            "expert_id": expert.objet["id"],
            "investigation_id": "inv-1",
            "contenu": "Écriture directe avec citation invalide",
            "statut": "PROPOSED",
            "hypothesis_ids_soutenues": [hors_parent.objet["id"]],
        }
        with psycopg.connect(DSN) as conn, \
                pytest.raises(ObjetsExploitationInvalide) as levee:
            objets_exploitation.enregistrer_objets_exploitation(
                conn, tenant, contournement)
        assert "appartient" in str(levee.value)

        with psycopg.connect(DSN) as conn:
            assert boucle.lire_boucle(
                conn, tenant, "contribution-citation-directe") is None
            investigation = boucle.lire_boucle(
                conn, tenant, "inv-1", as_dict=True)
        assert investigation["donnees"]["expert_ids"] == []
    finally:
        _nettoyer(tenant)


@pytest.mark.parametrize(("champ", "valeur"), [
    ("nom", "ghp_abcdefghijkl"),
    ("sources_autorisees", ["ghp_abcdefghijkl"]),
])
def test_pg_secret_dans_expert_refuse_sans_ecriture(champ, valeur):
    tenant = f"c5e-{uuid.uuid4().hex[:10]}"
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)

        expert = {
            "id": "expert-secret",
            "tenant_id": tenant,
            "famille": "investigation",
            "type": "EXPERT",
            "mode": "DECLARED",
            **DATES,
            "nom": "Camille Martin",
            "domaine": "Cartes",
            champ: valeur,
            "statut": "ACTIVE",
        }
        with psycopg.connect(DSN) as conn, pytest.raises(ObjetInvalide):
            objets_exploitation.enregistrer_objets_exploitation(
                conn, tenant, expert)

        with psycopg.connect(DSN) as conn:
            nombre = conn.execute(
                "SELECT count(*) FROM objet_entreprise "
                "WHERE tenant_id = %s AND type = 'EXPERT'",
                (tenant,),
            ).fetchone()[0]
        assert nombre == 0
    finally:
        _nettoyer(tenant)


@pytest.mark.parametrize(("champ", "valeur"), [
    ("contenu", "ghp_abcdefghijkl"),
    ("constats", ["ghp_abcdefghijkl"]),
    ("inconnues", ["ghp_abcdefghijkl"]),
    ("preuves", ["ghp_abcdefghijkl"]),
])
def test_pg_secret_dans_contribution_refuse_sans_ecriture(champ, valeur):
    tenant = f"c5e-{uuid.uuid4().hex[:10]}"
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            _pg_situation(tenant)
            _pg_investigation(tenant)
        expert = _pg_expert(tenant)

        contribution = {
            "id": "contribution-secret",
            "tenant_id": tenant,
            "famille": "investigation",
            "type": "EXPERT_CONTRIBUTION",
            "mode": "DECLARED",
            **DATES,
            "expert_id": expert.objet["id"],
            "investigation_id": "inv-c5e",
            "contenu": "Contribution avec secret",
            champ: valeur,
            "statut": "PROPOSED",
        }
        with psycopg.connect(DSN) as conn, pytest.raises(ObjetInvalide):
            objets_exploitation.enregistrer_objets_exploitation(
                conn, tenant, contribution)

        with psycopg.connect(DSN) as conn:
            nombre = conn.execute(
                "SELECT count(*) FROM objet_entreprise "
                "WHERE tenant_id = %s AND type = 'EXPERT_CONTRIBUTION'",
                (tenant,),
            ).fetchone()[0]
            investigation = boucle.lire_boucle(conn, tenant, "inv-c5e", as_dict=True)
        assert nombre == 0
        assert investigation["donnees"]["expert_ids"] == []
    finally:
        _nettoyer(tenant)


@besoin_pg
def test_pg_creation_contribution_est_atomique_si_le_lien_inverse_echoue(monkeypatch):
    tenant = f"c5e-{uuid.uuid4().hex[:10]}"
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            _pg_situation(tenant)
            _pg_investigation(tenant)
        expert = _pg_expert(tenant)

        def echouer(*_, **__):
            raise RuntimeError("échec simulé du lien inverse")

        monkeypatch.setattr(objets_exploitation, "_persister_parent", echouer)
        with psycopg.connect(DSN) as conn, pytest.raises(RuntimeError):
            commandes_boucle.creer_contribution_investigation(
                boucle, conn, tenant, "inv-c5e",
                expert_id=expert.objet["id"], contenu="Contribution partielle")

        with psycopg.connect(DSN) as conn:
            nombre = conn.execute(
                "SELECT count(*) FROM objet_entreprise "
                "WHERE tenant_id = %s AND type = 'EXPERT_CONTRIBUTION'",
                (tenant,),
            ).fetchone()[0]
            investigation = boucle.lire_boucle(conn, tenant, "inv-c5e", as_dict=True)
        assert nombre == 0
        assert investigation["donnees"]["expert_ids"] == []
    finally:
        _nettoyer(tenant)


@besoin_pg
def test_pg_contributions_concurrentes_ne_se_bloquent_pas():
    """Les deux routes concurrentes prennent Investigation puis Hypothesis : pas de deadlock."""
    tenant = f"c5e-{uuid.uuid4().hex[:10]}"
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            _pg_situation(tenant)
            _pg_investigation(tenant)
        expert = _pg_expert(tenant)
        hypothese = _pg_hypothese(tenant, "inv-c5e")
        barriere = threading.Barrier(2)

        def depuis_investigation():
            with psycopg.connect(DSN) as conn:
                barriere.wait(timeout=10)
                return commandes_boucle.creer_contribution_investigation(
                    boucle, conn, tenant, "inv-c5e",
                    expert_id=expert.objet["id"],
                    hypothesis_id=hypothese.objet["id"],
                    contenu="Contribution depuis l'investigation")

        def depuis_hypothese():
            with psycopg.connect(DSN) as conn:
                barriere.wait(timeout=10)
                return commandes_boucle.creer_contribution_hypothese(
                    boucle, conn, tenant, hypothese.objet["id"],
                    expert_id=expert.objet["id"],
                    contenu="Contribution depuis l'hypothèse")

        with ThreadPoolExecutor(max_workers=2) as executant:
            futurs = [
                executant.submit(depuis_investigation),
                executant.submit(depuis_hypothese),
            ]
            resultats = [futur.result(timeout=30) for futur in futurs]

        assert len({resultat.objet["id"] for resultat in resultats}) == 2
        with psycopg.connect(DSN) as conn:
            liste = commandes_boucle.lister_contributions(
                boucle, conn, tenant, investigation_id="inv-c5e")
            investigation = boucle.lire_boucle(conn, tenant, "inv-c5e", as_dict=True)
        assert len(liste) == 2
        assert investigation["donnees"]["expert_ids"] == [expert.objet["id"]]
    finally:
        _nettoyer(tenant)


@pytest.mark.parametrize("route", ["hypotheses", "investigations"])
@besoin_pg
def test_pg_citations_croisees_concurrentes_ne_produisent_jamais_503(
    monkeypatch, route,
):
    """Deux contributions croisées doivent répondre 422, jamais 503 par deadlock.

    Le verrou de la cible est pris par la commande avant l'adaptateur. Sans
    pré-validation des citations, chaque transaction verrouille ensuite la cible de
    l'autre : cycle H_A→H_B / H_B→H_A et DeadlockDetected. La pré-validation non
    verrouillée doit refuser les citations croisées avant tout verrou.
    """
    tenant = f"c5f-{uuid.uuid4().hex[:10]}"
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            _pg_situation(tenant)
            _pg_investigation(tenant, investigation_id="inv-A")
            _pg_investigation(tenant, investigation_id="inv-B")
        expert_a = _pg_expert(tenant, nom="Expert A")
        expert_b = _pg_expert(tenant, nom="Expert B")
        hypothese_a = _pg_hypothese(tenant, "inv-A", enonce="Hypothèse A")
        hypothese_b = _pg_hypothese(tenant, "inv-B", enonce="Hypothèse B")

        if route == "hypotheses":
            urls = [
                f"{BASE}/hypotheses/{hypothese_a.objet['id']}/contributions",
                f"{BASE}/hypotheses/{hypothese_b.objet['id']}/contributions",
            ]
            corps = [
                {
                    "expert_id": expert_a.objet["id"],
                    "contenu": "A cite B",
                    "hypothesis_ids_soutenues": [hypothese_b.objet["id"]],
                },
                {
                    "expert_id": expert_b.objet["id"],
                    "contenu": "B cite A",
                    "hypothesis_ids_soutenues": [hypothese_a.objet["id"]],
                },
            ]
        else:
            urls = [
                f"{BASE}/investigations/inv-A/contributions",
                f"{BASE}/investigations/inv-B/contributions",
            ]
            corps = [
                {
                    "expert_id": expert_a.objet["id"],
                    "hypothesis_id": hypothese_a.objet["id"],
                    "contenu": "A cite B",
                    "hypothesis_ids_soutenues": [hypothese_b.objet["id"]],
                },
                {
                    "expert_id": expert_b.objet["id"],
                    "hypothesis_id": hypothese_b.objet["id"],
                    "contenu": "B cite A",
                    "hypothesis_ids_soutenues": [hypothese_a.objet["id"]],
                },
            ]

        barriere = {"courante": None}
        creer_original = commandes_boucle._creer_contribution

        def creer_avec_barriere(*args, **kwargs):
            courante = barriere["courante"]
            if courante is not None:
                courante.wait(timeout=15)
            return creer_original(*args, **kwargs)

        monkeypatch.setattr(
            commandes_boucle, "_creer_contribution", creer_avec_barriere)

        resultats = []
        for _ in range(6):
            barriere["courante"] = threading.Barrier(2)
            clients = [_client_pg(monkeypatch), _client_pg(monkeypatch)]
            sorties = [None, None]
            erreurs = [None, None]

            def envoyer(rang):
                try:
                    reponse = clients[rang].post(
                        urls[rang], json=corps[rang],
                        headers={"X-Tenant": tenant})
                    sorties[rang] = reponse.status_code
                except Exception as exc:  # pragma: no cover - diagnostic
                    erreurs[rang] = f"{type(exc).__name__}: {exc}"

            threads = [
                threading.Thread(target=envoyer, args=(rang,))
                for rang in range(2)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=30)
            assert not any(thread.is_alive() for thread in threads), (
                "requête concurrente bloquée au-delà de 30 s")
            assert erreurs == [None, None], erreurs
            resultats.extend(sorties)

        compteur = Counter(resultats)
        assert compteur == Counter({422: 12}), compteur

        with psycopg.connect(DSN) as conn:
            nombre = conn.execute(
                "SELECT count(*) FROM objet_entreprise "
                "WHERE tenant_id = %s AND type = 'EXPERT_CONTRIBUTION'",
                (tenant,),
            ).fetchone()[0]
            investigation_a = boucle.lire_boucle(
                conn, tenant, "inv-A", as_dict=True)
            investigation_b = boucle.lire_boucle(
                conn, tenant, "inv-B", as_dict=True)
        assert nombre == 0
        assert investigation_a["donnees"]["expert_ids"] == []
        assert investigation_b["donnees"]["expert_ids"] == []
    finally:
        _nettoyer(tenant)


def _executer_paire_contribution_statut(
    monkeypatch, *, scenario: str, iterations: int = 3,
) -> None:
    """Contribution et changement de statut d'hypothèse en parallèle.

    Les deux opérations se rencontrent sur Investigation → Hypothesis. Un latch avec
    timeout (et non une attente infinie) laisse le test se terminer même quand le
    correctif fait bloquer un des deux threads sur le verrou Investigation avant son
    hook : on détecte uniquement les 503, pas un blocage de test.
    """
    tenant = f"c5f-{uuid.uuid4().hex[:10]}"
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            _pg_situation(tenant)
        expert = _pg_expert(tenant)

        creer_original = commandes_boucle._creer_contribution
        muer_original = boucle.muer_hypothese
        latches: dict[str, Any] = {}

        def creer_avec_latch(*args, **kwargs):
            latches["contribution"].set()
            latches["statut"].wait(timeout=0.3)
            return creer_original(*args, **kwargs)

        def muer_avec_latch(*args, **kwargs):
            latches["statut"].set()
            latches["contribution"].wait(timeout=0.3)
            return muer_original(*args, **kwargs)

        monkeypatch.setattr(
            commandes_boucle, "_creer_contribution", creer_avec_latch)
        monkeypatch.setattr(boucle, "muer_hypothese", muer_avec_latch)

        for iteration in range(iterations):
            investigation_id = f"inv-{scenario}-{iteration}"
            _pg_investigation(tenant, investigation_id=investigation_id)
            hypothese_1 = _pg_hypothese(
                tenant, investigation_id, enonce=f"H1 {scenario} {iteration}")
            hypothese_2 = _pg_hypothese(
                tenant, investigation_id, enonce=f"H2 {scenario} {iteration}")

            if scenario == "citation":
                url_contribution = (
                    f"{BASE}/hypotheses/{hypothese_1.objet['id']}/contributions")
                corps_contribution = {
                    "expert_id": expert.objet["id"],
                    "contenu": "Contribution citant H2",
                    "hypothesis_ids_soutenues": [hypothese_2.objet["id"]],
                }
                url_statut = (
                    f"{BASE}/hypotheses/{hypothese_2.objet['id']}/statut")
                hypothese_cible_statut = hypothese_2
            else:
                url_contribution = (
                    f"{BASE}/investigations/{investigation_id}/contributions")
                corps_contribution = {
                    "expert_id": expert.objet["id"],
                    "hypothesis_id": hypothese_1.objet["id"],
                    "contenu": "Contribution depuis H1",
                }
                url_statut = (
                    f"{BASE}/hypotheses/{hypothese_1.objet['id']}/statut")
                hypothese_cible_statut = hypothese_1

            latches = {
                "contribution": threading.Event(),
                "statut": threading.Event(),
            }
            barriere = threading.Barrier(2)
            clients = [_client_pg(monkeypatch), _client_pg(monkeypatch)]
            sorties: list[Any] = [None, None]
            erreurs: list[Any] = [None, None]

            def envoyer(rang):
                try:
                    barriere.wait(timeout=10)
                    if rang == 0:
                        reponse = clients[rang].post(
                            url_contribution, json=corps_contribution,
                            headers={"X-Tenant": tenant})
                    else:
                        reponse = clients[rang].post(
                            url_statut, json={"vers": "STRENGTHENED"},
                            headers={"X-Tenant": tenant})
                    sorties[rang] = reponse.status_code
                except Exception as exc:  # pragma: no cover - diagnostic
                    erreurs[rang] = f"{type(exc).__name__}: {exc}"

            threads = [
                threading.Thread(target=envoyer, args=(rang,))
                for rang in range(2)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=30)

            assert not any(thread.is_alive() for thread in threads), (
                f"paire {scenario}/{iteration} bloquée au-delà de 30 s")
            assert erreurs == [None, None], erreurs
            assert sorted(sorties) == [200, 201], (
                f"paire {scenario}/{iteration} : statuts {sorties!r}")

            with psycopg.connect(DSN) as conn:
                nombre = conn.execute(
                    "SELECT count(*) FROM objet_entreprise "
                    "WHERE tenant_id = %s AND type = 'EXPERT_CONTRIBUTION' "
                    "AND donnees->>'investigation_id' = %s",
                    (tenant, investigation_id),
                ).fetchone()[0]
                investigation = boucle.lire_boucle(
                    conn, tenant, investigation_id, as_dict=True)
                hypothese_mue = boucle.lire_boucle(
                    conn, tenant, hypothese_cible_statut.objet["id"],
                    historique=True)
            assert nombre == 1
            assert hypothese_mue["donnees"]["statut"] == "STRENGTHENED"
            assert len(hypothese_mue["historique"]) == 1
            assert investigation["donnees"]["expert_ids"] == [expert.objet["id"]]
            hypotheses_liees = investigation["donnees"]["hypothesis_ids"]
            assert len(hypotheses_liees) == len(set(hypotheses_liees)) == 2
            assert set(hypotheses_liees) == {
                hypothese_1.objet["id"], hypothese_2.objet["id"]}
    finally:
        _nettoyer(tenant)


@besoin_pg
def test_pg_citation_valide_et_statut_hypothese_concurrents_pas_de_503(monkeypatch):
    """Contribution H1 citant H2 (valide) + statut de H2 : aucun 503."""
    _executer_paire_contribution_statut(
        monkeypatch, scenario="citation", iterations=3)


@besoin_pg
def test_pg_contribution_et_statut_meme_hypothese_concurrents_pas_de_503(monkeypatch):
    """Contribution depuis H1 + statut de H1, sans citation : aucun 503."""
    _executer_paire_contribution_statut(
        monkeypatch, scenario="meme-hypothese", iterations=3)


@besoin_pg
def test_audit_citations_ignore_les_listes_null_et_detecte_les_fantomes():
    tenant = f"c5f-{uuid.uuid4().hex[:10]}"
    script = (
        Path(__file__).resolve().parents[2]
        / "scripts" / "auditer-citations-contributions.sql"
    )
    sql = script.read_text(encoding="utf-8")
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            _pg_situation(tenant)
            _pg_investigation(tenant)
        expert = _pg_expert(tenant)
        with psycopg.connect(DSN) as conn:
            contribution = commandes_boucle.creer_contribution_investigation(
                boucle, conn, tenant, "inv-c5e",
                expert_id=expert.objet["id"], contenu="Contribution auditée")
        contribution_id = contribution.objet["id"]

        with psycopg.connect(DSN, autocommit=True) as conn:
            conn.execute(
                "UPDATE objet_entreprise SET donnees = donnees || %s::jsonb "
                "WHERE tenant_id = %s AND id = %s",
                ('{"hypothesis_ids_soutenues": null}', tenant, contribution_id),
            )
        with psycopg.connect(DSN) as conn:
            lignes_null = [
                ligne for ligne in conn.execute(sql).fetchall()
                if ligne[0] == tenant and ligne[1] == contribution_id
            ]
        assert lignes_null == []

        with psycopg.connect(DSN, autocommit=True) as conn:
            conn.execute(
                "UPDATE objet_entreprise SET donnees = donnees || %s::jsonb "
                "WHERE tenant_id = %s AND id = %s",
                ('{"hypothesis_ids_soutenues": ["hypothesis-fantome"]}',
                 tenant, contribution_id),
            )
        with psycopg.connect(DSN) as conn:
            lignes_fantomes = [
                ligne for ligne in conn.execute(sql).fetchall()
                if ligne[0] == tenant and ligne[1] == contribution_id
            ]
        assert len(lignes_fantomes) == 1
        assert lignes_fantomes[0][2] == "hypothesis-fantome"
        assert lignes_fantomes[0][7].startswith("hypothèse absente")
    finally:
        _nettoyer(tenant)
