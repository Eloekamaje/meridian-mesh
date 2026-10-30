"""Persistance du Value Ledger, bornée au tenant.

Le ledger est un bounded context distinct des huit familles : il relie une hypothèse de valeur à une
décision, une initiative ou un outcome. Le dépôt ne calcule pas d'attribution ; il stocke les faits et
les preuves, et rend un résumé qui ne mélange jamais devises et unités.
"""
from __future__ import annotations

from collections.abc import Mapping

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

__all__ = ["ValeurInvalide", "enregistrer", "lire", "lister", "mettre_a_jour", "resume"]

_CHAMPS = (
    "id", "tenant_id", "type", "libelle", "proprietaire", "beneficiaire", "domaine",
    "objet_source_type", "objet_source_id", "baseline", "cible", "observe", "unite", "devise",
    "periode", "attribution", "confiance", "preuves", "fraicheur", "cout", "risque", "statut",
    "date_revue", "donnees", "cree_le", "maj_le",
)
_JSON = frozenset({"baseline", "cible", "observe", "preuves", "fraicheur", "cout", "risque", "donnees"})
_CHAMPS_ECRITURE = tuple(cle for cle in _CHAMPS if cle not in ("cree_le", "maj_le"))


class ValeurInvalide(ValueError):
    """Une ligne de valeur ne respecte pas le contrat du ledger."""


def _texte(valeur, champ, obligatoire=True):
    if valeur is None:
        if obligatoire:
            raise ValeurInvalide(f"{champ} obligatoire")
        return None
    texte = str(valeur).strip()
    if not texte and obligatoire:
        raise ValeurInvalide(f"{champ} obligatoire")
    return texte or None


def _json(valeur):
    if valeur is None:
        return None
    if not isinstance(valeur, (Mapping, list, tuple, int, float, str, bool)):
        raise ValeurInvalide("valeur JSON attendue")
    return valeur


def _ligne(ligne) -> dict:
    return {cle: ligne[cle] for cle in _CHAMPS if cle in ligne}


def _parametres(valeur: Mapping) -> tuple:
    return tuple(
        Jsonb(valeur.get(cle)) if cle in _JSON and valeur.get(cle) is not None else valeur.get(cle)
        for cle in _CHAMPS_ECRITURE
    )


def enregistrer(conn, tenant_id, valeur: Mapping) -> dict:
    """Upsert idempotent d'une ligne de valeur appartenant au tenant."""
    tenant = _texte(tenant_id, "tenant_id")
    if not isinstance(valeur, Mapping):
        raise ValeurInvalide("valeur : objet attendu")
    if _texte(valeur.get("tenant_id") or tenant, "tenant_id") != tenant:
        raise PermissionError("valeur hors tenant")
    identifiant = _texte(valeur.get("id"), "id")
    if not identifiant:
        raise ValeurInvalide("id obligatoire")
    for champ in ("type", "libelle", "proprietaire", "statut"):
        _texte(valeur.get(champ), champ)
    for champ in _JSON:
        _json(valeur.get(champ)) if valeur.get(champ) is not None else None
    champs = ", ".join(_CHAMPS_ECRITURE)
    marques = ", ".join(["%s"] * len(_CHAMPS_ECRITURE))
    mises_a_jour = ", ".join(
        f"{cle} = EXCLUDED.{cle}" for cle in _CHAMPS_ECRITURE
        if cle not in ("tenant_id", "id"))
    requete = (
        f"INSERT INTO valeur ({champs}) VALUES ({marques}) "
        f"ON CONFLICT (tenant_id, id) DO UPDATE SET {mises_a_jour}, maj_le = now() "
        f"RETURNING {champs}")
    donnees = {**dict(valeur), "tenant_id": tenant, "id": identifiant,
               "statut": valeur.get("statut") or "hypothese",
               "attribution": valeur.get("attribution") or "inconnue",
               "confiance": valeur.get("confiance", 0.5),
               "preuves": valeur.get("preuves", []),
               "donnees": valeur.get("donnees", {})}
    with conn.cursor(row_factory=dict_row) as cur:
        ligne = cur.execute(requete, _parametres(donnees)).fetchone()
    return _ligne(ligne)


def lire(conn, tenant_id, valeur_id) -> dict | None:
    tenant = _texte(tenant_id, "tenant_id")
    identifiant = _texte(valeur_id, "id")
    with conn.cursor(row_factory=dict_row) as cur:
        ligne = cur.execute(
            f"SELECT {', '.join(_CHAMPS)} FROM valeur WHERE tenant_id = %s AND id = %s",
            (tenant, identifiant)).fetchone()
    return _ligne(ligne) if ligne is not None else None


