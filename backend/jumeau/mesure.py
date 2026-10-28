"""Durée de chaque phase d'une réponse (exigences non fonctionnelles §5, §8 : première réponse utile < 2 s p50).

On ne peut pas tenir un objectif qu'on ne mesure pas : chaque réponse porte ses durées (contexte, modèle, outils,
relecture, contrôles), journalisées, et `python -m jumeau.latence` en tire les p50/p95 par classe de question.
"""
import time
from contextlib import contextmanager


class Chrono:
    def __init__(self):
        self.debut, self.phases = time.monotonic(), {}

    def _ajouter(self, nom, duree):
        self.phases[nom] = round(self.phases.get(nom, 0) + duree, 2)

    @contextmanager
    def phase(self, nom):
        t = time.monotonic()
        try:
            yield
        finally:
            self._ajouter(nom, time.monotonic() - t)

    def texte(self):
        """L'instant du premier mot envoyé à l'interlocuteur. Mesuré une seule fois, et seulement si un mot part :
        c'est la latence que l'on ressent, celle qu'aucun chronomètre ne relevait (plan de remédiation L0.6/L2.4)."""
        self.phases.setdefault("premier_texte", round(time.monotonic() - self.debut, 2))

    def agent(self, agent_strands):
        """Sépare le temps de l'agent entre ses outils (métriques Strands) et le modèle (le reste)."""
        metriques = getattr(agent_strands, "event_loop_metrics", None)
        outils = sum(m.total_time for m in (getattr(metriques, "tool_metrics", None) or {}).values())
        total = self.phases.pop("agent", 0)
        self._ajouter("outils", outils)
        self._ajouter("modele", max(0.0, total - outils))

    def bilan(self):
        return {"total": round(time.monotonic() - self.debut, 2), **self.phases}
