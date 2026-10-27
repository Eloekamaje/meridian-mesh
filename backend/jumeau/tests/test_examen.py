"""Examen d'un jumeau né du code : même forme que l'examen de l'atelier, tiré des connaissances prouvées."""
from jumeau import examen

CLAIMS = [
    {"predicat": "EXPOSE", "objet": "GET /articles", "statut": "ACCEPTED", "revues": []},
    {"predicat": "EXPOSE", "objet": "POST /login", "statut": "PROPOSED", "revues": []},
    {"predicat": "DEPEND_DE", "objet": "fastapi", "statut": "PROPOSED", "revues": []},
    {"predicat": "LIT_VARIABLE", "objet": "DB_URL", "statut": "PROPOSED", "revues": []},
    {"predicat": "DEPEND_DE", "objet": "motor", "statut": "CONTESTED",
     "revues": [{"decision": "CONTESTED", "motif": "plus utilisé"}]},
]
FICHE = """## Ce qu'elle fait
Texte.

## Ce qui reste inconnu
- Volumétrie et criticité `README.md#L3`
- Usage réel des favoris

## Autre
- ignoré
"""


def test_examen_tire_des_connaissances_prouvees():
    e = examen.depuis_connaissances({"nom": "Conduit", "mission": "Publier", "domaine": "Client"}, CLAIMS, FICHE)
    assert e["identite"] == {"nom": "Conduit", "mission": "Publier", "domaine": "Client"}
    assert e["capacites"] == ["Expose GET /articles (confirmé par l'équipe)", "Expose POST /login"]
    assert e["comportements"][0].startswith("Lu dans le code")
    assert any("fastapi" in c and "motor" not in c for c in e["comportements"])
    assert any("DB_URL" in c for c in e["comportements"])
    assert e["contradictions"] == ["motor — contesté : plus utilisé"]
    assert e["connaissances_manquantes"][:2] == ["Volumétrie et criticité", "Usage réel des favoris"]
    assert e["relations_supposees"] == []


def test_examen_sans_fiche_ni_contestation():
    e = examen.depuis_connaissances({"nom": "X"}, CLAIMS[:1], None)
    assert e["contradictions"] == [] and e["connaissances_manquantes"]
