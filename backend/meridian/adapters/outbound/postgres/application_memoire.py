"""Application contrôlée d'une consolidation approuvée à la mémoire durable.

Le module applique uniquement les groupes explicitement sélectionnés par leur
identifiant de mémoire gardée. Une mémoire retirée n'est jamais supprimée :
elle est archivée en posant ``expire_le`` à l'instant courant et en conservant
la raison, la mémoire de destination et l'acteur dans ``donnees.archive``. Les
conflits sont rendus à part et ne sont jamais tranchés ici. Toute lecture et
toute écriture reste bornée au tenant, et chaque groupe est appliqué dans une
transaction lorsque la connexion le permet.
"""
from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from datetime import date, datetime, time, timezone
import json
from typing import Any

from psycopg.types.json import Jsonb

from meridian.application import consolidation_memoire
from meridian.domain import tenant as tenant_module

__all__ = ["ConsolidationInvalide", "appliquer_consolidation"]

_MAX_PROVENANCE = 4000
_MAX_ACTEUR = 200

_REQUETE_LECTURE = (
    "SELECT id, provenance, expire_le, donnees FROM memoire_durable "
    "WHERE tenant_id = %s AND id = %s"
)
_REQUETE_GARDE = (
    "UPDATE memoire_durable SET provenance = %s, donnees = %s, maj_le = %s "
    "WHERE tenant_id = %s AND id = %s"
)
_REQUETE_ARCHIVE = (
    "UPDATE memoire_durable SET expire_le = %s, donnees = %s, maj_le = %s "
    "WHERE tenant_id = %s AND id = %s"
)


class ConsolidationInvalide(ValueError):
    """Une demande d'application ne respecte pas le contrat attendu."""


def _tenant(tenant_id: Any) -> str:
    try:
        return tenant_module.exiger_tenant(tenant_id).id
    except tenant_module.TenantError as exc:
        raise ConsolidationInvalide(str(exc)) from exc


def _texte_obligatoire(valeur: Any, champ: str) -> str:
    if valeur is None or isinstance(valeur, bool):
        raise ConsolidationInvalide(f"{champ} obligatoire")
    texte = str(valeur).strip()
    if not texte:
        raise ConsolidationInvalide(f"{champ} obligatoire")
    return texte


def _texte(valeur: Any) -> str:
    if valeur is None or isinstance(valeur, (bool, Mapping, bytes, bytearray)):
        return ""
    return str(valeur).strip()


def _liste(valeur: Any) -> list[Any]:
    if valeur is None:
        return []
    if isinstance(valeur, (str, bytes, bytearray, Mapping)):
        return [valeur]
    try:
        return list(valeur)
    except TypeError:
        return [valeur]


def _identifiant(valeur: Any) -> str:
    if isinstance(valeur, Mapping):
        valeur = valeur.get("id")
    return _texte(valeur)


def _selection(ids: Any) -> list[str]:
    resultat: list[str] = []
    for element in _liste(ids):
        identifiant = _identifiant(element)
        if identifiant and identifiant not in resultat:
            resultat.append(identifiant)
    return resultat


def _proposition(valeur: Any) -> consolidation_memoire.PropositionConsolidation:
    if isinstance(valeur, consolidation_memoire.PropositionConsolidation):
        return valeur
    if not isinstance(valeur, Mapping):
        raise TypeError("proposition : PropositionConsolidation ou mapping attendu")
    groupes = []
    for brut in _liste(valeur.get("groupes", valeur.get("fusions"))):
        if isinstance(brut, consolidation_memoire.GroupeFusion):
            groupes.append(brut)
        elif isinstance(brut, Mapping):
            groupes.append(consolidation_memoire.GroupeFusion(
                keep_id=brut.get("keep_id", brut.get("garder")),
                remove_ids=brut.get("remove_ids", brut.get("retirer", ())),
                raison=brut.get("raison", ""),
                confiance=brut.get("confiance", 1.0),
                evidences=brut.get("evidences", ()),
            ))
        else:
            raise TypeError("groupe de fusion invalide")
    conflits = []
    for brut in _liste(valeur.get("conflits")):
        if isinstance(brut, consolidation_memoire.Conflit):
            conflits.append(brut)
        elif isinstance(brut, Mapping):
            conflits.append(consolidation_memoire.Conflit(
                ids=brut.get("ids", ()),
                raison=brut.get("raison", ""),
                type=brut.get("type", "fait"),
                gravite=brut.get("gravite", "moyenne"),
            ))
        else:
            raise TypeError("conflit invalide")
    return consolidation_memoire.PropositionConsolidation(
        groupes=tuple(groupes),
        conflits=tuple(conflits),
        limites=tuple(_liste(valeur.get("limites"))),
    )


