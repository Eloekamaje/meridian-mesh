"""Détection déterministe des intentions d'action canonique (D4).

Un lexique verbe d'action + entité de la boucle (Situation, Investigation, Decision,
Initiative) produit un plan de manifestes : étapes ordonnées ou référence manquante.
Le modèle ne participe ni à la détection ni à l'autorité — le Harness exige chaque
manifeste dans `approuves` avant la moindre écriture. Aucune écriture n'est tentée ici :
ce module ne fait que lire la demande et produire un plan.
"""
from __future__ import annotations

import re
import unicodedata

__all__ = ["intention_action"]

# Identifiants cités : préfixes courts de l'API B1 (sit-, inv-, dec-, ini-) ou formes
# longues générées par le dépôt (situation-…, investigation-…, decision-…, initiative-…).
_RE_ID_OBJET = {
    "situation_id": re.compile(r"\b((?:sit|situation)-[a-z0-9]{4,})\b", re.IGNORECASE),
    "investigation_id": re.compile(
        r"\b((?:inv|investigation)-[a-z0-9]{4,})\b", re.IGNORECASE),
    "decision_id": re.compile(r"\b((?:dec|decision)-[a-z0-9]{4,})\b", re.IGNORECASE),
}
_RE_GUILLEMETS = re.compile(r"[\"«']([^\"»'\n]{2,200})[\"»']")
_NEGATIONS = {
    "ne", "pas", "jamais", "sans", "aucun", "aucune", "evite", "eviter",
    "annule", "annuler", "supprime", "supprimer", "stop", "abandonne",
}
# Ordre significatif : la première règle dont le verbe et l'entité sont présents gagne.
_REGLES_ACTION = (
    ("trancher_decision",
     {"tranche", "trancher", "tranchez", "acte", "acter", "arrete", "arreter",
      "choisis", "choisir", "decide", "decider", "decidez"},
     {"decision"}),
    ("proposer_decision",
     {"propose", "proposer", "proposez", "prepare", "preparer", "suggere", "suggerer",
      "formule", "formuler"},
     {"decision"}),
    ("lancer_initiative",
     {"lance", "lancer", "lancez", "demarre", "demarrer", "initie", "initier",
      "cree", "creer", "creez"},
     {"initiative"}),
    ("ouvrir_investigation",
     {"ouvre", "ouvrir", "ouvrez", "lance", "lancer", "lancez", "demarre", "demarrer",
      "cree", "creer", "creez", "investigue", "investiguer"},
     {"investigation", "enquete"}),
    ("creer_situation",
     {"cree", "creer", "creez", "enregistre", "enregistrer", "declare", "declarer",
      "signale", "signaler", "constate", "constater", "ouvre", "ouvrir", "ouvrez"},
     {"situation"}),
)
# « décider » reste interrogatif sans identifiant : seul un verbe fort ou un dec-… tranche.
_VERBES_TRANCHER_FORTS = {"tranche", "trancher", "tranchez", "acte", "acter", "arrete",
                         "arreter", "choisis", "choisir"}


