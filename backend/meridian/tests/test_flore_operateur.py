"""D4 — Flore opérateur : une intention d'action devient un objet canonique via le Harness.

La détection est déterministe ; chaque manifeste d'écriture exige son nom dans `approuves`.
Sans approbation : refus explicite audité, rien d'écrit. Avec : l'objet créé est cité dans
la réponse (type, id, statut) et l'appel est tracé. La base réelle sert à l'écriture
(tenant jetable, nettoyé en fin de test).
"""
import uuid

import psycopg
import pytest

from meridian.adapters.outbound.llm import orchestrateur
from meridian.adapters.outbound.llm.harness import Harness, OutilNonApprouve
from meridian.adapters.outbound.postgres import actions_canoniques, boucle
from meridian.domain import capacites
from meridian.tests.conftest import DSN, besoin_pg

MANIFESTES_ACTION = {
    "creer_situation", "ouvrir_investigation", "proposer_decision",
    "trancher_decision", "lancer_initiative",
}


@pytest.fixture
def tenant_jetable():
    """Un tenant réel mais jetable : les objets écrits sont supprimés après. Les événements
    d'épisode (`evenement_episode`) restent — le journal est append-only par conception."""
    tenant = f"test-d4-{uuid.uuid4().hex[:10]}"
    yield tenant
    with psycopg.connect(DSN, autocommit=True) as conn:
        conn.execute("DELETE FROM objet_entreprise WHERE tenant_id = %s", (tenant,))


def _compter(tenant):
    with psycopg.connect(DSN, connect_timeout=5) as conn:
        return conn.execute(
            "SELECT count(*) FROM objet_entreprise WHERE tenant_id = %s",
            (tenant,)).fetchone()[0]


def _executer(question, **kwargs):
    import asyncio
    return asyncio.run(orchestrateur.executer(
        question, jumeaux=[], mobiliser=lambda *a, **k: None,
        concevoir=lambda *a, **k: None, dsn=DSN, **kwargs))


# --- manifestes : la même règle que les écritures du jumeau (B4) --------------------------

def test_manifestes_action_non_lecture_seule_avec_effets():
    manifestes = {m.nom: m for m in capacites.manifestes_action_canonique()}
    assert set(manifestes) == MANIFESTES_ACTION
    for manifeste in manifestes.values():
        assert manifeste.lecture_seule is False
        assert manifeste.capacite == "agir"
        assert manifeste.effets_de_bord, f"{manifeste.nom} sans effet de bord déclaré"
        assert manifeste.types_objets_ecrits, f"{manifeste.nom} sans objet écrit"


def test_actions_invisibles_sans_approbation():
    """Comme B4 : hors `approuves`, l'écriture n'est ni visible ni exécutable."""
    registre = capacites.RegistreCapacites(capacites.manifestes_action_canonique())
    assert registre.lister(lecture_seule=True) == []
    harnais = Harness(registre, actions_canoniques.adaptateurs_dsn("dsn-invalide", "t"))
    assert not {m.nom for m in harnais._manifests()} & MANIFESTES_ACTION
    import asyncio
    with pytest.raises(OutilNonApprouve):
        asyncio.run(harnais.appeler("ouvrir_investigation", {"situation_id": "sit-x"}))
    refus = [ligne for ligne in harnais.auditer() if ligne["statut"] == "refuse"]
    assert refus and refus[0]["nom"] == "ouvrir_investigation"


def test_actions_visibles_une_fois_approuvees():
    registre = capacites.RegistreCapacites(capacites.manifestes_action_canonique())
    harnais = Harness(registre, actions_canoniques.adaptateurs_dsn("dsn-invalide", "t"),
                      approuves=MANIFESTES_ACTION)
    assert {m.nom for m in harnais._manifests()} & MANIFESTES_ACTION == MANIFESTES_ACTION


# --- détection déterministe de l'intention ------------------------------------------------

def test_intention_action_detectee_et_pipeline_inchange():
    assert orchestrateur.intention_action("ouvre une investigation")["manifeste"] == \
        "ouvrir_investigation"
    assert orchestrateur.intention_action(
        "crée une situation : délai fournisseur")["manifeste"] == "creer_situation"
    assert orchestrateur.intention_action(
        "lance une initiative sur dec-abc12345")["manifeste"] == "lancer_initiative"
    # Pas d'intention d'action : le pipeline normal reste le seul chemin.
    for question in (
        "quelle est la situation des ventes ?",
        "ne crée pas de situation",
        "peux-tu expliquer la décision d'architecture ?",
        "montre-moi les relations entre les applications",
        "comment fonctionne le module de facturation ?",
    ):
        assert orchestrateur.intention_action(question) is None, question


