"""D2 : décroissance de confiance — beliefs érodés et réfutation active des ACCEPTED."""
from datetime import datetime, timedelta, timezone

import pytest

from psycopg.types.json import Jsonb

from meridian.adapters.outbound.postgres import (
    boucle, decroissance_confiance, depot, entreprise_depot, memoire_prospective,
)
from meridian.application import beliefs as croyances
from meridian.tests.conftest import ACTIVITE, JUMEAU, SOURCE, besoin_pg, claim

psycopg = pytest.importorskip("psycopg")
pytestmark = besoin_pg

TENANT = "banque"
MAINTENANT = datetime(2026, 11, 7, 12, 0, 0, tzinfo=timezone.utc)
VIEUX = (MAINTENANT - timedelta(days=200)).isoformat()
RECENT = (MAINTENANT - timedelta(days=30)).isoformat()


def preparer_jumeau(conn):
    """Jumeau + source du tenant ; rend l'identifiant de la source."""
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim("base")], ACTIVITE)
    return depot.source_du_jumeau(conn, "tbt")["id"]


def _claim_propose(conn, objet):
    return conn.execute(
        "INSERT INTO claim (tenant_id, jumeau_id, sujet, predicat, objet, type, confiance) "
        "VALUES (%s, 'tbt', 'TBT', 'DEPEND_DE', %s, 'DEPENDENCY', 0.8) RETURNING id",
        (TENANT, objet)).fetchone()[0]


def _preuve(conn, source_id, claim_id, role, observee_le, locator):
    """Preuve datée explicitement : `preuve` est immuable, on choisit `observee_le` à l'INSERT."""
    pid = conn.execute(
        "INSERT INTO preuve (tenant_id, source_id, type, locator, chemin, sha, "
        "ligne_debut, ligne_fin, hash, activite, observee_le) "
        "VALUES (%s, %s, 'DOC', %s, 'doc.md', 's1', 1, 1, 'h', %s, %s) RETURNING id",
        (TENANT, source_id, locator, Jsonb({"extracteur": "test"}), observee_le)).fetchone()[0]
    conn.execute(
        "INSERT INTO claim_preuve (claim_id, preuve_id, role) VALUES (%s, %s, %s)",
        (claim_id, pid, role))
    return pid


def claim_accepte(conn, source_id, objet, support_le=VIEUX):
    """Claim ACCEPTED par la voie normale : SUPPORT daté + revue humaine."""
    cid = _claim_propose(conn, objet)
    _preuve(conn, source_id, cid, "SUPPORT", support_le, f"doc.md#s-{objet}")
    depot.reviser(conn, cid, "alice", "ACCEPTED", "revue faite")
    return cid


def statut_claim(conn, claim_id):
    return conn.execute("SELECT statut FROM claim WHERE id = %s", (claim_id,)).fetchone()[0]


def intentions_du_claim(conn, claim_id):
    return [
        ligne for ligne in memoire_prospective.lister(conn, TENANT, limite=100)
        if (ligne.get("donnees") or {}).get("claim_id") == claim_id
    ]


def belief(conn, identifiant, revalide_le, confiance=0.8):
    boucle.enregistrer_boucle(conn, TENANT, boucle.Belief(
        id=identifiant, tenant_id=TENANT, enonce=f"conclusion {identifiant}",
        sujet_id="twin-app", confiance=confiance, claim_ids=["claim-1"],
        revalide_le=revalide_le))


def ligne_belief(conn, identifiant):
    return entreprise_depot.lire_objet(conn, TENANT, identifiant)


# --- Beliefs érodés ---


def test_belief_erode_remonte_en_attention_sans_changer_statut(conn):
    belief(conn, "belief-erode", revalide_le=VIEUX)
    rapport = decroissance_confiance.evaluer(conn, TENANT, maintenant=MAINTENANT)

    assert [b["id"] for b in rapport["beliefs_erodes"]] == ["belief-erode"]
    ligne = ligne_belief(conn, "belief-erode")
    attention = ligne["donnees"]["attention"]
    assert attention["raison"] == "confiance_erodee"
    assert attention["confiance"] == pytest.approx(
        croyances.confiance_effective(ligne, MAINTENANT))
    assert ligne["donnees"]["statut"] == "ACTIF"
    assert ligne["version"] == 2
    assert rapport["erreurs"] == []

    # Idempotent : la seconde passe ne réécrit pas l'attention déjà posée.
    rapport_bis = decroissance_confiance.evaluer(conn, TENANT, maintenant=MAINTENANT)
    assert ligne_belief(conn, "belief-erode")["version"] == 2
    assert rapport_bis["beliefs_erodes"][0]["deja"] is True

    # La revalidation efface l'attention (objet canonique reconstruit) et sort le belief.
    boucle.revalider(conn, TENANT, "belief-erode")
    rapport_revalide = decroissance_confiance.evaluer(conn, TENANT, maintenant=MAINTENANT)
    assert rapport_revalide["beliefs_erodes"] == []
    assert "attention" not in ligne_belief(conn, "belief-erode")["donnees"]


def test_belief_frais_n_est_pas_remonte(conn):
    belief(conn, "belief-frais", revalide_le=MAINTENANT.isoformat())
    rapport = decroissance_confiance.evaluer(conn, TENANT, maintenant=MAINTENANT)

    assert rapport["beliefs_erodes"] == []
    assert "attention" not in ligne_belief(conn, "belief-frais")["donnees"]


