"""Exécutants des actions canoniques de la boucle (D4) — les callables du Harness.

Chaque fonction prend ``(conn, tenant, **args)`` et route via
``commandes_boucle`` — le même orchestrateur transactionnel que les routes B1
(source verrouillée ``FOR UPDATE``, statut/mode serveur, journal d'épisodes).
Convergence §7 phase 3 : l'autorité est unique, quel que soit l'appelant.
Le Harness décide seul si elles peuvent être appelées (manifeste approuvé).
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import psycopg

from meridian.adapters.outbound.postgres import boucle
from meridian.adapters.outbound.postgres import rls
from meridian.application import commandes_boucle

__all__ = [
    "NOMS_ACTIONS",
    "creer_situation",
    "ouvrir_investigation",
    "proposer_decision",
    "trancher_decision",
    "lancer_initiative",
    "adaptateurs",
    "adaptateurs_dsn",
]

NOMS_ACTIONS = (
    "creer_situation",
    "ouvrir_investigation",
    "proposer_decision",
    "trancher_decision",
    "lancer_initiative",
)


def _contexte(conn: Any, tenant: str):
    """La portée RLS du tenant, quand elle est activée — même discipline que les routes B1."""
    return rls.contexte_tenant(conn, tenant) if rls.est_actif() else _SansContexte()


class _SansContexte:
    def __enter__(self):
        return None

    def __exit__(self, *exc):
        return False


def _texte(valeur: Any) -> str:
    return " ".join(str(valeur or "").split())


def _tenant(tenant: Any) -> str:
    texte = _texte(tenant)
    if not texte:
        raise boucle.BoucleInvalide("tenant obligatoire pour une écriture canonique")
    return texte


def creer_situation(
    conn: Any, tenant: Any, titre: Any = "", donnees: Any = None, mode: Any = None,
) -> dict:
    """Crée une Situation canonique — route ``commandes_boucle.creer_situation``."""
    tenant_id = _tenant(tenant)
    titre_texte = _texte(titre)
    if not titre_texte:
        raise boucle.BoucleInvalide("une Situation exige un titre")
    donnees_libres = dict(donnees) if isinstance(donnees, Mapping) else {}
    champs = {
        "titre": titre_texte,
        "resume": donnees_libres.pop("resume", titre_texte),
        "mode": _texte(mode) or "OBSERVED",
        **donnees_libres,
    }
    with _contexte(conn, tenant_id):
        return commandes_boucle.creer_situation(
            boucle, conn, tenant_id, **champs).objet


def ouvrir_investigation(
    conn: Any, tenant: Any, situation_id: Any, **donnees: Any,
) -> dict:
    """Ouvre une Investigation sur une Situation du tenant — route ``commandes_boucle``."""
    tenant_id = _tenant(tenant)
    with _contexte(conn, tenant_id):
        return commandes_boucle.ouvrir_investigation(
            boucle, conn, tenant_id, _texte(situation_id), **donnees).objet


def proposer_decision(
    conn: Any, tenant: Any, investigation_id: Any, options: Any = None,
    criteres: Any = None, incertitudes: Any = None, **donnees: Any,
) -> dict:
    """Propose une Décision non tranchée — route ``commandes_boucle.proposer_decision``."""
    tenant_id = _tenant(tenant)
    champs = {"criteres": criteres, "incertitudes": incertitudes, **donnees}
    champs = {cle: valeur for cle, valeur in champs.items() if valeur is not None}
    with _contexte(conn, tenant_id):
        return commandes_boucle.proposer_decision(
            boucle, conn, tenant_id, _texte(investigation_id), options, **champs).objet


def trancher_decision(
    conn: Any, tenant: Any, decision_id: Any, acteur: Any = None, choix: Any = None,
    **donnees: Any,
) -> dict:
    """Tranche une Décision proposée — route ``commandes_boucle.trancher_decision``."""
    tenant_id = _tenant(tenant)
    with _contexte(conn, tenant_id):
        return commandes_boucle.trancher_decision(
            boucle, conn, tenant_id, _texte(decision_id),
            acteur=_texte(acteur), choix=_texte(choix), **donnees).objet


def lancer_initiative(
    conn: Any, tenant: Any, decision_id: Any, **donnees: Any,
) -> dict:
    """Lance une Initiative sur une Décision tranchée — route ``commandes_boucle``."""
    tenant_id = _tenant(tenant)
    with _contexte(conn, tenant_id):
        return commandes_boucle.lancer_initiative(
            boucle, conn, tenant_id, _texte(decision_id), **donnees).objet


def adaptateurs(conn: Any, tenant: Any, acteur: Any = None) -> dict[str, Callable]:
    """Les cinq callables prêts pour le Harness : connexion et tenant liés, nommage stable.

    ``acteur`` est le tranchant par défaut de ``trancher_decision`` quand l'appel ne
    le précise pas.
    """
    tenant_id = _tenant(tenant)
    acteur_defaut = _texte(acteur) or "flore"

    def _creer_situation(titre: str = "", donnees: Any = None, mode: Any = None) -> dict:
        return creer_situation(conn, tenant_id, titre=titre, donnees=donnees, mode=mode)

    def _ouvrir_investigation(situation_id: str, **donnees: Any) -> dict:
        return ouvrir_investigation(conn, tenant_id, situation_id, **donnees)

    def _proposer_decision(investigation_id: str, options: Any = None,
                           criteres: Any = None, incertitudes: Any = None,
                           **donnees: Any) -> dict:
        return proposer_decision(
            conn, tenant_id, investigation_id, options=options,
            criteres=criteres, incertitudes=incertitudes, **donnees)

    def _trancher_decision(decision_id: str, choix: Any = None, acteur: Any = None,
                           **donnees: Any) -> dict:
        return trancher_decision(
            conn, tenant_id, decision_id, acteur=_texte(acteur) or acteur_defaut,
            choix=choix, **donnees)

    def _lancer_initiative(decision_id: str, **donnees: Any) -> dict:
        return lancer_initiative(conn, tenant_id, decision_id, **donnees)

    return {
        "creer_situation": _creer_situation,
        "ouvrir_investigation": _ouvrir_investigation,
        "proposer_decision": _proposer_decision,
        "trancher_decision": _trancher_decision,
        "lancer_initiative": _lancer_initiative,
    }


def adaptateurs_dsn(dsn: Any, tenant: Any, acteur: Any = None) -> dict[str, Callable]:
    """Les mêmes callables, mais chaque appel ouvre sa propre connexion courte.

    La connexion est ouverte puis refermée dans l'appel — le ``with psycopg.connect``
    valide la transaction en sortie, comme les routes B1.
    """
    tenant_id = _tenant(tenant)
    acteur_defaut = _texte(acteur) or "flore"
    actions = {
        "creer_situation": lambda conn, args: creer_situation(conn, tenant_id, **args),
        "ouvrir_investigation": lambda conn, args: ouvrir_investigation(
            conn, tenant_id, args.pop("situation_id", None), **args),
        "proposer_decision": lambda conn, args: proposer_decision(
            conn, tenant_id, args.pop("investigation_id", None), **args),
        "trancher_decision": lambda conn, args: trancher_decision(
            conn, tenant_id, args.pop("decision_id", None),
            acteur=args.pop("acteur", None) or acteur_defaut, **args),
        "lancer_initiative": lambda conn, args: lancer_initiative(
            conn, tenant_id, args.pop("decision_id", None), **args),
    }

    def _outil(nom: str) -> Callable:
        action = actions[nom]

        def appel(**args: Any) -> dict:
            with psycopg.connect(dsn, connect_timeout=5) as conn:
                return action(conn, dict(args))
        appel.__name__ = nom
        return appel

    return {nom: _outil(nom) for nom in actions}
