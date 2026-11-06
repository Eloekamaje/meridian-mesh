"""Boucle de réconciliation globale, sans scheduler externe.

La boucle reçoit une fonction `executer` (généralement `reconcilier` pour un tenant)
et l'appelle à intervalle régulier. Elle est testable sans dormir : `attendre` est
injectable et `arreter` est idempotent.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable

journal = logging.getLogger("meridian.reconciliation_worker")

__all__ = ["BoucleReconciliation"]


class BoucleReconciliation:
    def __init__(self, executer: Callable[[], object], *, intervalle: float = 3600,
                 attendre: Callable[[float], object] | None = None):
        self.executer = executer
        self.intervalle = max(1.0, float(intervalle))
        self._stop = threading.Event()
        self._attendre = attendre or self._stop.wait
        self._thread: threading.Thread | None = None
        self.passes = 0

    @property
    def arretee(self) -> bool:
        return self._stop.is_set()

    def une_passe(self):
        if self.arretee:
            return None
        self.passes += 1
        return self.executer()

    def tourner(self):
        while not self.arretee:
            try:
                self.une_passe()
            except Exception:  # noqa: BLE001 - une passe ne doit pas tuer le worker
                journal.exception("réconciliation : passe en échec")
            self._attendre(self.intervalle)

    def demarrer(self):
        self._stop.clear()
        self._thread = threading.Thread(
            target=self.tourner, name="meridian-reconciliation", daemon=True)
        self._thread.start()
        return self._thread

    def arreter(self, timeout: float = 5.0):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)
