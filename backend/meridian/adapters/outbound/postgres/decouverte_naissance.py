"""Découverte locale à la naissance : `twin.born` → liens et cas.

La naissance déclenche une découverte **locale bornée** : le nouveau Twin ne paie pas
la réconciliation globale. Le handler :

1. exécute d'abord le résolveur historique (matching exact et ressources) ;
2. construit les entrées du moteur depuis les manifestes et bindings ;
3. ne garde que les liens et questions où le Twin naissant est impliqué ;
4. persiste les propositions éligibles et les cas non résolus.

Aucun lien n'est confirmé. Aucun agent n'est appelé ici.
"""
from __future__ import annotations

from meridian.adapters.outbound.postgres import decouverte_liens as decouverte_pg
from meridian.adapters.outbound.postgres import relations_naissance as relations_pg
from meridian.application import moteur_liens
from meridian.domain.decouverte_liens import ResolutionCase
from meridian.domain.naissance_relationnelle import ManifesteNaissance

__all__ = ["traiter_twin_born"]


def _manifeste(payload) -> ManifesteNaissance:
    if isinstance(payload, ManifesteNaissance):
        return payload
    return ManifesteNaissance.depuis_dict(payload)


def _proprietaires(manifests) -> dict[str, str]:
    proprietaires = {}
    for manifeste in manifests:
        proprietaires[manifeste.twin_id] = manifeste.owner
        if manifeste.application_id:
            proprietaires[manifeste.application_id] = manifeste.owner
    return proprietaires


def _case_de_frontiere(lien, tenant_id: str, owners: dict[str, str],
                       twin_id: str) -> ResolutionCase:
    """Un lien mesh non éligible reste visible comme question de frontière."""
    application_id = (lien.consommateur_application_id
                      if twin_id == lien.consommateur_composant_id
                      else lien.fournisseur_application_id)
    return ResolutionCase(
        tenant_id=tenant_id, twin_id=twin_id,
        reference=f"frontière: {lien.operation}", environment=lien.environment,
        missing_evidence=lien.missing_evidence or "portée de l'interface non établie",
        next_check=lien.next_check or "identifier la frontière de l'interface",
        owner=owners.get(twin_id) or owners.get(application_id, ""),
        evidence_ids=tuple(preuve.locator for preuve in lien.preuves),
        candidates=(
            {"composant_id": lien.fournisseur_composant_id,
             "application_id": lien.fournisseur_application_id,
             "operation": lien.operation,
             "service": lien.fournisseur_service},
        ),
    )


def traiter_twin_born(conn, payload) -> dict:
    """Consommateur idempotent de `twin.born` : découverte locale bornée."""
    manifeste = _manifeste(payload)
    # Le résolveur historique reste actif : il couvre le matching exact et les ressources.
    historique = relations_pg.traiter_twin_born(conn, manifeste.as_dict())

    manifests = relations_pg.lire_manifestes(conn, manifeste.tenant_id)
    if not any(candidat.twin_id == manifeste.twin_id for candidat in manifests):
        manifests.append(manifeste)
    bindings = decouverte_pg.lire_bindings(conn, manifeste.tenant_id)
    owners = _proprietaires(manifests)

    rapport = moteur_liens.moteur_liens(
        moteur_liens.extractions_depuis_manifests(manifests, bindings))
    local = moteur_liens.filtrer_local(rapport, manifeste.twin_id)

    propositions: list[str] = []
    cas: list[str] = []
    non_eligibles: list[str] = []
    for lien in local.liens:
        if lien.nature != "mesh":
            continue
        if lien.eligible:
            proposition = moteur_liens.vers_proposition(lien, manifeste.tenant_id,
                                                         owners=owners)
            relations_pg.enregistrer_proposition(conn, proposition)
            propositions.append(proposition.id)
            continue
        if lien.missing_evidence:
            responsable = (lien.consommateur_composant_id
                           if lien.consommateur_composant_id == manifeste.twin_id
                           else lien.fournisseur_composant_id)
            case = _case_de_frontiere(lien, manifeste.tenant_id, owners, responsable)
            decouverte_pg.enregistrer_resolution_case(conn, case)
            cas.append(case.id)
            non_eligibles.append(lien.id)

    for question in local.questions:
        if question.composant_id != manifeste.twin_id:
            continue
        case = moteur_liens.vers_resolution_case(
            question, manifeste.tenant_id, manifeste.twin_id,
            owner=owners.get(question.application_id, manifeste.owner))
        decouverte_pg.enregistrer_resolution_case(conn, case)
        cas.append(case.id)

    return {
        "propositions": historique["propositions"] + len(dict.fromkeys(propositions)),
        "historique": historique["propositions"],
        "decouverte": len(dict.fromkeys(propositions)),
        "cas": len(dict.fromkeys(cas)),
        "non_eligibles": list(dict.fromkeys(non_eligibles)),
        "liens_locaux": len(local.liens),
        "questions_locales": len(local.questions),
        "diagnostics": list(local.diagnostics),
    }
