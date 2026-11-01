"""Context Pack borné : ce qui entre dans une réponse, ce qui reste dehors, et son empreinte.

Le pack ne contient ni prompt complet ni secret : il sélectionne des propositions, preuves,
entités et limites déjà produites par le dossier. Il est borné, déterministe et fingerprinté pour
qu'une réponse puisse être rejouée et comparée.

Classement (CTX-003)
--------------------
Chaque fait reçoit un score combinant :

* ``pertinence`` : phrase exacte ou couverture lexicale de la question. Aucun provider
  d'embeddings n'étant disponible, la pertinence sémantique n'est pas inventée : elle reste
  approximée par le lexical et cette limite est déclarée par :class:`ContextePack`.
* ``proximite`` : score optionnel issu du graphe (distance en sauts convertie en ``1/(1+d)``),
  fourni via ``proximite`` ou déduit des identifiants liés au fait et des entités résolues.
* ``confiance`` : confiance portée par la proposition.
* ``fraicheur`` : récence relative au fait le plus récent du dossier.
* ``autorite`` : autorité de la source/spécialiste, ou ``autorite`` explicite.

Le budget (CTX-004) combine les compteurs faits/preuves/entités avec un budget de tokens
estimés (``ceil(nombre de caractères / 4)``, volontairement simple et déterministe). Les
troncatures sont toujours écrites dans ``limites``. Les inconnues, contradictions et preuves
périmées sont conservées explicitement (CTX-009), et un pack vide ou partiel porte
``completude`` ainsi qu'une limite explicite (CTX-011).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import hashlib
import json
import math
import re
import unicodedata
from collections.abc import Mapping
from typing import Any

__all__ = ["ContextePack", "construire", "estimer_tokens"]

_MAX_TEXTE = 500
_DEFAUT_TOKENS = 4000
_MAX_TOKENS = 200000
_CARACTERES_PAR_TOKEN = 4
_RE_SECRET = re.compile(
    r"(?i)(?:api[_-]?key|apikey|access[_-]?token|auth[_-]?token|client[_-]?secret|"
    r"password|passwd|secret|token)\s*[:=]\s*['\"]?[A-Za-z0-9_./+~-]{6,}"
)

_POIDS = {
    "pertinence": 2.5,
    "proximite": 2.0,
    "confiance": 1.0,
    "fraicheur": 0.5,
    "autorite": 0.8,
}
_AUTORITE_SOURCES = {
    "claim": 1.0,
    "preuve": 0.85,
    "evidence": 0.85,
    "source": 0.8,
    "impact": 0.8,
    "risque": 0.75,
    "outcome": 0.7,
    "limite": 0.6,
    "contradiction": 0.55,
    "hypothese": 0.4,
    "question": 0.3,
    "inconnue": 0.3,
}
_TYPES_PARTIELS = {"PARTIEL", "INCOMPLET", "VIDE"}
_CHAMPS_DATE = (
    "observe_le", "maj_le", "cree_le", "date", "valide_depuis", "enregistre_le",
    "expire_le",
)
_CHAMPS_LIES = (
    "twin_id", "twin_ids", "application_id", "application_ids", "situation_id",
    "situation_ids", "entity_id", "entite_id", "source", "cible", "work_id",
)


def estimer_tokens(valeur: Any) -> int:
    """Estime un nombre de tokens sans tokenizer : ``ceil(caractères / 4)``.

    L'estimation est volontairement grossière, stable et sans dépendance réseau. Elle sert de
    garde-fou de budget, pas de mesure facturée.
    """
    texte = " ".join(str(valeur or "").split())
    if not texte:
        return 0
    return max(1, math.ceil(len(texte) / _CARACTERES_PAR_TOKEN))


def _texte(valeur, maximum=_MAX_TEXTE) -> str:
    texte = " ".join(str(valeur or "").split())[:maximum]
    return _RE_SECRET.sub("***", texte)


def _normaliser(valeur: Any) -> str:
    texte = unicodedata.normalize("NFKD", str(valeur or ""))
    texte = "".join(caractere for caractere in texte if not unicodedata.combining(caractere)).lower()
    texte = "".join(caractere if caractere.isalnum() else " " for caractere in texte)
    return " ".join(texte.split())


def _liste(valeur) -> list:
    if valeur is None:
        return []
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return list(valeur)
    return [valeur]


def _ids(valeurs) -> tuple[str, ...]:
    resultat = []
    for valeur in _liste(valeurs):
        if isinstance(valeur, Mapping):
            valeur = valeur.get("id")
        texte = _texte(valeur, 160)
        if texte and texte not in resultat:
            resultat.append(texte)
    return tuple(resultat)


def _nombre(valeur: Any, defaut: float = 0.0) -> float:
    if isinstance(valeur, bool):
        return defaut
    try:
        nombre = float(valeur)
    except (TypeError, ValueError):
        return defaut
    return nombre if math.isfinite(nombre) else defaut


def _borne(valeur: float) -> float:
    return max(0.0, min(valeur, 1.0))


def _instant(valeur: Any) -> float:
    if isinstance(valeur, datetime):
        instant = valeur
    elif isinstance(valeur, date):
        instant = datetime(valeur.year, valeur.month, valeur.day, tzinfo=timezone.utc)
    elif isinstance(valeur, str) and valeur.strip():
        try:
            instant = datetime.fromisoformat(valeur.strip().replace("Z", "+00:00"))
        except ValueError:
            return 0.0
    else:
        return 0.0
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.timestamp()


def _date_fait(fait: Mapping) -> float:
    valeurs = []
    for conteneur in (fait, fait.get("donnees")):
        if not isinstance(conteneur, Mapping):
            continue
        for champ in _CHAMPS_DATE:
            instant = _instant(conteneur.get(champ))
            if instant:
                valeurs.append(instant)
    return max(valeurs, default=0.0)


def _ids_lies(fait: Mapping) -> tuple[str, ...]:
    valeurs = []
    for conteneur in (fait, fait.get("donnees")):
        if not isinstance(conteneur, Mapping):
            continue
        for champ in _CHAMPS_LIES:
            for valeur in _liste(conteneur.get(champ)):
                if isinstance(valeur, Mapping):
                    valeur = valeur.get("id")
                if valeur not in (None, ""):
                    valeurs.append(valeur)
    return _ids(valeurs)


def _score_proximite(valeur: Any) -> float | None:
    """Normalise une proximité : ``[0, 1]`` est un score, ``> 1`` une distance en sauts."""
    if isinstance(valeur, Mapping):
        for cle in ("score", "proximite", "proximity", "proximity_score"):
            if cle in valeur:
                return _score_proximite(valeur[cle])
        for cle in ("distance", "distance_graphe", "graph_distance", "sauts"):
            if cle in valeur:
                distance = _nombre(valeur[cle], -1.0)
                return None if distance < 0 else 1.0 / (1.0 + distance)
        return None
    nombre = _nombre(valeur, -1.0)
    if nombre < 0:
        return None
    if nombre <= 1.0:
        return _borne(nombre)
    return 1.0 / (1.0 + nombre)


def _proximite_fait(
    fait: Mapping, entites: set[str], proximite: Mapping | None,
) -> float:
    for conteneur in (fait, fait.get("donnees")):
        if not isinstance(conteneur, Mapping):
            continue
        for cle in ("proximite", "proximity", "proximity_score"):
            if cle in conteneur:
                score = _score_proximite(conteneur[cle])
                if score is not None:
                    return score
        for cle in ("distance_graphe", "graph_distance"):
            if cle in conteneur:
                distance = _nombre(conteneur[cle], -1.0)
                if distance >= 0:
                    return 1.0 / (1.0 + distance)
    lies = set(_ids_lies(fait))
    if proximite:
        for identifiant in sorted(lies):
            if identifiant in proximite:
                score = _score_proximite(proximite[identifiant])
                if score is not None:
                    return score
    return 1.0 if lies & entites else 0.0


def _autorite_fait(fait: Mapping) -> float:
    for conteneur in (fait, fait.get("donnees")):
        if not isinstance(conteneur, Mapping) or "autorite" not in conteneur:
            continue
        valeur = _nombre(conteneur.get("autorite"), -1.0)
        if valeur >= 0:
            return _borne(valeur)
    for champ in ("source", "specialiste", "type"):
        valeur = _normaliser(fait.get(champ))
        if valeur in _AUTORITE_SOURCES:
            return _AUTORITE_SOURCES[valeur]
    return 0.5


def _est_perime(fait: Mapping) -> bool:
    donnees = fait.get("donnees")
    donnees = donnees if isinstance(donnees, Mapping) else {}
    for conteneur in (fait, donnees):
        for cle in ("perime", "perimee", "expire", "est_perime"):
            if conteneur.get(cle) is True:
                return True
        expiration = _instant(conteneur.get("expire_le"))
        if expiration and expiration <= datetime.now(timezone.utc).timestamp():
            return True
    return _texte(fait.get("type"), 40).upper() in {"PREUVE_PERIMEE", "PERIME", "EXPIRE"}


def _faits(
    dossier: Mapping, *, question: str = "", entites: tuple[str, ...] = (),
    proximite: Mapping | None = None,
) -> list[dict]:
    bruts = []
    for fait in dossier.get("propositions") or ():
        if not isinstance(fait, Mapping):
            continue
        donnees = fait.get("donnees")
        donnees = donnees if isinstance(donnees, Mapping) else {}
        bruts.append({
            "id": _texte(fait.get("id") or fait.get("claim_id") or fait.get("fact_id"), 160),
            "specialiste": _texte(fait.get("specialiste"), 80),
            "type": _texte(fait.get("type"), 40).upper(),
            "titre": _texte(fait.get("titre"), 240),
            "resume": _texte(fait.get("resume"), 1000),
            "preuves": list(_ids(fait.get("preuves"))),
            "confiance": _borne(_nombre(fait.get("confiance"), 0.0)),
            "autorite": _autorite_fait(fait),
            "donnees": dict(donnees),
            "perime": _est_perime(fait),
            "_instant": _date_fait(fait),
        })
    maximum = max((brut["_instant"] for brut in bruts), default=0.0)
    tokens_question = {
        token for token in _normaliser(question).split() if len(token) > 2
    } or set(_normaliser(question).split())
    question_normalisee = _normaliser(question)
    entites_lies = set(entites)
    for brut in bruts:
        texte = _normaliser(" ".join((
            brut["titre"], brut["resume"], brut["specialiste"], brut["type"],
            json.dumps(brut["donnees"], ensure_ascii=False, sort_keys=True, default=str),
        )))
        couverts = len(tokens_question & set(texte.split())) if tokens_question else 0
        couverture = couverts / len(tokens_question) if tokens_question else 0.0
        phrase = bool(question_normalisee) and question_normalisee in texte
        pertinence = 1.0 if phrase else _borne(couverture)
        proximite_fait = _proximite_fait(brut, entites_lies, proximite)
        fraicheur = (brut["_instant"] / maximum) if maximum else 0.0
        brut["pertinence"] = round(pertinence, 6)
        brut["proximite"] = round(proximite_fait, 6)
        brut["fraicheur"] = round(_borne(fraicheur), 6)
        brut["score"] = round(
            _POIDS["pertinence"] * pertinence
            + _POIDS["proximite"] * proximite_fait
            + _POIDS["confiance"] * brut["confiance"]
            + _POIDS["fraicheur"] * _borne(fraicheur)
            + _POIDS["autorite"] * brut["autorite"],
            6,
        )
        brut.pop("_instant", None)
    return bruts


def _identites_fait(fait: Mapping) -> list[tuple]:
    identites: list[tuple] = []
    identifiant = _texte(fait.get("id"), 160)
    if identifiant:
        identites.append(("id", identifiant))
    contenu = (
        _normaliser(fait.get("type")), _normaliser(fait.get("titre")),
        _normaliser(fait.get("resume")),
    )
    if any(contenu):
        identites.append(("contenu", *contenu))
    preuves = tuple(sorted(
        _normaliser(preuve) for preuve in _liste(fait.get("preuves")) if _normaliser(preuve)
    ))
    if preuves:
        identites.append(("preuves", _normaliser(fait.get("type")), preuves))
    return identites or [("objet", id(fait))]


def _meilleur_fait(gauche: Mapping, droite: Mapping) -> bool:
    return (
        _nombre(gauche.get("score")), _nombre(gauche.get("confiance")),
        len(_texte(gauche.get("resume"))),
    ) > (
        _nombre(droite.get("score")), _nombre(droite.get("confiance")),
        len(_texte(droite.get("resume"))),
    )


def _dedupliquer_faits(faits: list[dict]) -> list[dict]:
    """Fusionne les faits de même id, contenu normalisé ou même preuve."""
    if len(faits) < 2:
        return list(faits)
    parents = list(range(len(faits)))

    def trouver(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def unir(gauche: int, droite: int) -> None:
        racine_gauche, racine_droite = trouver(gauche), trouver(droite)
        if racine_gauche != racine_droite:
            parents[racine_droite] = racine_gauche

    vus: dict[tuple, int] = {}
    for index, fait in enumerate(faits):
        for identite in _identites_fait(fait):
            precedent = vus.setdefault(identite, index)
            if precedent != index:
                unir(index, precedent)
    groupes: dict[int, dict] = {}
    for index, fait in enumerate(faits):
        racine = trouver(index)
        actuel = groupes.get(racine)
        if actuel is None or _meilleur_fait(fait, actuel):
            groupes[racine] = fait
    return list(groupes.values())


def _inconnues(dossier: Mapping, faits: list[Mapping]) -> tuple[str, ...]:
    valeurs = list(_listes_textes(dossier.get("inconnues")))
    valeurs.extend(
        _texte(fait.get("titre"), 240) or _texte(fait.get("resume"), 500)
        for fait in faits
        if _texte(fait.get("type"), 40).upper() in {"QUESTION", "HYPOTHESE", "INCONNUE", "UNKNOWN"}
    )
    resultat: list[str] = []
    for valeur in valeurs:
        if valeur and valeur not in resultat:
            resultat.append(valeur)
    return tuple(resultat)


def _listes_textes(valeur: Any) -> tuple[str, ...]:
    resultat: list[str] = []
    for element in _liste(valeur):
        if isinstance(element, Mapping):
            element = (
                element.get("titre") or element.get("resume") or element.get("contenu")
                or element.get("description") or element.get("id")
            )
        texte = _texte(element, 500)
        if texte and texte not in resultat:
            resultat.append(texte)
    return tuple(resultat)


def _contradictions(dossier: Mapping, faits: list[Mapping]) -> tuple[str, ...]:
    valeurs = list(_listes_textes(dossier.get("contradictions")))
    valeurs.extend(_listes_textes(dossier.get("conflits")))
    for fait in faits:
        donnees = fait.get("donnees")
        donnees = donnees if isinstance(donnees, Mapping) else {}
        if (
            _texte(fait.get("type"), 40).upper() in {"CONTRADICTION", "CONFLIT"}
            or donnees.get("contradiction") is True
        ):
            valeurs.extend(_listes_textes((
                _texte(fait.get("titre"), 240) or _texte(fait.get("resume"), 500)
            )))
    resultat: list[str] = []
    for valeur in valeurs:
        if valeur and valeur not in resultat:
            resultat.append(valeur)
    return tuple(resultat)


def _preuves_perimees(dossier: Mapping, faits: list[Mapping]) -> tuple[str, ...]:
    valeurs = list(_listes_textes(dossier.get("preuves_perimees")))
    valeurs.extend(_listes_textes(dossier.get("preuves_expirees")))
    for fait in faits:
        if not _est_perime(fait):
            continue
        preuves = _ids(fait.get("preuves"))
        valeurs.extend(preuves or _listes_textes(
            _texte(fait.get("titre"), 240) or _texte(fait.get("resume"), 500)))
    resultat: list[str] = []
    for valeur in valeurs:
        if valeur not in resultat:
            resultat.append(valeur)
    return tuple(resultat)


def _entites(dossier: Mapping, faits: list[Mapping], supplement: tuple[str, ...]) -> tuple[str, ...]:
    valeurs: list[Any] = list(supplement)
    for fait in faits:
        if isinstance(fait.get("donnees"), Mapping):
            for cle in ("twin_id", "application_id", "situation_id", "source", "cible"):
                valeur = fait["donnees"].get(cle)
                if valeur:
                    valeurs.append(valeur)
    return _ids(valeurs)


def _fingerprint(
    tenant: str, question: str, profil_id: str, faits, preuves, *,
    entites=(), inconnues=(), contradictions=(), preuves_perimees=(), completude="",
) -> str:
    charge = json.dumps(
        {"tenant": tenant, "question": question, "profil": profil_id,
         "faits": [
             (f["type"], f["titre"], f["resume"], f["confiance"],
              round(_nombre(f.get("score")), 6), round(_nombre(f.get("proximite")), 6))
             for f in faits
         ],
         "preuves": list(preuves), "entites": list(entites), "inconnues": list(inconnues),
         "contradictions": list(contradictions), "preuves_perimees": list(preuves_perimees),
         "completude": completude},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(charge.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ContextePack:
    tenant: str
    question: str
    profil_id: str
    autorite: str
    entites: tuple[str, ...] = ()
    faits: tuple[dict, ...] = ()
    preuves: tuple[str, ...] = ()
    contraintes: tuple[str, ...] = ()
    inconnues: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = ()
    preuves_perimees: tuple[str, ...] = ()
    completude: str = "complet"
    fingerprint: str = ""
    budget: dict = field(default_factory=dict)
    limites: tuple[str, ...] = ()

    @property
    def partiel(self) -> bool:
        """Vrai si le pack est vide ou déclaré partiel."""
        return self.completude != "complet"

    def as_dict(self) -> dict:
        return {
            "tenant": self.tenant,
            "question": self.question,
            "profil_id": self.profil_id,
            "autorite": self.autorite,
            "entites": list(self.entites),
            "faits": [dict(fait) for fait in self.faits],
            "preuves": list(self.preuves),
            "contraintes": list(self.contraintes),
            "inconnues": list(self.inconnues),
            "contradictions": list(self.contradictions),
            "preuves_perimees": list(self.preuves_perimees),
            "completude": self.completude,
            "fingerprint": self.fingerprint,
            "budget": dict(self.budget),
            "limites": list(self.limites),
        }


def _cout_fait(fait: Mapping) -> int:
    return (
        estimer_tokens(fait.get("specialiste")) + estimer_tokens(fait.get("type"))
        + estimer_tokens(fait.get("titre")) + estimer_tokens(fait.get("resume"))
        + sum(estimer_tokens(preuve) for preuve in _liste(fait.get("preuves")))
    )


def construire(question: str, profil: Any, dossier: Mapping, *,
               max_faits: int = 12, max_preuves: int = 20,
               max_entites: int = 20, max_tokens: int = _DEFAUT_TOKENS,
               entites: Any = (), proximite: Mapping | None = None) -> ContextePack:
    """Sélectionne et borne le contexte ; lève sur un dossier non mapping.

    ``proximite`` accepte un mapping ``identifiant -> score`` (``[0, 1]``) ou distance en
    sauts (``> 1``, convertie en ``1/(1+d)``). Sans provider sémantique ni mapping de graphe,
    la proximité se limite aux entités résolues et la pertinence reste lexicale : ces limites
    sont explicites dans ``limites``.
    """
    if not isinstance(dossier, Mapping):
        raise TypeError("dossier : objet attendu")
    if proximite is not None and not isinstance(proximite, Mapping):
        raise ValueError("proximite : mapping identifiant -> score attendu")
    try:
        budget_faits = max(1, min(int(max_faits), 100))
        budget_preuves = max(1, min(int(max_preuves), 200))
        budget_entites = max(1, min(int(max_entites), 200))
        budget_tokens = max(1, min(int(max_tokens), _MAX_TOKENS))
    except (TypeError, ValueError) as exc:
        raise ValueError("budgets de contexte invalides") from exc
    question_texte = _texte(question, 4000)
    entites_resolues = _ids([
        *_liste(entites), *_liste(dossier.get("entites")),
        *_liste(dossier.get("twin_ids")), *_liste(dossier.get("situation_id")),
    ])
    faits_bruts = _faits(
        dossier, question=question_texte, entites=entites_resolues, proximite=proximite)
    faits_tries = sorted(
        _dedupliquer_faits(faits_bruts),
        key=lambda fait: (-_nombre(fait.get("score")), -_nombre(fait.get("confiance")),
                          fait["type"], fait["titre"], fait["resume"]))
    contraintes = tuple(_texte(valeur, 500) for valeur in _liste(dossier.get("limites"))
                        if _texte(valeur, 500))
    inconnues = _inconnues(dossier, faits_tries)
    contradictions = _contradictions(dossier, faits_tries)
    preuves_perimees = _preuves_perimees(dossier, faits_tries)
    profil_id = _texte(getattr(profil, "id", ""), 80) or "generaliste"
    autorite = _texte(getattr(profil, "autorite", "lecture"), 20) or "lecture"
    tenant = _texte(dossier.get("tenant"), 128) or "local"

    limites: list[str] = []
    tokens_utilises = estimer_tokens(question_texte)
    for valeur in (*inconnues, *contradictions, *preuves_perimees):
        tokens_utilises += estimer_tokens(valeur)
    tokens_utilises += sum(estimer_tokens(valeur) for valeur in contraintes)

    faits: list[dict] = []
    tronque_compteur = tronque_tokens = False
    for fait in faits_tries:
        if len(faits) >= budget_faits:
            tronque_compteur = True
            break
        cout = _cout_fait(fait)
        if tokens_utilises + cout > budget_tokens:
            tronque_tokens = True
            continue
        faits.append(fait)
        tokens_utilises += cout
    if tronque_compteur:
        limites.append(f"faits tronqués à {budget_faits}")
    if tronque_tokens:
        limites.append(f"faits tronqués au budget de {budget_tokens} tokens estimés")

    toutes_preuves = _ids([preuve for fait in faits_tries for preuve in fait["preuves"]])
    preuves: list[str] = []
    for preuve in toutes_preuves:
        if len(preuves) >= budget_preuves:
            limites.append(f"preuves tronquées à {budget_preuves}")
            break
        cout = estimer_tokens(preuve)
        if tokens_utilises + cout > budget_tokens:
            if not any("preuves tronquées au budget" in limite for limite in limites):
                limites.append(f"preuves tronquées au budget de {budget_tokens} tokens estimés")
            continue
        preuves.append(preuve)
        tokens_utilises += cout

    entites_candidates = _entites(dossier, faits, entites_resolues)
    entites_pack: list[str] = []
    for entite in entites_candidates:
        if len(entites_pack) >= budget_entites:
            limites.append(f"entités tronquées à {budget_entites}")
            break
        cout = estimer_tokens(entite)
        if tokens_utilises + cout > budget_tokens:
            if not any("entités tronquées au budget" in limite for limite in limites):
                limites.append(f"entités tronquées au budget de {budget_tokens} tokens estimés")
            continue
        entites_pack.append(entite)
        tokens_utilises += cout

    if not faits:
        limites.append("aucun fait disponible : contexte borné et vide")
        limites.append("aucune conclusion certaine possible sans fait")
    elif not preuves:
        limites.append("aucune preuve sélectionnée : aucune conclusion certaine possible")
    statut_dossier = str(dossier.get("statut") or "").upper()
    if contraintes:
        limites.append("contexte partiel : " + " ; ".join(contraintes))
    elif statut_dossier in _TYPES_PARTIELS:
        limites.append("contexte partiel déclaré par le dossier")
    if tokens_utilises > budget_tokens:
        limites.append(
            f"budget de {budget_tokens} tokens estimés dépassé par les signaux obligatoires "
            "(inconnues, contradictions, preuves périmées)")
    if not faits:
        completude = "vide"
    elif limites or contraintes or statut_dossier in _TYPES_PARTIELS:
        completude = "partiel"
    else:
        completude = "complet"

    if proximite is None and not faits and not entites_resolues:
        limites.append("pertinence lexicale seule : aucun provider sémantique ni graphe fourni")
    elif not any(fait.get("proximite") for fait in faits):
        limites.append("proximité graphe absente : classement lexical, confiance et fraîcheur")

    return ContextePack(
        tenant=tenant,
        question=question_texte,
        profil_id=profil_id,
        autorite=autorite,
        entites=entites_pack,
        faits=tuple(faits),
        preuves=tuple(preuves),
        contraintes=contraintes,
        inconnues=inconnues,
        contradictions=contradictions,
        preuves_perimees=preuves_perimees,
        completude=completude,
        fingerprint=_fingerprint(
            tenant, question_texte, profil_id, faits, preuves, entites=entites_pack,
            inconnues=inconnues, contradictions=contradictions,
            preuves_perimees=preuves_perimees, completude=completude),
        budget={
            "faits": budget_faits, "preuves": budget_preuves,
            "entites": budget_entites, "tokens": budget_tokens,
            "tokens_utilises": tokens_utilises,
        },
        limites=tuple(limites),
    )
