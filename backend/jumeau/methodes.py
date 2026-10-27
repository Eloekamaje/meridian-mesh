"""Méthodes de Flore : fiches Markdown chargées à la demande selon la question (comme des skills).

Le prompt ne porte que le catalogue (nom + description) ; la fiche complète n'entre dans le contexte que si
Flore la consulte. Une fiche s'ajoute en déposant un fichier dans methodes/, sans toucher au code.
"""
import logging
from pathlib import Path

DOSSIER = Path(__file__).with_name("methodes")
journal = logging.getLogger("meridian.jumeau")


def _lire_fichier(chemin):
    """(champs de l'en-tête, corps) ; None si la fiche n'a pas d'en-tête avec nom et description."""
    texte = chemin.read_text(encoding="utf-8").replace("\r\n", "\n")
    if not texte.startswith("---\n"):
        return None
    entete, _, corps = texte[4:].partition("\n---\n")
    champs = {k.strip(): v.strip() for k, v in (l.split(":", 1) for l in entete.splitlines() if ":" in l)}
    return (champs, corps.strip()) if champs.get("nom") and champs.get("description") else None


def _fiches():
    for chemin in sorted(DOSSIER.glob("*.md")):
        fiche = _lire_fichier(chemin)
        if fiche:
            yield fiche
        else:
            journal.warning("méthode ignorée (en-tête nom/description manquant) : %s", chemin.name)


def catalogue():
    return [{"nom": champs["nom"], "description": champs["description"]} for champs, _ in _fiches()]


def lire(nom):
    """Consignes de la méthode `nom`, ou None si elle n'existe pas (seuls les noms du catalogue sont lisibles)."""
    return next((corps for champs, corps in _fiches() if champs["nom"] == nom), None)
