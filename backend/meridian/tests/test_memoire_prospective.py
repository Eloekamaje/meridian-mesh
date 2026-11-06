"""Mémoire prospective : intentions, échéances, clôture et purge."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from meridian.adapters.outbound.postgres import memoire_prospective
from meridian.domain.memoire_prospective import Intention, est_due
from meridian.tests.conftest import besoin_pg

TENANT = "banque"
AUTRE_TENANT = "assurance"


def _intention(**parametres):
    defaut = {
        "tenant_id": TENANT,
        "objet": "vérifier le lien comptes → antifraude",
        "echeance": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "scope": "twin",
        "scope_id": "comptes-api",
        "source": "case:accounts",
        "owner": "Équipe comptes",
    }
    return Intention(**{**defaut, **parametres})


def test_intention_valide_et_identifiant_stable():
    premiere = _intention()
    seconde = _intention()

    assert premiere.id == seconde.id
    assert premiere.statut == "a_faire"
    assert premiere.priorite == "normale"


def test_une_echeance_sans_fuseau_est_refusee():
    with pytest.raises(ValueError, match="fuseau"):
        _intention(echeance="2026-11-10T09:00:00")


def test_est_due_respecte_le_statut_et_l_echeance():
    passe = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    futur = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    assert est_due(_intention(echeance=passe))
    assert not est_due(_intention(echeance=futur))
    assert not est_due(_intention(echeance=passe, statut="fait"))


@besoin_pg
def test_creer_est_idempotent_et_borne_au_tenant(conn):
    premiere = memoire_prospective.creer(conn, _intention())
    seconde = memoire_prospective.creer(conn, _intention())

    assert premiere["id"] == seconde["id"]
    assert memoire_prospective.compter(conn, TENANT) == 1
    assert memoire_prospective.lire(conn, AUTRE_TENANT, premiere["id"]) is None


@besoin_pg
def test_lister_et_echeances_filtrent_et_ordonnent(conn):
    maintenant = datetime.now(timezone.utc)
    memoire_prospective.creer(conn, _intention(
        objet="basse", echeance=(maintenant - timedelta(days=2)).isoformat(),
        priorite="basse"))
    memoire_prospective.creer(conn, _intention(
        objet="critique", echeance=(maintenant - timedelta(days=1)).isoformat(),
        priorite="critique"))
    memoire_prospective.creer(conn, _intention(
        objet="future", echeance=(maintenant + timedelta(days=3)).isoformat(),
        scope="situation", scope_id="sit-1"))

    dues = memoire_prospective.echeances(conn, TENANT, maintenant=maintenant)
    assert [ligne["objet"] for ligne in dues] == ["basse", "critique"]

    situations = memoire_prospective.lister(conn, TENANT, scope="situation")
    assert [ligne["scope_id"] for ligne in situations] == ["sit-1"]


@besoin_pg
def test_clore_reporter_et_purger(conn):
    ligne = memoire_prospective.creer(conn, _intention())

    close = memoire_prospective.clore(
        conn, TENANT, ligne["id"], statut="fait", acteur="revue", motif="vérifié")
    assert close["statut"] == "fait"
    assert close["donnees"]["cloture"]["acteur"] == "revue"

    nouvelle = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(timespec="seconds")
    reportee = memoire_prospective.reporter(
        conn, TENANT, ligne["id"], nouvelle, acteur="revue", motif="attente")
    assert reportee["echeance"] == nouvelle
    assert reportee["donnees"]["report"]["motif"] == "attente"

    autre = memoire_prospective.creer(conn, _intention(tenant_id=AUTRE_TENANT))
    supprimees = memoire_prospective.purger(
        conn, TENANT, maintenant=datetime.now(timezone.utc) + timedelta(days=200))

    assert supprimees == 1
    assert memoire_prospective.lire(conn, TENANT, ligne["id"]) is None
    assert memoire_prospective.lire(conn, AUTRE_TENANT, autre["id"]) is not None
