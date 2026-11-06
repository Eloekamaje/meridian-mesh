"""Recherche et lecture bornées dans la documentation d'entreprise (Confluence, SharePoint)."""
from __future__ import annotations

from typing import Iterable

__all__ = ["collecter"]


def collecter(readers: Iterable, question: str, *, limite: int = 4) -> list[dict]:
    """Cherche la question dans des lecteurs déjà construits et lit au plus `limite` extraits.

    Chaque extrait porte son locator versionné : le modèle peut le citer, et la preuve reste
    vérifiable. Une source en panne est ignorée ; elle ne bloque pas les autres.
    """
    resultat: list[dict] = []
    for reader in readers:
        if len(resultat) >= limite:
            break
        try:
            trouves = reader.chercher(question)
        except Exception:
            continue
        for trouve in (trouves or [])[:2]:
            if len(resultat) >= limite:
                break
            try:
                doc = reader.lire(trouve["ref"], 1, 40)
            except Exception:
                continue
            lignes = doc.get("lignes") or []
            if not lignes:
                continue
            resultat.append({
                "source": getattr(reader, "nom", ""),
                "systeme": getattr(reader, "systeme", ""),
                "source_id": getattr(reader, "source_id", None),
                "twin_id": getattr(reader, "jumeau_id", ""),
                "espace": getattr(reader, "espace", ""),
                "acl": getattr(reader, "acl", None),
                "ref": str(doc.get("ref") or trouve.get("ref") or ""),
                "version": str(doc.get("version") or ""),
                "titre": doc.get("titre") or trouve.get("titre") or "",
                "locator": doc.get("locator", ""),
                "lignes": list(lignes),
                "extrait": "\n".join(lignes)[:1200],
            })
    return resultat