def _tokens(texte) -> list[str]:
    """Minuscules sans accents, en jetons — même normalisation que le routage historique."""
    decompose = unicodedata.normalize("NFKD", str(texte or "").lower())
    sans_accents = "".join(c for c in decompose if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+", sans_accents)


def _ids_objets(question) -> dict:
    return {
        cle: (m.group(1).lower() if (m := motif.search(str(question or ""))) else None)
        for cle, motif in _RE_ID_OBJET.items()
    }


def _motif_entite(entite) -> str:
    """L'entité orthographiée avec ou sans accents (« décision » ↔ « decision »)."""
    voyelles = {"e": "[eéèêë]", "a": "[aàâä]", "u": "[uùûü]", "i": "[iîï]",
                "o": "[oôö]", "c": "[cç]"}
    return "".join(voyelles.get(caractere, re.escape(caractere)) for caractere in entite)


def _titre_intention(question, entite) -> str:
    """Le libellé après l'entité nommée (« sur les retards ») ; la demande entière sinon."""
    m = re.search(rf"(?i)\b{_motif_entite(entite)}s?\b[\s:—–-]*(.+)", str(question or ""))
    reste = (m.group(1) if m else str(question or "")).strip()
    reste = re.sub(
        r"(?i)^(?:(?:de|du|des|la|le|les|une?|sur|pour|concernant|aux?|en|relative?|liée?)\b[\s'’]*)+",
        "", reste)
    reste = re.sub(
        r"\b(?:sit|situation|inv|investigation|dec|decision|ini|initiative|out|ler)-[a-z0-9]{4,}\b",
        "", reste, flags=re.IGNORECASE)
    reste = reste.strip(" \t:—–-,.;!?")
    return (reste or " ".join(str(question or "").split()) or "Intention d'action")[:200]


def _options_intention(question) -> list[str]:
    """Les options après « options : » ; jamais inventées — une seule option sinon."""
    m = re.search(r"(?i)\boptions?\b\s*[:=]\s*(.+)", str(question or ""))
    if not m:
        return []
    morceaux = re.split(r"[,;]|\s+ou\s+|\s+et\s+|\|", m.group(1))
    return [morceau.strip(" .;") for morceau in morceaux if morceau.strip(" .;")][:8]


def _choix_intention(question) -> str:
    """Le choix retenu, entre guillemets ou après « choix »/« choisis » ; vide sinon."""
    m = _RE_GUILLEMETS.search(str(question or ""))
    if m:
        return m.group(1).strip()[:200]
    m = re.search(r"(?i)\bchoix\b\s*[:=]?\s*[\"«']?(.+)", str(question or ""))
    if not m:
        m = re.search(r"(?i)\bchoisiss?\w*\s+[\"«']?(.+)", str(question or ""))
    return m.group(1).strip(" .;\"»'")[:200] if m else ""


def intention_action(question) -> dict | None:
    """Détection déterministe d'une intention d'action canonique ; ``None`` hors intention.

    Règle : un verbe d'action et une entité de la boucle doivent coexister dans la demande,
    sans négation proche du verbe. Le résultat porte le plan de manifestes (`etapes`) ou
    `complet=False` avec la référence manquante — aucune écriture n'est tentée ici.
    """
    tokens = _tokens(question)
    if not tokens:
        return None
    ensemble = set(tokens)
    ids = _ids_objets(question)
    for manifeste, verbes, entites in _REGLES_ACTION:
        entite = next((candidat for candidat in entites if candidat in ensemble), None)
        if entite is None:
            continue
        indice = next((i for i, token in enumerate(tokens) if token in verbes), None)
        if indice is None:
            continue
        verbe = tokens[indice]
        if manifeste == "trancher_decision" and verbe not in _VERBES_TRANCHER_FORTS \
                and not ids["decision_id"]:
            continue  # « décider » seul n'est pas un ordre de tranchée
        if any(token in _NEGATIONS for token in tokens[max(0, indice - 4):indice]):
            continue  # « ne crée pas », « sans ouvrir » : pas une intention d'exécution
        return _plan_action(manifeste, question, entite, ids)
    return None


def _plan_action(manifeste, question, entite, ids) -> dict:
    """Le plan de manifestes d'une intention : étapes ordonnées, ou référence manquante.

    « ouvre une investigation » sans situation citée crée d'abord la Situation qui la porte ;
    « $n » est l'identifiant du résultat de l'étape n, résolu à l'exécution.
    """
    question_texte = " ".join(str(question or "").split())
    titre = _titre_intention(question, entite)
    if manifeste == "creer_situation":
        return {"manifeste": manifeste, "complet": True,
                "etapes": [("creer_situation", {"titre": titre, "donnees": {"resume": titre}})]}
    if manifeste == "ouvrir_investigation":
        args = {"situation_id": ids["situation_id"] or "$0",
                "titre": titre, "question": question_texte[:500]}
        etapes = [] if ids["situation_id"] else [
            ("creer_situation", {"titre": titre, "donnees": {"resume": titre}})]
        etapes.append(("ouvrir_investigation", args))
        return {"manifeste": manifeste, "complet": True, "etapes": etapes}
    if manifeste == "proposer_decision":
        if not ids["investigation_id"]:
            return {"manifeste": manifeste, "complet": False,
                    "manquant": "l'investigation à rattacher (son identifiant inv-…)"}
        options = _options_intention(question) or [titre]
        return {"manifeste": manifeste, "complet": True,
                "etapes": [("proposer_decision", {
                    "investigation_id": ids["investigation_id"],
                    "options": options, "titre": titre})]}
    if manifeste == "trancher_decision":
        if not ids["decision_id"]:
            return {"manifeste": manifeste, "complet": False,
                    "manquant": "la décision à trancher (son identifiant dec-…)"}
        choix = _choix_intention(question)
        if not choix:
            return {"manifeste": manifeste, "complet": False,
                    "manquant": "le choix retenu (une option de la décision)"}
        return {"manifeste": manifeste, "complet": True,
                "etapes": [("trancher_decision", {
                    "decision_id": ids["decision_id"], "choix": choix})]}
    if manifeste == "lancer_initiative":
        if not ids["decision_id"]:
            return {"manifeste": manifeste, "complet": False,
                    "manquant": "la décision tranchée à lancer (son identifiant dec-…)"}
        return {"manifeste": manifeste, "complet": True,
                "etapes": [("lancer_initiative", {
                    "decision_id": ids["decision_id"], "titre": titre})]}
    return {"manifeste": manifeste, "complet": False, "manquant": "l'objet de l'action"}
