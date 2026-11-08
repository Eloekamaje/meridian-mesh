"""Détecteur déterministe d'opportunités (plan Cognition IA, B2 + D6).

Trois signatures, aucune IA, aucune requête réseau — uniquement des requêtes SQL bornées via psycopg :

- ``duplication`` (B2) : au moins ``min_overlap`` applications distinctes réalisent la même capacité
  (claims ``REALISE_CAPACITE`` confirmés — statut ``ACCEPTED`` ou mode ``CONFIRMED`` — encore
  valides). La capacité est l'``objet`` du claim : un identifiant de twin CAPABILITY quand il
  existe, sinon le libellé tel qu'écrit par les jumeaux.
- ``concentration_risque`` (D6) : au moins ``min_dependants`` twins distincts dépendent du même
  twin (claims confirmés ``DEPEND_DE`` / ``DECLARE_DEPENDANCE`` / ``APPELLE`` dont l'``objet``
  est un jumeau du tenant). Le twin concentré est un point unique de défaillance : plus son degré
  entrant est élevé, plus ``impact`` et ``severite`` montent dans l'opportunité produite.
- ``dette_vs_usage`` (D6) : un twin porte des signaux de dette récents (claim valide de type
  ``RISK``, de prédicat ``INCIDENT_AFFECTE``/``DETTE_TECHNIQUE``/``OBSOLESCENCE``, ou contesté)
  ET reste très utilisé (au moins ``min_usage`` preuves d'usage : appelants distincts via
  ``APPELLE``/``ECHANGE_AVEC`` confirmés vers lui + SITUATION canoniques récentes le citant).
  Dette sans usage, ou usage sans dette : rien — c'est l'intersection qui est critique.

Chaque opportunité porte : ``signature``, ``sujet_detection``, ``twin_ids``, ``claim_ids``
(preuves), statut ``PROPOSED`` (annexe B : une opportunité reste une proposition tant qu'aucun
humain ne la qualifie). ``type_opportunite`` = ``DUPLICATION`` / ``CONCENTRATION_RISQUE`` /
``DETTE_CRITIQUE``. L'objet produit reste une OPPORTUNITY — le type RISK canonique n'est pas dans
la boucle de persistance (``enregistrer_boucle`` le refuserait).

Quotas et dédup : au plus ``quota`` opportunités par run, toutes signatures confondues, jouées
dans l'ordre ``duplication`` → ``concentration_risque`` → ``dette_vs_usage``. Une OPPORTUNITY
déjà présente avec la même ``signature`` et le même sujet (``sujet_detection`` — ``capacite_id``
pour les opportunités ``duplication`` antérieures), quel que soit son statut, n'est pas recréée :
un détecteur ne rouvre jamais silencieusement une opportunité qualifiée ou close. Les
identifiants sont déterministes (sha256 tenant+signature+sujet) : un second run ne crée rien.

Fail-closed : une opportunité refusée par le dépôt remonte dans ``erreurs`` du rapport, jamais
avalée.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timedelta, timezone
import hashlib
from typing import Any

import psycopg
from psycopg.rows import dict_row

from meridian.adapters.outbound.postgres import boucle, entreprise_depot

__all__ = [
    "SIGNATURE",
    "SIGNATURES",
    "PREDICAT_CAPACITE",
    "PREDICATS_DEPENDANCE",
    "PREDICATS_USAGE",
    "PREDICATS_DETTE",
    "TYPES_CLAIM_DETTE",
    "QUOTA_DEFAUT",
    "MIN_OVERLAP_DEFAUT",
    "MIN_DEPENDANTS_DEFAUT",
    "MIN_USAGE_DEFAUT",
    "FENETRE_JOURS_DEFAUT",
    "DetectionInvalide",
    "detecter",
]

SIGNATURE = "duplication"
SIGNATURE_CONCENTRATION = "concentration_risque"
SIGNATURE_DETTE_USAGE = "dette_vs_usage"
SIGNATURES = (SIGNATURE, SIGNATURE_CONCENTRATION, SIGNATURE_DETTE_USAGE)

PREDICAT_CAPACITE = "REALISE_CAPACITE"
# Arêtes twin → twin lues en base : l'``objet`` du claim doit être l'id d'un jumeau du tenant.
PREDICATS_RELATION = ("DEPEND_DE", "DECLARE_DEPENDANCE", "APPELLE", "ECHANGE_AVEC")
# Concentration : ces arêtes expriment « je dépends de / j'appelle » la cible.
PREDICATS_DEPENDANCE = ("DEPEND_DE", "DECLARE_DEPENDANCE", "APPELLE")
# Usage : ces arêtes entrantes prouvent que le twin sert encore.
PREDICATS_USAGE = ("APPELLE", "ECHANGE_AVEC")
# Dette : claims signalant un risque, un incident ou une obsolescence, ou contestés.
PREDICATS_DETTE = ("INCIDENT_AFFECTE", "DETTE_TECHNIQUE", "OBSOLESCENCE")
TYPES_CLAIM_DETTE = ("RISK",)

QUOTA_DEFAUT = 10
MIN_OVERLAP_DEFAUT = 2
MIN_DEPENDANTS_DEFAUT = 5
MIN_USAGE_DEFAUT = 2
FENETRE_JOURS_DEFAUT = 90
_LIMITE_LECTURE = 1000


class DetectionInvalide(ValueError):
    """Un paramètre du détecteur ne respecte pas son contrat."""


def _tenant(valeur: Any) -> str:
    texte = str(valeur or "").strip()
    if not texte:
        raise DetectionInvalide("tenant_id obligatoire")
    return texte


def _borne(valeur: Any, champ: str, minimum: int = 1, maximum: int = 1000) -> int:
    if isinstance(valeur, bool):
        raise DetectionInvalide(f"{champ} doit être un entier positif")
    try:
        nombre = int(valeur)
    except (TypeError, ValueError) as exc:
        raise DetectionInvalide(f"{champ} doit être un entier positif") from exc
    if nombre < minimum:
        raise DetectionInvalide(f"{champ} doit être un entier positif")
    return min(nombre, maximum)


def _instant(valeur: Any = None) -> datetime:
    if valeur is None:
        return datetime.now(timezone.utc)
    if isinstance(valeur, datetime):
        instant = valeur
    else:
        try:
            instant = datetime.fromisoformat(str(valeur).replace("Z", "+00:00"))
        except ValueError as exc:
            raise DetectionInvalide("maintenant : date ISO attendue") from exc
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant


def _texte(valeur: Any, maximum: int = 1000) -> str:
    return " ".join(str(valeur or "").split())[:maximum]


def _id_stable(prefixe: str, *parties: Any) -> str:
    brut = "|".join(str(partie or "") for partie in parties)
    return f"{prefixe}-{hashlib.sha256(brut.encode('utf-8')).hexdigest()[:12]}"


def _donnees(ligne: Any) -> dict:
    return dict(ligne.get("donnees") or {}) if isinstance(ligne, Mapping) else {}


def _tri_ids(ids: Iterable) -> list:
    return sorted(ids, key=lambda c: (0, c) if isinstance(c, int) else (1, str(c)))


# --- Sources bornées ---


def _lire_liens_capacite(conn: Any, tenant: str) -> list[dict]:
    """Claims ``REALISE_CAPACITE`` confirmés d'applications du tenant, capacité résolue en twin si possible."""
    try:
        with conn.transaction():  # savepoint : une table absente ne casse pas la transaction de l'appelant
            with conn.cursor(row_factory=dict_row) as cur:
                return [dict(ligne) for ligne in cur.execute(
                    "SELECT c.id AS claim_id, c.jumeau_id AS application_id, "
                    "       c.objet AS capacite_id, jc.id AS capacite_twin_id, "
                    "       jc.nom AS capacite_nom "
                    "FROM claim c "
                    "JOIN jumeau j ON j.id = c.jumeau_id "
                    "LEFT JOIN jumeau jc ON jc.id = c.objet AND jc.tenant_id = c.tenant_id "
                    "                   AND jc.type = 'CAPABILITY' "
                    "WHERE c.tenant_id = %s AND c.predicat = %s AND c.valide_jusqua IS NULL "
                    "  AND (c.statut = 'ACCEPTED' OR c.mode = 'CONFIRMED') "
                    "  AND j.type = 'APPLICATION' "
                    "ORDER BY c.objet, c.jumeau_id, c.id LIMIT %s",
                    (tenant, PREDICAT_CAPACITE, _LIMITE_LECTURE)).fetchall()]
    except psycopg.errors.UndefinedTable:
        return []


