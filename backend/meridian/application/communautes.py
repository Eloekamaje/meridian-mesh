"""Communautés de graphe : label propagation déterministe, rapports factuels.

Ce module ne prétend pas remplacer Leiden/Louvain. Il fournit un pipeline complet et
reproductible : graphe observé → communautés → rapport → index global. Un moteur plus avancé
peut remplacer la fonction `construire` sans changer le reste.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict

__all__ = ["construire", "construire_hierarchique", "rapport"]


def _adjacence(store, tenant, ids, profondeur=1):
    adjacence: dict[str, set[str]] = {i: set() for i in ids}
    for twin_id in ids:
        try:
            voisins = store.voisins(tenant, twin_id, profondeur=profondeur, sens="les_deux")
        except Exception:
            voisins = []
        for voisin in voisins or ():
            identifiant = str(voisin.get("id") or "")
            if identifiant:
                adjacence.setdefault(twin_id, set()).add(identifiant)
                adjacence.setdefault(identifiant, set()).add(twin_id)
    return adjacence


def _labels(adjacence, iterations=12):
    labels = {noeud: noeud for noeud in adjacence}
    for _ in range(max(1, int(iterations))):
        change = False
        for noeud in sorted(adjacence):
            if not adjacence[noeud]:
                continue
            compteur = Counter(labels[voisin] for voisin in adjacence[noeud])
            meilleur = min(compteur, key=lambda label: (-compteur[label], label))
            if labels[noeud] != meilleur:
                labels[noeud] = meilleur
                change = True
        if not change:
            break
    return labels


def _composantes_labels(labels):
    groupes = defaultdict(set)
    for noeud, label in labels.items():
        groupes[label].add(noeud)
    return list(groupes.values())


def _fingerprint(membres, relations) -> str:
    charge = json.dumps({"membres": sorted(membres), "relations": relations},
                        ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(charge.encode()).hexdigest()[:20]


def construire(store, tenant: str, twin_ids, *, domaines=None, profondeur: int = 1,
               iterations: int = 12) -> list[dict]:
    """Graphe non orienté autour des Twins fournis, puis label propagation stable."""
    domaines = domaines or {}
    ids = sorted({str(i) for i in twin_ids or () if str(i)})
    if not ids:
        return []
    adjacence = _adjacence(store, tenant, ids, profondeur)
    groupes = _composantes_labels(_labels(adjacence, iterations))
    resultat = []
    for membres in groupes:
        relations = sum(1 for n in membres for v in adjacence[n] if v in membres) // 2
        resultat.append({
            "membres": sorted(membres),
            "relations": relations,
            "domain": sorted({domaines[n] for n in membres if domaines.get(n)})[:8],
            "fingerprint": _fingerprint(membres, relations),
        })
    return sorted(resultat, key=lambda c: (-len(c["membres"]), c["membres"][0]))


def construire_hierarchique(store, tenant: str, twin_ids, *, domaines=None,
                             profondeur: int = 1, niveaux: int = 3) -> list[dict]:
    """Communautés par coarsening successif : niveau 1, puis communautés de communautés."""
    domaines = domaines or {}
    ids = sorted({str(i) for i in twin_ids or () if str(i)})
    if not ids:
        return []
    ajacence = _adjacence(store, tenant, ids, profondeur)
    labels = _labels(ajacence)
    niveaux_sortie = []
    for niveau in range(1, max(1, int(niveaux)) + 1):
        groupes = _composantes_labels(labels)
        resultat = []
        for membres in groupes:
            relations = sum(1 for n in membres for v in ajacence.get(n, ()) if v in membres) // 2
            resultat.append({
                "membres": sorted(membres), "relations": relations,
                "domain": sorted({domaines[n] for n in membres if domaines.get(n)})[:8],
                "fingerprint": _fingerprint(membres, relations), "level": niveau,
            })
        niveaux_sortie.append({
            "niveau": niveau,
            "communautes": sorted(resultat, key=lambda c: (-len(c["membres"]), c["membres"][0])),
        })
        if len(groupes) <= 1:
            break
        # Coarsening : chaque communauté devient un nœud du niveau suivant.
        label_par_noeud = {n: labels[n] for n in labels}
        meta = defaultdict(set)
        for noeud, voisins in ajacence.items():
            for voisin in voisins:
                if label_par_noeud[noeud] != label_par_noeud[voisin]:
                    meta[label_par_noeud[noeud]].add(label_par_noeud[voisin])
        labels = {label: label for label in {label_par_noeud[n] for n in labels}}
        for source, cibles in meta.items():
            for cible in cibles:
                ajacence.setdefault(source, set()).add(cible)
        ajacence = {n: {v for v in ajacence.get(n, set()) if v in labels} for n in labels}
    return niveaux_sortie


def rapport(communaute: dict) -> str:
    membres = communaute.get("membres") or []
    domaines = communaute.get("domain") or []
    return (f"Communauté de {len(membres)} entité(s), {communaute.get('relations', 0)} relation(s) "
            f"observée(s). Entités : {', '.join(membres[:10])}."
            + (f" Domaines : {', '.join(domaines)}." if domaines else ""))