def test_demande_sans_intention_ne_declenche_aucune_action(monkeypatch):
    """Sans intention détectée, `executer` suit le chemin du modèle — ici indisponible."""
    monkeypatch.setattr(orchestrateur, "_modele", lambda modele: None)
    assert _executer("que penses-tu des dépendances entre applications ?") is None


# --- refus sans approbation : rien n'est écrit, le refus est audité ------------------------

@besoin_pg
def test_investigation_non_approuvee_refus_explicite_rien_ecrit(tenant_jetable):
    reponse = _executer(
        "ouvre une investigation sur les retards fournisseurs", tenant=tenant_jetable)
    assert reponse["comportement"] == "signaler"
    assert reponse["action"]["statut"] == "a_approuver"
    assert "ouvrir_investigation" in reponse["action"]["manifestes"]
    assert "approuver" in reponse["reponse"].lower()
    audit = reponse["orchestration"]["audit"]
    assert any(l["statut"] == "refuse" for l in audit)
    assert _compter(tenant_jetable) == 0


# --- exécution approuvée : objet créé, cité, audité ----------------------------------------

@besoin_pg
def test_investigation_approuvee_creee_citee_et_auditee(tenant_jetable):
    reponse = _executer(
        "ouvre une investigation sur les retards fournisseurs",
        tenant=tenant_jetable,
        approuves=("creer_situation", "ouvrir_investigation"))
    assert reponse["action"]["statut"] == "executee"
    objets = reponse["objets"]
    assert [o["type"] for o in objets] == ["SITUATION", "INVESTIGATION"]
    investigation = objets[-1]
    assert investigation["id"].startswith("investigation-")  # id généré par le dépôt
    assert investigation["statut"] == "OPEN"
    assert investigation["id"] in reponse["reponse"]  # l'objet créé est cité
    audit = {l["nom"]: l["statut"] for l in reponse["orchestration"]["audit"]}
    assert audit.get("creer_situation") == "ok"
    assert audit.get("ouvrir_investigation") == "ok"
    with psycopg.connect(DSN, connect_timeout=5) as conn:
        ligne = boucle.lire_boucle(conn, tenant_jetable, investigation["id"])
    assert ligne is not None and ligne["type"] == "INVESTIGATION"
    assert ligne["donnees"]["situation_id"] == objets[0]["id"]
    assert _compter(tenant_jetable) == 2


@besoin_pg
def test_situation_directe_creee_sans_chaine(tenant_jetable):
    reponse = _executer(
        "crée une situation : délai de traitement en hausse",
        tenant=tenant_jetable, approuves=("creer_situation",))
    assert reponse["action"]["statut"] == "executee"
    assert reponse["objets"][0]["type"] == "SITUATION"
    assert reponse["objets"][0]["id"].startswith("sit-")
    assert reponse["objets"][0]["id"] in reponse["reponse"]
    assert _compter(tenant_jetable) == 1


@besoin_pg
def test_investigation_sur_situation_existante(tenant_jetable):
    """La demande peut citer une situation existante : une seule écriture, un seul manifeste."""
    with psycopg.connect(DSN, connect_timeout=5) as conn:
        situation = actions_canoniques.creer_situation(
            conn, tenant_jetable, titre="Retards fournisseurs")
    reponse = _executer(
        f"ouvre une investigation sur {situation['id']}",
        tenant=tenant_jetable, approuves=("ouvrir_investigation",))
    assert reponse["action"]["statut"] == "executee"
    assert reponse["action"]["manifestes"] == ["ouvrir_investigation"]
    assert reponse["objets"][0]["id"].startswith("investigation-")
    assert _compter(tenant_jetable) == 2


@besoin_pg
def test_trancher_sans_reference_reste_une_clarification(tenant_jetable):
    reponse = _executer("tranche la décision", tenant=tenant_jetable)
    assert reponse["comportement"] == "clarifier"
    assert reponse["action"]["statut"] == "incomplet"
    assert _compter(tenant_jetable) == 0
