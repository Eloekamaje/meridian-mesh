"""Adapter sortant du runtime d'analyse : Postgres, graphe, identité et spécialistes.

Le service d'analyse ne dépend que de :class:`meridian.ports.analyse.RuntimeAnalyse`.
Cet adapter garde les connexions, le contexte RLS, la sérialisation publique et les
modules concrèts hors de la couche application.
"""
from __future__ import annotations

import asyncio
import math
import os
import re
from collections.abc import Callable, Mapping, Sequence
from contextlib import nullcontext
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qsl, unquote_plus, urlsplit

import psycopg

import auth as auth_identite
from meridian.adapters.outbound.neo4j import graph_store
from meridian.adapters.outbound.postgres import (
    calibration,
    decision_cognitive,
    portefeuille,
    retrieval_memoire,
    rls,
    session_memoire,
    specialiste_decouverte,
    specialiste_impact,
)
from meridian.application import specialiste_preuve
from meridian.domain import specialistes
from meridian.ports.analyse import ConfigurationManquante, RuntimeAnalyse

_MARQUEURS_SECRETS = ("password", "passwd", "secret", "token", "credential", "authorization")
_CLES_SECRETES = frozenset({
    "pwd", "pass", "auth", "key", "apikey", "api_key", "api-key", "access_key", "accesskey",
    "private_key", "privatekey", "client_secret", "clientsecret", "bearer", "password", "passwd",
})
_JETON_SENSIBLE = re.compile(
    r"(?i)(?:\bbearer\s+[A-Za-z0-9_.~+/=-]{12,}|\bsk-[A-Za-z0-9_-]{8,}|"
    r"\bgh[pousr]_[A-Za-z0-9]{10,}|\bxox[baprs]-[A-Za-z0-9-]{10,})"
)

SPECIALISTES = {
    "decouverte": specialiste_decouverte.SpecialisteDecouverte,
    "preuve": specialiste_preuve.SpecialistePreuve,
    "impact": specialiste_impact.SpecialisteImpact,
    "outcome": specialiste_impact.SpecialisteOutcome,
}


def _dsn() -> str:
    dsn = os.environ.get("JUMEAU_PG_DSN")
    if not dsn:
        raise ConfigurationManquante("JUMEAU_PG_DSN non défini")
    return dsn


def _contexte(conn, tenant):
    return rls.contexte_tenant(conn, tenant) if rls.est_actif() else nullcontext()


def _cle_sensible(cle) -> bool:
    normalisee = unquote_plus(str(cle)).strip().lower()
    if normalisee.endswith(("_ref", "-ref", "_reference", "-reference")):
        return False
    compacte = normalisee.replace("-", "_")
    # Budgets de contexte : « tokens » est une mesure, pas un secret.
    if compacte in {"tokens", "tokens_estimes", "tokens_utilises", "tokens_memoire",
                    "token_budget", "budget_tokens", "nb_tokens"}:
        return False
    if compacte in _CLES_SECRETES:
        return True
    if compacte.endswith("_key"):
        return True
    return any(marque in compacte for marque in _MARQUEURS_SECRETS)


def _url_porte_un_secret(url: str) -> bool:
    try:
        parties = urlsplit(url)
    except (ValueError, UnicodeError):
        return True
    if parties.username is not None or parties.password is not None or "@" in parties.netloc:
        return True
    return any(
        _cle_sensible(cle) and valeur not in ("", "***")
        for cle, valeur in parse_qsl(parties.query, keep_blank_values=True)
    )


def _assainir(valeur):
    """Copie locale de la sérialisation publique de la Boucle.

    L'adapter sortant ne peut pas importer un router inbound ; la fonction est donc
    conservée ici à l'identique pour garder le même comportement de masquage.
    """
    if isinstance(valeur, Mapping):
        resultat = {}
        for cle, contenu in valeur.items():
            nom = str(cle)
            resultat[nom] = "***" if _cle_sensible(nom) else _assainir(contenu)
        return resultat
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return [_assainir(element) for element in valeur]
    if isinstance(valeur, Decimal):
        return float(valeur)
    if isinstance(valeur, (datetime, date)):
        return valeur.isoformat()
    if isinstance(valeur, str):
        if _JETON_SENSIBLE.search(valeur) or _url_porte_un_secret(valeur):
            return "***"
        return valeur
    if isinstance(valeur, float) and not math.isfinite(valeur):
        return str(valeur)
    if valeur is None or isinstance(valeur, (bool, int, float)):
        return valeur
    return _assainir(str(valeur))


