"""Revue d'un jumeau né du code : présentée à tout employé, par niveaux, faits calculés par le harness."""
from jumeau import examen

def claim(predicat, objet, statut="PROPOSED", chemin="app.py"):
    return {"predicat": predicat, "objet": objet, "statut": statut, "preuves": [{"chemin": chemin}]}


CLAIMS = [claim("REALISE_CAPACITE", "Gérer les dossiers", "ACCEPTED"), claim("APPLIQUE_REGLE", "Double approbation"),
          claim("REALISE_CAPACITE", "Présenter la solution", chemin="memory/PRD.md"), claim("DEPEND_DE", "fastapi")]
FICHE = """# Fiche vivante

## En 30 secondes
Une maquette qui montre le suivi de **dossiers** `memory/PRD.md#L4`.
Elle sert à convaincre des évaluateurs.
Criticité : faible — aucune donnée réelle

## Une journée avec elle
Une agente ouvre un dossier.
Un réviseur le vérifie.

## Ce qu'elle permet de faire
- Ouvrir un dossier hors ligne `app.py#L3`

## Les règles à retenir
- Pas d'orientation sans consentement `app.py#L9`

## Avec qui elle travaille
Personne : maquette autonome `memory/PRD.md#L3`.

## D'où je le sais, et ce que j'ignore
- Qui l'utilisera réellement
"""


def test_presentation_par_niveaux():
    e = examen.depuis_connaissances({"nom": "X", "statut": "observation", "proprietaire": "Équipe Y"}, CLAIMS, FICHE)
    p = e["presentation"]
    assert p["phrases"] == ["Une maquette qui montre le suivi de dossiers.", "Elle sert à convaincre des évaluateurs."]
    assert p["reperes"] == {"statut": "en observation", "responsable": "Équipe Y", "criticite": "faible — aucune donnée réelle"}
    assert p["journee"] == "Une agente ouvre un dossier. Un réviseur le vérifie."
    assert [(b["cle"], b["items"]) for b in p["blocs"]] == [
        ("faire", ["Ouvrir un dossier hors ligne"]), ("regles", ["Pas d'orientation sans consentement"]),
        ("garde", []), ("avec", ["Personne : maquette autonome."])]
    assert p["ignore"] == ["Qui l'utilisera réellement"]
    sources = {s["nom"]: s["etat"] for s in p["sources"]}
    assert sources["Documentation"] == "lue" and sources["Équipe"] == "1 confirmée(s)"
    assert sources["Exploitation"] == "non branchée"
    assert "fastapi" not in str(e)


def test_pour_aller_plus_loin_les_sept_questions():
    e = examen.depuis_connaissances({"nom": "X"}, CLAIMS, None)
    blocs = {b["cle"]: b["items"] for b in e["comprendre"]}
    assert blocs["sert"] == [{"texte": "Gérer les dossiers", "statut": "ACCEPTED"},
                             {"texte": "Présenter la solution", "statut": "PROPOSED"}]
    assert e["presentation"]["reperes"]["responsable"] == "à confirmer"
    assert e["presentation"]["reperes"]["criticite"] == "inconnue"