def _est_sqlite(conn: Any) -> bool:
    return type(conn).__module__.split(".", 1)[0] == "sqlite3"


def _sql(conn: Any, requete: str) -> str:
    return requete.replace("%s", "?") if _est_sqlite(conn) else requete


def _executer(conn: Any, requete: str, parametres: tuple = ()) -> None:
    cur = conn.cursor()
    try:
        cur.execute(_sql(conn, requete), parametres)
    finally:
        fermer = getattr(cur, "close", None)
        if callable(fermer):
            fermer()


def _une(conn: Any, requete: str, parametres: tuple = ()) -> Any:
    cur = conn.cursor()
    try:
        cur.execute(_sql(conn, requete), parametres)
        return cur.fetchone()
    finally:
        fermer = getattr(cur, "close", None)
        if callable(fermer):
            fermer()


@contextmanager
def _transaction(conn: Any):
    if _est_sqlite(conn):
        with conn:
            yield
        return
    transaction = getattr(conn, "transaction", None)
    if callable(transaction):
        with transaction():
            yield
        return
    yield


def _champ(ligne: Any, nom: str, rang: int) -> Any:
    if isinstance(ligne, Mapping):
        return ligne.get(nom)
    return ligne[rang]


def _donnees(valeur: Any) -> dict[str, Any]:
    if isinstance(valeur, Mapping):
        return dict(valeur)
    if isinstance(valeur, str):
        try:
            charge = json.loads(valeur)
        except (TypeError, ValueError):
            return {}
        return dict(charge) if isinstance(charge, Mapping) else {}
    return {}


def _donnees_parametre(conn: Any, valeur: Mapping) -> Any:
    return json.dumps(dict(valeur), ensure_ascii=False) if _est_sqlite(conn) else Jsonb(dict(valeur))


