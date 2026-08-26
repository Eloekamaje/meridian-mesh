from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

GENRES_A_TRAITER = {"a_confirmer", "investigation_recommandee", "decision_a_examiner", "action_proposee"}
GENRES_RADAR = {"a_surveiller", "information"}


class ReponseInitiative(BaseModel):
    choix: str
    motif: Optional[str] = None
    travail_id: Optional[str] = None


class DelegationCreate(BaseModel):
    type: str  # surveillance | comparaison | confirmation
    jumeaux: list = []
    duree_h: int = 24


def build_initiatives_router(deps):
    db = deps["db"]
    resoudre_perimetre = deps["resoudre_perimetre"]
    autorisations = deps["autorisations"]
    journaler = deps["journaler"]
    slugify = deps["slugify"]
    NO_ID = deps["NO_ID"]

    router = APIRouter()

    async def contexte(x_persona, x_espace):
        persona, espace = resoudre_perimetre(x_persona, x_espace)
        tous = await db.jumeaux.find({}, NO_ID).to_list(200)
        aut = autorisations(espace, [j["id"] for j in tous])
        return persona, espace, aut

    def visible(init, persona, espace, aut):
        if init.get("jumeaux") and not any(j in aut for j in init["jumeaux"]):
            return False
        if espace.get("global"):
            return True
        return init.get("destinataire") in (None, persona["id"])

    def vue_de(init):
        if init["statut"] == "suivi":
            return "suivis"
        if init["statut"] != "en_attente":
            return "traitees"
        if init["genre"] in GENRES_A_TRAITER:
            return "a_traiter"
        return "radar"

    @router.get("/initiatives")
    async def lister_initiatives(vue: str = "toutes", x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
        persona, espace, aut = await contexte(x_persona, x_espace)
        toutes = await db.initiatives.find({}, NO_ID).to_list(200)
        out = []
        for i in toutes:
            if not visible(i, persona, espace, aut):
                continue
            v = vue_de(i)
            if vue != "toutes" and v != vue:
                continue
            if vue == "toutes" and v == "traitees":
                continue
            i["vue"] = v
            out.append(i)
        out.sort(key=lambda i: ({"haute": 0, "critique": 0, "moyenne": 1, "basse": 2}.get(i.get("urgence"), 3), i["quand"]), reverse=False)
        return out

    @router.get("/initiatives/compteurs")
    async def compteurs(x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
        persona, espace, aut = await contexte(x_persona, x_espace)
        toutes = await db.initiatives.find({}, NO_ID).to_list(200)
        c = {"a_traiter": 0, "radar": 0, "suivis": 0}
        for i in toutes:
            if visible(i, persona, espace, aut):
                v = vue_de(i)
                if v in c:
                    c[v] += 1
        return c

    @router.post("/initiatives/{iid}/repondre")
    async def repondre(iid: str, payload: ReponseInitiative, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
        persona, espace, aut = await contexte(x_persona, x_espace)
        init = await db.initiatives.find_one({"id": iid}, NO_ID)
        if not init or not visible(init, persona, espace, aut):
            raise HTTPException(404, "Initiative introuvable ou hors périmètre")
        if init["statut"] != "en_attente":
            raise HTTPException(409, "Cette initiative a déjà reçu une réponse")

        now = datetime.now(timezone.utc).isoformat()
        choix = payload.choix
        low = choix.lower()
        travail_cree = None

        if low == "suivre" or "surveiller" in low:
            statut = "suivi"
        elif low == "ignorer" or "rejeter" in low:
            statut = "refusee"
        elif low.startswith("créer") or low.startswith("creer"):
            statut = "acceptee"
            cid = f"case-{slugify(init['titre'])[:40]}-{int(datetime.now(timezone.utc).timestamp()) % 100000}"
            doc = {
                "id": cid, "titre": init["titre"], "type": "investigation", "statut": "ouvert",
                "responsable": persona["id"], "participants": [persona["id"]],
                "espace": espace["id"], "jumeaux": init.get("jumeaux", []), "situations": [],
                "objectif": init.get("raison", ""), "resume": "", "questions": [], "hypotheses": [],
                "options": [], "decisions": [], "conversation": [], "sources": [], "prochaine_etape": "",
                "a_revoir": False, "cree_le": now, "maj_le": now, "visites": {},
                "historique": [{"quand": now, "texte": f"Travail créé depuis l'initiative « {init['titre']} »"}],
            }
            await db.cases.insert_one(doc)
            travail_cree = cid
        elif "ajouter" in low:
            statut = "acceptee"
            tid = payload.travail_id or init.get("travail_id")
            if not tid:
                raise HTTPException(400, "Aucun travail cible")
            case = await db.cases.find_one({"id": tid})
            if not case:
                raise HTTPException(404, "Travail introuvable")
            histo = case.get("historique", []) + [{"quand": now, "texte": f"Initiative du Mesh ajoutée : {init['titre']}"}]
            jumeaux = sorted(set(case.get("jumeaux", [])) | set(init.get("jumeaux", [])))
            await db.cases.update_one({"id": tid}, {"$set": {"historique": histo, "jumeaux": jumeaux, "maj_le": now}})
            travail_cree = tid
        elif "comparer" in low:
            statut = "acceptee"
            travail_cree = init.get("travail_id")
        else:
            statut = "acceptee"

        reponse = {"choix": choix, "motif": payload.motif, "par": persona["id"], "quand": now}
        await db.initiatives.update_one({"id": iid}, {"$set": {"statut": statut, "reponse": reponse, "maj_le": now}})
        await journaler(persona["id"], "reponse_initiative", iid, f"{choix}" + (f" — motif : {payload.motif}" if payload.motif else ""))

        maj = await db.initiatives.find_one({"id": iid}, NO_ID)
        maj["vue"] = vue_de(maj)
        return {"initiative": maj, "travail_id": travail_cree}

    @router.get("/delegations")
    async def lister_delegations(x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
        persona, espace, aut = await contexte(x_persona, x_espace)
        out = []
        async for d in db.delegations.find({}, NO_ID):
            if d.get("jumeaux") and not any(j in aut for j in d["jumeaux"]):
                continue
            out.append(d)
        out.sort(key=lambda d: d["cree_le"], reverse=True)
        return out

    @router.post("/delegations", status_code=201)
    async def creer_delegation(payload: DelegationCreate, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
        persona, espace, aut = await contexte(x_persona, x_espace)
        jumeaux = [j for j in payload.jumeaux if j in aut]
        if not jumeaux:
            raise HTTPException(400, "Aucun jumeau autorisé dans le périmètre de délégation")
        now = datetime.now(timezone.utc)
        types = {
            "surveillance": ("Surveiller la sélection dans le Mesh", "Synthèse d'évolution en fin de période · signalement immédiat si anomalie"),
            "comparaison": ("Préparer une comparaison des scénarios", "Matrice de comparaison des options avec impacts estimés"),
            "confirmation": ("Demander confirmation aux propriétaires", "Demandes adressées aux propriétaires des jumeaux concernés"),
        }
        tache, livrable = types.get(payload.type, types["surveillance"])
        doc = {
            "id": f"deleg-{int(now.timestamp())}",
            "type": payload.type,
            "tache": tache,
            "demandeur": persona["id"],
            "jumeaux": jumeaux,
            "cree_le": now.isoformat(),
            "jusqu_a": (now + timedelta(hours=payload.duree_h)).isoformat(),
            "duree": f"{payload.duree_h} h",
            "sources": "Observations des jumeaux du périmètre uniquement",
            "livrable": livrable,
            "validation_requise": "Toute action proposée restera soumise à validation humaine",
            "statut": "active",
        }
        await db.delegations.insert_one(dict(doc))
        await journaler(persona["id"], "delegation", doc["id"], tache)
        return doc

    return router
