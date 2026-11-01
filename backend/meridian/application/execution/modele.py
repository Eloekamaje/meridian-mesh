"""Types du runtime d'exécution : commande, état, priorité, erreurs."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping
from uuid import uuid4


class EtatRun(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_RETRY = "WAITING_RETRY"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


ETATS_TERMINAUX = frozenset({
    EtatRun.SUCCEEDED.value,
    EtatRun.FAILED.value,
    EtatRun.CANCELLED.value,
    EtatRun.EXPIRED.value,
})

ETATS_ACTIFS = (
    EtatRun.QUEUED.value,
    EtatRun.RUNNING.value,
    EtatRun.WAITING_APPROVAL.value,
    EtatRun.WAITING_RETRY.value,
)


class Priorite(str, Enum):
    INTERACTIVE = "interactive"
    STANDARD = "standard"
    BATCH = "batch"


class ErreurExecution(Exception):
    """Erreur de base du runtime."""


class ErreurTransitoire(ErreurExecution):
    """Erreur explicitement rejouable (timeout, indisponibilité passagère)."""


class RunIntrouvable(ErreurExecution):
    """Le run demandé n'existe pas pour ce tenant."""


class TransitionInvalide(ErreurExecution):
    """Transition d'état refusée."""


class ConflitIdempotence(ErreurExecution):
    """La clé d'idempotence existe déjà avec un autre acteur, type ou payload."""


class AnnulationExecution(ErreurExecution):
    """Le run a été annulé pendant l'exécution."""


class ApprobationRequise(ErreurExecution):
    """Un effet d'écriture attend une décision humaine avant d'être exécuté."""

    def __init__(self, run_id: str, etape: str, outil: str, cible: str, operation: str):
        self.run_id = run_id
        self.etape = etape
        self.outil = outil
        self.cible = cible
        self.operation = operation
        super().__init__(
            f"approbation requise pour {outil}.{operation} "
            f"(run {run_id}, étape {etape}, cible {cible})")


class OutilRefuse(ErreurExecution):
    """L'outil, l'acteur ou l'opération n'est pas autorisé par la politique."""


class EffetRejete(ErreurExecution):
    """L'effet a été explicitement rejeté par un humain."""


class ApprobationIntrouvable(ErreurExecution):
    """Aucune demande d'approbation ne correspond à la clé demandée."""


class ConflitApprobation(ErreurExecution):
    """La demande a déjà reçu une décision contraire."""


class EchecEffet(ErreurExecution):
    """L'appel HTTP de l'effet a échoué de façon permanente."""


class QuotaDepasse(ErreurExecution):
    """Le tenant a atteint son nombre maximal de runs actifs."""

    def __init__(self, tenant_id: str, maximum: int, actifs: int):
        self.tenant_id = tenant_id
        self.maximum = int(maximum)
        self.actifs = int(actifs)
        super().__init__(
            f"quota de runs actifs atteint pour le tenant {tenant_id!r} "
            f"({actifs}/{self.maximum}) ; terminez ou annulez un run avant d'en créer un autre")


@dataclass(frozen=True)
class CommandeExecution:
    """Enveloppe d'une commande durable.

    `idempotency_key` est la clé de déduplication côté client. Un même tenant + clé
    retourne toujours le même run. Le payload reste opaque pour le runtime.
    """

    tenant_id: str
    type: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    idempotency_key: str = field(default_factory=lambda: uuid4().hex)
    acteur: str = "systeme"
    priorite: Priorite = Priorite.STANDARD
    deadline_at: datetime | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    command_id: str = field(default_factory=lambda: uuid4().hex)
    run_id: str = field(default_factory=lambda: uuid4().hex)

    def __post_init__(self):
        for nom in ("tenant_id", "type", "idempotency_key", "acteur", "command_id", "run_id"):
            valeur = getattr(self, nom)
            if not isinstance(valeur, str) or not valeur.strip():
                raise ValueError(f"{nom} doit être une chaîne non vide")
        if not isinstance(self.priorite, Priorite):
            object.__setattr__(self, "priorite", Priorite(str(self.priorite)))
        if not isinstance(self.payload, Mapping):
            raise ValueError("payload doit être un mapping")
        if self.deadline_at is not None and not isinstance(self.deadline_at, datetime):
            raise ValueError("deadline_at doit être un datetime ou None")


def etat_terminal(etat: str | EtatRun) -> bool:
    valeur = etat.value if isinstance(etat, EtatRun) else str(etat)
    return valeur in ETATS_TERMINAUX
