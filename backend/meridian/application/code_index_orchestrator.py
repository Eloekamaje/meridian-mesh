"""Orchestrateur d'indexation fédérée : adapters séquentiels, pannes tolérées, couverture explicite."""
from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from typing import Iterable, Mapping

from meridian.domain.code_index import (
    STATUTS,
    CouvertureFichier,
    Observation,
    fusionner,
)

__all__ = [
    "EXCLUSIONS",
    "CodeIndexOrchestrator",
    "OrchestrateurCodeIndex",
    "decouvrir_fichiers",
]

EXCLUSIONS = frozenset({".git", "node_modules", ".venv", "__pycache__"})
_PRIORITE = ("conflit", "partiel", "tronque", "ignore", "non_supporte")
_RAISONS = {
    "conflit": "conflit entre providers",
    "partiel": "indexation partielle",
    "tronque": "indexation tronquée",
    "ignore": "fichier ignoré",
    "non_supporte": "aucun parser n'a produit d'observation",
}


def _extensions_normalisees(extensions) -> set[str] | None:
    if extensions is None:
        return None
    return {("." + str(valeur).lower().lstrip(".")) for valeur in extensions}


def _fichiers_explicites(valeur) -> tuple:
    if valeur is None:
        return ()
    if isinstance(valeur, (str, os.PathLike)):
        return (valeur,)
    return tuple(valeur)


def _accepte(adapter, fichier: str) -> bool:
    """Un sidecar ne voit que ses extensions ; sans déclaration, il reçoit tout."""
    supporte = getattr(adapter, "supporte", None)
    if callable(supporte):
        return bool(supporte(fichier))
    extensions = getattr(adapter, "extensions", None)
    if not extensions:
        return True
    suffixes = {("." + str(valeur).lower().lstrip(".")) for valeur in extensions}
    return Path(str(fichier)).suffix.lower() in suffixes


def decouvrir_fichiers(racine, *, extensions=None) -> list[str]:
    """Parcourt la racine en ignorant les répertoires techniques et filtre par extension."""
    suffixes = _extensions_normalisees(extensions)
    trouves: list[str] = []
    for dossier, sous_dossiers, noms in os.walk(racine):
        sous_dossiers[:] = sorted(nom for nom in sous_dossiers if nom not in EXCLUSIONS)
        for nom in sorted(noms):
            chemin = Path(dossier) / nom
            if suffixes is not None and chemin.suffix.lower() not in suffixes:
                continue
            trouves.append(chemin.as_posix())
    return sorted(trouves)


def _canonique(racine: Path, chemin) -> str:
    valeur = str(chemin or "").strip()
    if not valeur:
        return ""
    chemin = Path(valeur)
    if not chemin.is_absolute():
        chemin = racine / chemin
    try:
        return chemin.resolve().relative_to(racine.resolve()).as_posix()
    except (OSError, ValueError):
        return chemin.as_posix()


def _erreur(provider: str, phase: str, exception: Exception) -> dict:
    return {
        "provider": provider,
        "phase": phase,
        "type": type(exception).__name__,
        "message": str(exception),
    }


def _providers_conflit(observations: Iterable[Observation]) -> list[str]:
    noms: set[str] = set()
    for observation in observations:
        if observation.status != "conflict":
            continue
        valeurs = observation.attributes.get("providers") or [observation.provider]
        if isinstance(valeurs, str):
            noms.add(valeurs)
        else:
            noms.update(str(valeur) for valeur in valeurs)
    return sorted(noms)


def _statut_sans_observation(
    lignes: list[CouvertureFichier], echecs: list[str]
) -> tuple[str, str]:
    if any(ligne.statut == "indexe" for ligne in lignes):
        return "indexe", ""
    statuts = [ligne.statut for ligne in lignes if ligne.statut != "indexe"]
    if echecs:
        statuts.append("partiel")
    if not statuts:
        return "non_supporte", _RAISONS["non_supporte"]
    statut = min(statuts, key=lambda valeur: _PRIORITE.index(valeur))
    raisons = [ligne.raison for ligne in lignes if ligne.statut == statut and ligne.raison]
    if statut == "partiel" and echecs:
        raisons.insert(0, "adapter(s) en échec: " + ", ".join(sorted(set(echecs))))
    return statut, raisons[0] if raisons else _RAISONS[statut]


