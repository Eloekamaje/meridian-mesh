"""Port runtime du cas d'usage d'analyse cognitive.

Le service d'analyse décrit ce dont il a besoin : identité, sérialisation publique,
connexions tenant et opérations cognitives. Les implémentations concrètes (Postgres,
graphe, spécialistes) vivent dans un adapter sortant.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Protocol


class ConfigurationManquante(RuntimeError):
    """Configuration runtime absente (DSN ou runtime d'analyse)."""


class RuntimeAnalyse(Protocol):
    def mode_auth(self) -> str: ...

    def assainir(self, valeur: Any) -> Any: ...

    async def avec_connexion(self, tenant: str, action: Callable[[Any], Any]) -> Any: ...

    async def agreger_portefeuille(
        self, tenant: str, *, domaine: str | None = None, limite: int = 100
    ) -> dict: ...

    async def lancer_specialistes(
        self, noms: Sequence[str], base: Any, tenant: str
    ) -> list[dict]: ...

    def proximite_graphe(self, tenant: str, twin_ids: Sequence[str]) -> dict[str, float]: ...

    async def recuperer_memoire(
        self,
        tenant: str,
        *,
        question: str,
        twin_ids: Sequence[str],
        situation_id: str | None = None,
        scope: str | None = None,
        scope_id: str | None = None,
        limite: int = 12,
        proximite: dict[str, float] | None = None,
    ) -> list[dict]: ...

    def enrichir_pack(
        self, pack: Any, candidats: Any, *, max_tokens: int | None = None
    ) -> dict: ...

    async def memoriser_session(
        self,
        tenant: str,
        session_id: str,
        question: str,
        resume: str,
        *,
        acteur: str,
        donnees: dict | None = None,
    ) -> dict: ...

    async def lire_calibration(self, tenant: str, prediction_id: str) -> Any | None: ...

    async def calibrer_decision(
        self,
        tenant: str,
        decision_support: Any,
        *,
        decision_id: str | None = None,
        confidence: float | None = None,
        prediction_id: str | None = None,
    ) -> Any | None: ...

    def decision_support_enrichi(
        self,
        decision_support: Any,
        *,
        options: Any = None,
        changements: Any = None,
        criteres: Any = (),
    ) -> dict: ...


__all__ = ["ConfigurationManquante", "RuntimeAnalyse"]
