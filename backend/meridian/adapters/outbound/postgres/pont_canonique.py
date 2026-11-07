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


ACTEURS_NON_HUMAINS = frozenset({
    "robot", "system", "système", "systeme", "automate", "auto", "legacy", "machine",
})


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


def _plus_recent(gauche: str, droite: str) -> bool:
    """Vrai si `gauche` est strictement plus récent que `droite`.

    Une égalité n'est jamais « plus récent » : deux événements au même timestamp sont
    départagés par l'ordre d'arrivée, jamais par « dernier écrivain gagne ».
    """
    try:
        return (datetime.fromisoformat(gauche.replace("Z", "+00:00"))
                > datetime.fromisoformat(droite.replace("Z", "+00:00")))
    except (TypeError, ValueError):
        return gauche > droite


def _origine_compatible(existant: Any, objet: Mapping[str, Any]) -> bool:
    origine = origine_objet(existant)
    source_existante = _source_objet(existant)
    source_nouvelle = _source_objet(objet)
    collection_nouvelle = pont._texte(source_nouvelle.get("collection"))

    if collection_nouvelle == "pont_interne":
        # Un producteur interne peut corriger un objet legacy, jamais un objet migré/API.
        return bool(origine and origine.lower() == pont.ORIGINE_LEGACY)

    # Une Initiative déjà matérialisée par la Situation et une Initiative issue d'une
    # proposition legacy partagent le même ID `ini-{decision_id}` : c'est la même action.
    if (pont._texte((existant or {}).get("type")).upper() == "INITIATIVE"
            and pont._texte(objet.get("type")).upper() == "INITIATIVE"):
        decision_existante = pont._texte(_donnees(existant).get("decision_id"))
        decision_nouvelle = pont._texte((objet.get("donnees") or {}).get("decision_id"))
        source_legacy = bool(
            (origine and origine.lower() in {
                pont.ORIGINE_LEGACY, pont.ORIGINE_MIGRATION, pont.ORIGINE_EXPLOITATION})
            or source_existante)
        if source_legacy and decision_existante and decision_existante == decision_nouvelle:
            return True

    if origine:
        normalisee = origine.lower()
        if normalisee not in {
                pont.ORIGINE_LEGACY, pont.ORIGINE_MIGRATION, pont.ORIGINE_EXPLOITATION}:
            return False
        if normalisee == pont.ORIGINE_EXPLOITATION:
            # B est un écrivain canonique de confiance : sa source `exploitation/<id>`
            # ne coïncide pas avec la source legacy du parent qu'il met à jour.
            return True
        if not source_existante:
            # Objets écrits par une version antérieure du pont, sans source mémorisée.
            return True
        if source_nouvelle:
            return (
                pont._texte(source_existante.get("collection"))
                == pont._texte(source_nouvelle.get("collection"))
                and pont._texte(source_existante.get("id"))
                == pont._texte(source_nouvelle.get("id"))
            )
        return False

    if str(_donnees(existant).get("origine") or "").strip().lower() == pont.ORIGINE_MIGRATION:
        return bool(
            source_existante and source_nouvelle
            and pont._texte(source_existante.get("collection"))
            == collection_nouvelle
            and pont._texte(source_existante.get("id"))
            == pont._texte(source_nouvelle.get("id"))
        )
    if source_existante and source_nouvelle:
        return (
            pont._texte(source_existante.get("collection")) == collection_nouvelle
            and pont._texte(source_existante.get("id"))
            == pont._texte(source_nouvelle.get("id"))
        )
    return False


def _origine_fiable(ligne: Any) -> bool:
    """Pour un parent mis à jour par un enfant : legacy/migration, jamais un objet API nu."""
    origine = origine_objet(ligne)
    if origine:
        return origine.lower() in {
            pont.ORIGINE_LEGACY, pont.ORIGINE_MIGRATION, pont.ORIGINE_EXPLOITATION}
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
        instance = boucle._objet_depuis_ligne(objet)
    except Exception as exc:  # noqa: BLE001 - toute invalidité est permanente
        raise ObjetCanoniqueInvalide(
            f"objet canonique invalide {identifiant} : {exc}") from exc
    if getattr(instance, "type", "") == "DECISION" and \
            getattr(instance, "statut", "") == "DECIDED":
        acteur = str(getattr(instance, "acteur", "") or "").strip()
        if not acteur or acteur.casefold() in ACTEURS_NON_HUMAINS:
            raise ObjetCanoniqueInvalide(
                f"décision {identifiant} DECIDED sans acteur humain vérifiable")
    return instance


