"""Évaluation : jeu tiré du jumeau, scores, panne isolée, empreinte des méthodes. Sans réseau ni modèle."""
import asyncio

import pytest

from meridian.adapters.outbound.llm import evaluation
from meridian.tests.conftest import JUMEAU, besoin_pg

CLAIMS = [{"id": 1, "predicat": "ECHANGE_AVEC", "objet": "Le système de paiement", "statut": "ACCEPTED"},
          {"id": 2, "predicat": "ECHANGE_AVEC", "objet": "Le courrier", "statut": "PROPOSED"},
          {"id": 3, "predicat": "APPLIQUE_REGLE", "objet": "Double approbation", "statut": "ACCEPTED"},
          {"id": 4, "predicat": "DEPEND_DE", "objet": "fastapi", "statut": "ACCEPTED"}]


def test_les_sept_questions_sont_lues_dans_la_methode():
    qs = evaluation.questions_ancrage()
    assert len(qs) == 7
    assert qs[0].startswith("À quoi elle sert") and "Prédicat" not in qs[0]
    assert qs[-1].startswith("Ce que l'on ne sait pas encore")


def test_jeu_exactitude_seulement_des_connaissances_validees_du_bon_type():
    jeu = evaluation.construire_jeu("TBT", CLAIMS, maximum=10)
    exact = [q for q in jeu if q["etage"] == "exactitude"]
    assert sorted(q["attendu"] for q in exact) == ["Double approbation", "Le système de paiement"]
    echange = next(q for q in exact if q["attendu"] == "Le système de paiement")
    assert echange["question"].startswith("TBT") and "échange" in echange["question"]
    assert "paiement" not in echange["question"]


def test_le_jeu_est_borne_par_max():
    jeu = evaluation.construire_jeu("TBT", CLAIMS, maximum=4)
    assert len(jeu) == 4 and {q["etage"] for q in jeu} == {"exactitude", "ancrage"}
    assert len(evaluation.construire_jeu("TBT", [], maximum=10)) == 7  # sans validation : l'ancrage seul
    assert len(evaluation.construire_jeu("TBT", CLAIMS, maximum=1)) == 1


def _faux(monkeypatch, reponses, jugements):
    async def repondre(jid, question, acteur, trace=None, **k):
        r = reponses.pop(0)
        if isinstance(r, Exception):
            raise r
        trace.update(texte=r, invalides=["x.py#L9-L9"] if "faux" in r else [])
        return {"comportement": "expliquer", "reponse": r}

    async def juger(question, reponse, attendu):
        return jugements.pop(0)
    monkeypatch.setattr(evaluation.flore, "repondre", repondre)
    monkeypatch.setattr(evaluation, "_juger", juger)


def test_scores_et_panne_d_une_question_sans_arreter_la_passe(monkeypatch):
    J = evaluation.Jugement
    _faux(monkeypatch,
          ["Elle échange avec le système de paiement `a.py#L1-L2`.", RuntimeError("délai"),
           "Texte faux `a.py#L1-L2` `x.py#L9-L9`."],
          [J(contient_attendu=True, contredit=False, affirmations=2, appuyees=2),
           J(contient_attendu=False, contredit=True, affirmations=2, appuyees=1)])
    jeu = [{"etage": "exactitude", "question": "q1", "attendu": "a"}, {"etage": "exactitude", "question": "q2", "attendu": "b"},
           {"etage": "ancrage", "question": "q3", "attendu": None}]
    scores, details = asyncio.run(evaluation.passe("tbt", jeu))
    assert scores["exactitude"] == 1.0 and scores["contradictions"] == 0
    assert scores["pannes"] == 1
    assert scores["citations_valides"] == pytest.approx(2 / 3, abs=1e-3)      # 1/1 puis 1/2
    assert scores["affirmations_appuyees"] == pytest.approx(0.5)
    assert details[1]["panne"] == "RuntimeError: délai" and "duree_s" in details[0]


def test_reponse_indisponible_est_une_panne(monkeypatch):
    async def repondre(*a, **k):
        return {"comportement": "signaler", "reponse": "Je ne peux pas"}
    monkeypatch.setattr(evaluation.flore, "repondre", repondre)
    scores, details = asyncio.run(evaluation.passe("tbt", [{"etage": "ancrage", "question": "q", "attendu": None}]))
    assert scores["pannes"] == 1 and scores["exactitude"] is None and "panne" in details[0]


def test_empreinte_des_methodes_change_avec_le_contenu(tmp_path):
    (tmp_path / "m.md").write_text("a")
    charte = tmp_path / "charte.md"
    charte.write_text("c")
    e1 = evaluation.empreinte_methodes(tmp_path, charte)
    assert len(e1) == 12 and e1 == evaluation.empreinte_methodes(tmp_path, charte)
    (tmp_path / "m.md").write_text("b")
    assert evaluation.empreinte_methodes(tmp_path, charte) != e1
    assert evaluation.empreinte_methodes() == evaluation.empreinte_methodes()


@besoin_pg
def test_enregistrement_d_une_passe(conn):
    from meridian.adapters.outbound.postgres import depot
    depot.creer_jumeau(conn, JUMEAU)
    evaluation.enregistrer(conn, "tbt", "abc", "modele-x", {"exactitude": 1.0}, [{"question": "q"}])
    ligne = conn.execute("SELECT version_methodes, modele, scores, details FROM evaluation WHERE jumeau_id = 'tbt'").fetchone()
    assert ligne == ("abc", "modele-x", {"exactitude": 1.0}, [{"question": "q"}])