# --- Réfutation active ---


def test_accepte_avec_contre_posterieure_passe_conteste(conn):
    source_id = preparer_jumeau(conn)
    cid = claim_accepte(conn, source_id, "refute")
    _preuve(conn, source_id, cid, "CONTRE", RECENT, "doc.md#contre-1")

    rapport = decroissance_confiance.evaluer(conn, TENANT, maintenant=MAINTENANT)

    assert statut_claim(conn, cid) == "CONTESTED"
    assert [c["claim_id"] for c in rapport["contestes"]] == [cid]
    revue = conn.execute(
        "SELECT acteur, decision, motif FROM revue WHERE claim_id = %s "
        "ORDER BY id DESC LIMIT 1", (cid,)).fetchone()
    assert revue[0] == decroissance_confiance.SOURCE and revue[1] == "CONTESTED"
    assert "doc.md#contre-1" in revue[2]
    intentions = intentions_du_claim(conn, cid)
    assert len(intentions) == 1
    assert intentions[0]["donnees"]["raison"] == "refutation_posterieure"

    # Le claim contesté n'est plus ACCEPTED : la passe suivante ne le reprend pas.
    rapport_bis = decroissance_confiance.evaluer(conn, TENANT, maintenant=MAINTENANT)
    assert rapport_bis["contestes"] == []


def test_contre_anterieure_au_support_ne_conteste_pas(conn):
    source_id = preparer_jumeau(conn)
    cid = _claim_propose(conn, "contre-ancien")
    _preuve(conn, source_id, cid, "CONTRE", VIEUX, "doc.md#contre-0")
    _preuve(conn, source_id, cid, "SUPPORT", RECENT, "doc.md#s-contre-ancien")
    depot.reviser(conn, cid, "alice", "ACCEPTED", "vu malgré la contre ancienne")

    rapport = decroissance_confiance.evaluer(conn, TENANT, maintenant=MAINTENANT)

    assert statut_claim(conn, cid) == "ACCEPTED"
    assert rapport["contestes"] == []
    # Le soutien a 30 jours : pas de remontée périmée non plus.
    assert rapport["claims_a_revalider"] == []


# --- ACCEPTED sans revalidation ---


def test_accepte_preuve_perimee_remonte_a_revalider(conn):
    source_id = preparer_jumeau(conn)
    cid = claim_accepte(conn, source_id, "perime")

    rapport = decroissance_confiance.evaluer(conn, TENANT, maintenant=MAINTENANT)

    assert statut_claim(conn, cid) == "ACCEPTED"  # remontée, pas de transition
    assert [c["claim_id"] for c in rapport["claims_a_revalider"]] == [cid]
    intentions = intentions_du_claim(conn, cid)
    assert len(intentions) == 1
    assert intentions[0]["donnees"]["raison"] == "preuve_perimee"
    assert intentions[0]["statut"] == "a_faire"

    # Idempotent : l'intention existe déjà, rien de nouveau n'est créé.
    decroissance_confiance.evaluer(conn, TENANT, maintenant=MAINTENANT)
    assert len(intentions_du_claim(conn, cid)) == 1


def test_accepte_frais_reste_accepte_sans_attention(conn):
    source_id = preparer_jumeau(conn)
    cid = claim_accepte(conn, source_id, "frais", support_le=RECENT)

    rapport = decroissance_confiance.evaluer(conn, TENANT, maintenant=MAINTENANT)

    assert statut_claim(conn, cid) == "ACCEPTED"
    assert rapport["claims_a_revalider"] == []
    assert rapport["contestes"] == []
    assert intentions_du_claim(conn, cid) == []


# --- Quota et erreurs ---


def test_quota_borne_les_marquages(conn):
    for rang in range(4):
        belief(conn, f"belief-q-{rang}", revalide_le=VIEUX)
    rapport = decroissance_confiance.evaluer(
        conn, TENANT, maintenant=MAINTENANT, quota=2)

    assert len(rapport["beliefs_erodes"]) == 2
    marques = sum(
        1 for rang in range(4)
        if "attention" in ligne_belief(conn, f"belief-q-{rang}")["donnees"])
    assert marques == 2
    # La passe suivante traite les deux restants.
    rapport_bis = decroissance_confiance.evaluer(
        conn, TENANT, maintenant=MAINTENANT, quota=2)
    assert len(rapport_bis["beliefs_erodes"]) == 2


def test_erreurs_remontees_sans_bloquer_la_suite(conn):
    belief(conn, "belief-ok", revalide_le=VIEUX)
    belief(conn, "belief-ko", revalide_le=VIEUX)

    def persister(c, t, objet):
        if objet["id"] == "belief-ko":
            raise ValueError("refus simulé")
        return entreprise_depot.enregistrer_objet(c, t, objet)

    rapport = decroissance_confiance.evaluer(
        conn, TENANT, maintenant=MAINTENANT, persister=persister)

    assert [b["id"] for b in rapport["beliefs_erodes"]] == ["belief-ok"]
    assert len(rapport["erreurs"]) == 1
    assert rapport["erreurs"][0]["id"] == "belief-ko"
    assert "refus simulé" in rapport["erreurs"][0]["erreur"]
    assert "attention" in ligne_belief(conn, "belief-ok")["donnees"]
    assert "attention" not in ligne_belief(conn, "belief-ko")["donnees"]
