"""Routes des pièces jointes d'un Travail — sources versées, jamais connaissances validées."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Response, UploadFile

import pieces
from auth import acteur as acteur_courant
from limites import autoriser


async def _sous_limite(cle: str, maxi: int, fenetre: int) -> bool:
    """`maxi <= 0` désactive la limite (hors production, ou réglage explicite à zéro)."""
    return maxi <= 0 or await autoriser(cle, maxi, fenetre)


async def _exiger_limite(cle: str, maxi: int, fenetre: int) -> None:
    if not await _sous_limite(cle, maxi, fenetre):
        raise HTTPException(429, "Trop de requêtes sur les pièces ; réessayez dans un instant.")


def ajouter_routes_pieces(router: APIRouter, deps: dict) -> None:
    db = deps["db"]
    charger_case = deps["charger_case"]
    resoudre_perimetre = deps["resoudre_perimetre"]
    journaler = deps["journaler"]

    async def _case(cid: str, acteur: str, espace_id: Optional[str]):
        _, espace = resoudre_perimetre(acteur, espace_id)
        case = await charger_case(cid, espace, acteur)
        return case, espace

    async def _historique(cid: str, texte: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await db.cases.update_one({"id": cid}, {"$push": {"historique": {"quand": now, "texte": texte}},
                                                "$set": {"maj_le": now}})

    @router.get("/cases/{cid}/pieces")
    async def lister_pieces(cid: str, response: Response, acteur: str = Depends(acteur_courant),
                            x_espace: Optional[str] = Header(None)):
        await _case(cid, acteur, x_espace)
        response.headers["Cache-Control"] = "private, no-store"
        return await pieces.lister(db, cid)

    @router.post("/cases/{cid}/pieces", status_code=201)
    async def ajouter_piece(cid: str, fichier: UploadFile = File(...), acteur: str = Depends(acteur_courant),
                            x_espace: Optional[str] = Header(None)):
        """Une pièce jointe est une source du Travail : elle est lue, stockée, et montrée comme non vérifiée."""
        await _exiger_limite(f"pieces-upload:{acteur}", pieces.PIECES_UPLOAD_MAX,
                             pieces.PIECES_UPLOAD_FENETRE)
        case, espace = await _case(cid, acteur, x_espace)
        if acteur != case.get("responsable") and acteur not in (case.get("participants") or []):
            raise HTTPException(403, "Seul le responsable ou un participant du travail peut ajouter une pièce jointe")
        try:
            meta = await pieces.enregistrer(db, cid, fichier, acteur)
        except pieces.PieceRefusee as e:
            raise HTTPException(e.statut, str(e))
        await _historique(cid, f"Pièce jointe ajoutée — {meta['nom']}")
        await journaler(acteur, espace["id"], "ajout d'une pièce jointe", cid, meta["nom"])
        return meta

    @router.get("/cases/{cid}/pieces/{pid}")
    async def telecharger_piece(cid: str, pid: str, acteur: str = Depends(acteur_courant),
                                x_espace: Optional[str] = Header(None)):
        _, espace = await _case(cid, acteur, x_espace)
        await _exiger_limite(f"pieces-lecture:{acteur}", pieces.PIECES_LECTURE_MAX,
                             pieces.PIECES_LECTURE_FENETRE)
        try:
            doc, contenu = await pieces.contenu(db, cid, pid)
        except FileNotFoundError:
            raise HTTPException(404, "Pièce jointe introuvable")
        await journaler(acteur, espace["id"], "téléchargement d'une pièce jointe", cid, doc["nom"])
        repli = re.sub(r"[^A-Za-z0-9._-]", "_", doc["nom"]) or "piece-jointe"
        return Response(
            content=contenu,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename=\"{repli}\"; filename*=UTF-8''{quote(doc['nom'])}",
                "Content-Length": str(len(contenu)),
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "private, no-store",
            },
        )

    @router.get("/cases/{cid}/pieces/{pid}/extrait")
    async def extrait_piece(cid: str, pid: str, response: Response, acteur: str = Depends(acteur_courant),
                            x_espace: Optional[str] = Header(None)):
        _, espace = await _case(cid, acteur, x_espace)
        await _exiger_limite(f"pieces-lecture:{acteur}", pieces.PIECES_LECTURE_MAX,
                             pieces.PIECES_LECTURE_FENETRE)
        try:
            doc = await pieces.extrait(db, cid, pid)
        except FileNotFoundError:
            raise HTTPException(404, "Pièce jointe introuvable")
        await journaler(acteur, espace["id"], "lecture d'un extrait de pièce jointe", cid, doc["nom"])
        response.headers["Cache-Control"] = "private, no-store"
        return doc

    @router.get("/cases/{cid}/pieces/{pid}/sections/{sid}")
    async def lire_section_piece(cid: str, pid: str, sid: str, response: Response,
                                 debut: int = Query(0, ge=0),
                                 limite: Optional[int] = Query(None, ge=0, le=pieces.MAX_CARACTERES_PIECE_PROMPT),
                                 acteur: str = Depends(acteur_courant), x_espace: Optional[str] = Header(None)):
        _, espace = await _case(cid, acteur, x_espace)
        await _exiger_limite(f"pieces-lecture:{acteur}", pieces.PIECES_LECTURE_MAX,
                             pieces.PIECES_LECTURE_FENETRE)
        try:
            doc = await pieces.lire_section(db, cid, pid, sid, debut=debut, limite=limite)
        except FileNotFoundError:
            raise HTTPException(404, "Pièce jointe introuvable")
        except KeyError:
            raise HTTPException(404, "Section introuvable")
        await journaler(acteur, espace["id"], "lecture d'un extrait de pièce jointe", cid,
                        f"{doc['nom']} — section {sid}, début {doc.get('debut', debut)}, "
                        f"limite {limite if limite is not None else pieces.MAX_CARACTERES_PIECE_PROMPT}")
        response.headers["Cache-Control"] = "private, no-store"
        return doc

    @router.delete("/cases/{cid}/pieces/{pid}", status_code=204)
    async def retirer_piece(cid: str, pid: str, acteur: str = Depends(acteur_courant),
                            x_espace: Optional[str] = Header(None)):
        case, espace = await _case(cid, acteur, x_espace)
        try:
            doc = await pieces.meta(db, cid, pid)
        except FileNotFoundError:
            raise HTTPException(404, "Pièce jointe introuvable")
        if acteur not in (doc.get("joint_par"), case.get("responsable")):
            raise HTTPException(403, "Seul l'auteur de la pièce ou le responsable du travail la retire")
        await pieces.supprimer(db, cid, pid)
        await _historique(cid, f"Pièce jointe retirée — {doc['nom']}")
        await journaler(acteur, espace["id"], "retrait d'une pièce jointe", cid, doc["nom"])
        return Response(status_code=204)
