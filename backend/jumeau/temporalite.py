"""Lecture temporelle du Mesh : validité d'intervalle, fraîcheur et topologie à une date.

Les objets canoniques portent ``valide_depuis`` / ``valide_jusqua`` ; les arêtes du port graphe
portent ``valid_from`` / ``valid_to``. La convention est uniforme : début inclus, fin exclue,
début absent = pas de borne basse, fin absente = intervalle ouvert. Une date invalide n'est
jamais interprétée comme une validité : elle rend ``False`` (conservateur).

Le module est pur : aucun réseau, aucune base. ``topologie_a_date`` ne lit que ce que le store
expose via ``as_dict`` et signale explicitement que les nœuds Twin n'ont pas de validité dans
le port.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime, timezone
from typing import Any

__all__ = [
    "est_valide",
    "etat_a_date",
    "fraicheur",
    "preuves_perimees",
    "topologie_a_date",
]

_LIMITE_TOPOLOGIE = (
    "Les nœuds Twin n'ont pas de période de validité dans le port : tous les nœuds du tenant "
    "sont rendus, seules les arêtes sont filtrées à la date (début inclus, fin exclue) et "
    "seulement si leurs deux extrémités sont présentes."
)
_CHAMPS_DEBUT = ("valide_depuis", "valid_from")
_CHAMPS_FIN = ("valide_jusqua", "valid_to", "valid_until")
_CHAMPS_OBSERVATION = (
    "observe_le", "observed_at", "valide_depuis", "valid_from", "maj_le", "updated_at",
    "cree_le", "created_at",
)


def _texte(valeur: Any) -> str:
    if valeur is None or isinstance(valeur, (bytes, bytearray, Mapping)):
        return ""
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return ""
    return str(valeur).strip()


def _valeur(objet: Any, *noms: str, defaut: Any = None) -> Any:
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
    for conteneur in ("donnees", "temporalite"):
        bloc = objet.get(conteneur) if isinstance(objet, Mapping) else None
        if isinstance(bloc, Mapping):
            for nom in noms:
                if nom in bloc and bloc[nom] is not None:
                    return bloc[nom]
    return defaut


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


def _borne(valeur: Any) -> tuple[bool, datetime | None]:
    """Rend ``(exploitable, instant)`` ; une borne absente ou vide est exploitable et ouverte."""
    texte = _texte(valeur)
    if not texte:
        return True, None
    instant = _en_datetime(valeur)
    if instant is None:
        return False, None
    return True, instant


def _maintenant(valeur: Any = None) -> datetime:
    return _en_datetime(valeur) or datetime.now(timezone.utc)


def _texte_date(valeur: Any) -> str:
    if isinstance(valeur, (datetime, date)):
        return valeur.isoformat()
    return _texte(valeur)


def _bornes(objet: Any) -> tuple[bool, datetime | None, datetime | None]:
    debut_ok, debut = _borne(_valeur(objet, *_CHAMPS_DEBUT))
    fin_ok, fin = _borne(_valeur(objet, *_CHAMPS_FIN))
    return debut_ok and fin_ok, debut, fin


def est_valide(objet: Any, date_reference: Any) -> bool:
    """Vrai si ``objet`` est valide à ``date_reference`` (début inclus, fin exclue).

    Les bornes absentes sont ouvertes. Une date de référence invalide, une borne invalide ou un
    intervalle inversé rendent ``False`` : on ne prouve pas une validité avec une date douteuse.
    """
    reference = _en_datetime(date_reference)
    if reference is None:
        return False
    bornes_ok, debut, fin = _bornes(objet)
    if not bornes_ok:
        return False
    if debut is not None and fin is not None and debut > fin:
        return False
    if debut is not None and reference < debut:
        return False
    if fin is not None and reference >= fin:
        return False
    return True


def etat_a_date(objets: Iterable[Any], date_reference: Any) -> list[Any]:
    """Rend les objets valides à la date, dans leur ordre d'entrée et sans les modifier."""
    reference = _en_datetime(date_reference)
    if reference is None:
        return []
    return [objet for objet in objets or () if est_valide(objet, reference)]


def _observation(objet: Any) -> tuple[Any, datetime | None]:
    for nom in _CHAMPS_OBSERVATION:
        valeur = _valeur(objet, nom)
        if _texte(valeur):
            return valeur, _en_datetime(valeur)
    return None, None


def fraicheur(objet: Any, *, maintenant: Any = None, seuil_jours: Any = 30) -> dict:
    """Âge et péremption d'une observation ; une date absente ou invalide est ``stale`` inconnue.

    Le résultat expose ``observed_at`` (valeur d'origine), ``age_jours``, ``stale`` et un état
    lisible. Une observation future est ramenée à un âge nul. Le seuil est strict : un âge
    exactement égal au seuil reste frais.
    """
    instant = _maintenant(maintenant)
    observed_at, observe = _observation(objet)
    try:
        seuil = float(seuil_jours)
    except (TypeError, ValueError):
        seuil = 30.0
    if seuil < 0:
        seuil = 30.0
    if observe is None:
        return {
            "observed_at": observed_at,
            "age_jours": None,
            "age": None,
            "stale": True,
            "etat": "inconnue",
            "connu": False,
            "seuil_jours": seuil,
            "raison": "date d'observation absente ou invalide",
        }
    age = (instant - observe).total_seconds() / 86400.0
    if age < 0:
        age = 0.0
    age = round(age, 2)
    stale = age > seuil
    return {
        "observed_at": observed_at,
        "age_jours": age,
        "age": age,
        "stale": stale,
        "etat": "perimee" if stale else "fraiche",
        "connu": True,
        "seuil_jours": seuil,
        "raison": None,
    }