def _doit_ecrire(conn: Any, tenant: str, objet: dict[str, Any],
                 ecrits: list[str], ignores: list[str]) -> bool:
    identifiant = objet["id"]
    existant = entreprise_depot.lire_objet(conn, tenant, identifiant)
    if existant is None:
        valider_objet(objet)
        ecrits.append(identifiant)
        return True
    source_maj_existante = _source_maj_objet(existant)
    source_maj_nouvelle = _source_maj_objet(objet)
    if source_maj_existante and not source_maj_nouvelle:
        raise pont.PontInvalide(
            f"objet {identifiant!r} : source_maj_le absente face à une version datée")
    # Un snapshot plus ancien est ignoré AVANT le jugement d'origine : une ancre stale
    # d'un producteur non legacy ne doit pas partir en dead-letter ni perdre les décisions
    # du case qu'elle accompagne.
    if (source_maj_existante and source_maj_nouvelle
            and not _plus_recent(source_maj_nouvelle, source_maj_existante)):
        ignores.append(identifiant)
        journal.info("pont : événement non plus récent ignoré objet=%s source=%s <= %s",
                     identifiant, source_maj_nouvelle, source_maj_existante)
        return False
    if not _origine_compatible(existant, objet):
        raise ConflitCanonique(
            f"identifiant canonique {identifiant!r} déjà écrit par une autre "
            "origine/source : le pont n'écrase pas cet objet")
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
                            a_ecrire: list[dict[str, Any]],
                            ecrits: list[str]) -> None:
    if objet.get("type") != "OUTCOME":
        return
    initiative_id = pont._texte((objet.get("donnees") or {}).get("initiative_id"))
    if not initiative_id:
        return
    parent = next((candidat for candidat in a_ecrire
                   if candidat.get("id") == initiative_id), None)
    if parent is None:
        # Toujours relire la ligne Postgres : le parent peut avoir été ignoré par le filtre
        # de hash/staleness et contenir des champs de migration à ne pas perdre.
        ligne = entreprise_depot.lire_objet(conn, tenant, initiative_id, for_update=True)
        if ligne is None:
            return
        parent = _copie_ligne(ligne)
        if not _origine_fiable(parent):
            raise ConflitCanonique(
                f"initiative {initiative_id!r} sans origine legacy/migration/exploitation : "
                "un Outcome ne modifie pas un objet canonique API")
        parent["donnees"] = _fusionner_donnees(
            parent.get("donnees"), {"outcome_ids": [objet["id"]]})
        valider_objet(parent)
        a_ecrire.append(parent)
        ecrits.append(initiative_id)
        return
    parent["donnees"] = _fusionner_donnees(
        parent.get("donnees"), {"outcome_ids": [objet["id"]]})


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
            _ajouter_parent_outcome(conn, tenant, objet, a_ecrire, ecrits)
    if a_ecrire:
        boucle.enregistrer_boucle(
            conn, tenant_id=tenant, objets=a_ecrire, historique=True)
    return ecrits, ignores


def appliquer_evenement(conn: Any, evenement: Mapping[str, Any], *,
                        tenant_id: Any = None, maintenant: Any = None,
                        cle: Any = None, cle_interne: Any = None) -> dict[str, Any]:
    """Appliquer un événement d'outbox ; vérifie signature, provenance et tenant avant écriture."""
    if not isinstance(evenement, Mapping):
        raise pont.PontInvalide("événement attendu")
    pont.verifier_evenement(
        evenement, pont.cle_pour_evenement(evenement, cle, cle_interne))
    pont.verifier_source_evenement(evenement, maintenant=maintenant)
    tenant = pont.normaliser_tenant(tenant_id or evenement.get("tenant_id"))
    if tenant_id is not None and pont._texte(evenement.get("tenant_id")):
        if pont.normaliser_tenant(evenement["tenant_id"]) != tenant:
            raise TenantMismatch(
                f"événement du tenant {evenement['tenant_id']!r}, attendu {tenant!r}")
    objets = pont.objets_depuis_evenement(
        evenement, tenant_id=tenant, maintenant=maintenant)
    operation = pont.normaliser_operation(evenement.get("operation"))
    canonical_id = pont._texte(evenement.get("canonical_id"))
    ids_objets = {objet["id"] for objet in objets}
    if operation in {pont.OPERATION_OBJETS, pont.OPERATION_OUTCOME,
                     pont.OPERATION_LEARNING} and canonical_id not in ids_objets:
        raise pont.PontInvalide(
            f"canonical_id {canonical_id!r} absent des objets construits "
            f"{sorted(ids_objets)!r}")
    # Les IDs retournés sont ceux réellement construits, pas ceux déclarés par l'émetteur.
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
        # Un événement Situation globalement plus ancien/égal est ignoré en bloc : sinon une
        # sous-partie manquante (Investigation) serait créée alors que la Situation est stale.
        if operation == pont.OPERATION_SITUATION:
            situation = next((objet for objet in objets
                              if objet.get("type") == "SITUATION"), None)
            if situation is not None:
                existant = entreprise_depot.lire_objet(conn, tenant, situation["id"])
                source_maj_existante = _source_maj_objet(existant)
                source_maj_evenement = pont._iso(evenement.get("source_maj_le"))
                if (source_maj_existante and source_maj_evenement
                        and not _plus_recent(source_maj_evenement, source_maj_existante)):
                    journal.info(
                        "pont : événement Situation non plus récent ignoré en bloc "
                        "objet=%s source=%s <= %s", situation["id"],
                        source_maj_evenement, source_maj_existante)
                    return {
                        "evenement_id": identifiant,
                        "tenant": tenant,
                        "canonical_ids": canonical_ids,
                        "ecrits": [],
                        "ignores": list(canonical_ids),
                    }
        # Verrou consultatif par (tenant, canonical_id) : deux workers qui auraient tous deux
        # passé le pré-check de bail sérialisent leur application ; le second relit l'état
        # et sera ignoré par source_maj/hash.
        for objet_id in sorted(ids_objets):
            conn.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s), hashtext(%s))",
                (tenant, objet_id))
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
