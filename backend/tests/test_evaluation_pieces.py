"""Harnais d'évaluation des sections de pièces : jeu JSONL, rang attendu et métriques agrégées."""
import json

import pytest

import evaluation_pieces
import pieces


def _texte_contrat():
    return (
        "# Préambule\n"
        "Le présent contrat décrit les conditions générales.\n\n"
        "# Tarifs\n"
        "Le prix annuel est de 1200 euros hors taxes.\n\n"
        "# Résiliation\n"
        "Le préavis de résiliation est de trois mois.\n"
    )


def _texte_annexe():
    return (
        "# Sauvegardes\n"
        "Les sauvegardes sont quotidiennes et chiffrées.\n\n"
        "# Support\n"
        "Le support répond sous vingt-quatre heures.\n"
    )


def _docs():
    contrat, annexe = _texte_contrat(), _texte_annexe()
    return [
        {"id": "p1", "nom": "Contrat", "texte": contrat,
         "sections": pieces.decouper_sections(contrat)},
        {"id": "p2", "nom": "Annexe", "texte": annexe,
         "sections": pieces.decouper_sections(annexe)},
    ]


def _questions():
    return [
        {"question": "Quel est le prix annuel ?", "piece": "p1", "section": "Tarifs"},
        {"question": "Les sauvegardes sont-elles quotidiennes ?", "piece": "p2", "section": "Sauvegardes"},
    ]


@pytest.fixture
def sans_detail(monkeypatch):
    """Force le repli documenté quand le détail du chemin réel est disponible."""
    monkeypatch.delattr(pieces, "sections_pour_prompt_detail", raising=False)


def test_charger_jeu_lit_les_lignes_et_ignore_les_vides(tmp_path):
    chemin = tmp_path / "questions.jsonl"
    premiere = json.dumps(_questions()[0], ensure_ascii=False) + "\n\n"
    seconde = json.dumps({**_questions()[1], "commentaire": "ignoré"}, ensure_ascii=False) + "\n"
    chemin.write_text(premiere + seconde, encoding="utf-8")
    assert evaluation_pieces.charger_jeu(chemin) == _questions()


