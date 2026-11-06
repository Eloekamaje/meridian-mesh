"""Persistance des bindings de configuration et des cas de résolution.

Les bindings sont des artefacts déclarés, pas des vérités : chaque ligne garde sa source, son
environnement et ses preuves. Un cas non résolu est un objet `UNKNOWN` durable, consultable
et reprenable.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from psycopg.rows import dict_row

from meridian.adapters.outbound.postgres import entreprise_depot
from meridian.adapters.outbound.postgres import relations_naissance as relations_pg
from meridian.application import decouverte_liens as resolution
from meridian.domain.decouverte_liens import Binding, ResolutionCase
from meridian.domain.naissance_relationnelle import Consommation, PropositionRelation

_FAMILLE_BINDING = "sources_preuves"
_TYPE_BINDING = "ARTIFACT"
_FAMILLE_CASE = "connaissance"
_TYPE_CASE = "UNKNOWN"


def _identifiant_binding(tenant_id: str, binding: Binding) -> str:
    return f"binding-{tenant_id}-{binding.kind.lower()}-{binding.nom.lower()}-{binding.environment}".replace(" ", "-")[:200]


def enregistrer_binding(conn, tenant_id: str, binding: Binding) -> dict:
    binding = binding if isinstance(binding, Binding) else Binding.depuis_dict(binding)
    return entreprise_depot.enregistrer_objet(conn, tenant_id, {
        "id": _identifiant_binding(tenant_id, binding),
        "famille": _FAMILLE_BINDING, "type": _TYPE_BINDING, "mode": "DECLARED",
        "titre": f"Binding {binding.kind} — {binding.nom}",
        "donnees": {"kind": "binding", "binding": binding.as_dict()},
    })


def lire_bindings(conn, tenant_id: str, *, environment: str | None = None,
                  limite: int = 1000) -> list[Binding]:
    objets = entreprise_depot.lister_objets(
        conn, tenant_id, famille=_FAMILLE_BINDING, type_=_TYPE_BINDING, limite=limite)
    sortie = []
    for objet in objets:
        donnees = objet.get("donnees") or {}
        if donnees.get("kind") != "binding":
            continue
        try:
            binding = Binding.depuis_dict(donnees.get("binding") or donnees)
        except ValueError:
            continue
        if environment and binding.environment not in (environment, "inconnu"):
            continue
        sortie.append(binding)
    return sortie


def enregistrer_resolution_case(conn, case: ResolutionCase) -> dict:
    return entreprise_depot.enregistrer_objet(conn, case.tenant_id, {
        "id": case.id, "famille": _FAMILLE_CASE, "type": _TYPE_CASE, "mode": "PROPOSED",
        "titre": f"Résolution ouverte — {case.reference}",
        "donnees": case.as_dict(),
    })


def lire_resolution_case(conn, tenant_id: str, case_id: str) -> ResolutionCase:
    objet = entreprise_depot.lire_objet(conn, tenant_id, case_id)
    if objet is None:
        raise LookupError("cas de résolution introuvable")
    donnees = objet.get("donnees") or {}
    if donnees.get("kind") != "resolution_case":
        raise LookupError("cet objet n'est pas un cas de résolution")
    return ResolutionCase.depuis_dict(donnees)


def contexte_investigation(conn, tenant_id: str, case_id: str):
    case = lire_resolution_case(conn, tenant_id, case_id)
    return case, lire_bindings(conn, tenant_id, environment=case.environment), \
        relations_pg.lire_manifestes(conn, tenant_id)


def lister_resolution_cases(conn, tenant_id: str, *, twin_id: str | None = None,
                            status: str | None = None, limite: int = 1000) -> list[dict]:
    objets = entreprise_depot.lister_objets(
        conn, tenant_id, famille=_FAMILLE_CASE, type_=_TYPE_CASE, limite=limite)
    sortie = []
    for objet in objets:
        donnees = objet.get("donnees") or {}
        if donnees.get("kind") != "resolution_case":
            continue
        if twin_id and donnees.get("twin_id") != twin_id:
            continue
        if status and donnees.get("status") != status:
            continue
        sortie.append({**donnees, "id": objet.get("id"), "version": objet.get("version")})
    return sortie


def resoudre_case(conn, tenant_id: str, case_id: str, *,
                  evidence_ids=(), target_twin_id: str = "") -> dict:
    objet = entreprise_depot.lire_objet(conn, tenant_id, case_id)
    if objet is None:
        raise LookupError("cas de résolution introuvable")
    donnees = objet.get("donnees") or {}
    if donnees.get("kind") != "resolution_case":
        raise LookupError("cet objet n'est pas un cas de résolution")
    case = ResolutionCase.depuis_dict(donnees)
    resolue = replace(case, status="resolved", attempts=case.attempts + 1,
                      target_twin_id=target_twin_id or case.target_twin_id,
                      resolved_at=datetime.now(timezone.utc).isoformat(),
                      updated_at=datetime.now(timezone.utc).isoformat(),
                      evidence_ids=tuple(dict.fromkeys([*case.evidence_ids,
                                                        *(str(x) for x in evidence_ids or ())])))
    enregistrer_resolution_case(conn, resolue)
    return resolue.as_dict()


async def investiguer_case(conn, tenant_id: str, case_id: str, investigateur) -> dict:
    case = lire_resolution_case(conn, tenant_id, case_id)
    bindings = lire_bindings(conn, tenant_id, environment=case.environment)
    manifests = relations_pg.lire_manifestes(conn, tenant_id)
    case = await resolution.investiguer_resolution_async(
        case, bindings, manifests, investigateur)
    enregistrer_resolution_case(conn, case)
    return case.as_dict()


def _proposition_depuis_case(conn, tenant_id: str, case: ResolutionCase) -> dict | None:
    if not case.target_twin_id:
        return None
    manifests = relations_pg.lire_manifestes(conn, tenant_id)
    consommateur = next((m for m in manifests if m.twin_id == case.twin_id), None)
    fournisseur = next((m for m in manifests if m.twin_id == case.target_twin_id), None)
    if consommateur is None or fournisseur is None:
        return None
    accepte = next((c for c in case.candidates if c.get("status") == "accepted"), {})
    source = str(accepte.get("source") or "AGENT").upper()
    preuves = tuple(dict.fromkeys([*case.evidence_ids, *(accepte.get("evidence_ids") or ())]))
    transport = "JMS" if (case.reference.lower().startswith(("jms/", "jndi:"))
                          or "queue" in case.reference.lower()) else "HTTP"
    provisoire = consommateur.status == "PROVISIONAL" or fournisseur.status == "PROVISIONAL"
    mode = "PROPOSED" if provisoire else ("INFERRED" if source == "AGENT" else "DECLARED")
    proposition = PropositionRelation(
        tenant_id=tenant_id, consumer_id=case.twin_id, provider_id=case.target_twin_id,
        object=case.reference, environment=case.environment, predicate="CONSOMME",
        mode=mode, state="supposee",
        confidence=float(accepte.get("confidence") or 0.5), evidence_ids=preuves,
        consumer_owner=consommateur.owner, provider_owner=fournisseur.owner,
        justification="résolution de destination acceptée en revue",
        unknowns=("usage runtime non vérifié",),
        transport=transport, portee="SERVICE",
        boundary_evidence=("revue:destination acceptée",),
        consumer_application_id=consommateur.application_id,
        provider_application_id=fournisseur.application_id,
    )
    relations_pg.enregistrer_proposition(conn, proposition)
    return proposition.as_dict()


def revoir_case(conn, tenant_id: str, case_id: str, candidate_id: str, decision: str,
                acteur: str, *, motif: str = "") -> dict:
    case = lire_resolution_case(conn, tenant_id, case_id)
    case, bindings = resolution.revoir_candidat(
        case, candidate_id, decision, acteur, motif=motif)
    for binding in bindings:
        enregistrer_binding(conn, tenant_id, binding)
    relation = None
    if case.status == "resolved":
        # La revue accepte une hypothèse ; le déterministe doit encore la résoudre.
        lus = lire_bindings(conn, tenant_id, environment=case.environment)
        consommation = Consommation(
            kind="HTTP", logical_ref=case.reference, environment=case.environment,
            portee="EXTERNAL")
        verification = resolution.resoudre_destination(
            consommation, lus, environment=case.environment)
        if not verification.resolved:
            case = replace(
                case, status="open", target_twin_id="", resolved_at="",
                next_check=verification.next_check or "binding accepté mais destination non résolue",
                updated_at=datetime.now(timezone.utc).isoformat())
        else:
            relation = _proposition_depuis_case(conn, tenant_id, case)
    enregistrer_resolution_case(conn, case)
    return {**case.as_dict(), "relation": relation}
