"""Contrefactuel : deltas explicites, dominance, valeurs manquantes et pureté."""
from copy import deepcopy
from types import SimpleNamespace

from jumeau import contrefactuel


def test_applique_valeurs_deltas_et_changements_explicites():
    options = [
        {"id": "a", "valeurs": {"benefice": 10, "maturite": 4}, "deltas": {"benefice": 2}},
        {"id": "b", "valeurs": {"benefice": 7, "maturite": 4}, "deltas": {"benefice": 1}},
    ]
    changements = {
        "benefice": -1,
        "b": {"benefice": {"delta": 3}, "maturite": {"valeur": 9}},
    }

    resultat = contrefactuel.comparer(options, changements, criteres=("benefice", "maturite"))

    assert resultat["criteres"] == ["benefice", "maturite"]
    assert resultat["impacts"]["a"] == {"benefice": 11.0, "maturite": 4.0}
    assert resultat["impacts"]["b"] == {"benefice": 10.0, "maturite": 9.0}
    assert [option["impacts"] for option in resultat["options"]] == [
        {"benefice": 11.0, "maturite": 4.0},
        {"benefice": 10.0, "maturite": 9.0},
    ]


def test_option_dominante_seulement_si_au_moins_egale_partout_et_stricte_quelque_part():
    options = [
        {"id": "a", "valeurs": {"score": 10, "securite": 8}},
        {"id": "b", "valeurs": {"score": 9, "securite": 8}},
        {"id": "c", "valeurs": {"score": 8, "securite": 7}},
    ]

    resultat = contrefactuel.comparer(options, {}, criteres=("score", "securite"))

    assert resultat["option_dominante"] == "a"
    assert resultat["recommandation"] is None


def test_pas_de_dominance_en_cas_d_arbitrage_ou_d_egalite():
    arbitrage = [
        {"id": "a", "valeurs": {"score": 10, "securite": 7}},
        {"id": "b", "valeurs": {"score": 9, "securite": 8}},
    ]
    egalite = [
        {"id": "a", "valeurs": {"score": 10, "securite": 8}},
        {"id": "b", "valeurs": {"score": 10, "securite": 8}},
    ]

    assert contrefactuel.comparer(arbitrage, {}, criteres=("score", "securite"))["option_dominante"] is None
    assert contrefactuel.comparer(egalite, {}, criteres=("score", "securite"))["option_dominante"] is None
    assert contrefactuel.comparer(arbitrage[:1], {}, criteres=("score", "securite"))["option_dominante"] is None


def test_valeurs_manquantes_restent_none_et_bloquent_la_dominance():
    options = [
        {"id": "a", "valeurs": {"score": 10}},
        {"id": "b", "valeurs": {"score": 9, "securite": 8}},
    ]

    resultat = contrefactuel.comparer(options, {}, criteres=("score", "securite"))

    assert resultat["impacts"]["a"] == {"score": 10.0, "securite": None}
    assert resultat["impacts"]["b"] == {"score": 9.0, "securite": 8.0}
    assert resultat["option_dominante"] is None

    vide = contrefactuel.comparer([{"id": "seul"}], {}, criteres=("cout",))
    assert vide["impacts"]["seul"] == {"cout": None}
    assert vide["option_dominante"] is None


def test_conditions_uniquement_explicites_et_sans_doublon():
    options = [
        {"id": "a", "valeurs": {"score": 1}, "conditions": "si le volume double"},
        {"id": "b", "valeurs": {"score": 2},
         "conditions": ["si le volume double", {"texte": "si le SLA se dégrade"}]},
        {"id": "c", "valeurs": {"score": 3}, "label": "Retournement si le prix baisse"},
    ]

    resultat = contrefactuel.comparer(options, {}, criteres=("score",))

    assert resultat["conditions_de_retournement"] == [
        "si le volume double", "si le SLA se dégrade"]
    assert "Retournement si le prix baisse" not in resultat["conditions_de_retournement"]


def test_accepte_dataclasses_mappings_et_objets_sans_muter_les_entrees():
    options = [
        contrefactuel.Option("a", {"score": 2}),
        contrefactuel.Scenario("b", {"score": 1}),
        SimpleNamespace(id="c", valeurs={"score": 0}, deltas={}, conditions=[]),
    ]
    changements = {"score": 1}
    avant_options = deepcopy(options)
    avant_changements = deepcopy(changements)

    resultat = contrefactuel.comparer(options, changements, criteres=("score",))

    assert resultat["impacts"] == {"a": {"score": 3.0}, "b": {"score": 2.0}, "c": {"score": 1.0}}
    assert resultat["option_dominante"] == "a"
    assert options == avant_options
    assert changements == avant_changements


def test_criteres_derives_des_seules_valeurs_et_deltas_declares():
    options = [
        {"id": "a", "valeurs": {"benefice": 3}, "deltas": {"cout": -1},
         "conditions": "si le risque augmente"},
    ]

    resultat = contrefactuel.comparer(options, {})

    assert resultat["criteres"] == ["benefice", "cout"]
    assert resultat["impacts"]["a"] == {"benefice": 3.0, "cout": -1.0}
    assert "risque" not in resultat["criteres"]


def test_simuler_est_pur_et_ne_genere_pas_de_recommandation():
    options = [{"id": "a", "valeurs": {"score": 1}}, {"id": "b", "valeurs": {"score": 2}}]

    premier = contrefactuel.simuler(options, {}, criteres=("score",))
    second = contrefactuel.simuler(options, {}, criteres=("score",))

    assert premier == second
    assert premier["recommandation"] is None
    assert premier["option_dominante"] == "b"