def _lire_relations(conn: Any, tenant: str) -> list[dict]:
    """Arêtes confirmées twin → twin : claims de dépendance/appel dont l'``objet`` est un jumeau du tenant."""
    try:
        with conn.transaction():
            with conn.cursor(row_factory=dict_row) as cur:
                return [dict(ligne) for ligne in cur.execute(
                    "SELECT c.id AS claim_id, c.jumeau_id AS dependant_id, "
                    "       c.objet AS cible_id, c.predicat, jc.nom AS cible_nom "
                    "FROM claim c "
                    "JOIN jumeau jc ON jc.id = c.objet AND jc.tenant_id = c.tenant_id "
                    "WHERE c.tenant_id = %s AND c.predicat = ANY(%s) AND c.valide_jusqua IS NULL "
                    "  AND (c.statut = 'ACCEPTED' OR c.mode = 'CONFIRMED') "
                    "  AND c.jumeau_id <> c.objet "
                    "ORDER BY c.objet, c.jumeau_id, c.id LIMIT %s",
                    (tenant, list(PREDICATS_RELATION), _LIMITE_LECTURE)).fetchall()]
    except psycopg.errors.UndefinedTable:
        return []


def _lire_signaux_dette(conn: Any, tenant: str, depuis: datetime) -> list[dict]:
    """Claims valides récents signalant une dette : type ``RISK``, prédicat de dette, ou contestés."""
    try:
        with conn.transaction():
            with conn.cursor(row_factory=dict_row) as cur:
                return [dict(ligne) for ligne in cur.execute(
                    "SELECT c.id AS claim_id, c.jumeau_id AS twin_id, "
                    "       c.predicat, c.type, c.statut "
                    "FROM claim c "
                    "WHERE c.tenant_id = %s AND c.valide_jusqua IS NULL "
                    "  AND c.enregistre_le >= %s "
                    "  AND (c.type = ANY(%s) OR c.predicat = ANY(%s) OR c.statut = 'CONTESTED') "
                    "ORDER BY c.jumeau_id, c.id LIMIT %s",
                    (tenant, depuis, list(TYPES_CLAIM_DETTE), list(PREDICATS_DETTE),
                     _LIMITE_LECTURE)).fetchall()]
    except psycopg.errors.UndefinedTable:
        return []


