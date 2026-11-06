"""Persistance de la mémoire prospective : intentions, échéances et rappels."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Mapping

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from meridian.domain import memoire_prospective as domaine
from meridian.domain import tenant as tenant_module

__all__ = [
    "DUREE_CONSERVATION",
    "MemoireProspectiveInvalide",
    "clore",
    "compter",
    "creer",
    "echeances",
    "lire",
    "lister",
    "purger",
    "reporter",
]

DUREE_CONSERVATION = timedelta(days=90)
_MAX_LECTURE = 1000

_COLONNES = (
    "id, tenant_id, scope, scope_id, objet, echeance, source, owner, statut, "
    "priorite, evidence_ids, donnees, cree_le AS created_at, maj_le AS updated_at"
)
_INSERT = (
    "INSERT INTO memoire_prospective "
    "(id, tenant_id, scope, scope_id, objet, echeance, source, owner, statut, "
    "priorite, evidence_ids, donnees) VALUES "
    "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
    "ON CONFLICT (tenant_id, id) DO NOTHING "
    f"RETURNING {_COLONNES}"
)


class MemoireProspectiveInvalide(ValueError):
    """L'intention ne respecte pas le contrat de mémoire prospective."""


def _tenant(tenant_id) -> str:
    try:
        return tenant_module.exiger_tenant(tenant_id).id
    except tenant_module.TenantError as exc:
        raise MemoireProspectiveInvalide(str(exc)) from exc


def _valeur(valeur):
    if isinstance(valeur, datetime):
        return valeur.astimezone(timezone.utc).isoformat(timespec="seconds")
    if isinstance(valeur, Decimal):
        return float(valeur)
    return valeur


def _ligne(ligne) -> dict:
    return {cle: _valeur(ligne[cle]) for cle in (
        "id", "tenant_id", "scope", "scope_id", "objet", "echeance", "source",
        "owner", "statut", "priorite", "evidence_ids", "donnees",
        "created_at", "updated_at") if cle in ligne}


def _intention(valeur) -> domaine.Intention:
    if isinstance(valeur, domaine.Intention):
        return valeur
    if not isinstance(valeur, Mapping):
        raise MemoireProspectiveInvalide("intention attendue")
    try:
        return domaine.Intention.depuis_dict(valeur)
    except ValueError as exc:
        raise MemoireProspectiveInvalide(str(exc)) from exc


def _instant(valeur, champ: str) -> datetime:
    try:
        instant = datetime.fromisoformat(str(valeur).replace("Z", "+00:00"))
    except ValueError as exc:
        raise MemoireProspectiveInvalide(f"{champ} : date ISO attendue") from exc
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant


def _limite(limite) -> int:
    if isinstance(limite, bool):
        raise MemoireProspectiveInvalide("limite doit être un entier positif")
    try:
        valeur = int(limite)
    except (TypeError, ValueError) as exc:
        raise MemoireProspectiveInvalide("limite doit être un entier positif") from exc
    if valeur < 1:
        raise MemoireProspectiveInvalide("limite doit être un entier positif")
    return min(valeur, _MAX_LECTURE)


def _lire_ligne(lignes):
    return [_ligne(ligne) for ligne in lignes]


def creer(conn, intention) -> dict:
    """Crée une intention ; un identifiant déjà présent est rendu sans écrasement."""
    valeur = _intention(intention)
    tenant = _tenant(valeur.tenant_id)
    with conn.cursor(row_factory=dict_row) as cur:
        ligne = cur.execute(_INSERT, (
            valeur.id, tenant, valeur.scope, valeur.scope_id, valeur.objet,
            valeur.echeance, valeur.source, valeur.owner, valeur.statut,
            valeur.priorite, Jsonb(list(valeur.evidence_ids)),
            Jsonb(dict(valeur.donnees)),
        )).fetchone()
    if ligne is not None:
        return _ligne(ligne)
    return lire(conn, tenant, valeur.id)


def lire(conn, tenant_id, intention_id) -> dict | None:
    tenant = _tenant(tenant_id)
    with conn.cursor(row_factory=dict_row) as cur:
        ligne = cur.execute(
            f"SELECT {_COLONNES} FROM memoire_prospective "
            "WHERE tenant_id = %s AND id = %s", (tenant, str(intention_id))).fetchone()
    return _ligne(ligne) if ligne is not None else None


def lister(conn, tenant_id, *, statut=None, scope=None, scope_id=None,
           source=None, avant=None, limite=200) -> list[dict]:
    tenant = _tenant(tenant_id)
    conditions = ["tenant_id = %s"]
    parametres: list[Any] = [tenant]
    if statut is not None and str(statut).strip():
        conditions.append("statut = %s")
        parametres.append(domaine._choix(statut, domaine.STATUTS, "statut"))
    if scope is not None and str(scope).strip():
        conditions.append("scope = %s")
        parametres.append(domaine._choix(scope, domaine.SCOPES, "scope"))
    if scope_id is not None and str(scope_id).strip():
        conditions.append("scope_id = %s")
        parametres.append(str(scope_id).strip())
    if source is not None and str(source).strip():
        conditions.append("source = %s")
        parametres.append(str(source).strip())
    if avant is not None and str(avant).strip():
        conditions.append("echeance <= %s")
        parametres.append(_instant(avant, "avant"))
    parametres.append(_limite(limite))
    with conn.cursor(row_factory=dict_row) as cur:
        lignes = cur.execute(
            f"SELECT {_COLONNES} FROM memoire_prospective WHERE "
            + " AND ".join(conditions)
            + " ORDER BY echeance, CASE priorite "
              "WHEN 'critique' THEN 0 WHEN 'haute' THEN 1 "
              "WHEN 'normale' THEN 2 ELSE 3 END, id LIMIT %s",
            tuple(parametres)).fetchall()
    return _lire_ligne(lignes)


