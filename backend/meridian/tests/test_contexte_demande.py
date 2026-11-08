"""Enveloppe de contexte : générique, sans application."""
from meridian.application import contexte_demande


def test_product_owner_pedagogique():
    cadrage = {"objectif": "Décider du prochain incrément", "perimetre": "master",
               "contraintes": ["Spring Boot + Vue + MySQL"], "criteres_succes": ["être testable"],
               "utilisateurs": ["équipe produit"]}
    enveloppe = contexte_demande.construire(
        "Je suis le Product Owner de l'équipe TaskAgile. Fais un état pédagogique.", cadrage)
    assert enveloppe["role"] == "Product Owner"
    assert enveloppe["niveau"] == "produit"
    assert enveloppe["decision"] == "Décider du prochain incrément"
    assert enveloppe["perimetre"] == "master"
    assert "trois constats" in enveloppe["contrat"]
    assert "Question d'origine" in contexte_demande.texte(enveloppe)
    assert "Product Owner" in contexte_demande.texte(enveloppe)


def test_tech_lead_technique_sans_contrat_pedagogique():
    enveloppe = contexte_demande.construire("Je suis le Tech Lead. Explique l'architecture du service.")
    assert enveloppe["role"] == "Tech Lead"
    assert enveloppe["niveau"] == "technique"
    assert "réponse directe" in enveloppe["contrat"]


def test_sans_role_sans_cadrage():
    enveloppe = contexte_demande.construire("Que fait cette application ?")
    assert enveloppe["question_origine"] == "Que fait cette application ?"
    assert enveloppe["role"] == ""
    assert enveloppe["niveau"] in {"auto", "produit", "technique"}
    assert enveloppe["contraintes"] == []
