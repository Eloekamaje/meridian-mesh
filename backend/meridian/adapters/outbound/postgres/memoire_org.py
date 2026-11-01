"""Mémoire organisationnelle durable : dépôt, recherche lexicale et rappel par situation.

Les entrées sont persistées comme objets ``ANNOTATION`` de la famille ``interaction_gouvernance`` de
:mod:`jumeau.modele_entreprise`. Ce type existe déjà et n'exige pas les liens Outcome/Investigation du type
``LEARNING`` : une note organisationnelle peut être conservée sans prétendre être une leçon mesurée. La recherche
est purement lexicale, déterministe, sans modèle ni réseau, et toujours bornée au tenant.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any
import unicodedata
import uuid

from meridian.adapters.outbound.postgres import entreprise_depot
from meridian.domain import modele_entreprise as modele
from meridian.domain import tenant as tenant_module

__all__ = [
    "FAMILLE_MEMOIRE",
    "MemoireInvalide",
    "MODE_MEMOIRE",
    "TYPE_MEMOIRE",
    "classer_memoires",
    "chercher",
    "memoriser",
    "memoriaux_pour_situation",
]

TYPE_MEMOIRE = "ANNOTATION"
FAMILLE_MEMOIRE = modele.famille_de(TYPE_MEMOIRE)
MODE_MEMOIRE = "DECLARED"
_MAX_LECTURE = 1000


class MemoireInvalide(ValueError):
    """Une entrée de mémoire organisationnelle ne respecte pas ses invariants."""


def _tenant(tenant_id: Any) -> str:
    return tenant_module.exiger_tenant(tenant_id).id


def _texte(valeur: Any) -> str:
    return "" if valeur is None else str(valeur).strip()


def _texte_obligatoire(valeur: Any, champ: str) -> str:
    texte = _texte(valeur)
    if not texte:
        raise MemoireInvalide(f"{champ} obligatoire")
    return texte


def _liste(valeur: Any) -> list[Any]:
    if valeur is None:
        return []
    if isinstance(valeur, (str, Mapping)) or not isinstance(valeur, Iterable):
        return [valeur]
    return list(valeur)


def _liste_ids(valeur: Any) -> list[str]:
    resultat: list[str] = []
    for element in _liste(valeur):
        if isinstance(element, Mapping):
            element = element.get("id")
        texte = _texte(element)
        if texte and texte not in resultat:
            resultat.append(texte)
    return resultat


def _donnees(ligne: Any) -> Mapping[str, Any]:
    if not isinstance(ligne, Mapping):
        return {}
    donnees = ligne.get("donnees")
    return donnees if isinstance(donnees, Mapping) else {}


def _ids_lies(ligne: Any, *noms: str) -> list[str]:
    resultat: list[str] = []
    for nom in noms:
        for conteneur in (_donnees(ligne), ligne):
            if isinstance(conteneur, Mapping) and nom in conteneur:
                for identifiant in _liste_ids(conteneur[nom]):
                    if identifiant not in resultat:
                        resultat.append(identifiant)
    return resultat


def _normaliser_texte(valeur: Any) -> str:
    texte = unicodedata.normalize("NFKD", str(valeur or ""))
    texte = "".join(c for c in texte if not unicodedata.combining(c)).lower()
    texte = "".join(c if c.isalnum() else " " for c in texte)
    return " ".join(texte.split())


def _recence(ligne: Any) -> tuple[float, float, float, float]:
    valeurs: list[float] = []
    for champ in ("cree_le", "observe_le", "maj_le", "valide_depuis"):
        instant = 0.0
        for conteneur in (ligne, _donnees(ligne)):
            if not isinstance(conteneur, Mapping):
                continue
            valeur = conteneur.get(champ)
            if not valeur:
                continue
            try:
                instant = datetime.fromisoformat(str(valeur).replace("Z", "+00:00")).timestamp()
            except ValueError:
                instant = 0.0
            break
        valeurs.append(instant)
    return tuple(valeurs)


def _limite(limite: Any) -> int:
    if isinstance(limite, bool):
        raise MemoireInvalide("limite doit être un entier positif")
    try:
        borne = int(limite)
    except (TypeError, ValueError) as exc:
        raise MemoireInvalide("limite doit être un entier positif") from exc
    if borne < 1:
        raise MemoireInvalide("limite doit être un entier positif")
    return min(borne, _MAX_LECTURE)


def _titre(texte: str) -> str:
    premiere = texte.splitlines()[0].strip()
    return premiere[:160].rstrip()


def _lire_memoires(conn: Any, tenant: str) -> list[dict]:
    return entreprise_depot.lister_objets(
        conn, tenant, type_=TYPE_MEMOIRE, limite=_MAX_LECTURE,
    )


def memoriser(
    conn: Any, tenant_id: Any, contenu: Any, *, genre: Any, source: Any,
    twin_ids: Any = (), situation_ids: Any = (), confiance: Any = None,
) -> dict:
    """Persiste une entrée de mémoire organisationnelle avec sa provenance.

    Le contenu, le genre et la source sont obligatoires. ``confiance`` vaut 0.5 par défaut et doit rester entre
    0 et 1. L'entrée est un objet ``ANNOTATION`` (famille ``interaction_gouvernance``) : aucun type nouveau ni
    table nouvelle n'est introduit.
    """
    tenant = _tenant(tenant_id)
    texte = _texte_obligatoire(contenu, "contenu")
    genre_final = _texte_obligatoire(genre, "genre")
    source_finale = _texte_obligatoire(source, "source")
    twins = _liste_ids(twin_ids)
    situations = _liste_ids(situation_ids)

    if confiance is None:
        confiance_finale = 0.5
    else:
        try:
            confiance_finale = float(confiance)
        except (TypeError, ValueError) as exc:
            raise MemoireInvalide("confiance doit être un nombre entre 0 et 1") from exc
        if not 0.0 <= confiance_finale <= 1.0:
            raise MemoireInvalide("confiance doit être comprise entre 0 et 1")

    payload = {
        "id": f"memoire-{uuid.uuid4().hex[:12]}",
        "famille": FAMILLE_MEMOIRE,
        "type": TYPE_MEMOIRE,
        "mode": MODE_MEMOIRE,
        "titre": _titre(texte),
        "donnees": {
            "contenu": texte,
            "genre": genre_final,
            "source": source_finale,
            "twin_ids": twins,
            "situation_ids": situations,
            "confiance": confiance_finale,
        },
    }
    return entreprise_depot.enregistrer_objet(conn, tenant, payload)


def classer_memoires(
    items: Any, *, requete: Any = "", twin_ids: Any = (), situation_id: Any = None,
    limite: Any = 20, exiger_chevauchement: bool = False,
) -> list[dict]:
    """Classe des entrées de mémoire sans base ni réseau (fonction pure).

    La requête est comparée aux titres, contenus, genres et sources après normalisation des accents et de la
    casse ; tous les mots utiles de la requête doivent être présents. Le classement suit : titre exact, titre
    contenant la requête, situation exacte, nombre de Twins partagés, puis récence et identifiant. Avec
    ``exiger_chevauchement``, seules les entrées liées à la situation ou à un Twin demandé sont gardées.
    """
    texte = _texte(requete)
    requete_normalisee = _normaliser_texte(texte)
    tokens_requete = set(requete_normalisee.split())
    tokens_utiles = {token for token in tokens_requete if len(token) > 2} or tokens_requete
    twins = set(_liste_ids(twin_ids))
    situation = _texte(situation_id)
    borne = _limite(limite)

    classes: list[tuple] = []
    for ligne in items or []:
        if not isinstance(ligne, Mapping):
            continue
        donnees = _donnees(ligne)
        titre = _texte(ligne.get("titre"))
        contenu = _texte(donnees.get("contenu"))
        genre = _texte(donnees.get("genre"))
        source = _texte(donnees.get("source"))
        complet = _normaliser_texte(" ".join(
            element for element in (titre, contenu, genre, source) if element
        ))
        tokens = set(complet.split())
        if tokens_utiles and not tokens_utiles.issubset(tokens):
            continue

        titre_normalise = _normaliser_texte(titre)
        exact_titre = bool(requete_normalisee) and titre_normalise == requete_normalisee
        phrase_titre = bool(requete_normalisee) and requete_normalisee in titre_normalise

        situations_liees = set(_ids_lies(ligne, "situation_id", "situation_ids", "source_situation_ids"))
        twins_lies = set(_ids_lies(ligne, "twin_ids", "source_twin_ids"))
        exact_situation = bool(situation and situation in situations_liees)
        chevauchement = len(twins & twins_lies)
        if exiger_chevauchement and (situation or twins) and not (exact_situation or chevauchement):
            continue

        recence = tuple(-valeur for valeur in _recence(ligne))
        classes.append((
            0 if exact_titre else 1,
            0 if phrase_titre else 1,
            0 if exact_situation else 1,
            -chevauchement,
            *recence,
            _texte(ligne.get("id")),
            ligne,
        ))
    classes.sort(key=lambda element: element[:-1])
    return [element[-1] for element in classes[:borne]]


def chercher(
    conn: Any, tenant_id: Any, requete: Any, *, twin_ids: Any = (), limite: Any = 20,
) -> list[dict]:
    """Cherche lexicalement dans les entrées de mémoire du tenant.

    Aucun modèle ni appel réseau n'est utilisé. Les Twins fournis servent au classement, pas de filtre strict :
    une entrée lexicalement pertinente reste visible même sans Twin commun. Une requête vide rend ``[]``.
    """
    tenant = _tenant(tenant_id)
    texte = _texte(requete)
    if not texte:
        return []
    return classer_memoires(
        _lire_memoires(conn, tenant), requete=texte, twin_ids=twin_ids, limite=limite,
    )


def memoriaux_pour_situation(
    conn: Any, tenant_id: Any, situation_id: Any, *, twin_ids: Any = (), limite: Any = 10,
) -> list[dict]:
    """Rend les mémoires liées exactement à une situation ou partageant au moins un Twin.

    Le classement place la situation exacte avant le simple chevauchement de Twins, puis la récence. Les
    entrées sans lien avec la situation ni avec les Twins demandés sont exclues.
    """
    tenant = _tenant(tenant_id)
    situation = _texte_obligatoire(situation_id, "situation_id")
    return classer_memoires(
        _lire_memoires(conn, tenant), twin_ids=twin_ids, situation_id=situation,
        limite=limite, exiger_chevauchement=True,
    )
