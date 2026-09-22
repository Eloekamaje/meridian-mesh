"""GET /api/mesh/vue — vue bornée du Mesh (fenêtre monde + zoom), quel que soit le nombre de jumeaux.

Le client ne charge jamais le graphe entier : il demande ce qu'il affiche. Les droits s'appliquent AVANT l'agrégation :
la pyramide n'est construite que sur les jumeaux autorisés du périmètre demandé, donc aucune grappe ne compte ni ne
laisse deviner un jumeau restreint. Les dépendances restreintes (anonymisées dans /mesh) sont volontairement absentes
des vues agrégées.
"""
import random
import time
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

import pyramide

TTL_S = 30.0
MAX_SYNTHETIQUE = 5_000_000
MAX_DOMAINES = 2000

# ---------- Détail synthétique d'UN jumeau (labo) : appelé seulement au clic, jamais dans une vue de viewport
# (qui reste minimale : id, position, degré). Déterministe par (graine, domaines, i) — un aller-retour, pas d'état.
_MISSIONS = ["Orchestre {x}", "Gère {x}", "Surveille {x}", "Consolide {x}", "Expose {x}", "Distribue {x}", "Calcule {x}", "Archive {x}", "Valide {x}", "Synchronise {x}"]
_OBJETS = ["les transactions du parcours", "les comptes et leurs soldes", "les alertes clients", "le catalogue produits",
           "les événements du bus", "les habilitations", "les rapports réglementaires", "les files d'attente",
           "les dossiers en cours", "la tarification", "les sessions actives", "les expéditions"]
_EQUIPES = ["Équipe Plateforme", "Équipe Risque", "Équipe Data", "Équipe Produit", "Équipe Ops", "Équipe Support", "Équipe Sécurité", "Équipe Client"]
_NOMS = ["Martin", "Dubois", "Nguyen", "Diallo", "Rossi", "Petit", "Keita", "Morel", "Bara", "Fabre"]
_STATUTS = ["actif", "actif", "actif", "actif", "observation", "en construction"]
_AUTONOMIES = ["supervisé", "restreint", "aucune"]
_SOURCES_NOMS = {"code": "GitHub", "bdd": "PostgreSQL", "observabilite": "Datadog", "incidents": "ServiceNow", "documentation": "Confluence", "projet": "Jira"}


def _detail_jumeau_synthetique(i: int, dom_nom: str, graine: int) -> dict:
    r = random.Random((graine * 1_000_003 + i * 2_654_435_761) & 0xFFFFFFFF)
    sources = [c for c in _SOURCES_NOMS if r.random() < 0.68] or ["code"]
    return {
        "nom": f"{dom_nom} · {i}",
        "mission": r.choice(_MISSIONS).format(x=r.choice(_OBJETS)),
        "proprietaire": f"{r.choice(_EQUIPES)} — {r.choice('ABCDEFGH')}. {r.choice(_NOMS)}",
        "statut": r.choice(_STATUTS),
        "autonomie": r.choice(_AUTONOMIES),
        "couverture": r.randint(32, 97),
        "fraicheur": f"il y a {r.randint(1, 180)} min",
        "capacites": r.sample(_OBJETS, k=min(3, len(_OBJETS))),
        "sources": {c: (c in sources) for c in _SOURCES_NOMS},
        "sources_detail": [{"cle": c, "nom": _SOURCES_NOMS[c], "statut": "prete"} for c in sources],
    }


