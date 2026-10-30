"""Spécialistes impact et outcome : lectures pures, comptes, chemins, partiels et isolation tenant."""
from copy import deepcopy

import pytest

from jumeau import specialiste_impact as module
from jumeau.specialiste_impact import SpecialisteImpact, SpecialisteOutcome
from jumeau.specialistes import ContexteSpecialiste

MAINTENANT = "2026-10-21T00:00:00+00:00"
LEARNING = {
    "id": "lea-1",
    "tenant_id": "banque",
    "type": "LEARNING",
    "titre": "Automatiser la pièce réduit le délai",
    "confiance": 0.8,
    "cree_le": "2026-10-20T08:00:00+00:00",
    "donnees": {
        "enonce": "Automatiser la pièce réduit le délai",
        "outcome_ids": ["out-1"],
        "twin_ids": ["t1"],
    },
}


class FauxStore:
    def __init__(self, impacts=None, chemins=None):
        self.impacts = impacts or {}
        self.chemins_par_couple = chemins or {}
        self.appels = []
        self.appels_chemins = []

    def impact(self, tenant, twin_id, profondeur):
        self.appels.append((tenant, twin_id, profondeur))
        return self.impacts.get(twin_id, {"amont": [], "aval": []})

    def chemins(self, tenant, source, cible, profondeur):
        self.appels_chemins.append((tenant, source, cible, profondeur))
        return self.chemins_par_couple.get((source, cible), [])


class StoreEnPanne:
    def __init__(self, twin_en_panne):
        self.twin_en_panne = twin_en_panne
        self.appels = []

    def impact(self, tenant, twin_id, profondeur):
        self.appels.append((tenant, twin_id, profondeur))
        if twin_id == self.twin_en_panne:
            raise RuntimeError("graphe indisponible")
        return {"amont": [{"id": "u"}], "aval": [{"id": "d"}]}


def _contexte(**options):
    options.setdefault("tenant", "banque")
    options.setdefault("maintenant", MAINTENANT)
    return ContexteSpecialiste(**options)


def test_impact_compte_amont_aval_et_borne_les_ids_a_huit():
    store = FauxStore(impacts={
        "a": {"amont": [{"id": "u1"}, {"id": "u2"}],
              "aval": [{"id": f"d{i}"} for i in range(10)]},
    })

    resultat = SpecialisteImpact().analyser(
        _contexte(twin_ids=("a",), profondeur=4, store=store))

    assert resultat.statut == "ok"
    assert resultat.erreur is None
    proposition = resultat.propositions[0]
    assert proposition.type == "IMPACT"
    assert "ouvrir_impact" in proposition.actions
    assert proposition.donnees["amont"] == 2
    assert proposition.donnees["aval"] == 10
    assert proposition.donnees["total"] == 12
    assert len(proposition.donnees["ids"]) == 8
    assert proposition.donnees["tronque"] is True
    assert len(proposition.preuves) == 8
    assert store.appels == [("banque", "a", 4)]


def test_impact_chemin_entre_les_deux_premiers_twins_et_desactivation():
    store = FauxStore(
        impacts={
            "a": {"amont": [], "aval": [{"id": "b"}]},
            "b": {"amont": [{"id": "a"}], "aval": []},
        },
        chemins={("a", "b"): [["a", "x", "b"]]},
    )
    contexte = _contexte(twin_ids=("a", "b"), store=store)

    resultat = SpecialisteImpact().analyser(contexte)

    assert resultat.statut == "ok"
    propositions_chemin = [p for p in resultat.propositions if p.donnees.get("chemin")]
    assert len(propositions_chemin) == 1
    chemin = propositions_chemin[0]
    assert chemin.type == "IMPACT"
    assert chemin.donnees["chemin"] == ["a", "x", "b"]
    assert chemin.preuves == ("a", "x", "b")
    assert store.appels_chemins == [("banque", "a", "b", 2)]

    sans_chemin = SpecialisteImpact(inclure_chemins=False).analyser(contexte)
    assert all("chemin" not in p.donnees for p in sans_chemin.propositions)
    assert store.appels_chemins == [("banque", "a", "b", 2)]


@pytest.mark.parametrize("store", [None, object()])
def test_impact_sans_store_ou_sans_operation_est_partiel(store):
    resultat = SpecialisteImpact().analyser(_contexte(twin_ids=("a",), store=store))

    assert resultat.statut == "partiel"
    assert resultat.propositions == []
    assert resultat.limites


def test_impact_sans_twin_est_partiel_sans_appel():
    store = FauxStore()

    resultat = SpecialisteImpact().analyser(_contexte(store=store))

    assert resultat.statut == "partiel"
    assert resultat.propositions == []
    assert store.appels == []
    assert resultat.limites


def test_impact_resultat_vide_est_partiel_sans_invention():
    store = FauxStore(impacts={"a": {}})

    resultat = SpecialisteImpact().analyser(_contexte(twin_ids=("a",), store=store))

    assert resultat.statut == "partiel"
    assert resultat.propositions == []
    assert any("invalide" in limite for limite in resultat.limites)


def test_impact_erreur_isolee_devient_partielle_avec_type():
    store = StoreEnPanne("a")

    resultat = SpecialisteImpact().analyser(
        _contexte(twin_ids=("a", "b"), store=store))

    assert resultat.statut == "partiel"
    assert resultat.erreur == "RuntimeError"
    assert len(resultat.propositions) == 1
    assert resultat.propositions[0].donnees["twin_id"] == "b"
    assert any("RuntimeError" in limite for limite in resultat.limites)


