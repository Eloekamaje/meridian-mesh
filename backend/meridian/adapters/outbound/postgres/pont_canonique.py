"""Application transactionnelle d'un événement du pont dans le canonique Postgres.

Un événement est appliqué dans **une seule transaction** : si un objet échoue, aucun objet
partiel n'est laissé. Les vérifications de conflit et de hash sont faites dans la transaction,
avant l'écriture. ``rls.contexte_tenant`` est posé quand RLS est actif.

Le worker ne marque l'événement ``done`` qu'après le retour de cette fonction, donc après le
commit. Aucune transaction distribuée Mongo/Postgres n'est tentée.
"""
from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from meridian.adapters.outbound.postgres import boucle, entreprise_depot, rls
from meridian.application import pont_canonique as pont

__all__ = [
    "ConflitCanonique",
    "TenantMismatch",
    "appliquer",
    "appliquer_evenement",
    "appliquer_pont",
    "origine_objet",
]

journal = logging.getLogger("meridian.pont_canonique.postgres")

ConflitCanonique = pont.ConflitCanonique
TenantMismatch = pont.TenantMismatch


def origine_objet(ligne: Any) -> str | None:
    """Origine explicite d'un objet canonique, ou ``None`` pour un objet legacy sans étiquette."""
    if not isinstance(ligne, Mapping):
        return None
    donnees = ligne.get("donnees")
    pont_donnees = donnees.get("_pont") if isinstance(donnees, Mapping) else None
    candidates = (
        pont_donnees.get("origine") if isinstance(pont_donnees, Mapping) else None,
        donnees.get("origine") if isinstance(donnees, Mapping) else None,
        ligne.get("origine"),
    )
    for valeur in candidates:
        if isinstance(valeur, str) and valeur.strip():
            return valeur.strip()
    return None


def _hash_objet(ligne: Any) -> str | None:
    if not isinstance(ligne, Mapping):
        return None
    donnees = ligne.get("donnees")
    if not isinstance(donnees, Mapping):
        return None
    pont_donnees = donnees.get("_pont")
    if not isinstance(pont_donnees, Mapping):
        return None
    valeur = pont_donnees.get("hash")
    return valeur if isinstance(valeur, str) and valeur else None


def _doit_ecrire(conn: Any, tenant: str, objet: Mapping[str, Any],
                  ecrits: list[str], ignores: list[str]) -> bool:
    identifiant = objet["id"]
    existant = entreprise_depot.lire_objet(conn, tenant, identifiant)
    if existant is None:
        ecrits.append(identifiant)
        return True
    origine = origine_objet(existant)
    if origine and origine.lower() != pont.ORIGINE_LEGACY:
        raise ConflitCanonique(
            f"identifiant canonique {identifiant!r} déjà utilisé avec l'origine {origine!r} : "
            "le pont legacy n'écrase pas un objet canonique")
    nouveau_hash = (objet.get("donnees") or {}).get("_pont", {}).get("hash")
    if nouveau_hash and nouveau_hash == _hash_objet(existant):
        ignores.append(identifiant)
        return False
    ecrits.append(identifiant)
    return True


def _appliquer_objets(conn: Any, tenant: str, objets: list[dict[str, Any]],
                       evenement: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    ecrits: list[str] = []
    ignores: list[str] = []
    a_ecrire = [objet for objet in objets
                if _doit_ecrire(conn, tenant, objet, ecrits, ignores)]
    if a_ecrire:
        boucle.enregistrer_boucle(
            conn, tenant_id=tenant, objets=a_ecrire, historique=True)
    return ecrits, ignores


def appliquer_evenement(conn: Any, evenement: Mapping[str, Any], *,
                        tenant_id: Any = None, maintenant: Any = None) -> dict[str, Any]:
    """Appliquer un événement d'outbox ; lève avant toute écriture si le tenant est invalide."""
    if not isinstance(evenement, Mapping):
        raise pont.PontInvalide("événement attendu")
    tenant = pont.normaliser_tenant(tenant_id or evenement.get("tenant_id"))
    if tenant_id is not None and pont._texte(evenement.get("tenant_id")):
        if pont.normaliser_tenant(evenement["tenant_id"]) != tenant:
            raise TenantMismatch(
                f"événement du tenant {evenement['tenant_id']!r}, attendu {tenant!r}")
    objets = pont.objets_depuis_evenement(
        evenement, tenant_id=tenant, maintenant=maintenant)
    brut_ids = evenement.get("canonical_ids") or []
    canonical_ids = ([brut_ids] if isinstance(brut_ids, str)
                     else [pont._texte(identifiant) for identifiant in brut_ids])
    if not canonical_ids:
        canonical_ids = [objet["id"] for objet in objets]
    identifiant = pont._texte(evenement.get("_id"))

    if not objets:
        return {
            "evenement_id": identifiant,
            "tenant": tenant,
            "canonical_ids": canonical_ids,
            "ecrits": [],
            "ignores": [],
        }

    with conn.transaction():
        if rls.est_actif():
            with rls.contexte_tenant(conn, tenant):
                ecrits, ignores = _appliquer_objets(conn, tenant, objets, evenement)
        else:
            ecrits, ignores = _appliquer_objets(conn, tenant, objets, evenement)

    journal.info(
        "pont appliqué evenement=%s tenant=%s objets=%d ecrits=%d ignores=%d",
        identifiant, tenant, len(objets), len(ecrits), len(ignores))
    return {
        "evenement_id": identifiant,
        "tenant": tenant,
        "canonical_ids": canonical_ids,
        "ecrits": ecrits,
        "ignores": ignores,
    }


appliquer = appliquer_evenement
appliquer_pont = appliquer_evenement
