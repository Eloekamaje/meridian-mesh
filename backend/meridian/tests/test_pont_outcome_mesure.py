"""Extension C1 de l'Outcome : origine ``exploitation`` et effets secondaires.

Le pont reste rétrocompatible : sans les nouveaux champs, un Outcome garde l'origine ``legacy``
et ne porte pas de clé ``effets_secondaires``.
"""
from __future__ import annotations

import copy

import pytest

from meridian.adapters.outbound.postgres import pont_canonique as pont_pg
from meridian.application import pont_canonique as pont

TENANT = "banque"
CLE = "cle-de-test-mesure-auto-32"


@pytest.fixture(autouse=True)
def _cle_pont(monkeypatch):
    monkeypatch.setenv(pont.PONT_KEY_ENV, CLE)


def _evenement(**champs):
    base = {
        "tenant_id": TENANT,
        "initiative_id": "ini-dec-case-c1-1",
        "mesure": {"metrique": "delai", "valeur_observee": 7},
        "metrique": "delai",
        "periode": "2026-11",
        "source_event_id": "mesure-1",
    }
    base.update(champs)
    return pont.evenement_outcome(**base)


def test_outcome_porte_l_origine_exploitation_et_les_effets_secondaires():
    evenement = _evenement(
        origine=pont.ORIGINE_EXPLOITATION,
        effets_secondaires=[{"type": "rework", "observe": 3}],
    )

    outcome = pont.objets_depuis_evenement(evenement, tenant_id=TENANT)[0]

    assert outcome["donnees"]["_pont"]["origine"] == pont.ORIGINE_EXPLOITATION
    assert outcome["donnees"]["_pont"]["source"]["origine"] == pont.ORIGINE_EXPLOITATION
    assert outcome["donnees"]["effets_secondaires"] == [
        {"type": "rework", "observe": 3},
    ]
    assert outcome["donnees"]["valeur_observee"] == 7


def test_outcome_sans_extension_reste_legacy_et_sans_cle_effets():
    outcome = pont.objets_depuis_evenement(_evenement(), tenant_id=TENANT)[0]

    assert outcome["donnees"]["_pont"]["origine"] == pont.ORIGINE_LEGACY
    assert "effets_secondaires" not in outcome["donnees"]


def test_maj_le_arbitre_une_correction_a_quand_egal(monkeypatch):
    """Deux événements même `quand`, `maj_le` croissant : le second doit être écrit."""
    premier = _evenement(
        maj_le="2026-11-05T09:01:00+00:00",
        mesure={"metrique": "delai", "valeur_observee": 7},
        interpretation="version 1",
        source_event_id="correction-1",
    )
    second = _evenement(
        maj_le="2026-11-05T09:02:00+00:00",
        mesure={"metrique": "delai", "valeur_observee": 8},
        interpretation="version 2",
        source_event_id="correction-2",
    )
    outcome_premier = pont.objets_depuis_evenement(premier, tenant_id=TENANT)[0]
    outcome_second = pont.objets_depuis_evenement(second, tenant_id=TENANT)[0]
    assert outcome_premier["donnees"]["_pont"]["source_maj_le"] \
        == "2026-11-05T09:01:00+00:00"
    assert outcome_second["donnees"]["_pont"]["source_maj_le"] \
        == "2026-11-05T09:02:00+00:00"

    monkeypatch.setattr(
        pont_pg.entreprise_depot, "lire_objet",
        lambda _conn, _tenant, identifiant: copy.deepcopy(outcome_premier)
        if identifiant == outcome_premier["id"] else None,
    )
    ecrits: list[str] = []
    ignores: list[str] = []

    assert pont_pg._doit_ecrire(None, TENANT, outcome_second, ecrits, ignores) is True
    assert ecrits == [outcome_second["id"]]
    assert ignores == []


def test_maj_le_egal_reste_strictement_ignore(monkeypatch):
    premier = _evenement(
        maj_le="2026-11-05T09:01:00+00:00",
        interpretation="version 1", source_event_id="egal-1")
    second = _evenement(
        maj_le="2026-11-05T09:01:00+00:00",
        interpretation="version 2", source_event_id="egal-2")
    outcome_premier = pont.objets_depuis_evenement(premier, tenant_id=TENANT)[0]
    outcome_second = pont.objets_depuis_evenement(second, tenant_id=TENANT)[0]

    monkeypatch.setattr(
        pont_pg.entreprise_depot, "lire_objet",
        lambda _conn, _tenant, identifiant: copy.deepcopy(outcome_premier)
        if identifiant == outcome_premier["id"] else None,
    )
    ecrits: list[str] = []
    ignores: list[str] = []

    assert pont_pg._doit_ecrire(None, TENANT, outcome_second, ecrits, ignores) is False
    assert ecrits == []
    assert ignores == [outcome_second["id"]]
