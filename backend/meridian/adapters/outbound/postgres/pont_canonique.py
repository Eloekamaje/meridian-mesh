"""Application transactionnelle d'un événement du pont dans le canonique Postgres.

Un événement est appliqué dans **une seule transaction** : si un objet échoue, aucun objet
partiel n'est laissé. La signature HMAC et la provenance sont vérifiées avant toute écriture.
Les objets sont instanciés dans leur dataclass canonique avant d'être écrits, puis comparés à
la version stockée par `source_maj_le` (rejeu tardif) et fusionnés champ par champ (drift
migration ↔ live, liens inverses).

Le worker ne marque l'événement ``done`` qu'après le retour de cette fonction, donc après le
commit. Aucune transaction distribuée Mongo/Postgres n'est tentée.

Politique de hash : ``donnees._pont.hash`` identifie le **payload de l'événement**, pas la
forme fusionnée stockée. Deux événements identiques sautent donc la réécriture même si des
champs de migration ont été conservés par fusion. ``_pont.source_maj_le`` reste l'arbitre de
l'ordre : un événement plus ancien est ignoré, un hash identique ne réécrit pas.
"""
from __future__ import annotations

from collections.abc import Mapping
import copy
from datetime import datetime
import logging
from typing import Any

from meridian.adapters.outbound.postgres import boucle, entreprise_depot, rls
from meridian.application import pont_canonique as pont

__all__ = [
    "ConflitCanonique",
    "ObjetCanoniqueInvalide",
    "TenantMismatch",
    "appliquer",
    "appliquer_evenement",
    "appliquer_pont",
    "origine_objet",
    "valider_objet",
]

journal = logging.getLogger("meridian.pont_canonique.postgres")

ConflitCanonique = pont.ConflitCanonique
TenantMismatch = pont.TenantMismatch


class ObjetCanoniqueInvalide(pont.PontInvalide):
    """L'objet sérialisé ne peut pas être instancié dans sa dataclass canonique."""


_LISTES_FUSIONNEES = frozenset({
    "outcome_ids", "outcome_attendu_ids", "investigation_ids", "twin_ids", "signal_ids",
    "claim_ids", "opportunite_ids", "risk_ids", "preuves", "conditions_applicabilite",
    "reutilisations", "source_ids", "scenarios_rejetes", "approbateur_ids", "expert_ids",
    "hypothesis_ids", "scenario_ids", "controles", "inconnues", "modes",
})


def _donnees(ligne: Any) -> dict[str, Any]:
    if not isinstance(ligne, Mapping):
        return {}
    donnees = ligne.get("donnees")
    return dict(donnees) if isinstance(donnees, Mapping) else {}


def origine_objet(ligne: Any) -> str | None:
    """Origine explicite d'un objet canonique, ou ``None`` s'il n'en porte pas."""
    if not isinstance(ligne, Mapping):
        return None
    donnees = _donnees(ligne)
    pont_donnees = donnees.get("_pont")
    candidates = (
        pont_donnees.get("origine") if isinstance(pont_donnees, Mapping) else None,
        donnees.get("origine"),
        ligne.get("origine"),
    )
    for valeur in candidates:
        if isinstance(valeur, str) and valeur.strip():
            return valeur.strip()
    return None


def _source_objet(ligne: Any) -> dict[str, Any]:
    if not isinstance(ligne, Mapping):
        return {}
    pont_donnees = _donnees(ligne).get("_pont")
    if not isinstance(pont_donnees, Mapping):
        return {}
    source = pont_donnees.get("source")
    return dict(source) if isinstance(source, Mapping) else {}


def _source_maj_objet(ligne: Any) -> str | None:
    if not isinstance(ligne, Mapping):
        return None
    pont_donnees = _donnees(ligne).get("_pont")
    if not isinstance(pont_donnees, Mapping):
        return None
    return pont._iso(pont_donnees.get("source_maj_le"))


