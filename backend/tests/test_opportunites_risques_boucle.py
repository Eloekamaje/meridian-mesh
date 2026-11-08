"""C5b — Opportunités et risques canoniques depuis une Expression.

Les tests de commande utilisent un magasin en mémoire qui satisfait la surface utile du
port ``BoucleStore`` et simule les liens inverses ``Expression.opportunity_ids`` /
``Expression.risk_ids``. Les tests HTTP remplacent les commandes et la connexion : ils
vérifient le contrat public et les traductions d'erreurs sans dépendre d'un serveur. Les
tests Postgres sont opt-in via ``JUMEAU_PG_DSN`` et prouvent la chaîne réelle
Situation → Expression → Opportunité/Risque, l'atomicité et les transitions.
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
from meridian.domain.objets_exploitation import ObjetsExploitationInvalide, TransitionObjetRefusee
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
    identifiant: str = "expr-1", *, situation_id: str = "sit-1",
    tenant: str = TENANT, **donnees,
) -> dict:
    valeurs = {
        "situation_id": situation_id,
        "type_expression": "OPPORTUNITE",
        "formulation": "Automatiser la ressaisie",
        "canal": "",
        "auteur": None,
        "statut": "PROPOSED",
        "claim_ids": [],
        "hypothesis_ids": [],
        "opportunity_ids": [],
        "risk_ids": [],
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


def _opportunity_row(
    identifiant: str = "opportunity-1", *, expression_id: str = "expr-1",
    situation_id: str = "sit-1", tenant: str = TENANT, **donnees,
) -> dict:
    valeurs = {
        "titre": "Automatiser la ressaisie",
        "description": "Supprimer la double saisie.",
        "statut": "DETECTED",
        "type_opportunite": "AUTOMATION",
        "valeur_potentielle": 12000.0,
        "probabilite": 0.7,
        "impact": "Deux ETP libérés",
        "horizon": "90 jours",
        "criteres": ["faisable", "mesurable"],
        "situation_id": situation_id,
        "expression_id": expression_id,
        "investigation_id": None,
        "proprietaire": None,
        "auteur": None,
        "justification": "",
        "twin_ids": [],
        "confiance": 0.6,
        "preuves": ["preuve-1"],
    }
    valeurs.update(donnees)
    return {
        "id": identifiant,
        "tenant_id": tenant,
        "famille": "emergence",
        "type": "OPPORTUNITY",
        "mode": "INFERRED",
        "titre": valeurs["titre"],
        "donnees": valeurs,
        "version": 1,
        "cree_le": "2026-11-07T00:00:00+00:00",
        "observe_le": "2026-11-07T00:00:00+00:00",
        "valide_depuis": "2026-11-07T00:00:00+00:00",
    }


def _risk_row(
    identifiant: str = "risk-1", *, expression_id: str = "expr-1",
    situation_id: str = "sit-1", tenant: str = TENANT, **donnees,
) -> dict:
    valeurs = {
        "titre": "Dépendance fournisseur",
        "description": "Le fournisseur de cartes peut disparaître.",
        "statut": "DETECTED",
        "type_risque": "FOURNISSEUR",
        "probabilite": 0.4,
        "severite": "HAUTE",
        "exposition": 0.3,
        "impact": "Arrêt des paiements",
        "horizon": "6 mois",
        "criteres": ["criticité", "réversibilité"],
        "situation_id": situation_id,
        "expression_id": expression_id,
        "investigation_id": None,
        "proprietaire": None,
        "auteur": None,
        "justification": "",
        "propagation": "paiements",
        "controles": ["veille-fournisseur"],
        "twin_ids": [],
        "confiance": 0.6,
        "preuves": ["preuve-1"],
    }
    valeurs.update(donnees)
    return {
        "id": identifiant,
        "tenant_id": tenant,
        "famille": "emergence",
        "type": "RISK",
        "mode": "INFERRED",
        "titre": valeurs["titre"],
        "donnees": valeurs,
        "version": 1,
        "cree_le": "2026-11-07T00:00:00+00:00",
        "observe_le": "2026-11-07T00:00:00+00:00",
        "valide_depuis": "2026-11-07T00:00:00+00:00",
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
            chaine = self._chaine(tenant_id, resultat)
            resultat["chaine"] = chaine
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
            if type_objet == "EXPRESSION":
                parent_id = donnees.get("situation_id")
            elif type_objet in {"OPPORTUNITY", "RISK"}:
                parent_id = (donnees.get("expression_id") or donnees.get("situation_id")
                             or donnees.get("investigation_id"))
            elif type_objet == "INVESTIGATION":
                parent_id = donnees.get("situation_id")
            if not parent_id:
                break
            parent = self.objets.get(parent_id)
            if parent is None or parent.get("tenant_id") != tenant_id:
                break
            courant = parent
        return list(reversed(chaine))

    def nouvelle_situation(self, **champs):
        return boucle.Situation(**champs)

    def nouvelle_expression(self, **champs):
        situation = champs.pop("situation")
        return construction_objets_exploitation.nouvelle_expression(situation, **champs)

    def nouvelle_opportunite(self, **champs):
        expression = champs.pop("expression", None)
        return construction_objets_exploitation.nouvelle_opportunite(expression, **champs)

    def nouveau_risque(self, **champs):
        expression = champs.pop("expression", None)
        return construction_objets_exploitation.nouveau_risque(expression, **champs)

    def muer_opportunite(self, opportunite, vers, **champs):
        return construction_objets_exploitation.muer_opportunite(opportunite, vers, **champs)

    def muer_risque(self, risque, vers, **champs):
        return construction_objets_exploitation.muer_risque(risque, vers, **champs)

    def enregistrer_boucle(self, conn, tenant_id=None, objets=None, **kwargs):
        objets = list(objets or [])
        self.enregistres_boucle.extend(copy.deepcopy(objets))
        for objet in objets:
            type_objet = str(getattr(objet, "type", "")).upper()
            if type_objet in {"EXPRESSION", "OPPORTUNITY", "RISK"}:
                raise AssertionError(
                    f"enregistrer_boucle ne doit pas persister un objet {type_objet}")
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
            expression_id = (ligne.get("donnees") or {}).get("expression_id")
            if not expression_id:
                continue
            parent = self.objets.get(expression_id)
            if parent is None:
                raise RuntimeError(f"expression introuvable : {expression_id}")
            cle = ("opportunity_ids" if ligne["type"] == "OPPORTUNITY"
                   else "risk_ids" if ligne["type"] == "RISK" else None)
            if cle is None:
                continue
            donnees = parent.setdefault("donnees", {})
            actuels = list(donnees.get(cle) or [])
            if ligne["id"] not in actuels:
                actuels.append(ligne["id"])
            donnees[cle] = actuels
        return objets if not as_dict else [_ligne(objet) for objet in objets]

    def lister_objets_exploitation(
        self, conn, tenant_id, *, type_=None, investigation_id=None,
        decision_id=None, expression_id=None, limite=100, as_dict=True,
    ):
        resultat = []
        for objet in self.objets.values():
            if objet.get("tenant_id") != tenant_id:
                continue
            if type_ is not None and objet.get("type") != type_:
                continue
            donnees = objet.get("donnees") or {}
            if expression_id is not None and donnees.get("expression_id") != expression_id:
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
# Domaine : transitions et champs C5b
# --------------------------------------------------------------------------- #


def test_les_transitions_reutilisent_les_statuts_canoniques():
    assert set(domaine.TRANSITIONS_OPPORTUNITE) == set(domaine.STATUTS_OPPORTUNITE)
    assert set(domaine.TRANSITIONS_RISQUE) == set(domaine.STATUTS_RISQUE)
    assert "QUALIFIED" in domaine.TRANSITIONS_OPPORTUNITE["DETECTED"]
    assert domaine.TRANSITIONS_OPPORTUNITE["LEARNED"] == ()
    assert domaine.TRANSITIONS_OPPORTUNITE["REJECTED"] == ()
    assert domaine.TRANSITIONS_RISQUE["DETECTED"] == (
        domaine.TRANSITIONS_OPPORTUNITE["DETECTED"])


def test_nouvelle_opportunite_expose_les_champs_c5b():
    situation = _situation_row()
    expression = construction_objets_exploitation.nouvelle_expression(
        situation, formulation="Automatiser la ressaisie")
    opportunite = construction_objets_exploitation.nouvelle_opportunite(
        expression,
        titre="  Automatiser la ressaisie  ",
        description="  Supprimer la double saisie.  ",
        type_opportunite="automation",
        valeur_potentielle=12000,
        probabilite=0.7,
        impact="Deux ETP libérés",
        horizon="90 jours",
        criteres=["faisable", "mesurable"],
        preuves=["preuve-1"],
        confiance=0.6,
    )

    assert opportunite.type == "OPPORTUNITY"
    assert opportunite.statut == "DETECTED"
    assert opportunite.expression_id == expression.id
    assert opportunite.situation_id == situation["id"]
    assert opportunite.titre == "Automatiser la ressaisie"
    assert opportunite.description == "Supprimer la double saisie."
    assert opportunite.type_opportunite == "AUTOMATION"
    assert opportunite.valeur_potentielle == 12000
    assert opportunite.probabilite == 0.7
    assert opportunite.impact == "Deux ETP libérés"
    assert opportunite.horizon == "90 jours"
    assert opportunite.criteres == ["faisable", "mesurable"]
    assert opportunite.preuves == ["preuve-1"]
    assert opportunite.confiance == 0.6


def test_nouveau_risque_expose_les_champs_c5b():
    situation = _situation_row()
    expression = construction_objets_exploitation.nouvelle_expression(
        situation, type_expression="RISQUE", formulation="Dépendance fournisseur")
    risque = construction_objets_exploitation.nouveau_risque(
        expression,
        titre="Dépendance fournisseur",
        description="Le fournisseur peut disparaître.",
        type_risque="fournisseur",
        probabilite=0.4,
        severite="haute",
        impact="Arrêt des paiements",
        horizon="6 mois",
        valeur_potentielle=50000,
        criteres=["criticité", "réversibilité"],
        preuves=["preuve-1"],
        confiance=0.6,
    )

    assert risque.type == "RISK"
    assert risque.statut == "DETECTED"
    assert risque.expression_id == expression.id
    assert risque.situation_id == situation["id"]
    assert risque.type_risque == "FOURNISSEUR"
    assert risque.probabilite == 0.4
    assert risque.severite == "HAUTE"
    assert risque.impact == "Arrêt des paiements"
    assert risque.horizon == "6 mois"
    assert risque.valeur_potentielle == 50000
    assert risque.criteres == ["criticité", "réversibilité"]
    assert risque.confiance == 0.6


@pytest.mark.parametrize(("fabrique", "champs", "erreur"), [
    ("nouvelle_opportunite", {"valeur_potentielle": -1}, "valeur_potentielle"),
    ("nouvelle_opportunite", {"probabilite": 1.2}, "probabilite"),
    ("nouvelle_opportunite", {"confiance": 1.2}, "confiance"),
    ("nouveau_risque", {"valeur_potentielle": -1}, "valeur_potentielle"),
    ("nouveau_risque", {"probabilite": -0.1}, "probabilite"),
    ("nouveau_risque", {"severite": "MAGIQUE"}, "severite"),
])
def test_les_fabriques_refusent_les_champs_c5b_invalides(fabrique, champs, erreur):
    expression = _expression_row()
    with pytest.raises(ModeleInvalide) as levee:
        getattr(construction_objets_exploitation, fabrique)(
            expression, **{"titre": "Valide", **champs})
    assert erreur in str(levee.value)


def test_muer_opportunite_refuse_une_transition_non_autorisee():
    opportunite = construction_objets_exploitation.nouvelle_opportunite(
        _expression_row(), titre="Opportunité", statut="QUALIFIED")

    with pytest.raises(TransitionObjetRefusee):
        construction_objets_exploitation.muer_opportunite(opportunite, "DETECTED")
    assert opportunite.statut == "QUALIFIED"


def test_muer_opportunite_rend_un_nouvel_objet_avec_le_motif():
    opportunite = construction_objets_exploitation.nouvelle_opportunite(
        _expression_row(), titre="Opportunité")
    changee = construction_objets_exploitation.muer_opportunite(
        opportunite, "QUALIFIED", motif="  Preuves suffisantes  ",
        preuves=["preuve-2"])

    assert changee is not opportunite
    assert changee.statut == "QUALIFIED"
    assert changee.motif == "Preuves suffisantes"
    assert changee.justification == ""
    assert changee.preuves == ["preuve-2"]
    assert opportunite.statut == "DETECTED"


# --------------------------------------------------------------------------- #
# Commandes
# --------------------------------------------------------------------------- #


def test_creer_opportunite_persiste_et_relie_l_expression():
    store = _Store([_situation_row(), _expression_row()])

    resultat = commandes_boucle.creer_opportunite(
        store, _Connexion(), TENANT, "expr-1",
        titre="  Automatiser la ressaisie  ",
        description="Supprimer la double saisie.",
        valeur_potentielle=12000,
        probabilite=0.7,
        impact="Deux ETP libérés",
        horizon="90 jours",
        criteres=["faisable", "mesurable"],
        preuves=["preuve-1"],
        confiance=0.6,
        mode="INFERRED",
    )

    assert resultat.objet["type"] == "OPPORTUNITY"
    assert resultat.objet["donnees"]["statut"] == "DETECTED"
    assert resultat.objet["donnees"]["expression_id"] == "expr-1"
    assert resultat.objet["donnees"]["situation_id"] == "sit-1"
    assert resultat.objet["titre"] == "Automatiser la ressaisie"
    assert resultat.objet["donnees"]["valeur_potentielle"] == 12000
    assert resultat.objet["donnees"]["probabilite"] == 0.7
    assert resultat.objet["donnees"]["criteres"] == ["faisable", "mesurable"]
    assert store.objets["expr-1"]["donnees"]["opportunity_ids"] == [resultat.objet["id"]]
    assert [element["type"] for element in resultat.chaine] == [
        "SITUATION", "EXPRESSION", "OPPORTUNITY"]
    assert store.appels_lire[0] == {
        "tenant_id": TENANT, "objet_id": "expr-1",
        "historique": False, "for_update": True,
    }
    assert len(store.enregistres_objets) == 1
    assert store.enregistres_boucle == []


def test_creer_risque_persiste_et_relie_l_expression():
    store = _Store([_situation_row(), _expression_row(type_expression="RISQUE")])

    resultat = commandes_boucle.creer_risque(
        store, _Connexion(), TENANT, "expr-1",
        titre="Dépendance fournisseur",
        probabilite=0.4,
        impact="Arrêt des paiements",
        horizon="6 mois",
        criteres=["criticité"],
        preuves=["preuve-1"],
    )

    assert resultat.objet["type"] == "RISK"
    assert resultat.objet["donnees"]["statut"] == "DETECTED"
    assert resultat.objet["donnees"]["expression_id"] == "expr-1"
    assert resultat.objet["donnees"]["probabilite"] == 0.4
    assert resultat.objet["donnees"]["impact"] == "Arrêt des paiements"
    assert resultat.objet["donnees"]["horizon"] == "6 mois"
    assert store.objets["expr-1"]["donnees"]["risk_ids"] == [resultat.objet["id"]]
    assert [element["type"] for element in resultat.chaine] == [
        "SITUATION", "EXPRESSION", "RISK"]
    assert store.enregistres_boucle == []


@pytest.mark.parametrize("fabrique", [
    commandes_boucle.creer_opportunite, commandes_boucle.creer_risque])
def test_creation_sans_expression_est_introuvable(fabrique):
    store = _Store()
    with pytest.raises(commandes_boucle.SourceIntrouvable) as levee:
        fabrique(store, _Connexion(), TENANT, "expr-absent", titre="Introuvable")
    assert levee.value.role == "expression"
    assert store.enregistres_objets == []


@pytest.mark.parametrize("fabrique", [
    commandes_boucle.creer_opportunite, commandes_boucle.creer_risque])
def test_creation_hors_tenant_est_introuvable(fabrique):
    store = _Store([_expression_row(tenant=AUTRE_TENANT)])
    with pytest.raises(commandes_boucle.SourceIntrouvable):
        fabrique(store, _Connexion(), TENANT, "expr-1", titre="Hors tenant")
    assert store.enregistres_objets == []


@pytest.mark.parametrize("fabrique", [
    commandes_boucle.creer_opportunite, commandes_boucle.creer_risque])
def test_creation_refuse_un_statut_client(fabrique):
    store = _Store([_expression_row()])
    with pytest.raises(ObjetsExploitationInvalide) as levee:
        fabrique(store, _Connexion(), TENANT, "expr-1",
                 titre="Statut forcé", statut="CONFIRMED")
    assert "statut" in str(levee.value)
    assert store.enregistres_objets == []
    assert not [objet for objet in store.objets.values()
                if objet["type"] in {"OPPORTUNITY", "RISK"}]


@pytest.mark.parametrize("fabrique", [
    commandes_boucle.creer_opportunite, commandes_boucle.creer_risque])
def test_creation_refuse_une_source_qui_n_est_pas_une_expression(fabrique):
    source = {"id": "inv-1", "tenant_id": TENANT, "type": "INVESTIGATION",
              "famille": "investigation", "mode": "DECLARED", "titre": "",
              "donnees": {"situation_id": "sit-1"}, "version": 1}
    store = _Store([source])
    with pytest.raises(ObjetsExploitationInvalide) as levee:
        fabrique(store, _Connexion(), TENANT, "inv-1", titre="Mauvaise source")
    assert "EXPRESSION" in str(levee.value)
    assert store.enregistres_objets == []


@pytest.mark.parametrize(("fabrique", "champs", "erreur"), [
    (commandes_boucle.creer_opportunite, {"titre": "   "}, "titre"),
    (commandes_boucle.creer_opportunite,
     {"titre": "Valide", "valeur_potentielle": -1}, "valeur_potentielle"),
    (commandes_boucle.creer_opportunite,
     {"titre": "Valide", "probabilite": 1.2}, "probabilite"),
    (commandes_boucle.creer_opportunite,
     {"titre": "Valide", "confiance": 2}, "confiance"),
    (commandes_boucle.creer_risque, {"titre": "   "}, "titre"),
    (commandes_boucle.creer_risque,
     {"titre": "Valide", "valeur_potentielle": -1}, "valeur_potentielle"),
    (commandes_boucle.creer_risque,
     {"titre": "Valide", "probabilite": -0.1}, "probabilite"),
])
def test_creation_refuse_les_champs_invalides_avant_persistance(
    fabrique, champs, erreur,
):
    store = _Store([_expression_row()])
    with pytest.raises(ModeleInvalide) as levee:
        fabrique(store, _Connexion(), TENANT, "expr-1", **champs)
    assert erreur in str(levee.value)
    assert store.enregistres_objets == []
    assert "_historique" not in store.objets["expr-1"]["donnees"]


@pytest.mark.parametrize("fabrique", [
    commandes_boucle.creer_opportunite, commandes_boucle.creer_risque])
def test_creation_annule_tout_si_le_lien_inverse_echoue(fabrique):
    store = _Store([_situation_row(), _expression_row()])
    store.echec_lien = True

    with pytest.raises(RuntimeError):
        fabrique(store, _Connexion(), TENANT, "expr-1", titre="Objet partiel")

    assert not [objet for objet in store.objets.values()
                if objet["type"] in {"OPPORTUNITY", "RISK"}]
    assert store.objets["expr-1"]["donnees"]["opportunity_ids"] == []
    assert store.objets["expr-1"]["donnees"]["risk_ids"] == []


def test_creation_refuse_un_identifiant_deja_present():
    store = _Store([_situation_row(), _expression_row(),
                    _opportunity_row(identifiant="opportunity-fixe")])

    with pytest.raises(commandes_boucle.DoublonExploitation):
        commandes_boucle.creer_opportunite(
            store, _Connexion(), TENANT, "expr-1",
            id="opportunity-fixe", titre="Doublon")

    assert store.objets["opportunity-fixe"]["donnees"]["titre"] == (
        "Automatiser la ressaisie")


def test_changer_statut_opportunite_valide_puis_refuse_une_transition_invalide():
    store = _Store([_situation_row(), _expression_row(), _opportunity_row()])

    resultat = commandes_boucle.changer_statut_opportunite(
        store, _Connexion(), TENANT, "opportunity-1",
        statut="QUALIFIED", motif="Preuves suffisantes", preuves=["preuve-2"])

    assert resultat.objet["donnees"]["statut"] == "QUALIFIED"
    assert resultat.objet["donnees"]["motif"] == "Preuves suffisantes"
    assert resultat.objet["donnees"]["preuves"] == ["preuve-2"]
    assert resultat.historique[-1]["donnees"]["statut"] == "DETECTED"

    with pytest.raises(commandes_boucle.TransitionRefusee):
        commandes_boucle.changer_statut_opportunite(
            store, _Connexion(), TENANT, "opportunity-1", statut="DETECTED")

    assert store.objets["opportunity-1"]["donnees"]["statut"] == "QUALIFIED"


def test_changer_statut_risque_valide_puis_refuse_une_transition_invalide():
    store = _Store([_situation_row(), _expression_row(), _risk_row()])

    resultat = commandes_boucle.changer_statut_risque(
        store, _Connexion(), TENANT, "risk-1",
        statut="MATURING", motif="Qualification en cours")

    assert resultat.objet["donnees"]["statut"] == "MATURING"
    assert resultat.objet["donnees"]["motif"] == "Qualification en cours"

    with pytest.raises(commandes_boucle.TransitionRefusee):
        commandes_boucle.changer_statut_risque(
            store, _Connexion(), TENANT, "risk-1", statut="LEARNED")


@pytest.mark.parametrize("fabrique", [
    commandes_boucle.changer_statut_opportunite,
    commandes_boucle.changer_statut_risque])
def test_changement_de_statut_refuse_un_statut_inconnu(fabrique):
    store = _Store([_situation_row(), _expression_row(),
                    _opportunity_row(), _risk_row()])
    identifiant = "opportunity-1" if fabrique is commandes_boucle.changer_statut_opportunite else "risk-1"
    with pytest.raises(ObjetsExploitationInvalide) as levee:
        fabrique(store, _Connexion(), TENANT, identifiant, statut="MAGIQUE")
    assert "statut" in str(levee.value)
    assert store.enregistres_objets == []


@pytest.mark.parametrize("fabrique", [
    commandes_boucle.changer_statut_opportunite,
    commandes_boucle.changer_statut_risque])
def test_changement_de_statut_inconnu_ou_hors_tenant_est_404(fabrique):
    store = _Store()
    with pytest.raises(commandes_boucle.SourceIntrouvable):
        fabrique(store, _Connexion(), TENANT, "absent", statut="QUALIFIED")

    store = _Store([_opportunity_row(tenant=AUTRE_TENANT), _risk_row(tenant=AUTRE_TENANT)])
    with pytest.raises(commandes_boucle.SourceIntrouvable):
        fabrique(store, _Connexion(), TENANT,
                 "opportunity-1" if fabrique is commandes_boucle.changer_statut_opportunite else "risk-1",
                 statut="QUALIFIED")


def test_lister_opportunites_et_risques_filtre_par_expression_et_tenant():
    store = _Store([
        _situation_row(),
        _expression_row("expr-1"),
        _expression_row("expr-2"),
        _expression_row("expr-autre", tenant=AUTRE_TENANT),
        _opportunity_row("opportunity-1", expression_id="expr-1"),
        _opportunity_row("opportunity-2", expression_id="expr-2"),
        _opportunity_row("opportunity-autre", expression_id="expr-autre",
                         tenant=AUTRE_TENANT),
        _risk_row("risk-1", expression_id="expr-1"),
        _risk_row("risk-2", expression_id="expr-2"),
    ])

    opportunites = commandes_boucle.lister_opportunites(
        store, _Connexion(), TENANT, "expr-1")
    risques = commandes_boucle.lister_risques(
        store, _Connexion(), TENANT, "expr-1")

    assert [objet["id"] for objet in opportunites] == ["opportunity-1"]
    assert [objet["id"] for objet in risques] == ["risk-1"]
    assert len(commandes_boucle.lister_opportunites(
        store, _Connexion(), TENANT, "expr-1", limite=1)) == 1


def test_lister_opportunites_expression_absente_est_404():
    store = _Store()
    with pytest.raises(commandes_boucle.SourceIntrouvable):
        commandes_boucle.lister_opportunites(
            store, _Connexion(), TENANT, "expr-absent")


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


def _resultat(type_objet: str, identifiant: str) -> commandes_boucle.ResultatTransition:
    situation = _situation_row()
    expression = _expression_row()
    if type_objet == "OPPORTUNITY":
        objet = _opportunity_row(identifiant)
    else:
        objet = _risk_row(identifiant)
    return commandes_boucle.ResultatTransition(
        objet=objet,
        chaine=[situation, expression, objet],
        historique=[],
    )


def test_post_opportunite_retourne_le_contrat_c5b(monkeypatch):
    client = _client(monkeypatch)
    appels = []

    def creer(depot, conn, tenant, expression_id, **champs):
        appels.append((tenant, expression_id, champs))
        return _resultat("OPPORTUNITY", "opportunity-1")

    monkeypatch.setattr(boucle_routes.commandes_boucle, "creer_opportunite", creer)

    reponse = client.post(f"{BASE}/expressions/expr-1/opportunities", json={
        "titre": "  Automatiser la ressaisie  ",
        "description": "Supprimer la double saisie.",
        "valeur_potentielle": 12000,
        "probabilite": 0.7,
        "impact": "Deux ETP libérés",
        "horizon": "90 jours",
        "criteres": ["faisable", "mesurable"],
        "preuves": ["preuve-1"],
        "confiance": 0.6,
        "mode": "INFERRED",
    })

    assert reponse.status_code == 201, reponse.text
    corps = reponse.json()
    assert corps["tenant"] == TENANT
    assert corps["objet"]["type"] == "OPPORTUNITY"
    assert corps["type"] == "OPPORTUNITY"
    assert corps["role"] == "opportunite"
    assert [element["type"] for element in corps["chaine"]] == [
        "SITUATION", "EXPRESSION", "OPPORTUNITY"]
    assert corps["historique"] == []
    assert corps["idempotency_key"] is None
    assert appels[0][0] == TENANT
    assert appels[0][1] == "expr-1"
    assert appels[0][2]["titre"] == "Automatiser la ressaisie"
    assert appels[0][2]["valeur_potentielle"] == 12000
    assert appels[0][2]["probabilite"] == 0.7
    assert appels[0][2]["criteres"] == ["faisable", "mesurable"]
    assert "statut" not in appels[0][2]


def test_post_risque_retourne_le_contrat_c5b(monkeypatch):
    client = _client(monkeypatch)
    appels = []

    def creer(depot, conn, tenant, expression_id, **champs):
        appels.append((tenant, expression_id, champs))
        return _resultat("RISK", "risk-1")

    monkeypatch.setattr(boucle_routes.commandes_boucle, "creer_risque", creer)

    reponse = client.post(f"{BASE}/expressions/expr-1/risks", json={
        "titre": "Dépendance fournisseur",
        "probabilite": 0.4,
        "impact": "Arrêt des paiements",
        "horizon": "6 mois",
        "criteres": ["criticité"],
    })

    assert reponse.status_code == 201, reponse.text
    corps = reponse.json()
    assert corps["objet"]["type"] == "RISK"
    assert corps["type"] == "RISK"
    assert corps["role"] == "risque"
    assert [element["type"] for element in corps["chaine"]] == [
        "SITUATION", "EXPRESSION", "RISK"]
    assert appels[0][2]["probabilite"] == 0.4
    assert "statut" not in appels[0][2]


@pytest.mark.parametrize(("chemin", "methode"), [
    ("/expressions/expr-1/opportunities", "creer_opportunite"),
    ("/expressions/expr-1/risks", "creer_risque"),
])
@pytest.mark.parametrize("corps", [
    {},
    {"titre": "   "},
    {"titre": "Valide", "statut": "CONFIRMED"},
    {"titre": "Valide", "probabilite": 1.2},
    {"titre": "Valide", "probabilite": -0.1},
    {"titre": "Valide", "confiance": 1.2},
    {"titre": "Valide", "valeur_potentielle": -1},
    {"titre": "Valide", "champ_inconnu": True},
])
def test_post_creation_valide_le_corps_avant_la_commande(monkeypatch, chemin, methode, corps):
    client = _client(monkeypatch)
    monkeypatch.setattr(
        boucle_routes.commandes_boucle, methode,
        lambda *_, **__: pytest.fail("la commande ne doit pas être appelée"),
    )
    assert client.post(f"{BASE}{chemin}", json=corps).status_code == 422


@pytest.mark.parametrize(("chemin", "methode"), [
    ("/expressions/expr-1/opportunities", "creer_opportunite"),
    ("/expressions/expr-1/risks", "creer_risque"),
])
def test_post_creation_traduit_les_erreurs(monkeypatch, chemin, methode):
    client = _client(monkeypatch)

    @contextmanager
    def contexte(conn, tenant):
        yield tenant

    monkeypatch.setattr(boucle_routes.rls, "est_actif", lambda: True)
    monkeypatch.setattr(boucle_routes.rls, "contexte_tenant", contexte)

    for erreur, statut in [
        (commandes_boucle.SourceIntrouvable("expression", "expr-x"), 404),
        (commandes_boucle.TransitionRefusee("transition refusée"), 409),
        (ObjetsExploitationInvalide("source invalide"), 422),
        (ObjetInvalide("secret refusé"), 400),
        (psycopg.OperationalError("panne"), 503),
    ]:
        def echouer(*_, _erreur=erreur, **__):
            raise _erreur

        monkeypatch.setattr(boucle_routes.commandes_boucle, methode, echouer)
        reponse = client.post(f"{BASE}{chemin}", json={"titre": "Valide"})
        assert reponse.status_code == statut
        assert "Traceback" not in reponse.text


def test_post_creation_refuse_une_cle_d_idempotence(monkeypatch):
    client = _client(monkeypatch)
    reponse = client.post(
        f"{BASE}/expressions/expr-1/opportunities",
        json={"titre": "Valide"},
        headers={"Idempotency-Key": "cle-1"},
    )
    assert reponse.status_code == 501


def test_post_creation_pose_le_tenant_rls_et_transmet_x_tenant(monkeypatch):
    client = _client(monkeypatch)
    contextes = []

    @contextmanager
    def contexte(conn, tenant):
        contextes.append(tenant)
        yield tenant

    monkeypatch.setattr(boucle_routes.rls, "est_actif", lambda: True)
    monkeypatch.setattr(boucle_routes.rls, "contexte_tenant", contexte)
    appels = []

    def creer(depot, conn, tenant, expression_id, **champs):
        appels.append((tenant, expression_id))
        return _resultat("OPPORTUNITY", "opportunity-1")

    monkeypatch.setattr(boucle_routes.commandes_boucle, "creer_opportunite", creer)
    reponse = client.post(
        f"{BASE}/expressions/expr-1/opportunities",
        json={"titre": "Valide"},
        headers={"X-Tenant": "banque"},
    )

    assert reponse.status_code == 201
    assert reponse.json()["tenant"] == "banque"
    assert contextes == ["banque"]
    assert appels == [("banque", "expr-1")]


def test_la_reponse_creation_ne_laisse_pas_passer_un_secret(monkeypatch):
    client = _client(monkeypatch)
    resultat = _resultat("OPPORTUNITY", "opportunity-1")
    resultat.objet["donnees"]["preuves"] = [{"password": "s3cr3t"}]
    monkeypatch.setattr(
        boucle_routes.commandes_boucle, "creer_opportunite",
        lambda *_, **__: resultat)

    reponse = client.post(
        f"{BASE}/expressions/expr-1/opportunities", json={"titre": "Valide"})

    assert reponse.status_code == 201
    assert "s3cr3t" not in reponse.text
    assert reponse.json()["objet"]["donnees"]["preuves"] == [{"password": "***"}]


def test_sans_dsn_la_route_creation_repond_503(monkeypatch):
    monkeypatch.delenv("AUTH_MODE", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("JUMEAU_PG_DSN", raising=False)
    reponse = _app().post(
        f"{BASE}/expressions/expr-1/opportunities", json={"titre": "Valide"})
    assert reponse.status_code == 503
    assert "JUMEAU_PG_DSN" in reponse.json()["detail"]


def test_get_opportunites_et_risques_retourne_les_listes(monkeypatch):
    client = _client(monkeypatch)
    appels = []

    def lister(depot, conn, tenant, expression_id, *, limite=100):
        appels.append((tenant, expression_id, limite))
        return [_opportunity_row()]

    monkeypatch.setattr(boucle_routes.commandes_boucle, "lister_opportunites", lister)
    reponse = client.get(
        f"{BASE}/expressions/expr-1/opportunities",
        params={"limite": 25},
        headers={"X-Tenant": "banque"},
    )

    assert reponse.status_code == 200
    assert reponse.json()["tenant"] == "banque"
    assert [objet["id"] for objet in reponse.json()["opportunites"]] == ["opportunity-1"]
    assert appels == [("banque", "expr-1", 25)]

    monkeypatch.setattr(
        boucle_routes.commandes_boucle, "lister_risques",
        lambda *_, **__: [_risk_row()])
    reponse = client.get(f"{BASE}/expressions/expr-1/risks")
    assert reponse.status_code == 200
    assert [objet["id"] for objet in reponse.json()["risques"]] == ["risk-1"]


def test_get_opportunites_expression_absente_repond_404(monkeypatch):
    client = _client(monkeypatch)

    def echouer(*_, **__):
        raise commandes_boucle.SourceIntrouvable("expression", "expr-x")

    monkeypatch.setattr(boucle_routes.commandes_boucle, "lister_opportunites", echouer)
    reponse = client.get(f"{BASE}/expressions/expr-x/opportunities")
    assert reponse.status_code == 404


@pytest.mark.parametrize(("chemin", "methode", "identifiant", "type_objet", "role"), [
    ("/opportunities/opportunity-1/statut", "changer_statut_opportunite",
     "opportunity-1", "OPPORTUNITY", "opportunite"),
    ("/risks/risk-1/statut", "changer_statut_risque",
     "risk-1", "RISK", "risque"),
])
def test_post_statut_retourne_le_contrat(
    monkeypatch, chemin, methode, identifiant, type_objet, role,
):
    client = _client(monkeypatch)
    appels = []

    def changer(depot, conn, tenant, objet_id, statut, **champs):
        appels.append((tenant, objet_id, {"statut": statut, **champs}))
        return _resultat(type_objet, identifiant)

    monkeypatch.setattr(boucle_routes.commandes_boucle, methode, changer)
    reponse = client.post(f"{BASE}{chemin}", json={
        "statut": "QUALIFIED",
        "motif": "  Preuves suffisantes  ",
        "preuves": ["preuve-2"],
    })

    assert reponse.status_code == 200, reponse.text
    corps = reponse.json()
    assert corps["objet"]["type"] == type_objet
    assert corps["type"] == type_objet
    assert corps["role"] == role
    assert appels[0][2]["statut"] == "QUALIFIED"
    assert appels[0][2]["motif"] == "Preuves suffisantes"
    assert appels[0][2]["preuves"] == ["preuve-2"]


@pytest.mark.parametrize(("chemin", "methode"), [
    ("/opportunities/opportunity-1/statut", "changer_statut_opportunite"),
    ("/risks/risk-1/statut", "changer_statut_risque"),
])
def test_post_statut_traduit_404_409_422_503(monkeypatch, chemin, methode):
    client = _client(monkeypatch)
    for erreur, statut in [
        (commandes_boucle.SourceIntrouvable("opportunité", "x"), 404),
        (commandes_boucle.TransitionRefusee("transition refusée"), 409),
        (ObjetsExploitationInvalide("statut inconnu"), 422),
        (psycopg.OperationalError("panne"), 503),
    ]:
        def echouer(*_, _erreur=erreur, **__):
            raise _erreur

        monkeypatch.setattr(boucle_routes.commandes_boucle, methode, echouer)
        reponse = client.post(f"{BASE}{chemin}", json={"statut": "QUALIFIED"})
        assert reponse.status_code == statut


@pytest.mark.parametrize("chemin", [
    "/opportunities/opportunity-1/statut", "/risks/risk-1/statut"])
@pytest.mark.parametrize("corps", [
    {},
    {"statut": "   "},
    {"statut": "QUALIFIED", "maj_le": "2026-11-07T00:00:00Z"},
    {"statut": "QUALIFIED", "champ_inconnu": True},
])
def test_post_statut_valide_le_corps(monkeypatch, chemin, corps):
    client = _client(monkeypatch)
    monkeypatch.setattr(
        boucle_routes.commandes_boucle, "changer_statut_opportunite",
        lambda *_, **__: pytest.fail("la commande ne doit pas être appelée"))
    monkeypatch.setattr(
        boucle_routes.commandes_boucle, "changer_statut_risque",
        lambda *_, **__: pytest.fail("la commande ne doit pas être appelée"))
    assert client.post(f"{BASE}{chemin}", json=corps).status_code == 422


# --------------------------------------------------------------------------- #
# Postgres réel : chaînes, liens inverses, transitions et atomicité
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
def test_pg_creation_opportunite_et_risque_chaines_liens_et_transitions(monkeypatch):
    tenant = f"c5b-{uuid.uuid4().hex[:10]}"
    client = _client_pg(monkeypatch)
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)

        assert client.post(
            f"{BASE}/situations",
            json={"id": "sit-c5b", "titre": "Latence des paiements"},
            headers={"X-Tenant": tenant},
        ).status_code == 201
        expression = client.post(
            f"{BASE}/situations/sit-c5b/expressions",
            json={"type_expression": "OPPORTUNITE",
                  "formulation": "Automatiser la ressaisie"},
            headers={"X-Tenant": tenant},
        )
        assert expression.status_code == 201, expression.text
        expression_id = expression.json()["objet"]["id"]

        opportunite = client.post(
            f"{BASE}/expressions/{expression_id}/opportunities",
            json={
                "titre": "Automatiser la ressaisie",
                "description": "Supprimer la double saisie.",
                "valeur_potentielle": 12000,
                "probabilite": 0.7,
                "impact": "Deux ETP libérés",
                "horizon": "90 jours",
                "criteres": ["faisable", "mesurable"],
                "preuves": ["preuve-1"],
                "confiance": 0.6,
            },
            headers={"X-Tenant": tenant},
        )
        assert opportunite.status_code == 201, opportunite.text
        opportunite_id = opportunite.json()["objet"]["id"]
        assert [element["type"] for element in opportunite.json()["chaine"]] == [
            "SITUATION", "EXPRESSION", "OPPORTUNITY"]

        risque = client.post(
            f"{BASE}/expressions/{expression_id}/risks",
            json={
                "titre": "Dépendance fournisseur",
                "probabilite": 0.4,
                "impact": "Arrêt des paiements",
                "horizon": "6 mois",
                "criteres": ["criticité"],
            },
            headers={"X-Tenant": tenant},
        )
        assert risque.status_code == 201, risque.text
        risque_id = risque.json()["objet"]["id"]
        assert [element["type"] for element in risque.json()["chaine"]] == [
            "SITUATION", "EXPRESSION", "RISK"]

        expression_lue = client.get(
            f"{BASE}/objets/{expression_id}", headers={"X-Tenant": tenant}).json()["objet"]
        assert sorted(expression_lue["donnees"]["opportunity_ids"]) == [opportunite_id]
        assert sorted(expression_lue["donnees"]["risk_ids"]) == [risque_id]

        for identifiant, type_attendu in [
            (opportunite_id, "OPPORTUNITY"), (risque_id, "RISK"),
        ]:
            lecture = client.get(
                f"{BASE}/objets/{identifiant}",
                params={"historique": True},
                headers={"X-Tenant": tenant},
            )
            assert lecture.status_code == 200
            assert [element["type"] for element in lecture.json()["chaine"]] == [
                "SITUATION", "EXPRESSION", type_attendu]

        liste_opportunites = client.get(
            f"{BASE}/expressions/{expression_id}/opportunities",
            headers={"X-Tenant": tenant})
        assert liste_opportunites.status_code == 200
        assert [objet["id"] for objet in liste_opportunites.json()["opportunites"]] == [
            opportunite_id]

        transition = client.post(
            f"{BASE}/opportunities/{opportunite_id}/statut",
            json={"statut": "QUALIFIED", "motif": "Preuves suffisantes",
                  "preuves": ["preuve-2"]},
            headers={"X-Tenant": tenant},
        )
        assert transition.status_code == 200, transition.text
        assert transition.json()["objet"]["donnees"]["statut"] == "QUALIFIED"
        assert transition.json()["historique"][-1]["donnees"]["statut"] == "DETECTED"
        assert transition.json()["objet"]["maj_le"]

        invalide = client.post(
            f"{BASE}/opportunities/{opportunite_id}/statut",
            json={"statut": "DETECTED"},
            headers={"X-Tenant": tenant},
        )
        assert invalide.status_code == 409

        transition_risque = client.post(
            f"{BASE}/risks/{risque_id}/statut",
            json={"statut": "MATURING", "motif": "Qualification en cours"},
            headers={"X-Tenant": tenant},
        )
        assert transition_risque.status_code == 200, transition_risque.text
        assert transition_risque.json()["objet"]["donnees"]["statut"] == "MATURING"
        invalide_risque = client.post(
            f"{BASE}/risks/{risque_id}/statut",
            json={"statut": "LEARNED"},
            headers={"X-Tenant": tenant},
        )
        assert invalide_risque.status_code == 409

        with psycopg.connect(DSN) as conn:
            assert boucle.lire_boucle(
                conn, tenant, opportunite_id, as_dict=True)["donnees"]["statut"] == "QUALIFIED"
            assert "OPPORTUNITY" in boucle.TYPES_LECTURE
            assert "RISK" in boucle.TYPES_LECTURE
            assert "OPPORTUNITY" not in boucle.TYPES_BOUCLE
            assert "RISK" not in boucle.TYPES_BOUCLE

            objet = boucle.lire_boucle(conn, tenant, opportunite_id, as_dict=False)
            assert objet.type == "OPPORTUNITY"
            assert objet.expression_id == expression_id
            assert objet.situation_id == "sit-c5b"

            with pytest.raises(boucle.BoucleInvalide):
                boucle.enregistrer_boucle(conn, tenant, objets=[objet], historique=True)

    finally:
        _nettoyer(tenant)


@besoin_pg
def test_pg_creation_est_atomique_si_le_lien_inverse_echoue(monkeypatch):
    tenant = f"c5b-{uuid.uuid4().hex[:10]}"
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            situation = {**_situation_row(), "tenant_id": tenant}
            boucle.enregistrer_boucle(conn, tenant, objets=[situation], historique=True)
            expression = construction_objets_exploitation.nouvelle_expression(
                {**situation, "tenant_id": tenant},
                type_expression="OPPORTUNITE", formulation="Expression atomique")
            objets_exploitation.enregistrer_objets_exploitation(
                conn, tenant, [expression])

        def echouer(*_, **__):
            raise RuntimeError("échec simulé du lien inverse")

        monkeypatch.setattr(objets_exploitation, "_persister_parent", echouer)
        with psycopg.connect(DSN) as conn:
            with pytest.raises(RuntimeError):
                commandes_boucle.creer_opportunite(
                    boucle, conn, tenant, expression.id,
                    titre="Opportunité partielle",
                    valeur_potentielle=12000,
                    probabilite=0.7)

        with psycopg.connect(DSN) as conn:
            nombre = conn.execute(
                "SELECT count(*) FROM objet_entreprise "
                "WHERE tenant_id = %s AND type IN ('OPPORTUNITY', 'RISK')",
                (tenant,),
            ).fetchone()[0]
            expression_lue = boucle.lire_boucle(conn, tenant, expression.id, as_dict=True)
        assert nombre == 0
        assert expression_lue["donnees"]["opportunity_ids"] == []
        assert expression_lue["donnees"]["risk_ids"] == []
    finally:
        _nettoyer(tenant)


@besoin_pg
def test_pg_second_tenant_ne_voit_ni_ne_relie_les_objets(monkeypatch):
    tenant = f"c5b-{uuid.uuid4().hex[:10]}"
    autre = f"{tenant}-autre"
    client = _client_pg(monkeypatch)
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            boucle.enregistrer_boucle(
                conn, tenant, objets=[{**_situation_row(), "tenant_id": tenant}],
                historique=True)
            expression = construction_objets_exploitation.nouvelle_expression(
                {**_situation_row(), "tenant_id": tenant},
                type_expression="OPPORTUNITE", formulation="Expression tenant A")
            objets_exploitation.enregistrer_objets_exploitation(
                conn, tenant, [expression])
            commandes_boucle.creer_opportunite(
                boucle, conn, tenant, expression.id,
                titre="Opportunité tenant A", probabilite=0.5)

        # Le même identifiant d'Expression existe dans un autre tenant : la création est 404,
        # la liste est vide et la lecture directe ne traverse pas la frontière.
        reponse = client.post(
            f"{BASE}/expressions/{expression.id}/opportunities",
            json={"titre": "Opportunité tenant B"},
            headers={"X-Tenant": autre},
        )
        assert reponse.status_code == 404

        liste = client.get(
            f"{BASE}/expressions/{expression.id}/opportunities",
            headers={"X-Tenant": autre},
        )
        assert liste.status_code == 404

        with psycopg.connect(DSN) as conn:
            assert boucle.lire_boucle(conn, autre, expression.id) is None
            assert objets_exploitation.lister_objets_exploitation(
                conn, autre, type_="OPPORTUNITY") == []
    finally:
        _nettoyer(tenant)
        _nettoyer(autre)


@besoin_pg
def test_pg_liste_filtre_par_expression_et_limite(monkeypatch):
    tenant = f"c5b-{uuid.uuid4().hex[:10]}"
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            depot.appliquer_schema(conn)
            situation_1 = {**_situation_row("sit-1"), "tenant_id": tenant}
            situation_2 = {**_situation_row("sit-2"), "tenant_id": tenant}
            boucle.enregistrer_boucle(
                conn, tenant, objets=[situation_1, situation_2], historique=True)
            expression_1 = construction_objets_exploitation.nouvelle_expression(
                situation_1, formulation="Expression 1")
            expression_2 = construction_objets_exploitation.nouvelle_expression(
                situation_2, formulation="Expression 2")
            objets_exploitation.enregistrer_objets_exploitation(
                conn, tenant, [expression_1, expression_2])
            commandes_boucle.creer_opportunite(
                boucle, conn, tenant, expression_1.id, titre="Opportunité 1")
            commandes_boucle.creer_opportunite(
                boucle, conn, tenant, expression_2.id, titre="Opportunité 2")

        with psycopg.connect(DSN) as conn:
            liste = commandes_boucle.lister_opportunites(
                boucle, conn, tenant, expression_1.id)
            assert [objet["titre"] for objet in liste] == ["Opportunité 1"]
            assert len(commandes_boucle.lister_opportunites(
                boucle, conn, tenant, expression_1.id, limite=1)) == 1
    finally:
        _nettoyer(tenant)