def _lire_situations(conn: Any, tenant: str, depuis: datetime) -> list[dict]:
    """SITUATION canoniques du tenant observées dans la fenêtre (preuves d'usage)."""
    try:
        with conn.transaction():
            with conn.cursor(row_factory=dict_row) as cur:
                return [dict(ligne) for ligne in cur.execute(
                    "SELECT * FROM objet_entreprise "
                    "WHERE tenant_id = %s AND type = 'SITUATION' "
                    "  AND observe_le >= %s AND (valide_jusqua IS NULL OR valide_jusqua >= %s) "
                    "ORDER BY observe_le DESC LIMIT %s",
                    (tenant, depuis, depuis, _LIMITE_LECTURE)).fetchall()]
    except psycopg.errors.UndefinedTable:
        return []


def _lire_opportunites_existantes(conn: Any, tenant: str) -> list[dict]:
    return entreprise_depot.lister_objets(conn, tenant, type_="OPPORTUNITY", limite=1000)


# --- Normalisation des lignes (mode READ sans base : même contrat que les requêtes) ---


def _lien(ligne: Mapping) -> dict | None:
    """Forme canonique ``{claim_id, application_id, capacite_id, capacite_twin_id, capacite_nom}``.

    Les lignes injectées (mode READ sans base) suivent le même contrat que la requête SQL ;
    quand ``statut``, ``mode`` ou ``type_twin`` sont présents, les mêmes filtres que la requête
    s'appliquent (confirmé et twin APPLICATION).
    """
    statut = _texte(ligne.get("statut")).upper()
    mode = _texte(ligne.get("mode")).upper()
    if (statut or mode) and statut != "ACCEPTED" and mode != "CONFIRMED":
        return None
    type_twin = _texte(ligne.get("type_twin") or ligne.get("jumeau_type")).upper()
    if type_twin and type_twin != "APPLICATION":
        return None
    claim_id = ligne.get("claim_id", ligne.get("id"))
    application_id = _texte(ligne.get("application_id") or ligne.get("jumeau_id"))
    capacite_id = _texte(ligne.get("capacite_id") or ligne.get("objet"))
    if claim_id is None or not application_id or not capacite_id:
        return None
    return {
        "claim_id": claim_id,
        "application_id": application_id,
        "capacite_id": capacite_id,
        "capacite_twin_id": _texte(ligne.get("capacite_twin_id")) or None,
        "capacite_nom": _texte(ligne.get("capacite_nom")),
    }


