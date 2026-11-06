"""Backfill du `perimetre_id` des Twins historiques, dérivé de leur `perimetre` libre.

La dérivation est celle du domaine (`slug_perimetre`) : accents retirés, minuscules et séparateurs
`-`. Aucun adapter n'est importé ici ; le cas d'usage ne connaît que la connexion fournie par
l'appelant. L'écriture est strictement additive : `perimetre_id` n'est renseigné que lorsqu'il est
NULL, et un texte de périmètre vide ou sans slug exploitable est ignoré.
"""
from __future__ import annotations

from typing import Any

from meridian.domain import import_identite

__all__ = ["migrer"]


def _tenant(valeur: Any) -> str | None:
    if valeur is None:
        return None
    texte = str(valeur).strip()
    if not texte:
        raise ValueError("tenant ne peut pas être vide")
    return texte


def _limite(valeur: Any) -> int | None:
    if valeur is None:
        return None
    if isinstance(valeur, bool):
        raise ValueError("limite doit être un entier positif")
    try:
        borne = int(valeur)
    except (TypeError, ValueError) as exc:
        raise ValueError("limite doit être un entier positif") from exc
    if borne < 1:
        raise ValueError("limite doit être un entier positif")
    return borne


def migrer(conn, tenant=None, limite=None, *, appliquer: bool = False) -> dict:
    """Compte ou applique le backfill ; deux appels de dry-run rendent le même rapport.

    `a_migrer` et `ids` décrivent le lot effectivement traité (borné par `limite`) ; `valeurs`
    associe chaque identifiant au `perimetre_id` calculé. `ignores` liste les Twins sans slug
    exploitable (périmètre vide ou composé uniquement de séparateurs), qui restent inchangés.
    """
    if not isinstance(appliquer, bool):
        raise TypeError("appliquer doit être un booléen")
    tenant_id = _tenant(tenant)
    borne = _limite(limite)

    conditions = ["perimetre_id IS NULL"]
    parametres: list[object] = []
    if tenant_id is not None:
        conditions.append("tenant_id = %s")
        parametres.append(tenant_id)
    requete = (
        "SELECT id, tenant_id, perimetre, perimetre_id FROM jumeau WHERE "
        + " AND ".join(conditions)
        + " ORDER BY tenant_id, id"
    )
    lignes = conn.execute(requete, parametres).fetchall()

    valeurs: dict[str, str] = {}
    ignores: list[str] = []
    for identifiant, _, perimetre, _ in lignes:
        perimetre_id = import_identite.slug_perimetre(perimetre)
        if not perimetre_id:
            ignores.append(identifiant)
            continue
        valeurs[identifiant] = perimetre_id

    if borne is not None:
        valeurs = dict(list(valeurs.items())[:borne])

    rapport = {
        "dry_run": not appliquer,
        "a_migrer": len(valeurs),
        "migres": 0,
        "ignores": ignores,
        "ids": list(valeurs),
        "valeurs": valeurs,
    }
    if not appliquer:
        return rapport
    for identifiant, perimetre_id in valeurs.items():
        resultat = conn.execute(
            "UPDATE jumeau SET perimetre_id = %s WHERE id = %s AND perimetre_id IS NULL",
            (perimetre_id, identifiant),
        )
        rapport["migres"] += resultat.rowcount
    return rapport
