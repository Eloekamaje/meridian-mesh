"""Chargement déclaratif de manifestes d'outils (ADR-0004).

Un manifeste est une donnée : un fichier JSON ou un dossier de fichiers JSON. Chaque contrat est validé par
`capacites.ManifesteOutil`, puis inscrit dans un `RegistreCapacites`. Les clés inconnues, les secrets, les URL et
les doublons sont refusés avant toute inscription. Aucun adaptateur, aucun code et aucun appel réseau ne sont
chargés ou exécutés : le chargeur ne produit que des manifestes.
"""
from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
from typing import Any

from jumeau.capacites import ConflitManifeste, ManifesteInvalide, ManifesteOutil, RegistreCapacites

_TAILLE_MAX = 1_000_000
_CHAMPS = frozenset({
    "nom", "version", "description", "capacite", "schema_entree", "schema_sortie",
    "types_objets_lus", "types_objets_ecrits", "portee", "tenant", "persona", "perimetre",
    "lecture_seule", "cout", "timeout_ms", "mode_preuve", "effets_de_bord", "source",
    "signature", "allowlist",
})


class ErreurManifestes(ValueError):
    """Le chemin, le fichier ou le manifeste ne peut pas être chargé."""


class ManifesteRefuse(ErreurManifestes):
    """Le manifeste viole le contrat de sûreté du registre."""


class DoublonManifeste(ErreurManifestes):
    """Le même nom et la même version sont déjà présents."""


class _DoublonCle(ValueError):
    pass


def _paires(paires: list[tuple[str, Any]]) -> dict:
    objet: dict[str, Any] = {}
    for cle, valeur in paires:
        if cle in objet:
            raise _DoublonCle
        objet[cle] = valeur
    return objet


def lister_fichiers(chemin: Any) -> list[Path]:
    """Les fichiers JSON d'un manifeste ou d'un dossier, triés ; les autres fichiers sont ignorés."""
    try:
        base = Path(chemin)
    except TypeError as erreur:
        raise ManifesteRefuse("chemin invalide") from erreur
    if not base.exists():
        raise ManifesteRefuse("chemin introuvable")
    if base.is_symlink():
        raise ManifesteRefuse("lien symbolique refusé")
    if base.is_file():
        if base.suffix.lower() != ".json":
            raise ManifesteRefuse("fichier JSON attendu")
        return [base]
    if base.is_dir():
        return sorted(
            fichier
            for fichier in base.iterdir()
            if fichier.is_file() and not fichier.is_symlink() and fichier.suffix.lower() == ".json"
        )
    raise ManifesteRefuse("fichier ou dossier attendu")


def _lire_json(fichier: Path) -> Any:
    try:
        taille = fichier.stat().st_size
    except OSError as erreur:
        raise ManifesteRefuse(f"{fichier.name} : fichier illisible") from erreur
    if taille > _TAILLE_MAX:
        raise ManifesteRefuse(f"{fichier.name} : fichier trop volumineux")
    try:
        texte = fichier.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as erreur:
        raise ManifesteRefuse(f"{fichier.name} : fichier illisible") from erreur
    try:
        return json.loads(texte, object_pairs_hook=_paires)
    except _DoublonCle as erreur:
        raise ManifesteRefuse(f"{fichier.name} : clé JSON dupliquée") from erreur
    except json.JSONDecodeError as erreur:
        raise ManifesteRefuse(f"{fichier.name} : JSON invalide") from erreur
    except (ValueError, RecursionError) as erreur:
        raise ManifesteRefuse(f"{fichier.name} : JSON invalide") from erreur


def _contrat(objet: Any, fichier: Path, rang: int) -> ManifesteOutil:
    if not isinstance(objet, Mapping):
        raise ManifesteRefuse(f"{fichier.name}[{rang}] : manifeste objet attendu")
    if set(objet) - _CHAMPS:
        raise ManifesteRefuse(f"{fichier.name}[{rang}] : clé de manifeste inconnue")
    try:
        return ManifesteOutil(**dict(objet))
    except ManifesteInvalide as erreur:
        raise ManifesteRefuse(f"{fichier.name}[{rang}] : {erreur}") from erreur
    except (TypeError, RecursionError) as erreur:
        raise ManifesteRefuse(f"{fichier.name}[{rang}] : manifeste invalide") from erreur


def _manifests(fichier: Path) -> list[ManifesteOutil]:
    charge = _lire_json(fichier)
    if isinstance(charge, Mapping):
        return [_contrat(charge, fichier, 0)]
    if isinstance(charge, list):
        return [_contrat(objet, fichier, rang) for rang, objet in enumerate(charge)]
    raise ManifesteRefuse(f"{fichier.name} : objet ou liste de manifestes attendu")


def _versions(registre: Any, nom: str) -> list[ManifesteOutil]:
    fonction = getattr(registre, "versions", None)
    if callable(fonction):
        return list(fonction(nom))
    decrire = getattr(registre, "decrire", None)
    if not callable(decrire):
        return []
    existant = decrire(nom)
    return [existant] if existant is not None else []


def charger(registre: RegistreCapacites, chemin: Any) -> list[ManifesteOutil]:
    """Valide tous les manifestes du chemin, puis les inscrit ; rend les contrats chargés."""
    inscrire = getattr(registre, "enregistrer", None)
    if not callable(inscrire):
        raise ManifesteRefuse("registre capacitaire attendu")

    contrats: list[ManifesteOutil] = []
    for fichier in lister_fichiers(chemin):
        contrats.extend(_manifests(fichier))

    vus: set[tuple[str, str]] = set()
    for contrat in contrats:
        cle = (contrat.nom, contrat.version)
        if cle in vus:
            raise DoublonManifeste(f"doublon de manifeste : {contrat.nom} {contrat.version}")
        vus.add(cle)
        if any(version.version == contrat.version for version in _versions(registre, contrat.nom)):
            raise DoublonManifeste(f"doublon de manifeste : {contrat.nom} {contrat.version}")

    for contrat in contrats:
        try:
            inscrire(contrat)
        except ConflitManifeste as erreur:
            raise DoublonManifeste(
                f"doublon de manifeste : {contrat.nom} {contrat.version}") from erreur
    return contrats


__all__ = [
    "DoublonManifeste",
    "ErreurManifestes",
    "ManifesteRefuse",
    "charger",
    "lister_fichiers",
]