def _relation(ligne: Mapping) -> dict | None:
    """Arête confirmée twin → twin : ``{claim_id, dependant_id, cible_id, predicat, cible_nom}``.

    Les lignes injectées suivent le contrat de :func:`_lire_relations` ; ``statut``, ``mode`` et
    ``predicat`` sont filtrés comme en base quand ils sont présents. Les boucles sur soi-même
    (dependant = cible) sont ignorées comme en base.
    """
    statut = _texte(ligne.get("statut")).upper()
    mode = _texte(ligne.get("mode")).upper()
    if (statut or mode) and statut != "ACCEPTED" and mode != "CONFIRMED":
        return None
    predicat = _texte(ligne.get("predicat")).upper()
    if predicat and predicat not in PREDICATS_RELATION:
        return None
    claim_id = ligne.get("claim_id", ligne.get("id"))
    dependant_id = _texte(ligne.get("dependant_id") or ligne.get("jumeau_id"))
    cible_id = _texte(ligne.get("cible_id") or ligne.get("objet"))
    if claim_id is None or not dependant_id or not cible_id or dependant_id == cible_id:
        return None
    return {
        "claim_id": claim_id,
        "dependant_id": dependant_id,
        "cible_id": cible_id,
        "predicat": predicat,
        "cible_nom": _texte(ligne.get("cible_nom")),
    }


def _date_ligne(ligne: Mapping) -> datetime | None:
    """Première date exploitable de la ligne (``enregistre_le``, ``observe_le``…), sinon ``None``."""
    for cle in ("enregistre_le", "observe_le", "cree_le", "maj_le"):
        valeur = ligne.get(cle)
        if valeur is None:
            continue
        if isinstance(valeur, datetime):
            return valeur if valeur.tzinfo else valeur.replace(tzinfo=timezone.utc)
        try:
            instant = datetime.fromisoformat(str(valeur).replace("Z", "+00:00"))
        except ValueError:
            continue
        return instant if instant.tzinfo else instant.replace(tzinfo=timezone.utc)
    return None


def _signal_dette(ligne: Mapping, depuis: datetime) -> dict | None:
    """Signal de dette d'un twin : ``{claim_id, twin_id, predicat, type, statut}``.

    Même filtre qu'en base : claim encore valide, signal = type ``RISK``, prédicat de dette
    (``INCIDENT_AFFECTE``/``DETTE_TECHNIQUE``/``OBSOLESCENCE``) ou statut ``CONTESTED`` ;
    la récence n'est contrôlée que si la ligne porte une date exploitable.
    """
    if _texte(ligne.get("valide_jusqua")):
        return None
    statut = _texte(ligne.get("statut")).upper()
    type_claim = _texte(ligne.get("type")).upper()
    predicat = _texte(ligne.get("predicat")).upper()
    if (statut != "CONTESTED" and type_claim not in TYPES_CLAIM_DETTE
            and predicat not in PREDICATS_DETTE):
        return None
    instant = _date_ligne(ligne)
    if instant is not None and instant < depuis:
        return None
    claim_id = ligne.get("claim_id", ligne.get("id"))
    twin_id = _texte(ligne.get("twin_id") or ligne.get("jumeau_id"))
    if claim_id is None or not twin_id:
        return None
    return {"claim_id": claim_id, "twin_id": twin_id, "predicat": predicat,
            "type": type_claim, "statut": statut}


def _twin_ids_situation(ligne: Mapping) -> list[str]:
    donnees = _donnees(ligne)
    ids = donnees.get("twin_ids") or ligne.get("twin_ids") or []
    return [str(t).strip() for t in ids if str(t).strip()]


def _situation_recente(ligne: Mapping, depuis: datetime) -> bool:
    type_ligne = _texte(ligne.get("type")).upper()
    if type_ligne and type_ligne != "SITUATION":
        return False
    instant = _date_ligne(ligne)
    return instant is None or instant >= depuis


# --- Regroupements déterministes ---


