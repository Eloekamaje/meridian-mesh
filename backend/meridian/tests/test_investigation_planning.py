"""Planification bornée de la compréhension initiale et des réexamens."""
import pytest

from meridian.application.investigation_planning import (
    MAX_FICHIERS_DIFF,
    fichiers_modifies,
    missions_initiales,
    planifier_reexamens,
)


def test_naissance_planifie_les_parcours_et_non_un_inventaire_exhaustif():
    missions = missions_initiales("paiements")
    assert [m.cle for m in missions] == [
        "points-entree", "controles-erreurs", "donnees-effets",
        "dependances-confirmees", "interfaces-sortantes",
    ]
    assert any("DECLARE_DEPENDANCE" in m.raison for m in missions)


def test_les_lacunes_de_couverture_deviennent_la_premiere_mission():
    missions = missions_initiales("paiements", {
        "couverture": {"indexe": 10, "non_supporte": 3, "tronque": 1},
        "erreurs_providers": ["cobol", "cobol", "java"],
    })
    assert missions[0].cle == "lacunes-couverture" and missions[0].priorite == 110
    assert "4 fichier(s)" in missions[0].raison
    assert "cobol, java" in missions[0].raison


def test_fichiers_modifies_deduplique_normalise_et_borne():
    assert fichiers_modifies([
        {"fichiers": ["src/a.py", "src/b.py"]},
        {"fichiers": ["src/a.py", "web\\app.js"]},
    ]) == ("src/a.py", "src/b.py", "web/app.js")
    beaucoup = [{"fichiers": [f"src/{i}.py" for i in range(MAX_FICHIERS_DIFF + 2)]}]
    assert len(fichiers_modifies(beaucoup)) == MAX_FICHIERS_DIFF
    with pytest.raises(ValueError, match="chemin"):
        fichiers_modifies([{"fichiers": ["../secret"]}])


def test_seules_les_preuves_du_depot_et_du_fichier_modifies_sont_reexaminees():
    claims = [
        {"id": "c1", "preuves": [
            {"depot": "api", "chemin": "src/pay.py"},
            {"depot": "docs", "chemin": "src/pay.py"},
        ]},
        {"id": "c2", "preuves": [{"repository": "api", "fichier": "src/stable.py"}]},
        {"id": "c3", "evidence": [{"source": "api", "file": "src/pay.py"}]},
    ]
    resultat = planifier_reexamens(claims, "api", ["src/pay.py", "README.md"])
    assert [(r.claim_id, r.fichiers) for r in resultat] == [
        ("c1", ("src/pay.py",)), ("c3", ("src/pay.py",)),
    ]


def test_un_diff_sans_preuve_touchee_ne_fabrique_pas_d_impact():
    assert planifier_reexamens(
        [{"id": "c1", "preuves": [{"depot": "api", "chemin": "src/a.py"}]}],
        "api", ["src/b.py"],
    ) == ()