class RuntimeAnalysePostgres(RuntimeAnalyse):
    """Implémentation concrète du port, partagée par la route HTTP et le worker."""

    def mode_auth(self) -> str:
        return auth_identite.mode()

    def assainir(self, valeur: Any) -> Any:
        return _assainir(valeur)

    async def avec_connexion(self, tenant: str, action: Callable[[Any], Any]) -> Any:
        def executer():
            with psycopg.connect(_dsn(), connect_timeout=5) as conn:
                with _contexte(conn, tenant):
                    return action(conn)

        return await asyncio.to_thread(executer)

    async def agreger_portefeuille(
        self, tenant: str, *, domaine: str | None = None, limite: int = 100
    ) -> dict:
        return await self.avec_connexion(
            tenant,
            lambda conn: portefeuille.agreger(
                conn, tenant, domaine=domaine, limite=limite),
        )

    async def lancer_specialistes(
        self, noms: Sequence[str], base: Any, tenant: str
    ) -> list[dict]:
        dsn = _dsn()

        async def lancer(nom):
            instance = SPECIALISTES[nom]()
            graph_context = None
            try:
                if nom in {"impact", "decouverte"}:
                    try:
                        graph_context = graph_store.ouvrir()
                    except Exception:
                        graph_context = None
                magasin = graph_context["store"] if graph_context is not None else None
                with psycopg.connect(dsn, connect_timeout=5) as conn:
                    with _contexte(conn, tenant):
                        contexte = replace(base, conn=conn, store=magasin)
                        orchestrateur = specialistes.OrchestrateurSpecialistes(
                            [instance], timeout_s=8.0)
                        dossier = await orchestrateur.analyser(contexte)
                        return dossier["specialistes"][0]
            finally:
                if graph_context is not None:
                    graph_context["fermer"]()

        return await asyncio.gather(*(lancer(nom) for nom in noms))

    def proximite_graphe(self, tenant: str, twin_ids: Sequence[str]) -> dict[str, float]:
        """Scores 1/(1+distance) pour les voisins des Twins actifs, sans rendre le graphe obligatoire."""
        if not twin_ids:
            return {}
        contexte = None
        try:
            contexte = graph_store.ouvrir()
            scores: dict[str, float] = {}
            for twin_id in twin_ids[:10]:
                for voisin in contexte["store"].voisins(tenant, twin_id, profondeur=2):
                    identifiant = str(voisin.get("id") or "")
                    if identifiant:
                        scores[identifiant] = max(
                            scores.get(identifiant, 0.0),
                            1.0 / (1.0 + max(1, int(voisin.get("profondeur") or 1))))
            return scores
        except Exception:
            return {}
        finally:
            if contexte is not None:
                contexte["fermer"]()

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
    ) -> list[dict]:
        return await self.avec_connexion(
            tenant,
            lambda conn: retrieval_memoire.recuperer(
                conn, tenant, question=question, twin_ids=tuple(twin_ids),
                situation_id=situation_id, scope=scope, scope_id=scope_id,
                limite=limite, proximite=proximite),
        )

    def enrichir_pack(
        self, pack: Any, candidats: Any, *, max_tokens: int | None = None
    ) -> dict:
        return retrieval_memoire.enrichir_pack(
            pack, candidats, max_tokens=max_tokens)

    async def memoriser_session(
        self,
        tenant: str,
        session_id: str,
        question: str,
        resume: str,
        *,
        acteur: str,
        donnees: dict | None = None,
    ) -> dict:
        return await self.avec_connexion(
            tenant,
            lambda conn: session_memoire.memoriser_session(
                conn, tenant, session_id, question, resume,
                acteur=acteur, donnees=donnees),
        )

    async def lire_calibration(self, tenant: str, prediction_id: str) -> Any | None:
        return await self.avec_connexion(
            tenant,
            lambda conn: calibration.lire(conn, tenant, prediction_id),
        )

    async def calibrer_decision(
        self,
        tenant: str,
        decision_support: Any,
        *,
        decision_id: str | None = None,
        confidence: float | None = None,
        prediction_id: str | None = None,
    ) -> Any | None:
        return await self.avec_connexion(
            tenant,
            lambda conn: decision_cognitive.calibrer_decision_support(
                conn, tenant, decision_support,
                decision_id=decision_id, confidence=confidence,
                prediction_id=prediction_id),
        )

    def decision_support_enrichi(
        self,
        decision_support: Any,
        *,
        options: Any = None,
        changements: Any = None,
        criteres: Any = (),
    ) -> dict:
        return decision_cognitive.decision_support_enrichi(
            decision_support, options=options,
            changements=changements, criteres=criteres)


__all__ = ["RuntimeAnalysePostgres", "SPECIALISTES"]