def test_charger_jeu_refuse_une_ligne_incomplete(tmp_path):
    chemin = tmp_path / "questions.jsonl"
    chemin.write_text('{"question": "Quel est le prix ?", "piece": "p1"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="ligne incomplète") as erreur:
        evaluation_pieces.charger_jeu(chemin)
    message = str(erreur.value)
    assert ":1" in message and "« section »" in message


def test_charger_jeu_refuse_un_champ_vide(tmp_path):
    chemin = tmp_path / "questions.jsonl"
    chemin.write_text('{"question": "  ", "piece": "p1", "section": "Tarifs"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="ligne incomplète"):
        evaluation_pieces.charger_jeu(chemin)


def test_charger_jeu_refuse_un_json_invalide(tmp_path):
    chemin = tmp_path / "questions.jsonl"
    chemin.write_text('{"question": "ok", "piece": "p1", "section": "s1"}\n{oups\n', encoding="utf-8")
    with pytest.raises(ValueError, match="JSON invalide") as erreur:
        evaluation_pieces.charger_jeu(chemin)
    assert ":2" in str(erreur.value)


def test_charger_jeu_refuse_une_ligne_qui_n_est_pas_un_objet(tmp_path):
    chemin = tmp_path / "questions.jsonl"
    chemin.write_text('["pas", "un", "objet"]\n', encoding="utf-8")
    with pytest.raises(ValueError, match="objet JSON"):
        evaluation_pieces.charger_jeu(chemin)


def test_repli_recall_at_1_et_at_k(sans_detail):
    resultat = evaluation_pieces.evaluer(_docs(), _questions(), k=4)
    assert resultat["n"] == 2
    assert [detail["rang"] for detail in resultat["details"]] == [1, 4]
    assert resultat["recall_at_k"] == 1.0
    assert resultat["mrr"] == pytest.approx((1.0 + 1.0 / 4.0) / 2.0)

    serre = evaluation_pieces.evaluer(_docs(), _questions(), k=1)
    assert serre["recall_at_k"] == 0.5
    assert serre["mrr"] == pytest.approx((1.0 + 1.0 / 4.0) / 2.0)


def test_une_question_sans_reponse_compte_zero(sans_detail):
    question = {"question": "Quelle est la couleur du logo ?", "piece": "p2", "section": "Pénalités"}
    resultat = evaluation_pieces.evaluer(_docs(), [question], k=4)
    detail = resultat["details"][0]
    assert detail["rang"] is None
    assert detail["hit"] is False
    assert resultat["recall_at_k"] == 0.0
    assert resultat["mrr"] == 0.0


def test_les_sections_sont_recalculees_sans_champ_sections(sans_detail):
    docs = [{cle: valeur for cle, valeur in doc.items() if cle != "sections"} for doc in _docs()]
    resultat = evaluation_pieces.evaluer(docs, _questions(), k=4)
    assert [detail["rang"] for detail in resultat["details"]] == [1, 4]


def test_le_detail_est_prioritaire_et_les_pieces_ne_se_melangent_pas(monkeypatch):
    appels = []

    def detail(docs, question):
        appels.append(question)
        return "bloc", [
            {"piece_id": "p2", "section_id": "s1", "titre": "Tarifs", "score": 9},
            {"piece_id": "p1", "section_id": "s2", "titre": "Tarifs", "score": 5},
        ]

    monkeypatch.setattr(pieces, "sections_pour_prompt_detail", detail, raising=False)
    texte = "# Tarifs\nLes tarifs de l'annexe sont forfaitaires.\n"
    docs = [_docs()[0], {"id": "p2", "nom": "Annexe", "texte": texte,
                         "sections": pieces.decouper_sections(texte)}]
    question = {"question": "Quel est le prix annuel ?", "piece": "p1", "section": "Tarifs"}
    resultat = evaluation_pieces.evaluer(docs, [question], k=1)
    assert appels == [question["question"]]
    assert resultat["details"][0]["rang"] == 2
    assert resultat["recall_at_k"] == 0.0
    assert resultat["mrr"] == 0.5


def test_une_piece_donnee_integralement_couvre_ses_sections(monkeypatch):
    def detail(docs, question):
        return "", [{"piece_id": "p1", "section_id": "document", "titre": "Document", "score": 1}]

    monkeypatch.setattr(pieces, "sections_pour_prompt_detail", detail, raising=False)
    resultat = evaluation_pieces.evaluer(
        _docs(),
        [{"question": "Quel est le prix annuel ?", "piece": "p1", "section": "Tarifs"},
         {"question": "Quel est le prix annuel ?", "piece": "p1", "section": "Pénalités"}],
        k=1,
    )
    assert [detail["rang"] for detail in resultat["details"]] == [1, None]
    assert resultat["recall_at_k"] == 0.5


def test_le_chemin_reel_trouve_les_deux_sections():
    resultat = evaluation_pieces.evaluer(_docs(), _questions(), k=4)
    assert resultat["n"] == 2
    assert resultat["recall_at_k"] == 1.0
    assert all(detail["hit"] for detail in resultat["details"])


def test_evaluer_valide_les_questions_et_k():
    with pytest.raises(ValueError, match="question incomplète"):
        evaluation_pieces.evaluer([], [{"question": "question ?", "piece": "p1"}])
    with pytest.raises(ValueError, match="k doit être"):
        evaluation_pieces.evaluer([], [], k=0)


def test_evaluer_un_jeu_vide_rend_des_metriques_nulles():
    assert evaluation_pieces.evaluer([], [], k=4) == {
        "n": 0, "recall_at_k": 0.0, "mrr": 0.0, "details": [],
    }


def test_cli_ecrit_le_json_sur_stdout(tmp_path, capsys):
    docs_path, questions_path = tmp_path / "docs.json", tmp_path / "questions.jsonl"
    docs_path.write_text(json.dumps(_docs(), ensure_ascii=False), encoding="utf-8")
    questions_path.write_text("\n".join(json.dumps(q, ensure_ascii=False) for q in _questions()) + "\n",
                              encoding="utf-8")
    code = evaluation_pieces.main(
        ["--docs", str(docs_path), "--questions", str(questions_path), "--k", "4"])
    assert code == 0
    resultat = json.loads(capsys.readouterr().out)
    assert set(resultat) == {"n", "recall_at_k", "mrr", "details"}
    assert resultat["n"] == 2
    assert resultat["recall_at_k"] == 1.0


def test_cli_signale_un_jeu_invalide(tmp_path, capsys):
    docs_path, questions_path = tmp_path / "docs.json", tmp_path / "questions.jsonl"
    docs_path.write_text("[]", encoding="utf-8")
    questions_path.write_text('{"question": "question ?", "piece": "p1"}\n', encoding="utf-8")
    code = evaluation_pieces.main(
        ["--docs", str(docs_path), "--questions", str(questions_path), "--k", "4"])
    assert code == 1
    assert "ligne incomplète" in capsys.readouterr().err
