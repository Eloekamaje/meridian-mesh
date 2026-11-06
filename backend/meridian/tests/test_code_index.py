"""Contrat d'indexation fédérée : provenance, fusion, couverture explicite."""
from meridian.domain.code_index import Observation, couverture, fusionner


def _obs(provider="cbm", file="a.jsp", kind="form", symbol="client"):
    return Observation(provider=provider, parser="test", parser_version="1", file=file,
                       language="jsp", kind=kind, symbol=symbol, start=10, end=12)


def test_deux_providers_ne_s_ecrasent_pas():
    fusion = fusionner([_obs("cbm"), _obs("jsp")])
    assert len(fusion) == 1
    assert fusion[0].status == "conflict"


def test_un_fichier_sans_observation_est_non_supporte():
    lignes = couverture(["a.jsp", "orphelin.cbl"], [_obs()])
    assert {l.file: l.statut for l in lignes} == {"a.jsp": "indexe", "orphelin.cbl": "non_supporte"}
