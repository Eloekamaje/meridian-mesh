"""Durée de chaque phase d'une réponse (exigences non fonctionnelles §5, §8 : première réponse utile < 2 s p50).

On ne peut pas tenir un objectif qu'on ne mesure pas : chaque réponse porte ses durées (contexte, modèle, outils,
relecture, contrôles), journalisées, et `python -m meridian.adapters.outbound.llm.latence` en tire les p50/p95 par classe de question.
"""
import os
import time
from contextlib import contextmanager

# Tarifs par million de jetons : estimation, jamais une facture. DeepSeek est le défaut local ; les autres
# fournisseurs doivent être renseignés explicitement (les tarifs changent).
PRIX_DEFAUT = {"deepseek": (0.27, 1.10)}


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


def usage(agent_strands):
    """L'usage cumulé du modèle pour un agent Strands, en jetons ; zéro si le fournisseur ne le rend pas."""
    metriques = getattr(agent_strands, "event_loop_metrics", None)
    brut = getattr(metriques, "accumulated_usage", None) or {}

    def entier(cle):
        try:
            return max(0, int(brut.get(cle) or 0))
        except (TypeError, ValueError):
            return 0
    return {"entree": entier("inputTokens"), "sortie": entier("outputTokens"),
            "total": entier("totalTokens"), "cache_lu": entier("cacheReadInputTokens"),
            "cache_ecrit": entier("cacheWriteInputTokens")}


def fusionner_usages(*usages):
    """Somme les usages d'un tour (agent principal, relecture, sous-agents)."""
    total = {"entree": 0, "sortie": 0, "total": 0, "cache_lu": 0, "cache_ecrit": 0}
    for u in usages:
        if not isinstance(u, dict):
            continue
        for cle in total:
            try:
                total[cle] += max(0, int(u.get(cle) or 0))
            except (TypeError, ValueError):
                pass
    return total


def cout(usage_tour):
    """Estimation du coût en devise configurée ; None si aucun tarif n'est connu (aucun chiffre inventé)."""
    if not isinstance(usage_tour, dict):
        return None
    fournisseur = os.environ.get("JUMEAU_MODELE", "deepseek").strip().lower()

    def prix(nom, defaut):
        try:
            return max(0.0, float(os.environ.get(nom, defaut)))
        except (TypeError, ValueError):
            return max(0.0, float(defaut))
    entree_defaut, sortie_defaut = PRIX_DEFAUT.get(fournisseur, (0.0, 0.0))
    prix_entree = prix("JUMEAU_COUT_ENTREE_MILLION", entree_defaut)
    prix_sortie = prix("JUMEAU_COUT_SORTIE_MILLION", sortie_defaut)
    if prix_entree <= 0 and prix_sortie <= 0:
        return None
    montant = (usage_tour.get("entree", 0) / 1_000_000 * prix_entree
               + usage_tour.get("sortie", 0) / 1_000_000 * prix_sortie)
    return {"montant": round(montant, 6), "devise": os.environ.get("JUMEAU_COUT_DEVISE", "USD").strip() or "USD",
            "estimation": True}
