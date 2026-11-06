import pytest

from meridian.adapters.outbound.llm.exploration_adapter import extraire_json, serialiser


def test_parse_json_avec_fence_et_texte():
    reponse = extraire_json('```json\n{"final":"ok"}\n```')
    assert reponse == {"final": "ok"}


def test_parse_ignore_les_objets_json_suivants():
    reponse = extraire_json('{"final":"ok"}\n{"autre":"objet"}')
    assert reponse == {"final": "ok"}


def test_parse_refuse_une_reponse_sans_decision():
    with pytest.raises(ValueError):
        extraire_json("pas de json")


def test_serialisation_inclut_les_outils_semantiques():
    texte = serialiser({"tools": {"cbm_routes": {"repo": "alias"}}, "messages": []})
    assert "cbm_routes" in texte


def test_serialisation_indique_le_nombre_de_claims():
    texte = serialiser({"messages": [], "claims_count": 7})
    assert "Claims déjà enregistrés : 7" in texte


def test_serialisation_limite_le_nombre_de_messages():
    messages = [{"role": "user", "content": f"message-{i}"} for i in range(5)]
    texte = serialiser({"messages": messages}, max_messages=2)
    assert "message-3" in texte and "message-4" in texte
    assert "message-0" not in texte


def test_serialisation_borne_les_outils():
    texte = serialiser({"messages": [{"role": "tool", "content": "x" * 10000}]})
    assert len(texte) <= 20000 + 20
