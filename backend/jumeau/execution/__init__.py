"""Exécution durable : runs, états, outbox et workers.

Ce paquet est volontairement indépendant de FastAPI, Strands et des clients de stores.
Les routes et les adapters sont branchés dans `jumeau.execution.routes`.
"""
from jumeau.execution.modele import (
    ApprobationIntrouvable,
    ApprobationRequise,
    CommandeExecution,
    ConflitApprobation,
    EffetRejete,
    EtatRun,
    Priorite,
    ErreurExecution,
    ErreurTransitoire,
    ConflitIdempotence,
    AnnulationExecution,
    OutilRefuse,
    QuotaDepasse,
    RunIntrouvable,
    TransitionInvalide,
    ETATS_ACTIFS,
    ETATS_TERMINAUX,
)
from jumeau.execution.depot import (
    creer_run,
    obtenir_run,
    reclamer_run,
    renouveler_bail,
    terminer,
    demander_annulation,
    planifier_retry,
    evenements,
    obtenir_effet,
    decider_approbation,
    lister_approbations,
    obtenir_approbation_par_id,
    etapes_run,
    obtenir_etape,
    demarrer_etape,
    terminer_etape,
    clore_etape,
    journaliser_etape,
    reprendre_run,
    compter_runs_actifs,
    max_actifs_par_tenant,
)
from jumeau.execution.moteur import MoteurExecution
from jumeau.execution.processus import ProcessManager
from jumeau.execution.tool_gateway import OutilHTTP, ToolGateway, allowlist_depuis_env

__all__ = [
    "ApprobationIntrouvable", "ApprobationRequise", "CommandeExecution", "ConflitApprobation",
    "EffetRejete", "EtatRun", "Priorite", "ErreurExecution", "ErreurTransitoire",
    "ConflitIdempotence", "AnnulationExecution", "OutilRefuse", "QuotaDepasse", "RunIntrouvable",
    "TransitionInvalide", "ETATS_ACTIFS", "ETATS_TERMINAUX", "creer_run", "obtenir_run",
    "reclamer_run", "renouveler_bail", "terminer", "demander_annulation", "planifier_retry",
    "evenements", "obtenir_effet", "decider_approbation", "lister_approbations",
    "obtenir_approbation_par_id", "etapes_run", "obtenir_etape", "demarrer_etape",
    "terminer_etape", "clore_etape", "journaliser_etape", "reprendre_run", "compter_runs_actifs",
    "max_actifs_par_tenant", "MoteurExecution", "ProcessManager", "OutilHTTP", "ToolGateway",
    "allowlist_depuis_env",
]
