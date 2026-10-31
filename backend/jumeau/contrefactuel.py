"""Comparaison contrefactuelle, pure et sans prétention causale.

Le module n'apprend ni ne simule aucun effet : il applique les valeurs et les
variations explicitement déclarées par chaque option, puis compare les résultats
sur les seuls critères demandés. Une valeur absente reste absente (``None``) :
elle n'est jamais remplacée par zéro. Aucune recommandation n'est produite ;
seule une dominance Pareto, calculée sur des nombres déclarés, est signalée.
Aucun accès réseau, aucune écriture, aucune mutation des entrées.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
import math
from typing import Any

__all__ = ["Option", "Scenario", "comparer", "simuler"]

_ALIAS_ID = ("id", "identifiant")
_ALIAS_LABEL = ("label", "nom", "titre", "libelle")
_ALIAS_VALEURS = ("valeurs", "values", "valeur")
_ALIAS_DELTAS = ("deltas", "delta", "variations", "variation")
_ALIAS_CONDITIONS = (
    "conditions",
    "conditions_de_retournement",
    "conditions_retournement",
    "condition_de_retournement",
    "condition_retournement",
    "condition",
)
_ALIAS_TEXTE_CONDITION = ("texte", "label", "titre", "condition", "resume")
_SPEC_DELTA = ("delta", "variation", "changement", "ajout")
_SPEC_VALEUR = ("valeur", "value", "absolu", "absolue", "cible")


@dataclass(frozen=True)
class Option:
    """Une option déclarée : valeurs absolues, variations et conditions explicites.

    ``valeurs`` porte les valeurs connues, ``deltas`` les variations déclarées
    par l'option, ``conditions`` les seules conditions de retournement admises.
    Les champs absents ne sont pas complétés.
    """

    id: str = ""
    valeurs: Mapping[str, Any] = field(default_factory=dict)
    deltas: Mapping[str, Any] = field(default_factory=dict)
    conditions: tuple[str, ...] = ()
    label: str = ""


Scenario = Option


def _valeur(objet: Any, noms: Iterable[str]) -> Any:
    if objet is None:
        return None
    if isinstance(objet, Mapping):
        for nom in noms:
            if nom in objet and objet[nom] is not None:
                return objet[nom]
        return None
    for nom in noms:
        if hasattr(objet, nom):
            valeur = getattr(objet, nom)
            if valeur is not None:
                return valeur
    return None


def _texte(valeur: Any) -> str:
    if valeur is None or isinstance(valeur, (bool, Mapping, bytes, bytearray)):
        return ""
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return ""
    return str(valeur).strip()


def _nombre(valeur: Any) -> float | None:
    if valeur is None or isinstance(valeur, bool):
        return None
    if not isinstance(valeur, (int, float)):
        return None
    nombre = float(valeur)
    return nombre if math.isfinite(nombre) else None


def _mapping(valeur: Any) -> dict[str, Any]:
    if valeur is None:
        return {}
    if isinstance(valeur, Mapping):
        return dict(valeur)
    if hasattr(valeur, "as_dict") and callable(valeur.as_dict):
        resultat = valeur.as_dict()
        return dict(resultat) if isinstance(resultat, Mapping) else {}
    if hasattr(valeur, "__dict__"):
        return dict(vars(valeur))
    return {}


def _mapping_criteres(valeur: Any) -> dict[str, Any]:
    resultat: dict[str, Any] = {}
    for cle, contenu in _mapping(valeur).items():
        texte = _texte(cle)
        if texte:
            resultat[texte] = contenu
    return resultat


def _conditions(valeur: Any) -> list[str]:
    if valeur is None:
        return []
    if isinstance(valeur, (str, Mapping)):
        elements: list[Any] = [valeur]
    elif isinstance(valeur, Iterable):
        elements = list(valeur)
    else:
        elements = [valeur]
    resultat: list[str] = []
    for element in elements:
        if isinstance(element, Mapping):
            texte = ""
            for nom in _ALIAS_TEXTE_CONDITION:
                texte = _texte(element.get(nom))
                if texte:
                    break
        else:
            texte = _texte(element)
        if texte and texte not in resultat:
            resultat.append(texte)
    return resultat


def _options(options: Any) -> list[dict[str, Any]]:
    if options is None:
        return []
    if isinstance(options, Mapping):
        valeurs: list[Any] = [options]
    elif isinstance(options, (str, bytes, bytearray)):
        raise TypeError("options : liste ou mapping d'options attendu")
    else:
        try:
            valeurs = list(options)
        except TypeError as exc:
            raise TypeError("options : liste ou mapping d'options attendu") from exc
    resultat = []
    for rang, objet in enumerate(valeurs, start=1):
        identifiant = (
            _texte(_valeur(objet, _ALIAS_ID))
            or _texte(_valeur(objet, _ALIAS_LABEL))
            or f"option-{rang}"
        )
        resultat.append({
            "id": identifiant,
            "label": _texte(_valeur(objet, _ALIAS_LABEL)),
            "valeurs": _mapping_criteres(_valeur(objet, _ALIAS_VALEURS)),
            "deltas": _mapping_criteres(_valeur(objet, _ALIAS_DELTAS)),
            "conditions": _conditions(_valeur(objet, _ALIAS_CONDITIONS)),
        })
    return resultat


def _specification(valeur: Any) -> tuple[str, float] | None:
    if isinstance(valeur, Mapping):
        for nom in _SPEC_DELTA:
            if nom in valeur:
                nombre = _nombre(valeur[nom])
                return ("delta", nombre) if nombre is not None else None
        for nom in _SPEC_VALEUR:
            if nom in valeur:
                nombre = _nombre(valeur[nom])
                return ("valeur", nombre) if nombre is not None else None
        return None
    nombre = _nombre(valeur)
    return ("delta", nombre) if nombre is not None else None


def _changements(
    changements: Any, ids: set[str],
) -> tuple[dict[str, tuple[str, float]], dict[str, dict[str, tuple[str, float]]]]:
    if changements is None:
        return {}, {}
    if not isinstance(changements, Mapping):
        if hasattr(changements, "__dict__"):
            changements = vars(changements)
        else:
            raise TypeError("changements : mapping attendu")
    globaux: dict[str, tuple[str, float]] = {}
    par_option: dict[str, dict[str, tuple[str, float]]] = {}
    for cle, contenu in changements.items():
        texte = _texte(cle)
        if not texte:
            continue
        if texte in ids and isinstance(contenu, Mapping):
            specifiques: dict[str, tuple[str, float]] = {}
            for critere, valeur in contenu.items():
                nom = _texte(critere)
                specification = _specification(valeur)
                if nom and specification is not None:
                    specifiques[nom] = specification
            par_option.setdefault(texte, {}).update(specifiques)
            continue
        specification = _specification(contenu)
        if specification is not None:
            globaux[texte] = specification
    return globaux, par_option


def _criteres(
    criteres: Any,
    options: list[dict[str, Any]],
    globaux: Mapping[str, Any],
    par_option: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    if criteres is None:
        demandes: Iterable[Any] = ()
    elif isinstance(criteres, str):
        demandes = (criteres,)
    else:
        try:
            demandes = tuple(criteres)
        except TypeError as exc:
            raise TypeError("criteres : itérable attendu") from exc
    resultat: list[str] = []
    for critere in demandes:
        texte = _texte(critere)
        if texte and texte not in resultat:
            resultat.append(texte)
    if resultat:
        return resultat
    conteneurs: list[Mapping[str, Any]] = []
    for option in options:
        conteneurs.extend((option["valeurs"], option["deltas"]))
        conteneurs.append(par_option.get(option["id"], {}))
    conteneurs.append(globaux)
    for conteneur in conteneurs:
        for cle in conteneur:
            texte = _texte(cle)
            if texte and texte not in resultat:
                resultat.append(texte)
    return resultat


def _impact(
    valeurs: Mapping[str, Any],
    deltas: Mapping[str, Any],
    globaux: Mapping[str, tuple[str, float]],
    specifiques: Mapping[str, tuple[str, float]],
    criteres: Iterable[str],
) -> dict[str, float | None]:
    resultat: dict[str, float | None] = {}
    for critere in criteres:
        base = _nombre(valeurs.get(critere))
        delta_total = 0.0
        a_delta = False
        absolu: float | None = None
        for source in (deltas.get(critere), specifiques.get(critere), globaux.get(critere)):
            if source is None:
                continue
            if isinstance(source, tuple) and len(source) == 2 and source[0] in ("delta", "valeur"):
                specification = source
            else:
                specification = _specification(source)
            if specification is None:
                continue
            mode, nombre = specification
            if mode == "delta":
                delta_total += nombre
                a_delta = True
            else:
                absolu = nombre
        if absolu is not None:
            base = absolu
        if base is None:
            resultat[critere] = delta_total if a_delta else None
        else:
            resultat[critere] = base + delta_total if a_delta else base
    return resultat


def _relation(candidat: Mapping[str, Any], autre: Mapping[str, Any], criteres: Iterable[str]) -> bool | None:
    """``True`` si strictement meilleur quelque part, ``False`` si égal, ``None`` si incomparable."""
    strict = False
    for critere in criteres:
        gauche, droite = candidat.get(critere), autre.get(critere)
        if gauche is None or droite is None:
            return None
        if gauche < droite:
            return None
        if gauche > droite:
            strict = True
    return strict


def _option_dominante(resultats: list[dict[str, Any]], criteres: list[str]) -> str | None:
    if len(resultats) < 2 or not criteres:
        return None
    candidats: list[str] = []
    for rang, candidat in enumerate(resultats):
        au_moins_un_ecart = False
        comparable = True
        for autre_rang, autre in enumerate(resultats):
            if rang == autre_rang:
                continue
            relation = _relation(candidat["impacts"], autre["impacts"], criteres)
            if relation is None:
                comparable = False
                break
            au_moins_un_ecart = au_moins_un_ecart or relation
        if comparable and au_moins_un_ecart:
            candidats.append(candidat["id"])
    return candidats[0] if len(candidats) == 1 else None


def comparer(options: Any, changements: Any = None, *, criteres: Any = ()) -> dict:
    """Compare des options sous des changements explicites, sans recommandation.

    Chaque option accepte un mapping ou un objet et déclare ``valeurs``,
    ``deltas`` et ``conditions``. Un changement global est un mapping
    critère → variation (un nombre, ou ``{"delta": ...}`` / ``{"valeur": ...}``) ;
    un mapping dont la clé est un identifiant d'option porte les changements de
    cette option. Seules les clés explicitement fournies sont calculées : une
    valeur manquante rend ``None`` et interdit la dominance sur ce critère.

    ``option_dominante`` n'est renseignée que si une seule option est au moins
    égale à toutes les autres sur chaque critère et strictement meilleure sur au
    moins un. ``recommandation`` reste toujours ``None`` : le module ne choisit
    pas à la place de l'humain et n'énonce aucun lien causal.
    """
    liste = _options(options)
    globaux, par_option = _changements(changements, {option["id"] for option in liste})
    criteres_retenus = _criteres(criteres, liste, globaux, par_option)
    resultats: list[dict[str, Any]] = []
    impacts: dict[str, dict[str, float | None]] = {}
    conditions: list[str] = []
    for option in liste:
        impact = _impact(
            option["valeurs"],
            option["deltas"],
            globaux,
            par_option.get(option["id"], {}),
            criteres_retenus,
        )
        resultats.append({
            "id": option["id"],
            "label": option["label"],
            "impacts": impact,
            "conditions": list(option["conditions"]),
        })
        impacts[option["id"]] = dict(impact)
        for condition in option["conditions"]:
            if condition not in conditions:
                conditions.append(condition)
    return {
        "criteres": list(criteres_retenus),
        "options": resultats,
        "impacts": impacts,
        "option_dominante": _option_dominante(resultats, criteres_retenus),
        "conditions_de_retournement": conditions,
        "recommandation": None,
    }


def simuler(options: Any, changements: Any = None, *, criteres: Any = ()) -> dict:
    """Alias pur de :func:`comparer` : aucune simulation externe n'est exécutée."""
    return comparer(options, changements, criteres=criteres)
