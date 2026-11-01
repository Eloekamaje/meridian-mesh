"""Attention déterministe : classer des situations ou objets canoniques sans modèle ni LLM.

Le module ne lit ni base ni réseau et ne modifie jamais les objets reçus. Il produit un score
explicable de 0 à 100 dont chaque point est justifié par une composante nommée :

- priorité métier (HAUTE / MOYENNE / BASSE) ;
- confiance déclarée ;
- récence de l'observation ;
- impact, contradictions, nouveauté et décisions non tranchées lorsqu'ils sont présents.

La déduplication repose sur une empreinte stable : type + jumeaux liés + titre/résumé normalisés.
Le titre et le résumé ne sortent jamais en clair de l'empreinte, qui n'est qu'un condensat SHA-256.
Le tenant n'est jamais interprété ici : l'appelant fournit des objets déjà bornés à son périmètre.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime, timezone
import hashlib
import json
import re
import unicodedata
from typing import Any

__all__ = ["signature", "score", "classer", "selectionner", "resume_attention"]

_POIDS_PRIORITE = {"HAUTE": 40, "MOYENNE": 25, "BASSE": 10}
_POIDS_CONFIANCE = 20
_POIDS_RECENCE = 20
_POIDS_IMPACT = 8
_POIDS_CONTRADICTIONS = 6
_POIDS_NOUVEAUTE = 3
_POIDS_DECISIONS = 3

_PRIORITES = {
    "HAUTE": "HAUTE", "HAUT": "HAUTE", "HIGH": "HAUTE", "URGENTE": "HAUTE", "URGENT": "HAUTE",
    "CRITIQUE": "HAUTE", "CRITICAL": "HAUTE",
    "MOYENNE": "MOYENNE", "MOYEN": "MOYENNE", "NORMALE": "MOYENNE", "NORMAL": "MOYENNE",
    "MEDIUM": "MOYENNE", "MEDIANE": "MOYENNE",
    "BASSE": "BASSE", "BAS": "BASSE", "LOW": "BASSE", "FAIBLE": "BASSE", "MINEURE": "BASSE",
}

_STATUTS_TRANCHES = {
    "DECIDED", "DECIDE", "TRANCHE", "TRANCHEE", "CLOSED", "CLOSE", "RESOLU", "RESOLUE",
    "RESOLVED", "DONE", "TERMINE", "TERMINEE",
}
_STATUTS_NON_TRANCHES = {
    "PROPOSED", "PROPOSE", "PROPOSEE", "OPEN", "OUVERT", "OUVERTE", "PENDING", "EN_ATTENTE",
    "A_TRANCHER", "A_DECIDER", "CANDIDATE", "CANDIDAT",
}

_CHAMPS_TITRE = ("titre", "nom", "label", "title", "name")
_CHAMPS_RESUME = ("resume", "résumé", "description", "summary")
_CHAMPS_JUMEAUX = ("twin_ids", "jumeaux", "twins", "twin_id", "twin")
_CHAMPS_ACTEUR = ("acteur", "acteurs", "acteure", "profil", "profils")
_CHAMPS_DOMAINE = ("domaine", "domaines", "domain", "domains")

_VIDES = {"", "0", "NON", "NO", "FALSE", "FAUX", "NONE", "NULL", "NUL"}


def _texte(valeur: Any) -> str:
    if valeur is None or isinstance(valeur, (bytes, bytearray, Mapping)):
        return ""
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return ""
    return str(valeur).strip()


def _nom(valeur: Any) -> str:
    """Normalise un libellé : sans accents, minuscules, séparateurs ramenés à l'espace."""
    texte = unicodedata.normalize("NFKD", _texte(valeur))
    texte = "".join(c for c in texte if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", texte).strip()


def _valeur(objet: Any, *noms: str, defaut: Any = None) -> Any:
    """Lit un champ sur un mapping, un objet ou son bloc ``donnees``, sans effet de bord."""
    if objet is None:
        return defaut
    for nom in noms:
        if isinstance(objet, Mapping):
            if nom in objet and objet[nom] is not None:
                return objet[nom]
        else:
            valeur = getattr(objet, nom, None)
            if valeur is not None:
                return valeur
    donnees = objet.get("donnees") if isinstance(objet, Mapping) else None
    if isinstance(donnees, Mapping):
        for nom in noms:
            if nom in donnees and donnees[nom] is not None:
                return donnees[nom]
    return defaut


def _identifiant(objet: Any) -> str:
    return _texte(_valeur(objet, "id", "identifiant", "identifier", defaut=""))


def _type(objet: Any) -> str:
    texte = _texte(_valeur(objet, "type", "type_", "type_objet", defaut=""))
    return texte.upper() or "OBJET"


def _identifiants(valeur: Any) -> list[str]:
    if valeur is None:
        return []
    if isinstance(valeur, Mapping):
        valeur = valeur.get("id")
        elements = [valeur] if valeur is not None else []
    elif isinstance(valeur, (str, bytes, bytearray)):
        elements = [valeur]
    else:
        try:
            elements = list(valeur)
        except TypeError:
            elements = [valeur]
    resultat: list[str] = []
    for element in elements:
        if isinstance(element, Mapping):
            element = element.get("id")
        texte = _texte(element)
        if texte and texte not in resultat:
            resultat.append(texte)
    return resultat


def _elements(valeur: Any) -> list[Any]:
    if valeur is None:
        return []
    if isinstance(valeur, Mapping):
        return [valeur]
    if isinstance(valeur, (str, bytes, bytearray)):
        return [valeur]
    try:
        return list(valeur)
    except TypeError:
        return [valeur]


def _quantite(valeur: Any) -> float:
    if valeur is None:
        return 0.0
    if isinstance(valeur, bool):
        return 1.0 if valeur else 0.0
    if isinstance(valeur, (int, float)):
        return max(0.0, float(valeur))
    if isinstance(valeur, Mapping):
        for cle in ("nombre", "count", "total", "nb"):
            if cle in valeur:
                return _quantite(valeur[cle])
        return float(len(valeur))
    if isinstance(valeur, (str, bytes, bytearray)):
        return 1.0 if _texte(valeur) else 0.0
    try:
        return float(len(valeur))
    except TypeError:
        return 1.0


def _verite(valeur: Any) -> bool:
    if valeur is None:
        return False
    if isinstance(valeur, bool):
        return valeur
    if isinstance(valeur, (int, float)):
        return valeur > 0
    if isinstance(valeur, Mapping):
        return bool(valeur)
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return bool(valeur)
    return _nom(valeur).upper() not in _VIDES


def signature(objet: Any) -> str:
    """Empreinte stable de déduplication : type, jumeaux liés et titre/résumé normalisés.

    Le résultat est un condensat SHA-256 préfixé par le type. Aucun titre, résumé ou secret
    n'est recopié en clair. L'ordre des jumeaux liés n'influence pas l'empreinte.
    """
    type_ = _type(objet)
    jumeaux = sorted({j for nom in _CHAMPS_JUMEAUX for j in _identifiants(_valeur(objet, nom))})
    titre = _nom(_valeur(objet, *_CHAMPS_TITRE, defaut=""))
    resume = _nom(_valeur(objet, *_CHAMPS_RESUME, defaut=""))
    charge = json.dumps(
        {"type": type_, "jumeaux": jumeaux, "titre": titre, "resume": resume},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return f"{type_}:{hashlib.sha256(charge.encode('utf-8')).hexdigest()}"


def _priorite(objet: Any) -> str:
    brut = _valeur(objet, "priorite", "priorité", "priority", "urgence", "severity", "gravite")
    if isinstance(brut, bool):
        return "MOYENNE"
    if isinstance(brut, (int, float)):
        if brut >= 3:
            return "HAUTE"
        if brut >= 2:
            return "MOYENNE"
        return "BASSE"
    texte = _nom(brut).upper()
    return _PRIORITES.get(texte, "MOYENNE")


def _confiance(objet: Any) -> float:
    for nom in ("confiance", "confidence", "score_confiance"):
        valeur = _valeur(objet, nom)
        if valeur is None or isinstance(valeur, bool):
            continue
        try:
            nombre = float(valeur)
        except (TypeError, ValueError):
            continue
        return max(0.0, min(1.0, nombre))
    return 0.5


def _en_datetime(valeur: Any) -> datetime | None:
    if isinstance(valeur, datetime):
        instant = valeur
    elif isinstance(valeur, date):
        instant = datetime(valeur.year, valeur.month, valeur.day, tzinfo=timezone.utc)
    elif isinstance(valeur, str):
        texte = valeur.strip()
        if not texte:
            return None
        try:
            instant = datetime.fromisoformat(texte.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(timezone.utc)


def _maintenant(valeur: Any = None) -> datetime:
    return _en_datetime(valeur) or datetime.now(timezone.utc)


def _date_observation(objet: Any) -> datetime | None:
    for nom in ("observe_le", "observed_at", "valide_depuis", "valid_from", "maj_le",
                "updated_at", "cree_le", "created_at"):
        instant = _en_datetime(_valeur(objet, nom))
        if instant is not None:
            return instant
    return None


def _points_recence(objet: Any, maintenant: datetime) -> int:
    instant = _date_observation(objet)
    if instant is None:
        return 0
    age_jours = (maintenant - instant).total_seconds() / 86400.0
    if age_jours < 0:
        age_jours = 0.0
    if age_jours <= 1:
        return _POIDS_RECENCE
    if age_jours <= 7:
        return 16
    if age_jours <= 30:
        return 12
    if age_jours <= 90:
        return 6
    if age_jours <= 365:
        return 2
    return 0


def _points_impact(objet: Any) -> int:
    return min(_POIDS_IMPACT, int(round(2 * _quantite(
        _valeur(objet, "impact", "impacts", "impact_ids", "nb_impacts", "nombre_impacts")
    ))))


def _points_contradictions(objet: Any) -> int:
    return min(_POIDS_CONTRADICTIONS, int(round(2 * _quantite(
        _valeur(objet, "contradictions", "contradiction_ids", "nb_contradictions")
    ))))


def _points_nouveaute(objet: Any) -> int:
    return _POIDS_NOUVEAUTE if _verite(
        _valeur(objet, "nouveaute", "nouveauté", "novelty", "nouveau", "nouvelle", "est_nouveau",
                "is_new")
    ) else 0


def _decisions_non_tranchees(objet: Any) -> int:
    quantite = _quantite(_valeur(
        objet, "decisions_non_tranchees", "decisions_ouvertes", "nb_decisions_non_tranchees"
    ))
    for element in _elements(_valeur(objet, "decisions")):
        statut = _nom(_valeur(element, "statut", "status")).upper()
        if not statut or statut in _STATUTS_NON_TRANCHES:
            quantite += 1
    if _type(objet) == "DECISION":
        statut = _nom(_valeur(objet, "statut", "status")).upper()
        if statut not in _STATUTS_TRANCHES:
            quantite += 1
    return min(_POIDS_DECISIONS, int(quantite))


def _raison(libelle: str, points: int) -> str:
    return f"{libelle} (+{points})"


def score(objet: Any, *, maintenant: Any = None) -> dict:
    """Score explicable de 0 à 100 ; chaque composante est un entier et la somme vaut le score."""
    instant = _maintenant(maintenant)
    priorite = _priorite(objet)
    confiance = _confiance(objet)
    composantes = {
        "priorite": _POIDS_PRIORITE[priorite],
        "confiance": int(round(_POIDS_CONFIANCE * confiance)),
        "recence": _points_recence(objet, instant),
        "impact": _points_impact(objet),
        "contradictions": _points_contradictions(objet),
        "nouveaute": _points_nouveaute(objet),
        "decisions_non_tranchees": _decisions_non_tranchees(objet),
    }
    raisons = [
        _raison(f"priorité {priorite}", composantes["priorite"]),
        _raison(f"confiance {confiance:.2f}", composantes["confiance"]),
        _raison("récence", composantes["recence"]),
        _raison("impact", composantes["impact"]),
        _raison("contradictions", composantes["contradictions"]),
        _raison("nouveauté", composantes["nouveaute"]),
        _raison("décisions non tranchées", composantes["decisions_non_tranchees"]),
    ]
    raisons = [raison for raison in raisons if not raison.endswith("(+0)")]
    total = max(0, min(100, sum(composantes.values())))
    return {
        "score": total,
        "priorite": priorite,
        "confiance": confiance,
        "composantes": composantes,
        "components": composantes,
        "raisons": raisons,
    }


def _limite(valeur: Any) -> int:
    try:
        nombre = int(valeur)
    except (TypeError, ValueError):
        return 0
    return max(0, nombre)


def _candidat(objet: Any, evaluation: dict, empreinte: str) -> dict:
    identifiant = _identifiant(objet)
    return {
        "id": identifiant,
        "original_id": identifiant,
        "signature": empreinte,
        "type": _type(objet),
        "titre": _texte(_valeur(objet, *_CHAMPS_TITRE, defaut="")),
        "resume": _texte(_valeur(objet, *_CHAMPS_RESUME, defaut="")),
        "priorite": evaluation["priorite"],
        "score": evaluation["score"],
        "raisons": evaluation["raisons"],
        "composantes": evaluation["composantes"],
        "objet": objet,
    }


def classer(objets: Iterable[Any], *, limite: int = 50, maintenant: Any = None) -> list[dict]:
    """Déduplique par signature, classe par score décroissant puis identifiant, et borne le résultat.

    Pour deux objets de même signature, le représentant retenu est celui qui a le meilleur score,
    puis le plus petit identifiant. Les objets d'entrée ne sont jamais modifiés.
    """
    instant = _maintenant(maintenant)
    meilleurs: dict[str, dict] = {}
    for objet in objets or ():
        empreinte = signature(objet)
        candidat = _candidat(objet, score(objet, maintenant=instant), empreinte)
        precedent = meilleurs.get(empreinte)
        if precedent is None or (-candidat["score"], candidat["id"]) < (
            -precedent["score"], precedent["id"]
        ):
            meilleurs[empreinte] = candidat
    resultat = sorted(meilleurs.values(), key=lambda item: (-item["score"], item["id"]))
    return resultat[: _limite(limite)]


def _valeurs_filtre(objet: Any, noms: tuple[str, ...]) -> set[str] | None:
    brut = _valeur(objet, *noms)
    if brut is None:
        return None
    if isinstance(brut, Mapping):
        elements = list(brut.values())
    elif isinstance(brut, (str, bytes, bytearray)):
        elements = re.split(r"[,;|]", _texte(brut))
    else:
        elements = _elements(brut)
    valeurs: set[str] = set()
    for element in elements:
        if isinstance(element, Mapping):
            element = element.get("id") or element.get("nom") or element.get("name")
        valeur = _nom(element)
        if valeur:
            valeurs.add(valeur)
    return valeurs or None


def _correspond(valeurs: set[str] | None, attendu: Any) -> bool:
    if valeurs is None:
        return True
    cible = _nom(attendu)
    if not cible:
        return True
    return any(cible == valeur or cible in valeur.split() for valeur in valeurs)


def selectionner(objets: Iterable[Any], *, acteur: Any = None, domaine: Any = None,
                 limite: int = 20, maintenant: Any = None) -> list[dict]:
    """Filtre par acteur et domaine seulement quand ces champs existent, puis classe.

    Un objet qui ne porte pas le champ demandé reste éligible : l'absence de métadonnée n'est
    pas une exclusion. Un champ présent mais vide est traité comme absent.
    """
    retenus = []
    for objet in objets or ():
        if not _correspond(_valeurs_filtre(objet, _CHAMPS_ACTEUR), acteur):
            continue
        if not _correspond(_valeurs_filtre(objet, _CHAMPS_DOMAINE), domaine):
            continue
        retenus.append(objet)
    return classer(retenus, limite=limite, maintenant=maintenant)


def resume_attention(objets: Iterable[Any], *, maintenant: Any = None, acteur: Any = None,
                     domaine: Any = None) -> dict:
    """Compte les objets retenus par priorité et par type, après déduplication et filtres."""
    liste = list(objets or ())
    selection = selectionner(
        liste, acteur=acteur, domaine=domaine,
        limite=len(liste) if liste else 0, maintenant=maintenant,
    )
    par_priorite: dict[str, int] = {}
    par_type: dict[str, int] = {}
    for item in selection:
        priorite = item["priorite"]
        type_ = item["type"]
        par_priorite[priorite] = par_priorite.get(priorite, 0) + 1
        par_type[type_] = par_type.get(type_, 0) + 1
    return {
        "total": len(selection),
        "total_brut": len(liste),
        "dedoublonnes": len(liste) - len(selection),
        "par_priorite": par_priorite,
        "par_type": par_type,
    }