def _hash_objet(ligne: Any) -> str | None:
    if not isinstance(ligne, Mapping):
        return None
    pont_donnees = _donnees(ligne).get("_pont")
    if not isinstance(pont_donnees, Mapping):
        return None
    valeur = pont_donnees.get("hash")
    return valeur if isinstance(valeur, str) and valeur else None


def _plus_ancien(gauche: str, droite: str) -> bool:
    try:
        return (datetime.fromisoformat(gauche.replace("Z", "+00:00"))
                < datetime.fromisoformat(droite.replace("Z", "+00:00")))
    except (TypeError, ValueError):
        return gauche < droite


def _origine_compatible(existant: Any, objet: Mapping[str, Any]) -> bool:
    origine = origine_objet(existant)
    if origine:
        normalisee = origine.lower()
        if normalisee == pont.ORIGINE_MIGRATION:
            return True
        if normalisee == pont.ORIGINE_LEGACY:
            source_existante = _source_objet(existant)
            source_nouvelle = _source_objet(objet)
            if source_existante and source_nouvelle:
                return (
                    pont._texte(source_existante.get("collection"))
                    == pont._texte(source_nouvelle.get("collection"))
                    and pont._texte(source_existante.get("id"))
                    == pont._texte(source_nouvelle.get("id"))
                )
            return True
        return False
    donnees = _donnees(existant)
    if str(donnees.get("origine") or "").strip().lower() == pont.ORIGINE_MIGRATION:
        return True
    source_existante = _source_objet(existant)
    source_nouvelle = _source_objet(objet)
    return bool(
        source_existante and source_nouvelle
        and pont._texte(source_existante.get("collection"))
        == pont._texte(source_nouvelle.get("collection"))
        and pont._texte(source_existante.get("id")) == pont._texte(source_nouvelle.get("id"))
    )


def _origine_fiable(ligne: Any) -> bool:
    """Pour un parent mis à jour par un enfant : legacy/migration, jamais un objet API nu."""
    origine = origine_objet(ligne)
    if origine:
        return origine.lower() in {pont.ORIGINE_LEGACY, pont.ORIGINE_MIGRATION}
    if str(_donnees(ligne).get("origine") or "").strip().lower() == pont.ORIGINE_MIGRATION:
        return True
    return bool(_source_objet(ligne))


def _fusionner_donnees(existant: Any, nouveau: Any) -> dict[str, Any]:
    """Fusionne les donnees : le nouveau gagne, les liens/listes sont unis, l'historique est géré par boucle."""
    fusion = copy.deepcopy(dict(existant)) if isinstance(existant, Mapping) else {}
    fusion.pop("_historique", None)
    for cle, valeur in (nouveau or {}).items():
        if cle == "_historique":
            continue
        if cle in _LISTES_FUSIONNEES and isinstance(valeur, list):
            actuels = fusion.get(cle) if isinstance(fusion.get(cle), list) else []
            fusion[cle] = actuels + [element for element in copy.deepcopy(valeur)
                                     if element not in actuels]
        elif isinstance(valeur, Mapping) and isinstance(fusion.get(cle), Mapping):
            fusion[cle] = {**copy.deepcopy(fusion[cle]), **copy.deepcopy(valeur)}
        else:
            fusion[cle] = copy.deepcopy(valeur)
    return fusion


def valider_objet(objet: Any) -> Any:
    """Instancie la dataclass canonique ; refuse Learning sans énoncé, Outcome booléen, etc."""
    if not isinstance(objet, Mapping):
        raise ObjetCanoniqueInvalide("objet canonique attendu")
    identifiant = pont._texte(objet.get("id")) or "?"
    try:
        return boucle._objet_depuis_ligne(objet)
    except Exception as exc:  # noqa: BLE001 - toute invalidité est permanente
        raise ObjetCanoniqueInvalide(
            f"objet canonique invalide {identifiant} : {exc}") from exc


