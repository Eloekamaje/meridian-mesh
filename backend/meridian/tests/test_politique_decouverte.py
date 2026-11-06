"""Politique des sources : niveaux, approbation et refus par défaut."""
from __future__ import annotations

import pytest

from meridian.domain.politique_decouverte import (
    NIVEAUX_SOURCES,
    SOURCES_PAR_DEFAUT,
    PolitiqueSources,
)


def test_par_defaut_seul_le_niveau_0_est_autorise():
    politique = PolitiqueSources(tenant_id="banque")

    assert politique.niveaux == (0,)
    assert politique.sources_autorisees == SOURCES_PAR_DEFAUT
    assert politique.autorise("code")
    assert politique.autorise("helm")
    assert not politique.autorise("traces")
    assert not politique.autorise("cmdb")
    assert not politique.autorise("export_websphere")


def test_le_niveau_1_ajoute_kubernetes_gateway_et_traces():
    politique = PolitiqueSources(tenant_id="banque", niveaux=(0, 1))

    assert politique.autorise("kubernetes")
    assert politique.autorise("gateway")
    assert politique.autorise("traces")
    assert not politique.autorise("cmdb")
    assert politique.niveau_max == 1


def test_le_niveau_3_exige_une_approbation_nommee():
    with pytest.raises(ValueError):
        PolitiqueSources(tenant_id="banque", niveaux=(0, 3))

    politique = PolitiqueSources(
        tenant_id="banque", niveaux=(0, 3),
        approuve_par="RSSI", motif="export read-only approuvé")

    assert politique.autorise("export_websphere")
    assert politique.autorise("serveur")
    assert politique.approuve_par == "RSSI"


def test_une_source_inconnue_est_refusee_et_les_alias_sont_acceptes():
    politique = PolitiqueSources(tenant_id="banque", niveaux=(0, 1))

    assert politique.autorise("k8s")
    assert politique.autorise("portail") is False
    assert politique.autorise("source-inventee") is False
    with pytest.raises(ValueError):
        PolitiqueSources(tenant_id="banque", sources_explicites=("source-inventee",))


def test_les_sources_explicites_completent_les_niveaux():
    politique = PolitiqueSources(
        tenant_id="banque", niveaux=(0,), sources_explicites=("cmdb",))

    assert politique.autorise("cmdb")
    assert not politique.autorise("portail_api")
    assert politique.niveau_max == 0


def test_la_politique_se_serialise_et_se_relit():
    politique = PolitiqueSources(
        tenant_id="banque", niveaux=(0, 1), approuve_par="Architecture",
        approuve_le="2026-11-06T10:00:00Z", motif="pilote")

    relue = PolitiqueSources.depuis_dict(politique.as_dict())

    assert relue == politique
    assert set(relue.as_dict()["sources_autorisees"]) == set(politique.sources_autorisees)


def test_les_niveaux_du_domaine_sont_stables():
    assert NIVEAUX_SOURCES[0] == ("code", "config", "contrats", "helm")
    assert NIVEAUX_SOURCES[1] == ("kubernetes", "gateway", "traces")
    assert NIVEAUX_SOURCES[2] == ("cmdb", "portail_api")
    assert NIVEAUX_SOURCES[3] == ("serveur", "export_websphere")
