"""Calibration des croyances : confiance annoncée contre outcome observé.

Le Brier et les tranches ne portent que sur les croyances résolues. Une croyance non résolue reste
hors mesure ; une résolution met à jour la calibration, pas silencieusement la croyance.
"""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import math

from psycopg.rows import dict_row

__all__ = [
    "CalibrationCroyanceInvalide",
    "enregistrer",
    "enregistrer_dossier",
    "enregistrer_dsn",
    "lister",
    "rapport",
    "rapport_dsn",
    "resoudre",
    "resoudre_dsn",
]


class CalibrationCroyanceInvalide(ValueError):
    """Une croyance ou un outcome ne respecte pas le contrat de calibration."""


def _texte(valeur, maximum=200) -> str:
    return " ".join(str(valeur or "").split())[:maximum]


def _tenant(valeur) -> str:
    texte = _texte(valeur, 128)
    if not texte:
        raise CalibrationCroyanceInvalide("tenant obligatoire")
    return texte


def _confiance(valeur) -> float:
    if isinstance(valeur, bool):
        raise CalibrationCroyanceInvalide("confiance doit être un nombre entre 0 et 1")
    try:
        nombre = float(valeur)
    except (TypeError, ValueError) as exc:
        raise CalibrationCroyanceInvalide("confiance invalide") from exc
    if not math.isfinite(nombre) or not 0 <= nombre <= 1:
        raise CalibrationCroyanceInvalide("confiance doit être un nombre entre 0 et 1")
    return nombre


def _outcome(valeur) -> bool:
    if not isinstance(valeur, bool):
        raise CalibrationCroyanceInvalide("outcome doit être un booléen")
    return valeur


def _belief_id(belief) -> str:
    if isinstance(belief, Mapping):
        return _texte(belief.get("id"), 80)
    return _texte(getattr(belief, "id", ""), 80)


def _confidence(belief) -> float:
    if isinstance(belief, Mapping):
        return _confiance(belief.get("confiance", 0.5))
    return _confiance(getattr(belief, "confiance", 0.5))


def _statut(belief) -> str:
    if isinstance(belief, Mapping):
        return _texte(belief.get("statut") or "INCONNU", 20).upper()
    return _texte(getattr(belief, "statut", "INCONNU"), 20).upper()


def _identifiant(tenant: str, dossier_id: str, belief_id: str) -> str:
    charge = f"{tenant}:{dossier_id}:{belief_id}"
    return "cal-" + hashlib.sha256(charge.encode("utf-8")).hexdigest()[:24]


def enregistrer(conn, tenant: str, dossier_id: str, belief) -> dict:
    """Enregistre une prédiction de croyance, idempotente par (tenant, dossier, belief)."""
    tenant = _tenant(tenant)
    dossier = _texte(dossier_id, 128)
    identifiant = _belief_id(belief)
    if not dossier or not identifiant:
        raise CalibrationCroyanceInvalide("dossier_id et belief_id obligatoires")
    cal_id = _identifiant(tenant, dossier, identifiant)
    with conn.cursor(row_factory=dict_row) as cur:
        ligne = cur.execute(
            "INSERT INTO belief_calibration "
            "(id, tenant_id, dossier_id, belief_id, confidence, predicted_statut) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (id) DO UPDATE SET confidence = EXCLUDED.confidence, "
            "predicted_statut = EXCLUDED.predicted_statut "
            "WHERE belief_calibration.tenant_id = EXCLUDED.tenant_id "
            "AND belief_calibration.outcome IS NULL "
            "RETURNING *",
            (cal_id, tenant, dossier, identifiant, _confidence(belief), _statut(belief)),
        ).fetchone()
    return dict(ligne) if ligne else {}


def enregistrer_dossier(conn, tenant: str, dossier_id: str, dossier) -> list[dict]:
    beliefs = dossier.get("beliefs") if isinstance(dossier, Mapping) else getattr(dossier, "beliefs", ())
    return [enregistrer(conn, tenant, dossier_id, belief) for belief in (beliefs or ())]


def resoudre(conn, tenant: str, dossier_id: str, belief_id: str, outcome: bool) -> dict | None:
    tenant = _tenant(tenant)
    outcome = _outcome(outcome)
    identifiant = _identifiant(tenant, _texte(dossier_id, 128), _texte(belief_id, 80))
    with conn.cursor(row_factory=dict_row) as cur:
        ligne = cur.execute(
            "UPDATE belief_calibration SET outcome = %s, resolue_le = now() "
            "WHERE tenant_id = %s AND id = %s RETURNING *",
            (outcome, tenant, identifiant),
        ).fetchone()
    return dict(ligne) if ligne else None


def lister(conn, tenant: str, *, dossier_id: str | None = None, limite: int = 200) -> list[dict]:
    tenant = _tenant(tenant)
    borne = max(1, min(int(limite), 1000))
    with conn.cursor(row_factory=dict_row) as cur:
        if dossier_id:
            lignes = cur.execute(
                "SELECT * FROM belief_calibration WHERE tenant_id = %s AND dossier_id = %s "
                "ORDER BY cree_le DESC LIMIT %s",
                (tenant, _texte(dossier_id, 128), borne),
            ).fetchall()
        else:
            lignes = cur.execute(
                "SELECT * FROM belief_calibration WHERE tenant_id = %s ORDER BY cree_le DESC LIMIT %s",
                (tenant, borne),
            ).fetchall()
    return [dict(ligne) for ligne in lignes]


def _brier(lignes) -> float | None:
    valeurs = []
    for ligne in lignes:
        if ligne.get("outcome") is None:
            continue
        valeurs.append((float(ligne["confidence"]) - (1.0 if ligne["outcome"] else 0.0)) ** 2)
    return round(sum(valeurs) / len(valeurs), 4) if valeurs else None


def rapport(conn, tenant: str) -> dict:
    tenant = _tenant(tenant)
    lignes = lister(conn, tenant, limite=1000)
    resolues = [ligne for ligne in lignes if ligne.get("outcome") is not None]
    tranches = []
    for debut, fin in ((0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0)):
        tranche = [
            ligne for ligne in resolues
            if debut <= float(ligne["confidence"]) < fin
            or (fin == 1.0 and float(ligne["confidence"]) == 1.0)
        ]
        if tranche:
            tranches.append({
                "debut": debut, "fin": fin, "n": len(tranche),
                "confiance_moyenne": round(
                    sum(float(ligne["confidence"]) for ligne in tranche) / len(tranche), 3),
                "taux_observe": round(
                    sum(1 for ligne in tranche if ligne["outcome"]) / len(tranche), 3),
            })
    return {
        "tenant": tenant,
        "total": len(lignes),
        "resolues": len(resolues),
        "en_attente": len(lignes) - len(resolues),
        "brier": _brier(lignes),
        "tranches": tranches,
    }


def enregistrer_dsn(dsn: str, tenant: str, dossier_id: str, dossier) -> list[dict]:
    import psycopg

    with psycopg.connect(dsn, connect_timeout=5) as conn:
        with conn.transaction():
            return enregistrer_dossier(conn, tenant, dossier_id, dossier)


def resoudre_dsn(dsn: str, tenant: str, dossier_id: str, belief_id: str, outcome: bool) -> dict | None:
    import psycopg

    with psycopg.connect(dsn, connect_timeout=5) as conn:
        with conn.transaction():
            return resoudre(conn, tenant, dossier_id, belief_id, outcome)


def rapport_dsn(dsn: str, tenant: str) -> dict:
    import psycopg

    with psycopg.connect(dsn, connect_timeout=5) as conn:
        return rapport(conn, tenant)
