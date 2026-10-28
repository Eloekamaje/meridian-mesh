"""Banc de latence : des questions de référence par classe (exigences non fonctionnelles §5, §8), leurs durées
par phase, comparées à l'objectif. Usage : python -m jumeau.latence [--repetitions 1]

Ponctuel et manuel (chaque question coûte des appels au modèle) ; à rejouer avant et après une optimisation.
"""
import argparse
import asyncio
import logging
import statistics

from jumeau import flore

# (classe, jumeaux mobilisés ou None = Flore orchestratrice, question) ; objectif = première réponse utile, en s.
REFERENCES = [
    ("simple", None, "qui es-tu ?"),
    ("simple", "conduit", "que fait Conduit ?"),
    ("analyse", "conduit", "comment fonctionne la publication d'un article sur Conduit ?"),
    ("analyse", ["conduit", "gestion-des-articles", "meridian"],
     "illustre-moi avec un schéma la publication d'un article dans Conduit"),
]
OBJECTIFS = {"simple": 2.0, "analyse": 5.0}


NOMS = {"conduit": "Conduit", "gestion-des-articles": "Gestion des articles", "meridian": "Méridian Mesh"}


async def mesurer(jumeaux, question):
    """Comme le serveur : une application sélectionnée, sinon celle que la question nomme, sinon l'orchestration."""
    visibles = jumeaux if isinstance(jumeaux, list) else list(NOMS)
    cible = [jumeaux] if isinstance(jumeaux, str) else flore.application_nommee(
        question, [{"id": j, "nom": NOMS.get(j, j)} for j in visibles])
    if cible:
        r = await flore.repondre(cible[0], question, "banc-latence")
    else:
        r = await flore.mobiliser(visibles, question, "banc-latence")
    return (r or {}).get("durees") or {}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--repetitions", type=int, default=1)
    a = p.parse_args()
    logging.basicConfig(level=logging.WARNING)
    for classe, jumeaux, question in REFERENCES:
        mesures = [asyncio.run(mesurer(jumeaux, question)) for _ in range(max(1, a.repetitions))]
        totaux = sorted(m.get("total", 0) for m in mesures)
        p95 = totaux[min(len(totaux) - 1, int(0.95 * len(totaux)))]
        phases = {k: round(statistics.median(m.get(k, 0) for m in mesures), 1)
                  for k in ("contexte", "cartes", "modele", "outils", "relecture", "controles")}
        print(f"[{classe}] {question}\n  p50 {statistics.median(totaux):.1f} s · p95 {p95:.1f} s · objectif "
              f"{OBJECTIFS[classe]} s (première réponse utile) · phases {phases}")


if __name__ == "__main__":
    main()