def _duplications(liens: Iterable[Mapping], min_overlap: int) -> list[dict]:
    """Capacités réalisées par au moins ``min_overlap`` applications distinctes (ordre stable)."""
    par_capacite: dict[str, dict] = {}
    for ligne in liens or ():
        lien = _lien(ligne)
        if lien is None:
            continue
        groupe = par_capacite.setdefault(lien["capacite_id"], {
            "capacite_id": lien["capacite_id"],
            "capacite_twin_id": lien["capacite_twin_id"],
            "capacite_nom": lien["capacite_nom"],
            "applications": {},
            "claim_ids": [],
        })
        groupe["capacite_twin_id"] = groupe["capacite_twin_id"] or lien["capacite_twin_id"]
        groupe["capacite_nom"] = groupe["capacite_nom"] or lien["capacite_nom"]
        groupe["applications"].setdefault(lien["application_id"], [])
        groupe["applications"][lien["application_id"]].append(lien["claim_id"])
        groupe["claim_ids"].append(lien["claim_id"])
    duplications = []
    for capacite_id in sorted(par_capacite):
        groupe = par_capacite[capacite_id]
        if len(groupe["applications"]) < min_overlap:
            continue
        groupe["claim_ids"] = _tri_ids(groupe["claim_ids"])
        duplications.append(groupe)
    return duplications


def _concentrations(relations: Iterable[Mapping], min_dependants: int) -> list[dict]:
    """Twins cibles dont au moins ``min_dependants`` twins distincts dépendent (ordre stable)."""
    par_cible: dict[str, dict] = {}
    for ligne in relations or ():
        rel = _relation(ligne)
        if rel is None or rel["predicat"] not in PREDICATS_DEPENDANCE:
            continue
        groupe = par_cible.setdefault(rel["cible_id"], {
            "cible_id": rel["cible_id"],
            "cible_nom": rel["cible_nom"],
            "dependants": {},
            "claim_ids": [],
        })
        groupe["cible_nom"] = groupe["cible_nom"] or rel["cible_nom"]
        groupe["dependants"].setdefault(rel["dependant_id"], []).append(rel["claim_id"])
        groupe["claim_ids"].append(rel["claim_id"])
    concentrations = []
    for cible_id in sorted(par_cible):
        groupe = par_cible[cible_id]
        if len(groupe["dependants"]) < min_dependants:
            continue
        groupe["claim_ids"] = _tri_ids(groupe["claim_ids"])
        concentrations.append(groupe)
    return concentrations


def _dettes_critiques(
    relations: Iterable[Mapping], signaux: Iterable[Mapping],
    situations: Iterable[Mapping], min_usage: int, depuis: datetime,
) -> list[dict]:
    """Twins avec dette récente ET au moins ``min_usage`` preuves d'usage (ordre stable).

    L'usage d'un twin = nombre d'appelants distincts (arêtes ``APPELLE``/``ECHANGE_AVEC``
    confirmées vers lui) + nombre de SITUATION récentes distinctes le citant. Les deux
    conditions — dette et usage — sont exigées : une dette sur un twin mort n'est pas
    critique, un twin très utilisé sans signal de dette non plus.
    """
    dette_par_twin: dict[str, list[dict]] = {}
    for ligne in signaux or ():
        signal = _signal_dette(ligne, depuis)
        if signal is not None:
            dette_par_twin.setdefault(signal["twin_id"], []).append(signal)
    usage_par_twin: dict[str, dict] = {}

    def usage(twin_id: str) -> dict:
        return usage_par_twin.setdefault(twin_id, {
            "appelants": set(), "claim_ids": [], "situation_ids": set()})

    for ligne in relations or ():
        rel = _relation(ligne)
        if rel is None or rel["predicat"] not in PREDICATS_USAGE:
            continue
        groupe = usage(rel["cible_id"])
        groupe["appelants"].add(rel["dependant_id"])
        groupe["claim_ids"].append(rel["claim_id"])
        groupe["cible_nom"] = rel["cible_nom"]
    for ligne in situations or ():
        if not _situation_recente(ligne, depuis):
            continue
        situation_id = _texte(ligne.get("id"))
        for twin_id in _twin_ids_situation(ligne):
            if situation_id:
                usage(twin_id)["situation_ids"].add(situation_id)
    dettes = []
    for twin_id in sorted(dette_par_twin):
        groupe = usage_par_twin.get(twin_id)
        appelants = sorted(groupe["appelants"]) if groupe else []
        situation_ids = sorted(groupe["situation_ids"]) if groupe else []
        if len(appelants) + len(situation_ids) < min_usage:
            continue
        dettes.append({
            "twin_id": twin_id,
            "twin_nom": (groupe or {}).get("cible_nom") or "",
            "signaux": dette_par_twin[twin_id],
            "appelants": appelants,
            "situation_ids": situation_ids,
            "claim_ids_usage": _tri_ids(groupe["claim_ids"]) if groupe else [],
        })
    return dettes