def echeances(conn, tenant_id, *, maintenant=None, limite=100) -> list[dict]:
    """Intentions ouvertes dont l'échéance est atteinte, triées par échéance."""
    tenant = _tenant(tenant_id)
    instant = (_instant(maintenant, "maintenant") if maintenant is not None
               else datetime.now(timezone.utc))
    with conn.cursor(row_factory=dict_row) as cur:
        lignes = cur.execute(
            f"SELECT {_COLONNES} FROM memoire_prospective "
            "WHERE tenant_id = %s AND statut IN ('a_faire', 'en_cours') "
            "AND echeance <= %s ORDER BY echeance, CASE priorite "
            "WHEN 'critique' THEN 0 WHEN 'haute' THEN 1 "
            "WHEN 'normale' THEN 2 ELSE 3 END, id LIMIT %s",
            (tenant, instant, _limite(limite))).fetchall()
    return _lire_ligne(lignes)


def _fusion(donnees, cle: str, valeur: Mapping) -> Jsonb:
    charge = dict(donnees or {})
    charge[cle] = dict(valeur)
    return Jsonb(charge)


def clore(conn, tenant_id, intention_id, *, statut="fait", acteur="", motif="") -> dict:
    tenant = _tenant(tenant_id)
    statut = domaine._choix(statut, ("fait", "annule", "expire"), "statut")
    with conn.cursor(row_factory=dict_row) as cur:
        courant = cur.execute(
            "SELECT donnees FROM memoire_prospective WHERE tenant_id = %s AND id = %s",
            (tenant, str(intention_id))).fetchone()
        if courant is None:
            raise MemoireProspectiveInvalide(f"intention introuvable : {intention_id}")
        donnees = _fusion(courant["donnees"], "cloture", {
            "acteur": str(acteur or "").strip(),
            "motif": str(motif or "").strip(),
            "le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        ligne = cur.execute(
            "UPDATE memoire_prospective SET statut = %s, donnees = %s, maj_le = now() "
            "WHERE tenant_id = %s AND id = %s "
            f"RETURNING {_COLONNES}",
            (statut, donnees, tenant, str(intention_id))).fetchone()
    return _ligne(ligne)


def reporter(conn, tenant_id, intention_id, echeance, *, acteur="", motif="") -> dict:
    tenant = _tenant(tenant_id)
    instant = _instant(echeance, "echeance")
    with conn.cursor(row_factory=dict_row) as cur:
        courant = cur.execute(
            "SELECT donnees FROM memoire_prospective WHERE tenant_id = %s AND id = %s",
            (tenant, str(intention_id))).fetchone()
        if courant is None:
            raise MemoireProspectiveInvalide(f"intention introuvable : {intention_id}")
        donnees = _fusion(courant["donnees"], "report", {
            "acteur": str(acteur or "").strip(),
            "motif": str(motif or "").strip(),
            "le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        ligne = cur.execute(
            "UPDATE memoire_prospective SET echeance = %s, donnees = %s, maj_le = now() "
            "WHERE tenant_id = %s AND id = %s "
            f"RETURNING {_COLONNES}",
            (instant, donnees, tenant, str(intention_id))).fetchone()
    return _ligne(ligne)


def purger(conn, tenant_id, *, maintenant=None) -> int:
    """Supprime les intentions closes depuis plus de 90 jours."""
    tenant = _tenant(tenant_id)
    instant = (_instant(maintenant, "maintenant") if maintenant is not None
               else datetime.now(timezone.utc))
    seuil = instant - DUREE_CONSERVATION
    with conn.cursor() as cur:
        lignes = cur.execute(
            "DELETE FROM memoire_prospective WHERE tenant_id = %s "
            "AND statut IN ('fait', 'annule', 'expire') AND maj_le < %s "
            "RETURNING id",
            (tenant, seuil)).fetchall()
    return len(lignes)


def compter(conn, tenant_id, *, statut=None) -> int:
    tenant = _tenant(tenant_id)
    sql = "SELECT count(*) FROM memoire_prospective WHERE tenant_id = %s"
    parametres: list[Any] = [tenant]
    if statut is not None and str(statut).strip():
        sql += " AND statut = %s"
        parametres.append(domaine._choix(statut, domaine.STATUTS, "statut"))
    with conn.cursor() as cur:
        return int(cur.execute(sql, tuple(parametres)).fetchone()[0])
