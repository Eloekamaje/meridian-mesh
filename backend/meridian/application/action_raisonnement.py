"""Passage d'une décision de raisonnement à une action gouvernée.

Le noyau ne remplace pas le ToolGateway : il vérifie que le dossier est décidable et que l'autorité
est suffisante, puis délègue l'effet. Une écriture sans approbation est refusée avant tout appel.
"""
from __future__ import annotations

from collections.abc import Mapping
from types import SimpleNamespace

from meridian.domain import dossier_raisonnement as domaine

__all__ = ["ActionRefusee", "executer", "executer_rollback", "verifier"]


class ActionRefusee(RuntimeError):
    """Le dossier ou l'autorité ne permettent pas l'action demandée."""

    def __init__(self, motif: str):
        self.motif = motif
        super().__init__(motif)


def _normaliser(dossier):
    if not isinstance(dossier, Mapping):
        return dossier
    demande = dossier.get("demande") or {}
    if isinstance(demande, Mapping):
        demande = SimpleNamespace(**dict(demande))
    gates = tuple(
        SimpleNamespace(**dict(g)) if isinstance(g, Mapping) else g
        for g in dossier.get("gates") or ()
    )
    return SimpleNamespace(
        statut=dossier.get("statut") or "reponse",
        demande=demande,
        gates=gates,
    )


def _gate(dossier, identifiant: str):
    for gate in getattr(dossier, "gates", ()) or ():
        if getattr(gate, "id", None) == identifiant:
            return gate
        if isinstance(gate, Mapping) and gate.get("id") == identifiant:
            return domaine.Gate(**dict(gate))
    return None


def verifier(dossier, *, ecriture: bool = False) -> None:
    """Vérifie les gates et l'autorité avant de laisser le ToolGateway agir."""
    dossier = _normaliser(dossier)
    if dossier is None:
        raise ActionRefusee("aucun dossier de raisonnement")
    if getattr(dossier, "statut", "") in {"refus", "echec", "clarification_requise"}:
        raise ActionRefusee(f"dossier non exécutable : {getattr(dossier, 'statut', '')}")
    demande = getattr(dossier, "demande", None)
    if demande is None:
        raise ActionRefusee("demande absente du dossier")
    if ecriture and demande.autorite not in {"approbation", "decision", "action"}:
        raise ActionRefusee(
            f"écriture sans autorité d'approbation (autorité={demande.autorite})")
    gate = _gate(dossier, "G-KRN-07")
    if gate is not None:
        statut = getattr(gate, "statut", None) if not isinstance(gate, Mapping) else gate.get("statut")
        if statut == "echec":
            raise ActionRefusee("gate G-KRN-07 : action non autorisée")


def executer(
    gateway,
    dossier,
    run: Mapping,
    *,
    etape: str,
    outil: str,
    operation: str,
    cible: str,
    payload: Mapping | None = None,
    ecriture: bool = False,
):
    """Délègue au ToolGateway après vérification du dossier ; le gateway garde l'idempotence et l'audit."""
    if not isinstance(run, Mapping):
        raise ActionRefusee("run d'action invalide")
    verifier(dossier, ecriture=ecriture)
    proposer = getattr(gateway, "proposer", None)
    if not callable(proposer):
        raise ActionRefusee("ToolGateway indisponible")
    return proposer(
        run, etape=etape, outil=outil, operation=operation,
        cible=cible, payload=payload)


def executer_rollback(
    gateway,
    dossier,
    run: Mapping,
    *,
    etape: str,
    outil: str,
    operation: str,
    cible: str,
    payload: Mapping | None = None,
):
    """Exécute une opération compensatoire explicite, jamais déduite automatiquement.

    Le rollback est une écriture : il exige la même autorité que l'action initiale et reste soumis
    au ToolGateway, à son idempotence et à l'approbation. L'appelant fournit l'opération compensatoire.
    """
    if not operation or not cible:
        raise ActionRefusee("rollback : opération et cible obligatoires")
    return executer(
        gateway, dossier, run, etape=etape, outil=outil,
        operation=operation, cible=cible, payload=payload, ecriture=True)