def _doit_ecrire(conn: Any, tenant: str, objet: dict[str, Any],
                 ecrits: list[str], ignores: list[str]) -> bool:
    identifiant = objet["id"]
    existant = entreprise_depot.lire_objet(conn, tenant, identifiant)
    if existant is None:
        valider_objet(objet)
        ecrits.append(identifiant)
        return True
    if not _origine_compatible(existant, objet):
        raise ConflitCanonique(
            f"identifiant canonique {identifiant!r} déjà utilisé sans origine "
            "legacy/migration : le pont n'écrase pas un objet canonique")
    source_maj_existante = _source_maj_objet(existant)
    source_maj_nouvelle = _source_maj_objet(objet)
    if (source_maj_existante and source_maj_nouvelle
            and _plus_ancien(source_maj_nouvelle, source_maj_existante)):
        ignores.append(identifiant)
        journal.info("pont : événement plus ancien ignoré objet=%s source=%s < %s",
                     identifiant, source_maj_nouvelle, source_maj_existante)
        return False
    if _hash_objet(existant) and _hash_objet(existant) == _hash_objet(objet):
        ignores.append(identifiant)
        return False
    objet["donnees"] = _fusionner_donnees(existant.get("donnees"), objet.get("donnees"))
    valider_objet(objet)
    ecrits.append(identifiant)
    return True


def _copie_ligne(ligne: Mapping[str, Any]) -> dict[str, Any]:
    copie = copy.deepcopy(dict(ligne))
    copie.pop("version", None)
    copie.pop("maj_le", None)
    copie.pop("_id", None)
    copie["donnees"] = _donnees(copie)
    return copie


def _ajouter_parent_outcome(conn: Any, tenant: str, objet: dict[str, Any],
                            objets_evenement: list[dict[str, Any]],
                            a_ecrire: list[dict[str, Any]]) -> None:
    if objet.get("type") != "OUTCOME":
        return
    initiative_id = pont._texte((objet.get("donnees") or {}).get("initiative_id"))
    if not initiative_id:
        return
    parent = next((candidat for candidat in a_ecrire
                   if candidat.get("id") == initiative_id), None)
    if parent is None:
        parent = next((candidat for candidat in objets_evenement
                       if candidat.get("id") == initiative_id), None)
    if parent is None:
        ligne = entreprise_depot.lire_objet(conn, tenant, initiative_id)
        if ligne is None:
            return
        parent = _copie_ligne(ligne)
    if not _origine_fiable(parent):
        raise ConflitCanonique(
            f"initiative {initiative_id!r} sans origine legacy/migration : "
            "un Outcome ne modifie pas un objet canonique API")
    parent = copy.deepcopy(parent)
    parent["donnees"] = _fusionner_donnees(
        parent.get("donnees"), {"outcome_ids": [objet["id"]]})
    valider_objet(parent)
    if not any(candidat.get("id") == initiative_id for candidat in a_ecrire):
        a_ecrire.append(parent)


def _appliquer_objets(conn: Any, tenant: str, objets: list[dict[str, Any]],
                       evenement: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    ecrits: list[str] = []
    ignores: list[str] = []
    a_ecrire: list[dict[str, Any]] = []
    for objet in objets:
        if _doit_ecrire(conn, tenant, objet, ecrits, ignores):
            a_ecrire.append(objet)
    for objet in list(a_ecrire):
        if objet.get("type") == "OUTCOME":
            _ajouter_parent_outcome(conn, tenant, objet, objets, a_ecrire)
    if a_ecrire:
        boucle.enregistrer_boucle(
            conn, tenant_id=tenant, objets=a_ecrire, historique=True)
    return ecrits, ignores


def appliquer_evenement(conn: Any, evenement: Mapping[str, Any], *,
                        tenant_id: Any = None, maintenant: Any = None,
                        cle: Any = None) -> dict[str, Any]:
    """Appliquer un événement d'outbox ; vérifie signature, provenance et tenant avant écriture."""
    if not isinstance(evenement, Mapping):
        raise pont.PontInvalide("événement attendu")
    pont.verifier_evenement(evenement, cle)
    pont.verifier_source_evenement(evenement)
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
        # Le GUC est posé systématiquement : sans policy il est sans effet, avec policy il
        # évite les écritures refusées/invisibles quand JUMEAU_RLS n'est pas propagé.
        with rls.contexte_tenant(conn, tenant):
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
