"""Enveloppe de contexte transmise au jumeau avec la mission.

La mission est la tâche bornée ; l'enveloppe rappelle la question d'origine, le rôle, la décision,
le niveau et le contrat. C'est un contexte, jamais une instruction de remplacer la mission.
"""
from __future__ import annotations

import re
import unicodedata

ROLES = {
    "product owner": "Product Owner",
    "product manager": "Product Manager",
    "tech lead": "Tech Lead",
    "architecte": "Architecte",
    "developpeur": "Développeur",
    "développeur": "Développeur",
    "qa": "QA",
    "testeur": "QA",
    "sre": "SRE",
    "ops": "Ops",
    "métier": "Métier",
}
MOTS_PEDAGOGIQUES = ("pedagogique", "verdict", "diagnostic", "etat des lieux", "ecart",
                     "rendu", "schema")
CONTRAT_PEDAGOGIQUE = (
    "verdict en une phrase ; schéma si utile ; trois constats maximum avec preuve ; conséquence ; "
    "décision recommandée avec deux conditions ; trois tests ; inconnues."
)
CONTRAT_DIRECT = "réponse directe ; faits observés, déduits et inconnus séparés ; preuves citées."


def construire(question, cadrage=None, pedagogique=None):
    """L'enveloppe de contexte : question d'origine, rôle, décision, niveau, périmètre, contrat."""
    cadrage = dict(cadrage or {})
    role = _role(question)
    niveau = _niveau(question, role)
    contrat = CONTRAT_PEDAGOGIQUE if (pedagogique or _pedagogique(question)) else CONTRAT_DIRECT
    return {
        "question_origine": _texte(question),
        "role": role,
        "decision": _texte(cadrage.get("objectif")) or _texte(question),
        "niveau": niveau,
        "perimetre": _texte(cadrage.get("perimetre")),
        "contraintes": _liste(cadrage.get("contraintes")),
        "criteres_succes": _liste(cadrage.get("criteres_succes")),
        "utilisateurs": _liste(cadrage.get("utilisateurs") or cadrage.get("parties_prenantes")),
        "contrat": contrat,
    }


def texte(enveloppe):
    """Le rendu de l'enveloppe pour un prompt : des données, pas des instructions."""
    lignes = ["Question d'origine : " + enveloppe.get("question_origine", "")]
    if enveloppe.get("role"):
        lignes.append("Rôle : " + enveloppe["role"])
    if enveloppe.get("decision"):
        lignes.append("Décision à prendre : " + enveloppe["decision"])
    if enveloppe.get("niveau"):
        lignes.append("Niveau attendu : " + enveloppe["niveau"])
    if enveloppe.get("perimetre"):
        lignes.append("Périmètre : " + enveloppe["perimetre"])
    if enveloppe.get("contraintes"):
        lignes.append("Contraintes : " + "; ".join(enveloppe["contraintes"]))
    if enveloppe.get("criteres_succes"):
        lignes.append("Critères de succès : " + "; ".join(enveloppe["criteres_succes"]))
    if enveloppe.get("utilisateurs"):
        lignes.append("Utilisateurs : " + "; ".join(enveloppe["utilisateurs"]))
    if enveloppe.get("contrat"):
        lignes.append("Contrat de réponse : " + enveloppe["contrat"])
    lignes.append("La mission qui suit est la tâche bornée ; réponds-y en gardant ce niveau et cette intention.")
    return "\n".join("- " + ligne for ligne in lignes)


def _role(question):
    normalise = _normaliser(question)
    for cle, libelle in ROLES.items():
        if cle in normalise:
            return libelle
    trouve = re.search(r"je suis (?:le |la |un |une )?([^.,\n]{3,80})", normalise)
    return trouve.group(1).strip().title() if trouve else ""


def _niveau(question, role):
    if role in {"Product Owner", "Product Manager", "Métier"}:
        return "produit"
    if role in {"Tech Lead", "Architecte", "Développeur"}:
        return "technique"
    if role == "QA":
        return "produit + recette"
    if role in {"SRE", "Ops"}:
        return "exploitation"
    normalise = _normaliser(question)
    if any(mot in normalise for mot in ("produit", "increment", "decision", "metier", "parcours", "besoin")):
        return "produit"
    if any(mot in normalise for mot in ("architecture", "code", "controleur", "service", "entite")):
        return "technique"
    return "auto"


def _pedagogique(question):
    normalise = _normaliser(question)
    return any(mot in normalise for mot in MOTS_PEDAGOGIQUES)


def _normaliser(valeur):
    texte = unicodedata.normalize("NFKD", str(valeur or ""))
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return texte.lower().replace("’", "'").replace("'", " ")


def _texte(valeur, maximum=1000):
    return " ".join(str(valeur or "").split())[:maximum]


def _liste(valeur):
    if valeur is None:
        return []
    if isinstance(valeur, str):
        return [valeur.strip()] if valeur.strip() else []
    return [str(v).strip() for v in valeur if str(v).strip()]