# --- Dédup ---


def _sujets_connus(opportunites: Iterable[Mapping]) -> dict[tuple[str, str], str]:
    """``(signature, sujet)`` → statut, pour les OPPORTUNITY du tenant (tous statuts).

    Le sujet est ``sujet_detection`` ; pour les opportunités ``duplication`` écrites avant
    D6 (sans ``sujet_detection``), ``capacite_id`` fait foi.
    """
    connus: dict[tuple[str, str], str] = {}
    for ligne in opportunites or ():
        donnees = _donnees(ligne)
        signature = _texte(donnees.get("signature"))
        if signature not in SIGNATURES:
            continue
        sujet = _texte(donnees.get("sujet_detection"))
        if not sujet and signature == SIGNATURE:
            sujet = _texte(donnees.get("capacite_id"))
        if sujet:
            connus.setdefault((signature, sujet), _texte(donnees.get("statut")) or "?")
    return connus


# --- Écriture ---


def _creer_opportunite(
    conn: Any, tenant: str, persister: Callable, *, signature: str, sujet: str,
    titre: str, description: str, type_opportunite: str,
    twin_ids: list, claim_ids: list, extras: Mapping,
    erreurs: list,
) -> str | None:
    """Construit et persiste l'OPPORTUNITY ; rend son id, ``None`` si le dépôt refuse."""
    opportunite_id = _id_stable("opp", tenant, signature, sujet)
    try:
        opportunite = boucle.Opportunity(
            id=opportunite_id, tenant_id=tenant, titre=titre, description=description,
            statut="PROPOSED", type_opportunite=type_opportunite, signature=signature,
            twin_ids=twin_ids, claim_ids=claim_ids)
        payload = dict(opportunite.to_dict())
        payload["sujet_detection"] = sujet
        payload.update(dict(extras))
        persister(conn, tenant, payload)
    except Exception as exc:
        erreurs.append({"signature": signature, "sujet": sujet, "erreur": str(exc)})
        return None
    return opportunite_id


# --- Orchestration ---


