"""A5 — le jeu d'or sur le chemin réel : registre capacitaire + invariants + politique.

- `selectionneur_regles` produit le candidat depuis `cas.entree` et le registre réel,
  jamais depuis les attendus : le jeu mesure la couche politique, pas sa propre référence.
- Le contrôle négatif prouve que la suite peut échouer.
- `evaluer()` sans sélectionneur est refusé : noter le jeu contre `cas.attendu()` n'est
  pas une mesure (utiliser `evaluer_reference` pour l'auto-contrôle du jeu).
"""
import pytest

from meridian.application import evaluation_gold as eg
from meridian.domain import capacites


def _registre():
    from meridian.adapters.outbound.llm import harness
    # Le catalogue réel : manifestes intégrés + méta-outils que le Harness ajoute toujours.
    return capacites.RegistreCapacites(
        [*capacites.manifestes_integres(), *harness.manifestes_decouverte()])


def test_evaluer_exige_un_selectionneur():
    with pytest.raises(TypeError):
        eg.evaluer(eg.charger())


def test_reference_passe_et_est_marquee():
    resultat = eg.evaluer_reference()
    assert resultat["mode"] == "reference"
    assert resultat["passe"] == resultat["total"] == 10


def test_selectionneur_regles_passe_le_jeu():
    resultat = eg.evaluer(eg.charger(), eg.selectionneur_regles(_registre()))
    assert resultat["pass_rate"] == 1.0
    assert resultat["passe"] == resultat["total"]


def test_controle_negatif_statut_inverse_echoue():
    """Un sélectionneur qui inverse les statuts de Claims doit échouer : la suite mesure."""
    regles = eg.selectionneur_regles(_registre())

    def corrompu(cas):
        candidat = regles(cas)
        for claim in candidat["claims"]:
            claim["statut"] = "PROPOSED" if claim["statut"] != "PROPOSED" else "ACCEPTED"
        return candidat

    resultat = eg.evaluer(eg.charger(), corrompu)
    assert resultat["pass_rate"] < 1.0
    assert resultat["passe"] < resultat["total"]


def test_controle_negatif_outil_supprime_echoue():
    def corrompu(cas):
        return {"outils": [], "texte": "", "claims": [], "decision": {}}

    resultat = eg.evaluer(eg.charger(), corrompu)
    assert resultat["passe"] == 0


def test_outil_ecriture_invisible_sans_approbation():
    """`comptes.creercompte` n'existe pas dans le registre intégré : le cas garde son
    interdit par construction, et l'évaluateur le vérifie contre le vrai catalogue."""
    selectionner = eg.selectionneur_regles(_registre())
    cas = next(c for c in eg.charger() if c.id == "lecture-ecriture-interdite")
    candidat = selectionner(cas)
    assert "comptes.creercompte" not in candidat["outils"]
    assert "decrire_outil" in candidat["outils"]
