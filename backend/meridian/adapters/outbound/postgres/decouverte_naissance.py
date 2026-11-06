"""Découverte des liens à la naissance et réconciliation globale.

Deux chemins, un même moteur :

- `traiter_twin_born` : découverte **locale bornée** au `twin.born` ;
- `reconcilier` : découverte **globale** du tenant, périodique ou événementielle.

Le handler de naissance exécute d'abord le résolveur historique (matching exact et
ressources), puis le moteur de composants. Aucun lien n'est confirmé ; aucun agent
n'est appelé ici.
"""
from __future__ import annotations

from meridian.adapters.outbound.connectors import cbm_liens
from meridian.adapters.outbound.postgres import code_index_store
from meridian.adapters.outbound.postgres import decouverte_liens as decouverte_pg
from meridian.adapters.outbound.postgres import relations_naissance as relations_pg
from meridian.application import moteur_liens
from meridian.domain.decouverte_liens import ResolutionCase
from meridian.domain.naissance_relationnelle import ManifesteNaissance

__all__ = ["reconcilier", "reconcilier_twin", "traiter_twin_born"]


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


def _extractions_code(conn, manifests) -> tuple[list, list[str]]:
    """Observations CBM persistées → une extraction par Twin.

    C'est la source principale pour les routes et les appels HTTP. Les manifestes
    restent la déclaration ; le code apporte la preuve. Une observation orpheline,
    dont le Twin n'a plus de manifeste, est ignorée plutôt que de créer un composant
    fantôme.
    """
    par_twin = {manifeste.twin_id: manifeste for manifeste in manifests}
    if not par_twin:
        return [], []
    lignes, tronque = code_index_store.lire_observations_liens(
        conn, manifests[0].tenant_id, tuple(par_twin))
    groupes: dict[str, list] = {}
    for twin_id, observation in lignes:
        groupes.setdefault(twin_id, []).append(observation)
    extractions = [
        cbm_liens.extraire_observations(
            groupes[twin_id], manifeste.application_id or twin_id, twin_id,
            # Le code n'est pas rattaché à un environnement par l'index : le moteur
            # traite « inconnu » comme compatible, sans prétendre connaître le déploiement.
            "inconnu", owner=manifeste.owner, type_composant=manifeste.type)
        for twin_id, manifeste in par_twin.items() if twin_id in groupes
    ]
    diagnostics = []
    if tronque:
        diagnostics.append(
            "observations de liens tronquées à "
            f"{code_index_store.LIMITE_LIENS} lignes : la découverte reste partielle")
    return extractions, diagnostics


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


def _persister(conn, tenant_id: str, rapport, owners: dict[str, str], *,
               appliquer: bool = True, filtrer_twin: str = "") -> dict:
    propositions: list[str] = []
    cas: list[str] = []
    non_eligibles: list[str] = []
    for lien in rapport.liens:
        if lien.nature != "mesh":
            continue
        if lien.eligible:
            proposition = moteur_liens.vers_proposition(lien, tenant_id, owners=owners)
            if appliquer:
                relations_pg.enregistrer_proposition(conn, proposition)
            propositions.append(proposition.id)
            continue
        if not lien.missing_evidence:
            continue
        if filtrer_twin:
            responsable = (lien.consommateur_composant_id
                           if lien.consommateur_composant_id == filtrer_twin
                           else lien.fournisseur_composant_id)
        else:
            responsable = lien.consommateur_composant_id
        case = _case_de_frontiere(lien, tenant_id, owners, responsable)
        if appliquer:
            decouverte_pg.enregistrer_resolution_case(conn, case)
        cas.append(case.id)
        non_eligibles.append(lien.id)

    for question in rapport.questions:
        if filtrer_twin and question.composant_id != filtrer_twin:
            continue
        twin_id = question.composant_id or filtrer_twin or "inconnu"
        case = moteur_liens.vers_resolution_case(
            question, tenant_id, twin_id,
            owner=owners.get(question.application_id, ""))
        if appliquer:
            decouverte_pg.enregistrer_resolution_case(conn, case)
        cas.append(case.id)

    return {
        "propositions": len(dict.fromkeys(propositions)),
        "cas": len(dict.fromkeys(cas)),
        "non_eligibles": list(dict.fromkeys(non_eligibles)),
        "liens": len(rapport.liens),
        "questions": len(rapport.questions),
        "diagnostics": list(rapport.diagnostics),
    }


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

    extractions_code, diagnostics_code = _extractions_code(conn, manifests)
    rapport = moteur_liens.moteur_liens([
        *moteur_liens.extractions_depuis_manifests(manifests, bindings),
        *extractions_code,
    ])
    local = moteur_liens.filtrer_local(rapport, manifeste.twin_id)
    resultat = _persister(conn, manifeste.tenant_id, local, owners,
                          appliquer=True, filtrer_twin=manifeste.twin_id)

    return {
        "propositions": historique["propositions"] + resultat["propositions"],
        "historique": historique["propositions"],
        "decouverte": resultat["propositions"],
        "cas": resultat["cas"],
        "non_eligibles": resultat["non_eligibles"],
        "liens_locaux": resultat["liens"],
        "questions_locales": resultat["questions"],
        "diagnostics": [*resultat["diagnostics"], *diagnostics_code],
    }


def reconcilier_twin(conn, tenant_id: str, twin_id: str) -> dict:
    """Relance la découverte locale d'un Twin après un changement de code.

    C'est le chemin incrémental : l'ingestion d'un dépôt rafraîchit les liens du Twin
    concerné sans lancer la réconciliation globale. Un Twin sans manifeste est ignoré.
    """
    manifeste = next(
        (candidat for candidat in relations_pg.lire_manifestes(conn, tenant_id)
         if candidat.twin_id == twin_id), None)
    if manifeste is None:
        return {"statut": "ignore", "raison": "manifeste de naissance absent"}
    return {"statut": "decouvert", **traiter_twin_born(conn, manifeste.as_dict())}


def reconcilier(conn, tenant_id: str, *, appliquer: bool = True,
                limite: int | None = None) -> dict:
    """Réconcilie tous les Twins d'un tenant, sans broadcast ni confirmation."""
    manifests = relations_pg.lire_manifestes(conn, tenant_id)
    if limite is not None:
        manifests = manifests[:max(1, int(limite))]
    bindings = decouverte_pg.lire_bindings(conn, tenant_id)
    owners = _proprietaires(manifests)
    extractions_code, diagnostics_code = _extractions_code(conn, manifests)
    rapport = moteur_liens.moteur_liens([
        *moteur_liens.extractions_depuis_manifests(manifests, bindings),
        *extractions_code,
    ])
    resultat = _persister(conn, tenant_id, rapport, owners, appliquer=appliquer)
    return {
        "dry_run": not appliquer,
        "twins": len(manifests),
        "propositions": resultat["propositions"],
        "cas": resultat["cas"],
        "non_eligibles": resultat["non_eligibles"],
        "liens": resultat["liens"],
        "questions": resultat["questions"],
        "diagnostics": [*resultat["diagnostics"], *diagnostics_code],
    }
