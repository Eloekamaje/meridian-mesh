"""Lecture live de la trace canonique C2 (Postgres réel, opt-in)."""
from __future__ import annotations

import os
import uuid

import psycopg
import pytest

from meridian.adapters.inbound.http import cases as cases_routes
from meridian.adapters.outbound.postgres import boucle, depot, rls

DSN = os.environ.get("JUMEAU_PG_DSN")
besoin_pg = pytest.mark.skipif(not DSN, reason="JUMEAU_PG_DSN non défini")


@besoin_pg
def test_lire_boucle_sync_pose_le_guc_et_lit_la_chaine(monkeypatch):
    tenant = f"test-{uuid.uuid4().hex[:10]}"
    identifiant = f"dec-test-{uuid.uuid4().hex[:8]}"
    objet = {
        "id": identifiant,
        "tenant_id": tenant,
        "famille": "decision",
        "type": "DECISION",
        "mode": "DECLARED",
        "titre": "Décision live",
        "donnees": {"statut": "DECIDED", "choix": "A", "acteur": "test"},
    }
    with psycopg.connect(DSN, autocommit=True) as conn:
        depot.appliquer_schema(conn)
        with rls.contexte_tenant(conn, tenant):
            boucle.enregistrer_boucle(conn, tenant, objets=[objet], historique=True)
    monkeypatch.setenv("JUMEAU_PG_DSN", DSN)
    try:
        ligne = cases_routes._lire_boucle_sync(tenant, identifiant)
        assert ligne is not None
        assert ligne["id"] == identifiant
        assert [etape["id"] for etape in ligne["chaine"]] == [identifiant]
    finally:
        with psycopg.connect(DSN, autocommit=True) as conn:
            with rls.contexte_tenant(conn, tenant):
                conn.execute(
                    "DELETE FROM objet_entreprise WHERE tenant_id = %s AND id = %s",
                    (tenant, identifiant))
