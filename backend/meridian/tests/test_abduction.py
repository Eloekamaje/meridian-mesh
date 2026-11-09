"""Abduction D7 : rivales qui s'excluent, preuve discriminante, question maximale."""
import pytest

from meridian.application import abduction

TENANT = "banque"
CONTRAINTE = {
    "tenant_id": TENANT,
    "signature": "contournement",
    "subject": "app-cartes",
    "predicate": "CONSOMME",
    "declared": ["GET /v1/payments"],
    "observed": ["GET /v1/payments", "POST /legacy/pay"],
    "excedent": ["POST /legacy/pay"],
}


def test_rivales_s_excluent_mutuellement_et_restent_conjecture_compatibles():
    from meridian.adapters.outbound.postgres import boucle

    rivales = abduction.rivaliser(CONTRAINTE)
    assert 3 <= len(rivales) <= 4
    ids = {r["id"] for r in rivales}
    for rivale in rivales:
        # Exclusion mutuelle : chaque rivale nomme toutes les autres.
        assert set(rivale["rival_ids"]) == ids - {rivale["id"]}
        assert rivale["statut"] == "EMISE"
        assert rivale["type"] == "CONJECTURE"
        assert rivale["enonce"] and rivale["preuve_discriminante"]
        # Le dict passe tel quel au constructeur du modèle persisté.
        boucle.Conjecture(**rivale)
    # Une preuve discriminante distincte par rivale.
    assert len({r["preuve_discriminante"] for r in rivales}) == len(rivales)
    assert all("POST /legacy/pay" in r["preuve_discriminante"] for r in rivales)


def test_rivaliser_est_deterministe():
    premiere = abduction.rivaliser(CONTRAINTE)
    seconde = abduction.rivaliser(dict(CONTRAINTE))
    assert [r["id"] for r in premiere] == [r["id"] for r in seconde]
    assert premiere == seconde


def test_indice_evenement_ajoute_une_quatrieme_rivale():
    indices = [{"titre": "release 12.4 déployée le 2026-10-30",
                "locator": "ci://run/42"}]
    rivales = abduction.rivaliser(CONTRAINTE, indices)
    assert len(rivales) == 4
    ids = {r["id"] for r in rivales}
    assert all(set(r["rival_ids"]) == ids - {r["id"]} for r in rivales)
    assert "release 12.4" in rivales[-1]["enonce"]
    assert "release 12.4" in rivales[-1]["preuve_discriminante"]


def test_contrainte_vide_produit_quand_meme_des_rivales_generiques():
    rivales = abduction.rivaliser({})
    assert len(rivales) == 3
    assert all(r["enonce"] for r in rivales)


def test_question_maximale_choisit_la_preuve_qui_separe_le_plus_de_mondes():
    """Deux preuves qui décrivent la même observation (« flux réels ») forment une
    famille qui départage deux rivales ; la troisième est seule. La question
    retient la famille la plus large, puis la preuve la moins chère."""
    rivales = abduction.rivaliser(CONTRAINTE)
    verdict = abduction.question_maximale(rivales)

    assert verdict["question"] and "?" in verdict["question"]
    # La famille gagnante couvre les deux rivales tranchées par les flux réels
    # (usage réel vs mesure défaillante), pas la rivale « déclaré obsolète ».
    assert verdict["score"] == 2
    assert len(verdict["couvre"]) == 2
    assert "flux réels" in verdict["preuve"]
    # La moins chère : l'observation manuelle ponctuelle avant la fenêtre 30 jours.
    assert "manuelle" in verdict["preuve"]
    assert "jours" not in verdict["preuve"]


def test_question_maximale_prefere_la_famille_la_plus_large():
    """Avec des preuves synthétiques, la famille couvrant deux rivales l'emporte."""
    rivales = [
        {"id": "h1", "enonce": "usage réel",
         "preuve_discriminante": "la requête batch reste dans les flux réels"},
        {"id": "h2", "enonce": "mesure défaillante",
         "preuve_discriminante": "la requête batch est absente des flux réels"},
        {"id": "h3", "enonce": "référence obsolète",
         "preuve_discriminante": "relire le contrat papier signé en 2019"},
    ]
    verdict = abduction.question_maximale(rivales)
    assert set(verdict["couvre"]) == {"h1", "h2"}
    assert verdict["score"] == 2


def test_question_maximale_sans_rivale_ni_preuve_rend_vide():
    assert abduction.question_maximale([])["question"] == ""
    assert abduction.question_maximale([{"id": "h", "enonce": "x"}])["question"] == ""


def test_trancher_appui_rend_testee_et_refute_les_rivales():
    rivales = abduction.rivaliser(CONTRAINTE)
    cible = rivales[1]["id"]
    res = abduction.trancher(rivales, {"appuie": cible})

    assert res["appuyee"] == cible
    assert res["statuts"][cible] == "TESTEE"
    for rivale in rivales:
        if rivale["id"] != cible:
            assert res["statuts"][rivale["id"]] == "REFUTEE"
    assert set(res["refutees_par_exclusion"]) == {
        r["id"] for r in rivales if r["id"] != cible}
    # Les dicts rendus restent persistables : TESTEE exige des rivales, conservées.
    maj = {r["id"]: r for r in res["rivales"]}
    assert maj[cible]["rival_ids"]


def test_trancher_appui_decisif_rend_retenue():
    rivales = abduction.rivaliser(CONTRAINTE)
    cible = rivales[0]["id"]
    res = abduction.trancher(rivales, {"appuie": cible, "decisif": True})
    assert res["statuts"][cible] == "RETENUE"
    assert all(
        res["statuts"][r["id"]] == "REFUTEE"
        for r in rivales if r["id"] != cible)


def test_trancher_refutation_laisse_les_rivales_vivantes():
    rivales = abduction.rivaliser(CONTRAINTE)
    cible = rivales[0]["id"]
    res = abduction.trancher(rivales, {"refute": cible})
    assert res["refutee"] == cible
    assert res["statuts"][cible] == "REFUTEE"
    assert all(
        res["statuts"][r["id"]] == "EMISE"
        for r in rivales if r["id"] != cible)


def test_trancher_par_texte_rattache_a_la_bonne_preuve():
    rivales = abduction.rivaliser(CONTRAINTE)
    mesure = next(
        r for r in rivales if "mesure" in r["enonce"].lower())
    res = abduction.trancher(rivales, {
        "texte": "observation manuelle du terrain : absence confirmée",
        "verdict": "appuie"})
    assert res["appuyee"] == mesure["id"]
    assert res["statuts"][mesure["id"]] == "TESTEE"


def test_trancher_ne_mute_pas_les_entrees_et_rejette_les_cibles_inconnues():
    rivales = abduction.rivaliser(CONTRAINTE)
    avant = [dict(r) for r in rivales]
    abduction.trancher(rivales, {"appuie": rivales[0]["id"]})
    assert rivales == avant
    with pytest.raises(abduction.AbductionInvalide):
        abduction.trancher(rivales, {"appuie": "hyp-inexistante"})
    with pytest.raises(abduction.AbductionInvalide):
        abduction.trancher(rivales, {})


def test_ou_question_rend_le_texte_socratique_pret():
    texte = abduction.ou_question(abduction.rivaliser(CONTRAINTE))
    assert "?" in texte
    assert "Hypothèses rivales" in texte
    assert "Question à valeur maximale" in texte
    assert "POST /legacy/pay" in texte
    assert abduction.ou_question([]) == ""
