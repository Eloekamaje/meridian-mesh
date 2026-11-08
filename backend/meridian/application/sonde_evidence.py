"""Sonde de preuve pré-raisonnement (plan Cognition IA, B8).

Avant tout raisonnement, une sonde bornée regarde ce que le Mesh sait déjà de la
question : recherche lexicale, graphe et mémoire — trois fonctions **injectées** par
l'appelant (l'adapter câble les vraies requêtes Postgres/Neo4j ; ce module reste pur,
sans base ni réseau, pour ``test_architecture``).

Verdicts déterministes :

- ``trivial`` : la question résout un identifiant direct (clé de ticket, citation
  ``chemin.ext#Ldébut``, locator ``git://``/``systeme://``) **et** une sonde confirme
  l'artefact — la réponse peut être restituée sans modèle (0 token) ;
- ``clair`` : des preuves couvrant le sujet sont présentes ;
- ``incertain`` : preuves absentes, identifiant non résolu ou interprétations rivales —
  le tour normal décide.

``sonder`` ne lève jamais : une sonde en panne est un « manque », pas une erreur.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
import re
import unicodedata
from typing import Any

__all__ = [
    "VERDICTS", "TRIVIAL", "CLAIR", "INCERTAIN",
    "MAX_EXEMPLES", "MAX_PREUVES",
    "sonder", "reponse_triviale",
]

TRIVIAL, CLAIR, INCERTAIN = "trivial", "clair", "incertain"
VERDICTS = (TRIVIAL, CLAIR, INCERTAIN)

MAX_EXEMPLES = 5    # exemples retenus par source dans les indices et la réponse triviale
MAX_PREUVES = 10    # indices bruts conservés dans le résultat (épilogue C8 les compte)
_SEUIL_RIVAL = 0.8  # deux interprétations à moins de 20 % de score : le sujet n'est pas tranché

# Un identifiant direct désigne un artefact précis : clé de ticket (ABC-123), citation de
# code « chemin.ext#Ldébut » (même motif que groundedness/connaissance), locator complet.
_RE_TICKET = re.compile(r"\b[A-Z][A-Z0-9]{1,9}-\d+\b")
_RE_CITATION_CODE = re.compile(
    r"(?<![\w/:.-])[A-Za-z_][\w.-]*(?:/[\w.-]+)*\.[A-Za-z]\w*#L\d+(?:-L\d+)?")
_RE_LOCATOR = re.compile(r"(?:git|[a-z][a-z0-9+.-]*)://[\w@:./#-]+", re.IGNORECASE)


def _normaliser(valeur: Any) -> str:
    texte = unicodedata.normalize("NFKD", str(valeur or "").lower())
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return " ".join(texte.split())


def _identifiants(question: Any) -> list[str]:
    """Les identifiants directs cités dans la question, dans l'ordre, sans doublon."""
    texte = str(question or "")
    trouves = (
        _RE_TICKET.findall(texte)
        + _RE_CITATION_CODE.findall(texte)
        + _RE_LOCATOR.findall(texte)
    )
    return list(dict.fromkeys(trouves))


def _etiquette(preuve: Mapping) -> str:
    """Libellé court d'un indice — jamais le corps entier d'une entrée."""
    predicat, objet = str(preuve.get("predicat") or ""), str(preuve.get("objet") or "")
    if predicat and objet:
        return f"{predicat} {objet}"[:160]
    for cle in ("titre", "locator", "objet", "contenu", "nom", "libelle", "id"):
        valeur = str(preuve.get(cle) or "").strip()
        if valeur:
            return valeur[:160]
    return ""


def _detail(preuve: Mapping) -> str:
    for cle in ("locator", "detail", "preuve", "id"):
        valeur = str(preuve.get(cle) or "").strip()
        if valeur:
            return valeur[:300]
    return ""


def _identite(preuve: Mapping) -> str:
    """L'entité que désigne un indice, pour détecter les interprétations rivales."""
    for cle in ("jumeau_id", "twin_id", "sujet", "id"):
        valeur = str(preuve.get(cle) or "").strip()
        if valeur:
            return valeur
    return ""


def _score(preuve: Mapping) -> float | None:
    try:
        return float(preuve.get("score"))
    except (TypeError, ValueError):
        return None


def _lancer(nom: str, sonde: Callable, question: str,
            indices: list, manque: list) -> list[dict]:
    """Exécute une sonde injectée ; sa panne rejoint ``manque``, jamais l'appelant."""
    try:
        trouvees = [dict(indice) for indice in (sonde(question) or ())
                    if isinstance(indice, Mapping)]
    except Exception:
        manque.append(f"{nom} indisponible")
        return []
    indices.append({
        "source": nom,
        "trouves": len(trouvees),
        "exemples": [
            etiquette
            for etiquette in (_etiquette(indice) for indice in trouvees[:MAX_EXEMPLES])
            if etiquette
        ],
    })
    return trouvees


