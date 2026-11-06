"""Indexation fédérée du legacy : sidecars, couverture explicite et liens prouvés.

Le module ne produit pas de Claims : il rend des observations et des liens que les packs
framework pourront ensuite promouvoir. Chaque sidecar reste remplaçable et isolé.
"""
from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

from meridian.adapters.outbound.connectors.abap import AbapSidecar
from meridian.adapters.outbound.connectors.abap_semantic import AbapSemanticSidecar
from meridian.adapters.outbound.connectors.cbm_observations import CbmObservations
from meridian.adapters.outbound.connectors.cobol import CobolSidecar
from meridian.adapters.outbound.connectors.java_descriptors import JavaDescriptorSidecar
from meridian.adapters.outbound.connectors.java_source import JavaSourceSidecar
from meridian.adapters.outbound.connectors.jcl import JclSidecar
from meridian.adapters.outbound.connectors.jsp import JspSidecar
from meridian.adapters.outbound.connectors.oracle_forms import OracleFormsSidecar
from meridian.adapters.outbound.connectors.pli import PliSidecar
from meridian.adapters.outbound.connectors.pli_semantic import parser_disponible as pli_semantic_disponible
from meridian.adapters.outbound.connectors.pli_semantic import PliSemanticSidecar
from meridian.adapters.outbound.connectors.powerbuilder import PowerBuilderSidecar
from meridian.adapters.outbound.connectors.rpg import RpgSidecar
from meridian.adapters.outbound.connectors.rpg_semantic import RpgSemanticSidecar
from meridian.adapters.outbound.connectors.sql_schema import SqlSchemaSidecar
from meridian.application.code_index_orchestrator import OrchestrateurCodeIndex
from meridian.application.code_links import lier, rapport_liens
from meridian.application.legacy_packs import claims_promouvables, packs, rapport_packs
from meridian.domain.code_index import CouvertureFichier, Observation, fusionner

__all__ = ["SIDECARS", "indexer_legacy", "rapport_legacy"]


def SIDECARS(projet_cbm: str | None = None, sql_live=None):
    """Les sidecars actifs, dans l'ordre de déclaration ; aucun n'écrit de Claim."""
    try:
        abap = (AbapSemanticSidecar(provider="abap")
                if AbapSemanticSidecar.disponible() else AbapSidecar())
    except Exception:
        abap = AbapSidecar()
    try:
        rpg = (RpgSemanticSidecar(provider="rpg")
               if RpgSemanticSidecar.disponible() else RpgSidecar())
    except Exception:
        rpg = RpgSidecar()
    try:
        pli = (PliSemanticSidecar(provider="pli")
               if pli_semantic_disponible() else PliSidecar())
    except Exception:
        pli = PliSidecar()
    adaptateurs = [
        JspSidecar(),
        JavaSourceSidecar(),
        JavaDescriptorSidecar(),
        CobolSidecar(),
        JclSidecar(),
        SqlSchemaSidecar(),
        abap,
        rpg,
        pli,
        OracleFormsSidecar(),
        PowerBuilderSidecar(),
    ]
    if projet_cbm:
        adaptateurs.append(CbmObservations(projet_cbm))
    if sql_live is not None:
        adaptateurs.append(sql_live)
    return adaptateurs


def _chemin_sql_live(fichier: str) -> str:
    """Restaure les schémas ``db://`` et ``pbl://`` réduits par le chemin Posix."""
    for schema in ("db", "pbl"):
        prefixe = f"{schema}:/"
        if fichier.startswith(prefixe) and not fichier.startswith(f"{schema}://"):
            return f"{schema}://" + fichier[len(prefixe):]
    return fichier


def _accepte_sql_live(sql_live, fichier: str) -> bool:
    """Applique le même filtre d'extension que l'orchestrateur pour savoir s'il a exécuté le sidecar."""
    supporte = getattr(sql_live, "supporte", None)
    if callable(supporte):
        return bool(supporte(fichier))
    extensions = getattr(sql_live, "extensions", None)
    if not extensions:
        return True
    suffixes = {("." + str(valeur).lower().lstrip(".")) for valeur in extensions}
    return Path(str(fichier)).suffix.lower() in suffixes


