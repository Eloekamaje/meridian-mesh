"""GET /api/mesh/vue — vue bornée du Mesh (fenêtre monde + zoom), quel que soit le nombre de jumeaux.

Le client ne charge jamais le graphe entier : il demande ce qu'il affiche. Les droits s'appliquent AVANT l'agrégation :
la pyramide n'est construite que sur les jumeaux autorisés du périmètre demandé, donc aucune grappe ne compte ni ne
laisse deviner un jumeau restreint. Les dépendances restreintes (anonymisées dans /mesh) sont volontairement absentes
des vues agrégées.
"""
import time
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

import pyramide

TTL_S = 30.0
MAX_SYNTHETIQUE = 5_000_000


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

    def pyramide_synthetique(n: int, graine: int) -> pyramide.Pyramide:
        cle = ("synth", n, graine)
        if cle not in cache:
            for k in [k for k in cache if k[0] == "synth"]:
                del cache[k]  # un seul jeu synthétique en mémoire à la fois
            cache[cle] = (time.monotonic(), pyramide.synthetique(n, graine))
        return cache[cle][1]

    @router.get("/mesh/vue")
    async def vue_mesh(
        x0: float, y0: float, x1: float, y1: float,
        zoom: float = Query(..., gt=0, le=64),
        synthetique: Optional[int] = Query(None, ge=1, le=MAX_SYNTHETIQUE, description="essais d'échelle : n jumeaux fictifs"),
        graine: int = 1,
        x_persona: str = Header("architecte"),
        x_espace: Optional[str] = Header(None),
    ):
        if x1 <= x0 or y1 <= y0:
            raise HTTPException(422, "Fenêtre vide")
        _, espace = resoudre_perimetre(x_persona, x_espace)
        p = pyramide_synthetique(synthetique, graine) if synthetique else await pyramide_reelle(espace)
        rep = p.vue(x0, y0, x1, y1, zoom)
        rep["source"] = "synthetique" if synthetique else "reel"
        rep["domaines"] = p.noms_domaines
        if not synthetique:
            rep["perimetre"] = espace["label"]
        return rep

    return router