def lister(conn, tenant_id, *, statut=None, domaine=None, type_=None,
           proprietaire=None, limite=200) -> list[dict]:
    tenant = _texte(tenant_id, "tenant_id")
    conditions, parametres = ["tenant_id = %s"], [tenant]
    for colonne, valeur in (("statut", statut), ("domaine", domaine), ("type", type_),
                            ("proprietaire", proprietaire)):
        if valeur is not None:
            conditions.append(f"{colonne} = %s")
            parametres.append(_texte(valeur, colonne))
    try:
        borne = max(1, min(int(limite), 1000))
    except (TypeError, ValueError) as exc:
        raise ValeurInvalide("limite invalide") from exc
    parametres.append(borne)
    with conn.cursor(row_factory=dict_row) as cur:
        lignes = cur.execute(
            f"SELECT {', '.join(_CHAMPS)} FROM valeur WHERE " + " AND ".join(conditions) +
            " ORDER BY maj_le DESC, id LIMIT %s", parametres).fetchall()
    return [_ligne(ligne) for ligne in lignes]


def mettre_a_jour(conn, tenant_id, valeur_id, changements: Mapping) -> dict:
    tenant = _texte(tenant_id, "tenant_id")
    identifiant = _texte(valeur_id, "id")
    if not isinstance(changements, Mapping):
        raise ValeurInvalide("changements : objet attendu")
    autorises = {"statut", "observe", "baseline", "cible", "confiance", "preuves",
                 "fraicheur", "cout", "risque", "date_revue", "attribution", "donnees"}
    inconnus = set(changements) - autorises
    if inconnus:
        raise ValeurInvalide(f"champ non modifiable : {sorted(inconnus)[0]}")
    if not changements:
        existant = lire(conn, tenant, identifiant)
        if existant is None:
            raise ValeurInvalide("valeur introuvable")
        return existant
    champs = ", ".join(f"{cle} = %s" for cle in changements)
    parametres = [
        Jsonb(valeur) if cle in _JSON and valeur is not None else valeur
        for cle, valeur in changements.items()
    ]
    with conn.cursor(row_factory=dict_row) as cur:
        ligne = cur.execute(
            f"UPDATE valeur SET {champs}, maj_le = now() "
            f"WHERE tenant_id = %s AND id = %s RETURNING {', '.join(_CHAMPS)}",
            (*parametres, tenant, identifiant)).fetchone()
    if ligne is None:
        raise ValeurInvalide("valeur introuvable")
    return _ligne(ligne)


def _nombre(valeur):
    if isinstance(valeur, Mapping):
        valeur = valeur.get("valeur")
    if isinstance(valeur, bool):
        return None
    try:
        return float(valeur)
    except (TypeError, ValueError):
        return None


def resume(conn, tenant_id, *, domaine=None) -> dict:
    """Résumé sans mélange d'unités/devises : chaque agrégat reste séparé."""
    lignes = lister(conn, tenant_id, domaine=domaine, limite=1000)
    par_statut, par_type = {}, {}
    devises, unites = {}, {}
    dette = 0
    for ligne in lignes:
        statut = ligne.get("statut") or "hypothese"
        type_ = ligne.get("type") or "autre"
        par_statut[statut] = par_statut.get(statut, 0) + 1
        par_type[type_] = par_type.get(type_, 0) + 1
        if statut == "hypothese" or ligne.get("observe") is None:
            dette += 1
        cible = _nombre(ligne.get("cible"))
        observe = _nombre(ligne.get("observe"))
        devise = (ligne.get("devise") or "").upper()
        unite = ligne.get("unite") or ""
        if devise:
            agregat = devises.setdefault(devise, {"attendue": 0.0, "observee": 0.0,
                                                  "valeur_a_risque": 0.0, "entrees": 0})
        elif unite:
            agregat = unites.setdefault(unite, {"attendue": 0.0, "observee": 0.0,
                                                "valeur_a_risque": 0.0, "entrees": 0})
        else:
            continue
        agregat["entrees"] += 1
        if cible is not None:
            agregat["attendue"] += cible
        if observe is not None:
            agregat["observee"] += observe
        if statut == "hypothese" and observe is None and cible is not None:
            confiance = max(0.0, min(1.0, float(ligne.get("confiance") or 0.5)))
            agregat["valeur_a_risque"] += cible * (1 - confiance)
    return {
        "entrees": len(lignes),
        "par_statut": par_statut,
        "par_type": par_type,
        "devises": {cle: {**valeur, "attendue": round(valeur["attendue"], 2),
                          "observee": round(valeur["observee"], 2),
                          "valeur_a_risque": round(valeur["valeur_a_risque"], 2)}
                    for cle, valeur in sorted(devises.items())},
        "unites": {cle: {**valeur, "attendue": round(valeur["attendue"], 2),
                         "observee": round(valeur["observee"], 2),
                         "valeur_a_risque": round(valeur["valeur_a_risque"], 2)}
                   for cle, valeur in sorted(unites.items())},
        "dette_mesure": dette,
        "limites": [
            "les devises et unités ne sont jamais additionnées entre elles",
            "le ledger ne prouve pas la causalité : l'attribution est déclarée",
            "une valeur observée sans baseline reste une mesure, pas une valeur réalisée",
        ],
    }
