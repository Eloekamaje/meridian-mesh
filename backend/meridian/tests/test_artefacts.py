"""Contrat d'artefact chat/Canvas : type, titre, hash et identifiant stable."""
import pytest

from meridian.domain import artefacts


def test_enveloppe_un_artefact_avec_hash_et_id_stables():
    premier = artefacts.envelopper("planification.capacite", "Capacité", {"equipes": []})
    second = artefacts.envelopper("planification.capacite", "Capacité", {"equipes": []})
    assert premier["type"] == "planification.capacite"
    assert premier["artefact_id"] == second["artefact_id"]
    assert premier["hash"] == second["hash"]
    assert premier["titre"] == "Capacité"


def test_type_inconnu_et_titre_vide_sont_refuses():
    with pytest.raises(artefacts.ArtefactInvalide):
        artefacts.envelopper("planification.inconnu", "X", {})
    with pytest.raises(artefacts.ArtefactInvalide):
        artefacts.envelopper("table", "", {})
