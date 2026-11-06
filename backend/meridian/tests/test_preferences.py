"""Préférences : forme de la réponse, jamais autorité ou preuve."""
from meridian.application import preferences
from meridian.domain.preferences import Preferences


def test_les_preferences_invalides_retombent_sur_les_defauts():
    p = Preferences(ton="agressif", longueur="roman", langue="")
    assert p.ton == "direct"
    assert p.longueur == "moyenne"
    assert p.langue == "fr"


def test_les_preferences_sont_projetees_dans_le_prompt():
    lignes = preferences.lignes_prompt({"ton": "pedagogique", "langue": "fr",
                                        "longueur": "concis", "suggestions": False})
    assert any("pedagogique" in ligne for ligne in lignes)
    assert any("concis" in ligne for ligne in lignes)
    assert any("Ne propose pas" in ligne for ligne in lignes)


def test_les_preferences_ne_sont_pas_des_instructions_de_securite():
    p = preferences.depuis_doc({"ton": "direct", "langue": "en"})
    assert p.as_dict()["langue"] == "en"
    assert "autorite" not in p.as_dict()