def build_mesh_vue_router(deps: dict) -> APIRouter:
    router = APIRouter()
    db = deps["db"]
    resoudre_perimetre = deps["resoudre_perimetre"]
    autorisations = deps["autorisations"]
    NO_ID = deps["NO_ID"]
    cache: dict = {}  # (espace, n) -> (instant, Pyramide) ; synthétiques conservés par (n, graine)

    async def pyramide_reelle(espace: dict) -> pyramide.Pyramide:
        cle = ("reel", espace["id"])
        vu = cache.get(cle)
        if vu and time.monotonic() - vu[0] < TTL_S:
            return vu[1]
        tous = await db.jumeaux.find({}, NO_ID).to_list(None)
        aut = autorisations(espace, [j["id"] for j in tous])
        visibles = [j for j in tous if j["id"] in aut]
        rels = await db.relations.find({}, NO_ID).to_list(None)
        sit = await db.situations.find({}, {"_id": 0, "jumeaux": 1, "statut": 1}).to_list(None)
        noms = {j["nom"]: j["id"] for j in tous}
        en_alerte = {noms.get(x, x) for s in sit if s.get("statut") not in ("resolue", "close") for x in s.get("jumeaux", [])}
        p = pyramide.depuis_mesh(visibles, rels, en_alerte)
        cache[cle] = (time.monotonic(), p)
        return p

    def pyramide_synthetique(n: int, graine: int, domaines: int) -> pyramide.Pyramide:
        cle = ("synth", n, graine, domaines)
        if cle not in cache:
            for k in [k for k in cache if k[0] == "synth"]:
                del cache[k]  # un seul jeu synthétique en mémoire à la fois
            cache[cle] = (time.monotonic(), pyramide.synthetique(n, graine, domaines))
        return cache[cle][1]

    @router.get("/mesh/vue")
    async def vue_mesh(
        x0: float, y0: float, x1: float, y1: float,
        zoom: float = Query(..., gt=0, le=64),
        synthetique: Optional[int] = Query(None, ge=1, le=MAX_SYNTHETIQUE, description="essais d'échelle : n jumeaux fictifs"),
        domaines: int = Query(8, ge=1, le=MAX_DOMAINES, description="essais d'échelle : nombre de domaines fictifs"),
        graine: int = 1,
        x_persona: str = Header("architecte"),
        x_espace: Optional[str] = Header(None),
    ):
        if x1 <= x0 or y1 <= y0:
            raise HTTPException(422, "Fenêtre vide")
        _, espace = resoudre_perimetre(x_persona, x_espace)
        p = pyramide_synthetique(synthetique, graine, domaines) if synthetique else await pyramide_reelle(espace)
        rep = p.vue(x0, y0, x1, y1, zoom)
        rep["source"] = "synthetique" if synthetique else "reel"
        rep["domaines"] = p.noms_domaines
        if getattr(p, "couleurs_domaines", None):
            rep["domaines_couleur"] = p.couleurs_domaines
            rep["domaines_famille"] = p.familles_domaines
        rep["domaines_taille"] = p.niv[3].taille.tolist() if p.n else []
        if not synthetique:
            rep["perimetre"] = espace["label"]
        return rep

    @router.get("/mesh/vue/jumeau")
    async def vue_jumeau(
        i: int,
        synthetique: int = Query(..., ge=1, le=MAX_SYNTHETIQUE),
        domaines: int = Query(8, ge=1, le=MAX_DOMAINES),
        graine: int = 1,
    ):
        """Détail complet d'UN jumeau synthétique — appelé au clic depuis le laboratoire (jamais dans une vue de
        viewport, qui reste minimale). Même forme que l'objet jumeau réel : le panneau de détail de l'Atlas s'y
        ouvre à l'identique."""
        p = pyramide_synthetique(synthetique, graine, domaines)
        if i < 0 or i >= p.n:
            raise HTTPException(404, "Jumeau introuvable")
        dom_nom = p.noms_domaines[int(p.dom[i])]
        detail = _detail_jumeau_synthetique(i, dom_nom, graine)
        detail.update({
            "id": f"synth-{synthetique}-{domaines}-{graine}-{i}",
            "i": i,  # index dans le jeu synthétique — sert à retrouver ce jumeau dans une vue (il n'a pas d'id réel)
            "domaine": dom_nom,
            "degre": int(p.degre[i]),
            "ecart": bool(p.ecart[i]),
            "alerte": bool(p.alerte[i]),
        })
        return detail

    @router.get("/mesh/vue/localiser")
    async def localiser(
        q: str,
        synthetique: int = Query(..., ge=1, le=MAX_SYNTHETIQUE),
        domaines: int = Query(8, ge=1, le=MAX_DOMAINES),
        graine: int = 1,
    ):
        """Recherche du laboratoire : un numéro trouve le jumeau (index global), un nom trouve son domaine — la
        vue vole ensuite jusqu'aux coordonnées rendues ici (mêmes coordonnées que celles du rendu)."""
        p = pyramide_synthetique(synthetique, graine, domaines)
        q = q.strip()
        if q.isdigit():
            i = int(q)
            if not (0 <= i < p.n):
                raise HTTPException(404, "Jumeau introuvable")
            return {"type": "jumeau", "i": i, "x": float(p.x[i]), "y": float(p.y[i]), "dom": int(p.dom[i]), "nom": f"{p.noms_domaines[int(p.dom[i])]} · {i}"}
        ql = q.lower()
        candidats = [d for d, nom in enumerate(p.noms_domaines) if ql in nom.lower()]
        if not candidats:
            raise HTTPException(404, "Aucun domaine ne correspond")
        d = min(candidats, key=lambda d: len(p.noms_domaines[d]))  # correspondance la plus proche (nom le plus court qui contient q)
        v = p.niv[3]
        return {"type": "domaine", "id": d, "nom": p.noms_domaines[d], "x": float(v.x[d]), "y": float(v.y[d]), "r": float(v.r[d]), "n": int(v.taille[d])}

    return router