class OrchestrateurCodeIndex:
    """Registre d'adapters CodeIndexPort exécutés séquentiellement, sans panne globale."""

    def __init__(self, adapters=(), *, decouvreur=None, extensions=None):
        self._adapters: dict[str, object] = {}
        self._decouvreur = decouvreur
        self._extensions = _extensions_normalisees(extensions)
        if decouvreur is not None and not callable(decouvreur):
            raise TypeError("le découvreur doit être appelable")
        if isinstance(adapters, Mapping):
            for provider, adapter in adapters.items():
                self.enregistrer(provider, adapter)
        else:
            for adapter in adapters or ():
                self.enregistrer(adapter)

    def enregistrer(self, provider, adapter=None) -> "OrchestrateurCodeIndex":
        """Ajoute un adapter ; le provider peut venir de l'objet ou être explicite."""
        if adapter is None:
            adapter = provider
            provider = getattr(adapter, "provider", "")
        nom = str(provider or "").strip()
        if not nom:
            raise ValueError("un provider non vide est requis")
        if not callable(getattr(adapter, "index", None)):
            raise TypeError(f"l'adapter {nom!r} ne respecte pas CodeIndexPort")
        if nom in self._adapters:
            raise ValueError(f"provider déjà enregistré : {nom!r}")
        self._adapters[nom] = adapter
        return self

    @property
    def providers(self) -> tuple[str, ...]:
        return tuple(self._adapters)

    def executer(self, racine, fichiers=()) -> dict:
        """Exécute les adapters et rend les observations et couvertures non sérialisées."""
        return self._executer(racine, fichiers)

    def index(self, racine, fichiers=()) -> list[Observation]:
        """Exécute les adapters et rend les observations fusionnées."""
        return list(self._executer(racine, fichiers)["observations"])

    def rapport(self, racine, fichiers=()) -> dict:
        """Exécute les adapters et rend un rapport entièrement sérialisable en JSON."""
        resultat = self._executer(racine, fichiers)
        compteurs = {statut: 0 for statut in STATUTS}
        for ligne in resultat["couvertures"]:
            compteurs[ligne.statut] += 1
        return {
            "racine": str(Path(racine)),
            "providers": list(resultat["providers"]),
            "fichiers_decouverts": list(resultat["fichiers"]),
            "observations": [observation.as_dict() for observation in resultat["observations"]],
            "couvertures": [ligne.as_dict() for ligne in resultat["couvertures"]],
            "compteurs": compteurs,
            "erreurs": [dict(erreur) for erreur in resultat["erreurs"]],
        }

    def _demandes(self, racine: Path, fichiers) -> list[str]:
        explicites = [valeur for valeur in _fichiers_explicites(fichiers) if str(valeur).strip()]
        if explicites:
            return sorted({_canonique(racine, valeur) for valeur in explicites})
        if self._decouvreur is None:
            trouves = decouvrir_fichiers(racine, extensions=self._extensions)
        else:
            trouves = self._decouvreur(str(racine))
            trouves = _fichiers_explicites(trouves)
            if self._extensions is not None:
                trouves = [
                    valeur for valeur in trouves
                    if Path(str(valeur)).suffix.lower() in self._extensions
                ]
        return sorted({_canonique(racine, valeur) for valeur in trouves if str(valeur).strip()})

    def _executer(self, racine, fichiers=()) -> dict:
        root = Path(racine)
        demandes = self._demandes(root, fichiers)
        observations: list[Observation] = []
        erreurs: list[dict] = []
        couvertures_adapters: dict[str, list[CouvertureFichier]] = {}
        echecs_par_fichier: dict[str, list[str]] = {}

        for provider, adapter in self._adapters.items():
            cibles = [fichier for fichier in demandes if _accepte(adapter, fichier)]
            if not cibles:
                continue
            try:
                brutes = adapter.index(str(racine), fichiers=tuple(cibles))
            except Exception as exception:
                erreurs.append(_erreur(provider, "index", exception))
                for fichier in cibles:
                    echecs_par_fichier.setdefault(fichier, []).append(provider)
                continue

            for observation in brutes or ():
                if not isinstance(observation, Observation) or not observation.file:
                    continue
                fichier = _canonique(root, observation.file)
                if not fichier:
                    continue
                observations.append(
                    observation if fichier == observation.file
                    else replace(observation, file=fichier)
                )

            try:
                lignes = adapter.couverture(str(racine), fichiers=tuple(cibles))
            except Exception as exception:
                erreurs.append(_erreur(provider, "couverture", exception))
                for fichier in cibles:
                    echecs_par_fichier.setdefault(fichier, []).append(provider)
                continue

            for ligne in lignes or ():
                if not isinstance(ligne, CouvertureFichier) or not ligne.file:
                    continue
                fichier = _canonique(root, ligne.file)
                if not fichier:
                    continue
                couvertures_adapters.setdefault(fichier, []).append(
                    ligne if fichier == ligne.file else replace(ligne, file=fichier)
                )

        fusion = fusionner(observations)
        par_fichier: dict[str, list[Observation]] = {}
        for observation in fusion:
            par_fichier.setdefault(observation.file, []).append(observation)

        fichiers = set(demandes) | set(par_fichier) | set(couvertures_adapters)
        couvertures: list[CouvertureFichier] = []
        for fichier in sorted(fichiers):
            observations_fichier = par_fichier.get(fichier, [])
            lignes = couvertures_adapters.get(fichier, [])
            if observations_fichier:
                conflit = any(observation.status == "conflict" for observation in observations_fichier)
                statut = "conflit" if conflit else "indexe"
                raison = ""
                if conflit:
                    noms = _providers_conflit(observations_fichier)
                    raison = "conflit entre providers: " + ", ".join(noms)
                language = next(
                    (o.language for o in observations_fichier if o.language), ""
                )
                parser = next((o.parser for o in observations_fichier if o.parser), "")
            else:
                statut, raison = _statut_sans_observation(
                    lignes, echecs_par_fichier.get(fichier, [])
                )
                language = next((ligne.language for ligne in lignes if ligne.language), "")
                parser = next((ligne.parser for ligne in lignes if ligne.parser), "")
            couvertures.append(CouvertureFichier(
                file=fichier, language=language, parser=parser,
                statut=statut, raison=raison,
            ))

        return {
            "providers": tuple(self._adapters),
            "fichiers": demandes,
            "observations": fusion,
            "couvertures": couvertures,
            "erreurs": erreurs,
        }


CodeIndexOrchestrator = OrchestrateurCodeIndex