def detecter(
    conn: Any, tenant_id: Any, *, signature: str | None = None,
    quota: int = QUOTA_DEFAUT,
    min_overlap: int = MIN_OVERLAP_DEFAUT,
    min_dependants: int = MIN_DEPENDANTS_DEFAUT,
    min_usage: int = MIN_USAGE_DEFAUT,
    fenetre_jours: int = FENETRE_JOURS_DEFAUT,
    maintenant: Any = None,
    claims: Iterable[Mapping] | None = None,
    relations: Iterable[Mapping] | None = None,
    signaux: Iterable[Mapping] | None = None,
    situations: Iterable[Mapping] | None = None,
    opportunites: Iterable[Mapping] | None = None,
    persister: Callable | None = None,
) -> dict:
    """Joue les détecteurs d'opportunités et rend le rapport du run.

    ``signature`` borne le run à un seul détecteur (les trois sinon). ``quota`` borne le nombre
    total d'opportunités produites, toutes signatures confondues, jouées dans l'ordre
    ``duplication`` → ``concentration_risque`` → ``dette_vs_usage``.

    Les paramètres ``claims``, ``relations``, ``signaux``, ``situations`` et ``opportunites``
    remplacent la lecture en base quand ils sont fournis — mode READ sans fixture DB. Contrats
    identiques aux requêtes : ``claims`` = liens application → capacité ; ``relations`` = arêtes
    twin → twin (``dependant_id``/``jumeau_id``, ``cible_id``/``objet``, ``predicat``) ;
    ``signaux`` = claims de dette par twin (``twin_id``/``jumeau_id``, ``type``, ``predicat``,
    ``statut``) ; ``situations`` = lignes ``objet_entreprise`` SITUATION (``twin_ids`` dans
    ``donnees`` ou au sommet). Une source non fournie avec ``conn=None`` vaut liste vide.

    ``persister(conn, tenant, objet)`` écrit dans ``objet_entreprise`` (défaut :
    :func:`boucle.enregistrer_boucle`).

    Rapport : ``{tenant, signatures, crees, ignores, erreurs, totaux}``. Toute erreur d'écriture
    est visible dans ``erreurs``.
    """
    tenant = _tenant(tenant_id)
    quota = _borne(quota, "quota", maximum=100)
    min_overlap = _borne(min_overlap, "min_overlap", minimum=2, maximum=50)
    min_dependants = _borne(min_dependants, "min_dependants", minimum=2, maximum=100)
    min_usage = _borne(min_usage, "min_usage", minimum=1, maximum=50)
    fenetre_jours = _borne(fenetre_jours, "fenetre_jours", maximum=3650)
    instant = _instant(maintenant)
    depuis = instant - timedelta(days=fenetre_jours)
    signatures = SIGNATURES if signature is None else (_texte(signature),)
    inconnues = set(signatures) - set(SIGNATURES)
    if inconnues:
        raise DetectionInvalide(
            f"signature inconnue : {sorted(inconnues)!r} (connues : {list(SIGNATURES)})")
    if persister is None:
        def persister(c, t, objets):
            return boucle.enregistrer_boucle(c, t, objets)

    def source(lot, lecture):
        if lot is not None:
            return list(lot)
        return lecture(conn, tenant) if conn is not None else []

    lignes_opportunites = (
        list(opportunites) if opportunites is not None
        else _lire_opportunites_existantes(conn, tenant))
    connus = _sujets_connus(lignes_opportunites)
    crees: list[dict] = []
    ignores: list[dict] = []
    erreurs: list[dict] = []
    produits = 0

    if SIGNATURE in signatures:
        liens = source(claims, _lire_liens_capacite)
        for groupe in _duplications(liens, min_overlap):
            if produits >= quota:
                break
            capacite_id = groupe["capacite_id"]
            statut_connu = connus.get((SIGNATURE, capacite_id))
            if statut_connu:
                ignores.append({"signature": SIGNATURE, "sujet": capacite_id,
                                "raison": f"opportunity déjà présente (statut {statut_connu})"})
                continue
            application_ids = sorted(groupe["applications"])
            claim_ids = groupe["claim_ids"]
            capacite_nom = groupe["capacite_nom"] or capacite_id
            twin_ids = list(application_ids)
            if groupe["capacite_twin_id"]:
                twin_ids.append(groupe["capacite_twin_id"])
            opportunite_id = _creer_opportunite(
                conn, tenant, persister, signature=SIGNATURE, sujet=capacite_id,
                titre=f"Duplication : « {capacite_nom} » réalisée par "
                      f"{len(application_ids)} applications",
                description=(
                    f"{len(application_ids)} applications déclarent la même capacité "
                    f"« {capacite_nom} » ({', '.join(application_ids)}). Mutualiser ou "
                    "spécialiser l'une d'elles réduirait la redondance."),
                type_opportunite="DUPLICATION",
                twin_ids=twin_ids, claim_ids=claim_ids,
                extras={"capacite_id": capacite_id, "application_ids": application_ids},
                erreurs=erreurs)
            if opportunite_id is None:
                continue
            connus[(SIGNATURE, capacite_id)] = "PROPOSED"
            produits += 1
            crees.append({"signature": SIGNATURE, "sujet": capacite_id,
                          "id": opportunite_id, "type": "OPPORTUNITY",
                          "applications": len(application_ids), "claim_ids": claim_ids})

    if SIGNATURE_CONCENTRATION in signatures:
        toutes_relations = source(relations, _lire_relations)
        for groupe in _concentrations(toutes_relations, min_dependants):
            if produits >= quota:
                break
            cible_id = groupe["cible_id"]
            statut_connu = connus.get((SIGNATURE_CONCENTRATION, cible_id))
            if statut_connu:
                ignores.append({"signature": SIGNATURE_CONCENTRATION, "sujet": cible_id,
                                "raison": f"opportunity déjà présente (statut {statut_connu})"})
                continue
            dependants = sorted(groupe["dependants"])
            degre = len(dependants)
            cible_nom = groupe["cible_nom"] or cible_id
            impact = round(min(1.0, degre / (min_dependants * 2)), 2)
            severite = "CRITIQUE" if degre >= min_dependants * 2 else "ELEVEE"
            opportunite_id = _creer_opportunite(
                conn, tenant, persister, signature=SIGNATURE_CONCENTRATION, sujet=cible_id,
                titre=f"Concentration de risque : {degre} twins dépendent de « {cible_nom} »",
                description=(
                    f"{degre} twins déclarent une dépendance vers « {cible_nom} » "
                    f"({', '.join(dependants)}). « {cible_nom} » est un point unique de "
                    "défaillance : réduire le couplage ou prévoir un repli limiterait le "
                    "rayon d'un incident."),
                type_opportunite="CONCENTRATION_RISQUE",
                twin_ids=[cible_id, *dependants], claim_ids=groupe["claim_ids"],
                extras={"cible_id": cible_id, "dependant_ids": dependants,
                        "degre_entrant": degre, "impact": impact, "severite": severite},
                erreurs=erreurs)
            if opportunite_id is None:
                continue
            connus[(SIGNATURE_CONCENTRATION, cible_id)] = "PROPOSED"
            produits += 1
            crees.append({"signature": SIGNATURE_CONCENTRATION, "sujet": cible_id,
                          "id": opportunite_id, "type": "OPPORTUNITY",
                          "dependants": degre, "severite": severite,
                          "claim_ids": groupe["claim_ids"]})

    if SIGNATURE_DETTE_USAGE in signatures:
        toutes_relations = (
            toutes_relations if SIGNATURE_CONCENTRATION in signatures
            else source(relations, _lire_relations))
        lignes_signaux = source(signaux, lambda c, t: _lire_signaux_dette(c, t, depuis))
        lignes_situations = source(situations, lambda c, t: _lire_situations(c, t, depuis))
        for groupe in _dettes_critiques(
                toutes_relations, lignes_signaux, lignes_situations, min_usage, depuis):
            if produits >= quota:
                break
            twin_id = groupe["twin_id"]
            statut_connu = connus.get((SIGNATURE_DETTE_USAGE, twin_id))
            if statut_connu:
                ignores.append({"signature": SIGNATURE_DETTE_USAGE, "sujet": twin_id,
                                "raison": f"opportunity déjà présente (statut {statut_connu})"})
                continue
            twin_nom = groupe["twin_nom"] or twin_id
            nb_dette = len(groupe["signaux"])
            nb_appelants = len(groupe["appelants"])
            nb_situations = len(groupe["situation_ids"])
            usage_total = nb_appelants + nb_situations
            impact = round(min(1.0, (nb_dette + usage_total) / 10), 2)
            claim_ids = _tri_ids(
                [s["claim_id"] for s in groupe["signaux"]] + groupe["claim_ids_usage"])
            opportunite_id = _creer_opportunite(
                conn, tenant, persister, signature=SIGNATURE_DETTE_USAGE, sujet=twin_id,
                titre=f"Dette critique : « {twin_nom} » porte {nb_dette} signaux "
                      "de dette malgré un usage élevé",
                description=(
                    f"{nb_dette} signaux de dette récents (claims RISK, incidents ou "
                    f"contestés) pèsent sur « {twin_nom} » alors qu'il reste utilisé : "
                    f"{nb_appelants} twins l'appellent et {nb_situations} situations "
                    "récentes l'impliquent. Traiter cette dette protège un point encore "
                    "très sollicité."),
                type_opportunite="DETTE_CRITIQUE",
                twin_ids=[twin_id, *groupe["appelants"]], claim_ids=claim_ids,
                extras={"twin_id": twin_id,
                        "claim_ids_dette": [
                            str(c) for c in _tri_ids(s["claim_id"] for s in groupe["signaux"])],
                        "appelant_ids": groupe["appelants"],
                        "situation_ids": groupe["situation_ids"],
                        "signaux_dette": nb_dette, "usage": usage_total, "impact": impact},
                erreurs=erreurs)
            if opportunite_id is None:
                continue
            connus[(SIGNATURE_DETTE_USAGE, twin_id)] = "PROPOSED"
            produits += 1
            crees.append({"signature": SIGNATURE_DETTE_USAGE, "sujet": twin_id,
                          "id": opportunite_id, "type": "OPPORTUNITY",
                          "signaux_dette": nb_dette, "usage": usage_total,
                          "claim_ids": claim_ids})
    return {
        "tenant": tenant,
        "signatures": list(signatures),
        "crees": crees,
        "ignores": ignores,
        "erreurs": erreurs,
        "totaux": {"crees": len(crees), "ignores": len(ignores), "erreurs": len(erreurs)},
    }
