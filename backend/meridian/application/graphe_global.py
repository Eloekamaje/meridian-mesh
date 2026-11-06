"""Graph RAG global déterministe : communautés de voisinage et résumés bornés.

Ce n'est pas un LLM qui invente une synthèse : on regroupe les Twins connectés autour des
entités actives, puis on rend un résumé factuel (taille, domaines, entités les plus liées,
relations observées). Le modèle reçoit ce résumé comme contexte, jamais comme vérité.
"""
from __future__ import annotations

from collections import defaultdict

__all__ = ["communautes", "resume_contextuel"]


def _composantes(adjacence: dict[str, set[str]]) -> list[set[str]]:
    vues, resultat = set(), []
    for depart in adjacence:
        if depart in vues:
            continue
        pile, composante = [depart], set()
        vues.add(depart)
        while pile:
            noeud = pile.pop()
            composante.add(noeud)
            for voisin in adjacence.get(noeud, ()):
                if voisin not in vues:
                    vues.add(voisin)
                    pile.append(voisin)
        resultat.append(composante)
    return resultat


def communautes(store, tenant: str, seeds, *, profondeur: int = 2,
                domaines_connus: dict | None = None) -> list[dict]:
    """Composantes connexes autour des seeds, avec degré et domaines observés."""
    adjacence: dict[str, set[str]] = defaultdict(set)
    domaines: dict[str, str] = dict(domaines_connus or {})
    for seed in list(dict.fromkeys(str(s) for s in seeds or ()))[:20]:
        if not seed:
            continue
        adjacence.setdefault(seed, set())
        try:
            voisins = store.voisins(tenant, seed, profondeur=profondeur, sens="les_deux")
        except Exception:
            voisins = []
        for voisin in voisins or ():
            identifiant = str(voisin.get("id") or "")
            if not identifiant:
                continue
            adjacence[seed].add(identifiant)
            adjacence[identifiant].add(seed)
            if voisin.get("domaine"):
                domaines[identifiant] = str(voisin["domaine"])
    resultat = []
    for composante in _composantes(dict(adjacence)):
        degres = sorted(((len(adjacence[n]), n) for n in composante), reverse=True)
        resultat.append({
            "taille": len(composante),
            "entites": [n for _, n in degres[:8]],
            "degre_max": degres[0][0] if degres else 0,
            "domaines": sorted({domaines[n] for n in composante if n in domaines})[:8],
            "relations_observees": sum(len(adjacence[n]) for n in composante) // 2,
        })
    return sorted(resultat, key=lambda c: (-c["taille"], -c["degre_max"]))[:8]


def resume_contextuel(store, tenant: str, seeds, *, profondeur: int = 2,
                      domaines_connus: dict | None = None) -> dict:
    groupes = communautes(store, tenant, seeds, profondeur=profondeur,
                          domaines_connus=domaines_connus)
    if not groupes:
        return {}
    return {
        "mode": "global-deterministe",
        "communautes": groupes,
        "resume": " ; ".join(
            f"{g['taille']} entités autour de {', '.join(g['entites'][:3])}"
            + (f" (domaines : {', '.join(g['domaines'])})" if g["domaines"] else "")
            for g in groupes[:5]),
    }