def _executer_sql_live(sql_live, racine, fichiers):
    """Exécute un sidecar SQL live hors découverte de fichiers, comme un adapter isolé."""
    observations: list[Observation] = []
    couvertures: list[CouvertureFichier] = []
    erreurs: list[dict] = []
    provider = str(getattr(sql_live, "provider", "") or "sql-live")
    cibles = (fichiers,) if isinstance(fichiers, (str, os.PathLike)) else tuple(fichiers or ())
    try:
        for observation in sql_live.index(str(racine), fichiers=cibles) or ():
            if isinstance(observation, Observation) and observation.file:
                observations.append(observation)
    except Exception as exception:
        erreurs.append({
            "provider": provider, "phase": "index",
            "type": type(exception).__name__, "message": str(exception),
        })
    try:
        for ligne in sql_live.couverture(str(racine), fichiers=cibles) or ():
            if isinstance(ligne, CouvertureFichier) and ligne.file:
                couvertures.append(ligne)
    except Exception as exception:
        erreurs.append({
            "provider": provider, "phase": "couverture",
            "type": type(exception).__name__, "message": str(exception),
        })
    return observations, couvertures, erreurs


def _observation_dict(observation: Observation) -> dict:
    return observation.as_dict()


def _lecteur(racine):
    """Lit une preuve au chemin relatif déjà indexé, sans sortir de la racine."""
    base = Path(racine).resolve()

    def lire(chemin: str):
        if not chemin:
            return None
        cible = Path(chemin)
        if not cible.is_absolute():
            cible = base / cible
        try:
            cible.resolve().relative_to(base)
        except (OSError, ValueError):
            return None
        try:
            return cible.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return None

    return lire


def indexer_legacy(racine, fichiers=(), projet_cbm: str | None = None,
                   commit: str = "", sql_live=None) -> dict:
    """Indexe une racine et rend un rapport sérialisable : couverture, observations, liens, constats.

    Le sidecar SQL live est injecté explicitement par l'appelant ; ce module ne lit
    jamais l'environnement et n'ouvre aucune connexion de lui-même.
    """
    orchestrateur = OrchestrateurCodeIndex(SIDECARS(projet_cbm, sql_live))
    resultat = orchestrateur.executer(racine, fichiers)
    observations = resultat["observations"]
    couvertures = resultat["couvertures"]
    erreurs = resultat["erreurs"]
    if sql_live is not None:
        observations = [
            replace(observation, file=_chemin_sql_live(observation.file))
            for observation in observations
        ]
        couvertures = [
            replace(ligne, file=_chemin_sql_live(ligne.file)) for ligne in couvertures
        ]
        if not any(_accepte_sql_live(sql_live, fichier) for fichier in resultat["fichiers"]):
            directes, directes_couvertures, directes_erreurs = _executer_sql_live(
                sql_live, racine, fichiers)
            observations = fusionner([*observations, *directes])
            couvertures = sorted(
                [*couvertures, *directes_couvertures], key=lambda ligne: ligne.file)
            erreurs = [*erreurs, *directes_erreurs]
    if commit:
        observations = [replace(observation, commit=commit) for observation in observations]
    liens = lier(observations)
    findings = packs(observations, liens)
    compteurs = {}
    for ligne in couvertures:
        compteurs[ligne.statut] = compteurs.get(ligne.statut, 0) + 1
    return {
        "racine": str(Path(racine)),
        "providers": list(resultat["providers"]),
        "fichiers_decouverts": list(resultat["fichiers"]),
        "observations": [_observation_dict(o) for o in observations],
        "couvertures": [ligne.as_dict() for ligne in couvertures],
        "liens": rapport_liens(liens),
        "packs": rapport_packs(findings),
        "claims_promouvables": claims_promouvables(findings, _lecteur(racine)),
        "compteurs": compteurs,
        "erreurs": [dict(erreur) for erreur in erreurs],
    }


def rapport_legacy(racine, fichiers=(), projet_cbm: str | None = None, sql_live=None) -> dict:
    """Alias lisible : même rapport que :func:`indexer_legacy`."""
    return indexer_legacy(racine, fichiers, projet_cbm, sql_live=sql_live)