def _preuve_expiree(preuve: Any, reference: datetime, seuil_jours: float) -> bool:
    fin_brute = _valeur(preuve, *_CHAMPS_FIN)
    if _texte(fin_brute):
        fin = _en_datetime(fin_brute)
        return fin is None or reference >= fin
    _, observe = _observation(preuve)
    if observe is None:
        return True
    age = (reference - observe).total_seconds() / 86400.0
    return age > seuil_jours


def preuves_perimees(preuves: Iterable[Any], date_reference: Any, *,
                     seuil_jours: Any = 30) -> list[Any]:
    """Rend les preuves expirées à la date, sans copie ni mutation.

    ``valid_until`` / ``valid_to`` / ``valide_jusqua`` est une fin exclue. Sans fin explicite,
    l'âge de ``observed_at`` (ou d'une date d'observation équivalente) est comparé au seuil.
    Une preuve sans date exploitable est conservée comme périmée inconnue. Une date de
    référence invalide rend toutes les preuves (on ne peut en certifier aucune fraîche).
    """
    liste = list(preuves or ())
    reference = _en_datetime(date_reference)
    if reference is None:
        return liste
    try:
        seuil = float(seuil_jours)
    except (TypeError, ValueError):
        seuil = 30.0
    if seuil < 0:
        seuil = 30.0
    return [preuve for preuve in liste if _preuve_expiree(preuve, reference, seuil)]


def _en_dict(element: Any) -> dict:
    if isinstance(element, Mapping):
        return dict(element)
    if hasattr(element, "__dict__"):
        return dict(vars(element))
    return {}


def _liste_elements(valeur: Any) -> list[Any]:
    if valeur is None:
        return []
    if isinstance(valeur, Mapping):
        return [valeur]
    if isinstance(valeur, (str, bytes, bytearray)):
        return []
    try:
        return list(valeur)
    except TypeError:
        return []


def _meme_tenant(element: Any, tenant: str, *, absent_autorise: bool) -> bool:
    valeur = _texte(_valeur(element, "tenant_id", "tenant"))
    if not valeur:
        return absent_autorise
    return valeur == tenant


def _as_dict(store: Any, tenant: str) -> tuple[dict, bool]:
    methode = getattr(store, "as_dict", None)
    if not callable(methode):
        return {}, True
    try:
        resultat = methode(tenant)
        return resultat if isinstance(resultat, Mapping) else {}, True
    except TypeError:
        resultat = methode()
        return resultat if isinstance(resultat, Mapping) else {}, False


def topologie_a_date(store: Any, tenant_id: Any, date_reference: Any) -> dict:
    """Topologie d'un tenant à une date, lue via ``store.as_dict`` sans réseau.

    Neo4j expose ``as_dict(tenant)`` ; ``GrapheMemoire.as_dict()`` n'accepte pas de tenant, d'où
    le repli sur un appel sans argument suivi d'un filtrage local. Les nœuds sont rendus tels
    quels (le port ne porte pas leur validité), les arêtes doivent être valides à la date et
    avoir leurs deux extrémités présentes. Le champ ``limite`` documente cette asymétrie.
    """
    tenant = _texte(tenant_id)
    date_texte = _texte_date(date_reference)
    reference = _en_datetime(date_reference)
    donnees, scope_direct = _as_dict(store, tenant)
    noeuds_par_id: dict[str, dict] = {}
    for brut in _liste_elements(donnees.get("noeuds")):
        noeud = _en_dict(brut)
        identifiant = _texte(_valeur(noeud, "id"))
        if not identifiant or not _meme_tenant(noeud, tenant, absent_autorise=scope_direct):
            continue
        noeuds_par_id.setdefault(identifiant, noeud)
    aretes_par_id: dict[str, dict] = {}
    for brut in _liste_elements(donnees.get("aretes")):
        arete = _en_dict(brut)
        identifiant = _texte(_valeur(arete, "id"))
        if not identifiant or not _meme_tenant(arete, tenant, absent_autorise=scope_direct):
            continue
        if reference is None or not est_valide(arete, reference):
            continue
        source = _texte(_valeur(arete, "source"))
        target = _texte(_valeur(arete, "target"))
        if source not in noeuds_par_id or target not in noeuds_par_id:
            continue
        aretes_par_id.setdefault(identifiant, arete)
    return {
        "tenant": tenant,
        "date": date_texte,
        "noeuds": [noeuds_par_id[identifiant] for identifiant in sorted(noeuds_par_id)],
        "aretes": [aretes_par_id[identifiant] for identifiant in sorted(aretes_par_id)],
        "limite": _LIMITE_TOPOLOGIE,
    }
