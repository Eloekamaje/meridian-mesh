"""Tests hors ligne du benchmark retrieval et du scoring hybride."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[3]


def _module():
    spec = importlib.util.spec_from_file_location(
        "retrieval_benchmark",
        RACINE / "plugin" / "meridian" / "evals" / "retrieval" / "run.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["retrieval_benchmark"] = module
    spec.loader.exec_module(module)
    return module


def test_metriques_hit_et_mrr():
    rb = _module()
    assert rb.metriques([{"rang": 1}, {"rang": 2}, {"rang": 0}], k=3) == {
        "n": 3, "hit1": 0.333, "hitk": 0.667, "mrr": 0.5,
    }


def test_classement_hybride_utilise_le_vecteur():
    rb = _module()
    chunks = [
        {"id": "a", "titre": "a", "section": "", "texte": "articles auteurs"},
        {"id": "b", "titre": "b", "section": "", "texte": "météo marine"},
    ]
    lexical = rb.classer("publication", chunks, None)
    hybride = rb.classer("publication", [
        {**chunks[0], "embedding": [1.0, 0.0]},
        {**chunks[1], "embedding": [0.0, 1.0]},
    ], [1.0, 0.0])
    assert lexical[0]["id"] == "a"
    assert hybride[0]["id"] == "a"
    assert hybride[0]["score"] >= hybride[1]["score"]


def test_chargement_du_corpus_reel():
    rb = _module()
    donnees = rb.charger(RACINE / "plugin" / "meridian" / "evals" / "retrieval" / "cases.json")
    assert len(donnees["chunks"]) >= 8
    assert len(donnees["queries"]) >= 8
