"""Backfill des identités : mapping, tenant, dry-run et idempotence."""
import asyncio

import pytest

from meridian.adapters.outbound.mongo import migration_identites

TENANT = "banque"
SECRET = "secret-a-ne-pas-copier"


class _Db:
    def __init__(self, jumeaux):
        self.jumeaux = jumeaux


def _migrer(db, dry_run=True, conn=None):
    return asyncio.run(migration_identites.migrer(db, TENANT, conn=conn, dry_run=dry_run))


def _doc(**extra):
    return {
        "id": "paiements",
        "nom": "Paiements",
        "domaine": "Paiement",
        "mission": "Orchestre les paiements",
        "proprietaire": "Équipe Checkout — L. Marchand",
        "statut": "actif",
        "sources": {"code": {"token": SECRET}},
        **extra,
    }


def test_mapping_identite_ne_copie_pas_les_secrets():
    identite = migration_identites.identite_depuis_jumeau(_doc(), TENANT)

    assert identite == {
        "id": "paiements",
        "tenant_id": TENANT,
        "nom": "Paiements",
        "equipe": "Équipe Checkout — L. Marchand",
        "type": "APPLICATION",
        "domaine": "Paiement",
        "mission": "Orchestre les paiements",
    }
    assert SECRET not in str(identite)


def test_mapping_refuse_un_autre_tenant_et_un_type_inconnu():
    with pytest.raises(PermissionError):
        migration_identites.identite_depuis_jumeau({**_doc(), "tenant_id": "autre"}, TENANT)
    with pytest.raises(ValueError, match="type"):
        migration_identites.identite_depuis_jumeau({**_doc(), "type": "ROBOT"}, TENANT)


def test_dry_run_ne_touche_pas_la_connexion():
    class _Conn:
        def __init__(self):
            self.appels = []

        def execute(self, *_):
            self.appels.append(True)
            raise AssertionError("écriture en dry-run")

    conn = _Conn()
    rapport = _migrer(_Db([_doc(), {"id": "sans-nom"}]), dry_run=True, conn=conn)

    assert rapport["jumeaux"] == 2 and rapport["inseres"] == 0
    assert conn.appels == []


def test_mode_reel_insere_les_identites_et_ignore_les_doublons():
    class _Ligne:
        def __init__(self, present):
            self.present = present

        def fetchone(self):
            return ("paiements",) if self.present else None

    class _Conn:
        def __init__(self):
            self.appels = []

        def execute(self, requete, params):
            self.appels.append((requete, params))
            return _Ligne(len(self.appels) == 1)

    conn = _Conn()
    rapport = _migrer(_Db([_doc(), _doc()]), dry_run=False, conn=conn)

    assert rapport["jumeaux"] == 2 and rapport["inseres"] == 1
    assert len(rapport["ignores"]) == 1
    assert "canonique" in rapport["ignores"][0]["raison"]
    assert len(conn.appels) == 2


def test_un_document_etranger_est_ignore_sans_erreur():
    rapport = _migrer(_Db([{**_doc(), "tenant_id": "assurance"}]), dry_run=True)

    assert rapport["jumeaux"] == 0
    assert rapport["ignores"] == [
        {"type": "jumeau", "id": "paiements", "raison": "autre tenant"}
    ]
