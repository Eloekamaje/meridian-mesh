"""Revue d'un jumeau né du code : les sept questions, tirées des connaissances prouvées et de la fiche vivante."""
from jumeau import examen

CLAIMS = [
    {"predicat": "REALISE_CAPACITE", "objet": "Gérer les dossiers", "statut": "ACCEPTED"},
    {"predicat": "REALISE_CAPACITE", "objet": "Présenter la solution", "statut": "PROPOSED"},
    {"predicat": "APPLIQUE_REGLE", "objet": "Double approbation", "statut": "CONTESTED"},
    {"predicat": "DEPEND_DE", "objet": "fastapi", "statut": "PROPOSED"},
]
FICHE = """## Comment elle vit
- **Refonte** le 25 octobre `app.py#L6`

## Ce que l'on ne sait pas encore
- Qui s'en sert réellement
"""


def test_sept_questions_sans_detail_technique():
    e = examen.depuis_connaissances({"nom": "X", "mission": "m", "domaine": "d", "proprietaire": "Équipe Y"}, CLAIMS, FICHE)
    blocs = {b["cle"]: b for b in e["comprendre"]}
    assert list(blocs) == ["sert", "pour_qui", "informations", "regles", "echanges", "vie", "inconnu"]
    assert blocs["sert"]["items"] == [{"texte": "Gérer les dossiers", "statut": "ACCEPTED"},
                                      {"texte": "Présenter la solution", "statut": "PROPOSED"}]
    assert blocs["regles"]["items"][0]["statut"] == "CONTESTED"
    assert [i["texte"] for i in blocs["vie"]["items"]] == ["Refonte le 25 octobre", "Responsable : Équipe Y"]
    assert blocs["inconnu"]["items"][:2] == [{"texte": "Qui s'en sert réellement"},
                                             {"texte": "1 connaissance(s) sur 3 validée(s) par l'équipe"}]
    assert "fastapi" not in str(e)


def test_sans_fiche():
    e = examen.depuis_connaissances({"nom": "X"}, [], None)
    assert all(b["items"] == [] for b in e["comprendre"] if b["cle"] not in ("vie", "inconnu"))