def _confirme(identifiants: Iterable[str], trouvees: Iterable[Mapping]) -> bool:
    """Un identifiant cité est-il confirmé par au moins un indice trouvé ?"""
    textes = [
        _normaliser(" ".join(str(valeur) for valeur in dict(indice).values()))
        for indice in trouvees
    ]
    for identifiant in identifiants:
        cle = _normaliser(identifiant)
        morceaux = [m for m in re.split(r"[/:#@\s.()_-]+", cle) if len(m) >= 4]
        for texte in textes:
            if cle in texte or any(morceau in texte for morceau in morceaux):
                return True
    return False


def _rivales(trouvees: Iterable[Mapping]) -> bool:
    """Deux interprétations à scores proches sur des sujets distincts : la sonde ne tranche pas."""
    notes = sorted(
        (
            (score, identite)
            for score, identite in ((_score(t), _identite(t)) for t in trouvees)
            if score is not None and identite
        ),
        reverse=True,
    )
    if len(notes) < 2:
        return False
    (meilleur, identite1), (second, identite2) = notes[0], notes[1]
    return identite1 != identite2 and meilleur > 0 and second >= _SEUIL_RIVAL * meilleur


def sonder(question: Any, *, recherche_lexicale: Callable | None = None,
           graphe: Callable | None = None, memoire: Callable | None = None) -> dict:
    """Verdict pré-raisonnement : ``trivial`` | ``clair`` | ``incertain``.

    Chaque sonde injectée reçoit la question et rend un itérable d'indices (mappings) ;
    ``None`` = source non câblée pour ce tour — elle n'est simplement pas lancée.
    Rend ``{verdict, indices, manque, preuves}`` : ``preuves`` borne les indices bruts
    (réponse triviale, épilogue C8) ; ``manque`` dit ce qui n'a pas pu être établi.
    """
    question_texte = " ".join(str(question or "").split())
    indices: list[dict] = []
    manque: list[str] = []
    trouvees: list[dict] = []
    for nom, sonde in (
        ("lexicale", recherche_lexicale), ("graphe", graphe), ("memoire", memoire)
    ):
        if sonde is None:
            continue
        for indice in _lancer(nom, sonde, question_texte, indices, manque):
            trouvees.append({"origine": nom, **indice})

    identifiants = _identifiants(question_texte)
    if identifiants:
        indices.append({"source": "question", "identifiants": identifiants})
        if _confirme(identifiants, trouvees):
            return {"verdict": TRIVIAL, "indices": indices, "manque": manque,
                    "preuves": trouvees[:MAX_PREUVES]}
        # Un identifiant cité que rien ne confirme n'est pas couvert par les autres
        # indices : la sonde reste incertaine plutôt que de trancher faux.
        manque.append("identifiant non résolu : " + ", ".join(identifiants[:3]))
        if trouvees:
            return {"verdict": INCERTAIN, "indices": indices, "manque": manque,
                    "preuves": trouvees[:MAX_PREUVES]}
    if not trouvees:
        manque.append("aucune preuve : la question n'est couverte par aucune source sondée")
        return {"verdict": INCERTAIN, "indices": indices, "manque": manque, "preuves": []}
    if _rivales(trouvees):
        manque.append("interpretations rivales : la sonde ne tranche pas le sujet")
        return {"verdict": INCERTAIN, "indices": indices, "manque": manque,
                "preuves": trouvees[:MAX_PREUVES]}
    return {"verdict": CLAIR, "indices": indices, "manque": manque,
            "preuves": trouvees[:MAX_PREUVES]}


def reponse_triviale(resultat: Mapping) -> dict:
    """Réponse déterministe d'un verdict ``trivial`` : les indices trouvés, restitués tels quels.

    Zéro token : le texte est composé, pas généré — il dit que la réponse vient de la
    sonde et ne prétend rien au-delà des indices effectivement trouvés.
    """
    resultat = dict(resultat or {})
    exemples: list[str] = []
    for indice in resultat.get("indices") or ():
        for etiquette in indice.get("exemples") or ():
            if etiquette and etiquette not in exemples:
                exemples.append(etiquette)
    exemples = exemples[:MAX_EXEMPLES]
    lignes = "\n".join(f"- {exemple}" for exemple in exemples) or "- aucun détail affichable"
    preuves = [
        {"source": _etiquette(preuve) or "indice de la sonde",
         "detail": _detail(preuve) or _etiquette(preuve)}
        for preuve in (resultat.get("preuves") or ())[:MAX_EXEMPLES]
    ]
    return {
        "comportement": "repondre",
        "reponse": (
            "J'ai trouvé directement ce que la question désigne — cette réponse vient de la "
            "sonde de preuve, sans raisonnement ni modèle :\n\n" + lignes
        ),
        "questions": [],
        "preuves": preuves,
        "contributions": [],
        "jumeaux_participants": [],
        "sonde": resultat,
    }