def _instant(valeur: Any) -> datetime | None:
    if valeur is None:
        return None
    if isinstance(valeur, datetime):
        instant = valeur
    elif isinstance(valeur, date):
        instant = datetime.combine(valeur, time.min)
    elif isinstance(valeur, str):
        try:
            instant = datetime.fromisoformat(valeur.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant


def _est_archivee(ligne: Any, maintenant: datetime) -> bool:
    donnees = _donnees(_champ(ligne, "donnees", 3))
    if isinstance(donnees.get("archive"), Mapping):
        return True
    expiration = _instant(_champ(ligne, "expire_le", 2))
    return expiration is not None and expiration <= maintenant


def _lire(conn: Any, tenant: str, identifiant: str) -> Any:
    requete = _REQUETE_LECTURE if _est_sqlite(conn) else _REQUETE_LECTURE + " FOR UPDATE"
    return _une(conn, requete, (tenant, identifiant))


def _marquer_garde(
    conn: Any,
    tenant: str,
    groupe: consolidation_memoire.GroupeFusion,
    ligne: Any,
    acteur: str,
    instant: datetime,
) -> None:
    provenance = _texte(_champ(ligne, "provenance", 1))
    marqueur = f"consolidation: {acteur}"
    if marqueur not in provenance:
        provenance = f"{provenance} | {marqueur}" if provenance else marqueur
        provenance = provenance[:_MAX_PROVENANCE]
    donnees = _donnees(_champ(ligne, "donnees", 3))
    donnees["consolidation"] = {
        "acteur": acteur,
        "raison": groupe.raison,
        "fusionne_avec": list(groupe.remove_ids),
        "le": instant.isoformat(),
    }
    _executer(
        conn,
        _REQUETE_GARDE,
        (provenance, _donnees_parametre(conn, donnees), instant, tenant, groupe.keep_id),
    )


def _archiver(
    conn: Any,
    tenant: str,
    identifiant: str,
    ligne: Any,
    groupe: consolidation_memoire.GroupeFusion,
    acteur: str,
    instant: datetime,
) -> None:
    donnees = _donnees(_champ(ligne, "donnees", 3))
    donnees["archive"] = {
        "raison": groupe.raison,
        "fusionne_dans": groupe.keep_id,
        "acteur": acteur,
    }
    _executer(
        conn,
        _REQUETE_ARCHIVE,
        (instant, _donnees_parametre(conn, donnees), instant, tenant, identifiant),
    )


def _ajouter(valeurs: list[str], valeur: str) -> None:
    if valeur and valeur not in valeurs:
        valeurs.append(valeur)


def appliquer_consolidation(conn: Any, tenant_id: Any, proposition: Any, *, ids: Any, acteur: Any) -> dict:
    """Applique les groupes sélectionnés par ``ids`` aux seules mémoires durables.

    ``ids`` désigne les identifiants ``keep_id`` des groupes à appliquer ; un
    identifiant de mémoire retirée ne sélectionne donc pas son groupe. La
    mémoire gardée reçoit un marqueur de provenance et une métadonnée de
    consolidation ; les mémoires retirées encore actives sont archivées, jamais
    supprimées. Les conflits de la proposition sont rendus séparément et ne sont
    jamais appliqués. Les lignes déjà archivées ou absentes du tenant sont
    ignorées, ce qui rend une réexécution sans effet supplémentaire.
    """
    tenant = _tenant(tenant_id)
    acteur_propre = _texte_obligatoire(acteur, "acteur")[:_MAX_ACTEUR]
    proposition_valide = _proposition(proposition)
    selection = _selection(ids)
    maintenant = datetime.now(timezone.utc)
    connus = {groupe.keep_id for groupe in proposition_valide.groupes}
    groupes: list[dict[str, Any]] = []
    gardees: list[str] = []
    archivees: list[str] = []
    ignorees: list[str] = []

    for identifiant in selection:
        if identifiant not in connus:
            _ajouter(ignorees, identifiant)

    with _transaction(conn):
        for groupe in proposition_valide.groupes:
            if groupe.keep_id not in selection:
                continue
            garde = _lire(conn, tenant, groupe.keep_id)
            if garde is None or _est_archivee(garde, maintenant):
                _ajouter(ignorees, groupe.keep_id)
                continue
            a_archiver: list[tuple[str, Any]] = []
            for identifiant in groupe.remove_ids:
                ligne = _lire(conn, tenant, identifiant)
                if ligne is None or _est_archivee(ligne, maintenant):
                    _ajouter(ignorees, identifiant)
                    continue
                a_archiver.append((identifiant, ligne))
            if not a_archiver:
                _ajouter(ignorees, groupe.keep_id)
                continue
            for identifiant, ligne in a_archiver:
                _archiver(conn, tenant, identifiant, ligne, groupe, acteur_propre, maintenant)
                _ajouter(archivees, identifiant)
            _marquer_garde(conn, tenant, groupe, garde, acteur_propre, maintenant)
            _ajouter(gardees, groupe.keep_id)
            groupes.append({
                "garder": groupe.keep_id,
                "retirer": list(groupe.remove_ids),
                "keep_id": groupe.keep_id,
                "remove_ids": list(groupe.remove_ids),
                "raison": groupe.raison,
                "confiance": groupe.confiance,
                "archivees": [identifiant for identifiant, _ in a_archiver],
            })

    return {
        "tenant": tenant,
        "groupes": groupes,
        "gardees": gardees,
        "archivees": archivees,
        "ignorees": ignorees,
        "conflits": [conflit.as_dict() for conflit in proposition_valide.conflits],
        "ecritures": True,
    }
