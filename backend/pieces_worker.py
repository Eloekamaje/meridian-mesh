"""Processus d'extraction isolé : un document hostile ne peut ni bloquer ni envenimer le serveur.

Le parent envoie un JSON sur stdin, le worker pose ses limites Unix, extrait, puis rend un JSON sur stdout.
Il ne journalise jamais le contenu de la pièce et n'ouvre aucune connexion réseau.
"""
from __future__ import annotations

import base64
import contextlib
import io
import json
import socket
import sys

try:  # limites POSIX ; Windows n'a pas resource, le timeout du parent reste la borne
    import resource
except ImportError:  # pragma: no cover - plateforme non POSIX
    resource = None

MAX_MEMOIRE = 768 * 1024 * 1024
MAX_CPU = 20


def _limites() -> None:
    """Borne la mémoire et le temps CPU avant même de charger les extracteurs natifs."""
    if resource is None:
        return
    for limite, valeur in ((resource.RLIMIT_AS, (MAX_MEMOIRE, MAX_MEMOIRE)),
                           (resource.RLIMIT_CPU, (MAX_CPU, MAX_CPU + 5))):
        try:
            resource.setrlimit(limite, valeur)
        except (OSError, ValueError):
            pass  # une plateforme sans limite disponible ne doit pas empêcher l'extraction


def _sans_reseau() -> None:
    """Interdit toute prise de contact réseau depuis le processus d'extraction."""
    def refuser(*args, **kwargs):
        raise OSError("réseau interdit dans le processus d'extraction")

    socket.socket = refuser
    socket.create_connection = refuser
    socket.socketpair = refuser


def _refus(message: str, statut: int = 400) -> dict:
    return {"ok": False, "refus": True, "message": message, "statut": int(statut)}


def _decoder(charge: dict) -> tuple[str, str, str, bytes, dict]:
    mode = str(charge.get("mode") or "")
    nom = str(charge.get("nom") or "")
    mime = str(charge.get("mime") or "")
    params = charge.get("params")
    if not isinstance(params, dict):
        params = {}
    data = base64.b64decode(str(charge.get("data_b64") or ""), validate=True)
    return mode, nom, mime, data, params


def _executer(pieces, mode: str, nom: str, mime: str, data: bytes, params: dict):
    if mode == "analyse":
        return pieces.analyser(nom, mime, data)
    if mode == "tables":
        return pieces.tableaux_bruts(nom, data, params)
    raise pieces.PieceRefusee("Mode d'extraction inconnu.")


def _ecrire(reponse: dict) -> None:
    sortie = json.dumps(reponse, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(sortie)
    sys.stdout.buffer.flush()


def main() -> int:
    _limites()
    import pieces  # les limites sont posées avant le chargement du parseur natif

    _sans_reseau()
    try:
        charge = json.loads(sys.stdin.buffer.read() or b"{}")
        if not isinstance(charge, dict):
            raise ValueError("charge invalide")
        mode, nom, mime, data, params = _decoder(charge)
    except (OSError, ValueError, TypeError, KeyError):
        _ecrire(_refus("Entrée d'extraction invalide."))
        return 0

    try:
        with contextlib.redirect_stdout(io.StringIO()):
            resultat = _executer(pieces, mode, nom, mime, data, params)
    except pieces.PieceRefusee as e:
        reponse = _refus(str(e), getattr(e, "statut", 400))
    except Exception:  # jamais de trace ni de contenu dans la réponse
        reponse = _refus("Lecture impossible : le fichier est peut-être corrompu.")
    else:
        reponse = {"ok": True, "result": resultat}
    try:
        _ecrire(reponse)
    except (TypeError, ValueError):
        _ecrire(_refus("Lecture impossible : résultat non sérialisable."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
