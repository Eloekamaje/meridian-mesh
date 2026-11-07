"""Extension C1 de l'Outcome : origine ``exploitation`` et effets secondaires.

Le pont reste rétrocompatible : sans les nouveaux champs, un Outcome garde l'origine ``legacy``
et ne porte pas de clé ``effets_secondaires``.
"""
from __future__ import annotations

import pytest

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
