"""Process manager d'un run multi-étapes, adossé au journal `execution_etape`.

Le manager est volontairement synchrone et sans dépendance FastAPI/Strands : un
exécuteur de worker peut l'utiliser directement, tandis qu'un service asynchrone
appelle les mêmes méthodes via `asyncio.to_thread`.

Contrat d'étape :
- `demarrer` journalise EN_COURS et retourne l'étape ;
- `terminer` écrit le checkpoint (`sortie`) et l'état TERMINE ;
- `echouer` / `annuler` / `suspendre` conservent la trace d'un arrêt non terminal :
  une étape ECHEC, ANNULE ou SUSPENDU sera rejouée à la reprise ;
- une étape TERMINE n'est jamais rejouée quand `reprendre=True`.
"""
from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable, Mapping, Sequence

from jumeau.execution import depot
from jumeau.execution.modele import AnnulationExecution, ApprobationRequise


def _appeler(fonction: Callable[..., Any], contexte: dict[str, Any]) -> Any:
    """Appelle une étape avec le contexte, ou sans argument si sa signature est vide."""
    try:
        parametres = inspect.signature(fonction).parameters
    except (TypeError, ValueError):
        parametres = {"contexte": None}
    resultat = fonction(contexte) if parametres else fonction()
    if inspect.isawaitable(resultat):
        resultat = asyncio.run(resultat)
    return resultat


class ProcessManager:
    """Journalise et reprend les étapes d'un run.

    `connect` est une fabrique de connexion psycopg (comme dans `MoteurExecution`).
    `run` doit porter au moins `tenant_id` et `run_id`. `verifier_annulation` est le
    point d'annulation coopérative consulté avant chaque étape.
    """

    def __init__(
        self,
        connect: Callable[[], Any],
        run: Mapping[str, Any],
        *,
        verifier_annulation: Callable[[], bool] | None = None,
    ):
        if not isinstance(run, Mapping):
            raise ValueError("run doit être un mapping")
        tenant_id = str(run.get("tenant_id") or "")
        run_id = str(run.get("run_id") or "")
        if not tenant_id or not run_id:
            raise ValueError("run sans tenant_id ou run_id")
        self.connect = connect
        self.run = dict(run)
        self.tenant_id = tenant_id
        self.run_id = run_id
        self.verifier_annulation = verifier_annulation

    def _avec(self, action):
        fabrique = self.connect
        possede = callable(fabrique)
        conn = fabrique() if possede else fabrique
        try:
            return action(conn)
        finally:
            if possede:
                close = getattr(conn, "close", None)
                if close:
                    close()

    def annule(self) -> bool:
        """Vrai si l'annulation a été demandée (callback ou drapeau persistant)."""
        if self.verifier_annulation is not None:
            try:
                if self.verifier_annulation():
                    return True
            except Exception:  # noqa: BLE001 - le drapeau en base reste la source de vérité
                pass
        run = self._avec(lambda conn: depot.obtenir_run(conn, self.tenant_id, self.run_id))
        return bool(run and run.get("cancel_requested_at"))

    def etapes(self) -> list[dict]:
        return self._avec(lambda conn: depot.etapes_run(conn, self.tenant_id, self.run_id))

    def lire(self, nom: str) -> dict | None:
        return self._avec(lambda conn: depot.obtenir_etape(
            conn, self.tenant_id, self.run_id, nom))

    def checkpoint(self) -> dict[str, Any]:
        """Sorties des étapes TERMINE, indexées par nom."""
        return {
            etape["nom"]: etape.get("sortie")
            for etape in self.etapes()
            if etape.get("etat") == "TERMINE"
        }

    def demarrer(self, nom: str, *, entree: Mapping[str, Any] | None = None,
                 seq: int | None = None, forcer: bool = False) -> dict:
        etape, _ = self._avec(lambda conn: depot.demarrer_etape(
            conn, self.tenant_id, self.run_id, nom, seq=seq, entree=entree, forcer=forcer))
        return etape

    def terminer(self, nom: str, sortie: Any = None) -> dict:
        return self._avec(lambda conn: depot.terminer_etape(
            conn, self.tenant_id, self.run_id, nom, sortie))

    def echouer(self, nom: str, erreur: str | Exception) -> dict:
        return self._avec(lambda conn: depot.clore_etape(
            conn, self.tenant_id, self.run_id, nom, "ECHEC", str(erreur)))

    def annuler(self, nom: str, erreur: str | Exception = "annulé") -> dict:
        return self._avec(lambda conn: depot.clore_etape(
            conn, self.tenant_id, self.run_id, nom, "ANNULE", str(erreur)))

    def suspendre(self, nom: str, erreur: str | Exception = "suspendu") -> dict:
        return self._avec(lambda conn: depot.clore_etape(
            conn, self.tenant_id, self.run_id, nom, "SUSPENDU", str(erreur)))

    def executer(self, etapes: Mapping[str, Callable[..., Any]]
                 | Sequence[tuple[str, Callable[..., Any]]], *,
                 reprendre: bool = True) -> dict:
        """Exécute une séquence d'étapes nommées, en reprenant les checkpoints.

        Une étape reçoit un contexte `{"run", "etape", "seq", "resultats",
        "checkpoint"}` ; une fonction sans paramètre est appelée directement. Une
        annulation demandée avant ou pendant une étape lève `AnnulationExecution`.
        """
        elements = list(etapes.items()) if isinstance(etapes, Mapping) else list(etapes)
        resultats: dict[str, Any] = {}
        reprises: list[str] = []
        for seq, (nom, fonction) in enumerate(elements):
            nom = str(nom).strip()
            if not nom:
                raise ValueError("nom d'étape requis")
            if self.annule():
                raise AnnulationExecution(f"run {self.run_id} annulé avant l'étape {nom!r}")
            if reprendre:
                existante = self.lire(nom)
                if existante is not None and existante.get("etat") == "TERMINE":
                    resultats[nom] = existante.get("sortie")
                    reprises.append(nom)
                    continue
            self.demarrer(nom, entree={"run_id": self.run_id, "seq": seq}, seq=seq,
                          forcer=not reprendre)
            contexte = {
                "run": self.run,
                "etape": nom,
                "seq": seq,
                "resultats": dict(resultats),
                "checkpoint": self.checkpoint(),
            }
            try:
                sortie = _appeler(fonction, contexte)
            except AnnulationExecution as exc:
                self.annuler(nom, exc)
                raise
            except ApprobationRequise as exc:
                self.suspendre(nom, exc)
                raise
            except Exception as exc:  # noqa: BLE001 - l'étape est journalisée puis relancée
                self.echouer(nom, f"{type(exc).__name__}: {exc}")
                raise
            self.terminer(nom, sortie)
            resultats[nom] = sortie
        return {"run_id": self.run_id, "resultats": resultats, "reprises": reprises}


__all__ = ["ProcessManager"]