def test_impact_toutes_erreurs_donnent_statut_erreur():
    resultat = SpecialisteImpact().analyser(
        _contexte(twin_ids=("a",), store=StoreEnPanne("a")))

    assert resultat.statut == "erreur"
    assert resultat.erreur == "RuntimeError"
    assert resultat.propositions == []
    assert resultat.limites


def test_impact_transmet_le_tenant_et_ne_mute_pas_le_graphe():
    impact = {"amont": [{"id": "u"}], "aval": [{"id": "d"}]}
    store = FauxStore(impacts={"a": impact})
    avant = deepcopy(impact)

    resultat = SpecialisteImpact().analyser(
        _contexte(tenant="assurance", twin_ids=("a",), store=store))

    assert store.appels == [("assurance", "a", 2)]
    assert impact == avant
    assert resultat.propositions[0].donnees["ids"] == ["u", "d"]


def test_outcome_reutilise_un_learning_et_reste_isole_par_tenant(monkeypatch):
    appels = []

    def faux_learnings(conn, tenant, *, situation_id=None, twin_ids=(), limite=20):
        appels.append({
            "conn": conn, "tenant": tenant, "situation_id": situation_id,
            "twin_ids": tuple(twin_ids), "limite": limite,
        })
        return [dict(LEARNING)] if tenant == "banque" else []

    monkeypatch.setattr(module.outcomes, "learnings_pour", faux_learnings)
    conn = object()
    resultat = SpecialisteOutcome().analyser(
        _contexte(situation_id="sit-1", twin_ids=("t1", "t2"), conn=conn))

    assert resultat.statut == "ok"
    proposition = resultat.propositions[0]
    assert proposition.type == "LEARNING"
    assert "reutiliser_learning" in proposition.actions
    assert proposition.preuves == ("lea-1",)
    assert proposition.donnees["learning_id"] == "lea-1"
    assert proposition.donnees["outcome_ids"] == ["out-1"]
    assert proposition.donnees["fraicheur"]["etat"] == "fraiche"
    assert "réduit le délai" in proposition.titre
    assert appels[-1] == {
        "conn": conn, "tenant": "banque", "situation_id": "sit-1",
        "twin_ids": ("t1", "t2"), "limite": 10,
    }

    autre = SpecialisteOutcome().analyser(
        _contexte(tenant="assurance", situation_id="sit-1", conn=conn))
    assert appels[-1]["tenant"] == "assurance"
    assert autre.propositions[0].type == "QUESTION"


def test_outcome_sans_learning_produit_une_question_mesurer_outcome(monkeypatch):
    monkeypatch.setattr(module.outcomes, "learnings_pour", lambda *a, **k: [])

    resultat = SpecialisteOutcome().analyser(
        _contexte(situation_id="sit-1", conn=object()))

    assert resultat.statut == "ok"
    assert len(resultat.propositions) == 1
    question = resultat.propositions[0]
    assert question.type == "QUESTION"
    assert question.titre == "Aucun learning réutilisable"
    assert "mesurer_outcome" in question.actions
    assert question.donnees["learnings"] == 0
    assert question.donnees["situation_id"] == "sit-1"


def test_outcome_sans_connexion_est_partiel_sans_lecture(monkeypatch):
    def interdit(*args, **kwargs):
        raise AssertionError("aucune lecture sans connexion")

    monkeypatch.setattr(module.outcomes, "learnings_pour", interdit)

    resultat = SpecialisteOutcome().analyser(
        _contexte(situation_id="sit-1", conn=None))

    assert resultat.statut == "partiel"
    assert resultat.propositions == []
    assert resultat.limites


def test_outcome_sans_ancrage_est_partiel_sans_lecture(monkeypatch):
    def interdit(*args, **kwargs):
        raise AssertionError("aucune lecture sans ancrage")

    monkeypatch.setattr(module.outcomes, "learnings_pour", interdit)

    resultat = SpecialisteOutcome().analyser(_contexte(conn=object()))

    assert resultat.statut == "partiel"
    assert resultat.propositions == []
    assert resultat.limites


def test_outcome_erreur_de_lecture_donne_type_et_aucune_invention(monkeypatch):
    def casse(*args, **kwargs):
        raise RuntimeError("lecture impossible")

    monkeypatch.setattr(module.outcomes, "learnings_pour", casse)

    resultat = SpecialisteOutcome().analyser(
        _contexte(situation_id="sit-1", conn=object()))

    assert resultat.statut == "erreur"
    assert resultat.erreur == "RuntimeError"
    assert resultat.propositions == []
    assert resultat.limites


def test_outcome_borne_les_learnings_et_ne_mute_pas_les_lignes(monkeypatch):
    lignes = [dict(LEARNING, id=f"lea-{rang}") for rang in range(12)]
    avant = deepcopy(lignes)
    monkeypatch.setattr(module.outcomes, "learnings_pour", lambda *a, **k: lignes)

    resultat = SpecialisteOutcome(limite=3).analyser(
        _contexte(situation_id="sit-1", conn=object()))

    assert len(resultat.propositions) == 3
    assert resultat.statut == "partiel"
    assert any("tronqués" in limite for limite in resultat.limites)
    assert lignes == avant
