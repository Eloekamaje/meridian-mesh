"""Enquête bornée sur un `ResolutionCase`, avec les données déjà persistées.

Le service charge le cas, les bindings et les manifestes, construit les outils
read-only, exécute la boucle puis met à jour les candidats du cas. Il ne crée aucune
proposition et ne confirme rien.
"""
from __future__ import annotations

import os
from dataclasses import replace
from datetime import datetime, timezone

from meridian.adapters.outbound.connectors import atlassian, datadog, servicenow
from meridian.adapters.outbound.postgres import decouverte_liens as decouverte_pg
from meridian.adapters.outbound.postgres import depot
from meridian.adapters.outbound.postgres import relations_naissance as relations_pg
from meridian.adapters.outbound.postgres.sources_investigation import (
    lire_code_jumeau,
    lire_code_preuves,
    lister_cmdb,
)
from meridian.adapters.outbound.postgres.outils_investigation import (
    OutilAPM,
    OutilBindings,
    OutilCMDB,
    OutilCode,
    OutilGateway,
    OutilManifestes,
    OutilPortail,
    OutilRuntime,
    OutilServiceNow,
    OutilVide,
)
from meridian.application.boucle_investigation import (
    BudgetEnquete,
    PlanificateurRegles,
    executer,
)
from meridian.domain.decouverte_liens import CandidatResolution

__all__ = ["enqueter_case"]


def _outils(bindings, manifests, environment: str, *,
            fichiers=None, cmdb=None, servicenow_fn=None, apm_fn=None,
            runtime_graph=None, portail=None) -> dict:
    bindings_tool = OutilBindings(bindings, environment)
    manifests_tool = OutilManifestes(manifests)
    if servicenow_fn is not None:
        annuaire = OutilServiceNow(servicenow_fn, cmdb)
    elif cmdb:
        annuaire = OutilCMDB(cmdb)
    else:
        annuaire = manifests_tool
    return {
        "configuration": bindings_tool,
        "deploiement": bindings_tool,
        "gateway": OutilGateway(bindings),
        "messagerie": bindings_tool,
        "annuaire": annuaire,
        "portail": OutilPortail(portail, cmdb) if portail
        else OutilVide("portail API non branché"),
        "contrats": manifests_tool,
        "code": OutilCode(fichiers or {}),
        "traces": OutilAPM(apm_fn, cmdb) if apm_fn is not None
        else OutilVide("traces non branchées dans cette version"),
        "runtime": OutilRuntime(runtime_graph, cmdb) if runtime_graph
        else OutilVide("runtime APM/gateway non branché"),
    }


def _lecteurs_externes(conn, twin_id: str):
    """Construit les lecteurs ServiceNow/Datadog si la politique l'autorise."""
    sources = depot.toutes_les_sources(conn, twin_id) if twin_id else []
    servicenow_fn = None
    apm_fn = None
    if os.environ.get("JUMEAU_ENQUETE_CMDB", "").strip().lower() == "servicenow":
        source = next((s for s in sources if s.get("type") == "SERVICENOW"), None)
        if source and source.get("secret_ref"):
            reference = source["secret_ref"]
            hote = atlassian.hote_de_url(source.get("url"))
            servicenow_fn = lambda recherche: servicenow.perimetres(  # noqa: E731
                reference, recherche, hote)
    if os.environ.get("JUMEAU_ENQUETE_APM", "").strip().lower() == "datadog":
        source = next((s for s in sources if s.get("type") == "DATADOG"), None)
        if source and source.get("secret_ref"):
            lecteur = datadog.LecteurDatadog(
                source["nom"], source["emplacement"], source["secret_ref"],
                datadog._hote_api(source.get("url")))
            apm_fn = lambda: lecteur._lire("dependances", None)["lignes"]  # noqa: E731
    return servicenow_fn, apm_fn


def _planificateur(outils):
    mode = os.environ.get("JUMEAU_ENQUETE_PLANIFICATEUR", "regles").strip().lower()
    if mode == "llm":
        from meridian.adapters.outbound.llm.planificateur_liens import PlanificateurLLM
        return PlanificateurLLM(outils=tuple(outils), fallback=PlanificateurRegles())
    return PlanificateurRegles()


def enqueter_case(conn, tenant_id: str, case_id: str, *,
                  planificateur=None,
                  budget: BudgetEnquete | None = None,
                  fichiers=None, cmdb=None,
                  servicenow_fn=None, apm_fn=None,
                  runtime_graph=None, portail=None) -> dict:
    case = decouverte_pg.lire_resolution_case(conn, tenant_id, case_id)
    bindings = decouverte_pg.lire_bindings(
        conn, tenant_id, environment=case.environment)
    manifests = relations_pg.lire_manifestes(conn, tenant_id)
    diagnostics = []
    if cmdb is None:
        cmdb = lister_cmdb(conn, tenant_id)
    if fichiers is None:
        fichiers, diagnostics = lire_code_preuves(conn, tenant_id, case.twin_id)
        if not fichiers and os.environ.get("JUMEAU_ENQUETE_CODE", "").strip() == "1":
            locaux, problemes = lire_code_jumeau(conn, tenant_id, case.twin_id)
            diagnostics.extend(problemes)
            fichiers = locaux
    if servicenow_fn is None or apm_fn is None:
        lecteur_sn, lecteur_apm = _lecteurs_externes(conn, case.twin_id)
        servicenow_fn = servicenow_fn or lecteur_sn
        apm_fn = apm_fn or lecteur_apm
    outils = _outils(bindings, manifests, case.environment,
                     fichiers=fichiers, cmdb=cmdb,
                     servicenow_fn=servicenow_fn, apm_fn=apm_fn,
                     runtime_graph=runtime_graph, portail=portail)
    resultat = executer(
        case, planificateur or _planificateur(outils), outils, budget=budget)

    candidats = {c.get("id"): dict(c) for c in case.candidates}
    for brut in resultat.candidats:
        try:
            candidat = CandidatResolution.depuis_dict(brut)
        except ValueError:
            continue
        candidats[candidat.id] = candidat.as_dict()
    prochaine = "revue des candidats" if candidats else (
        resultat.etapes[-1].resume if resultat.etapes else case.next_check)
    mis_a_jour = replace(
        case, candidates=tuple(candidats.values()), attempts=case.attempts + 1,
        next_check=prochaine or case.next_check,
        updated_at=datetime.now(timezone.utc).isoformat())
    decouverte_pg.enregistrer_resolution_case(conn, mis_a_jour)
    return {
        "case": mis_a_jour.as_dict(),
        "investigation": resultat.as_dict(),
        "diagnostics": diagnostics,
    }
