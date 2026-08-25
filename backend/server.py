from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from typing import Optional, Dict
from datetime import datetime, timezone
import os
import re
import random
import logging
import unicodedata
from pathlib import Path

from seed_data import (
    TWINS, RELATIONS, REGIONS, SITUATIONS, CHANGE_LAB, PARCOURS, ACTIVITE,
    AURORA_SCRIPTS, AURORA_FALLBACK, AURORA_SUGGESTIONS, DEMO_ACTES, SOURCES_LABELS,
)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="Méridian")
api_router = APIRouter(prefix="/api")

NO_ID = {"_id": 0}
logger = logging.getLogger("meridian")


SEED_VERSION = 2


@app.on_event("startup")
async def seed_database():
    meta = await db.meta.find_one({"id": "seed"})
    if not meta or meta.get("version") != SEED_VERSION:
        for col in ["jumeaux", "relations", "situations", "change_lab", "dossiers"]:
            await db[col].delete_many({})
        await db.meta.replace_one({"id": "seed"}, {"id": "seed", "version": SEED_VERSION}, upsert=True)
        logger.info("Seed version %s — réinitialisation des données de démo", SEED_VERSION)
    for name, docs in [("jumeaux", TWINS), ("relations", RELATIONS), ("situations", SITUATIONS)]:
        if await db[name].count_documents({}) == 0:
            await db[name].insert_many([dict(d) for d in docs])
            logger.info("Seeded %s (%d documents)", name, len(docs))
    if await db.change_lab.count_documents({}) == 0:
        await db.change_lab.insert_one(dict(CHANGE_LAB))


def slugify(nom: str) -> str:
    s = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


# ---------- Santé ----------

@api_router.get("/")
async def root():
    return {"message": "Méridian API"}

@api_router.get("/health")
async def health():
    return {"status": "ok", "service": "meridian"}


# ---------- Mesh ----------

@api_router.get("/mesh")
async def get_mesh():
    jumeaux = await db.jumeaux.find({}, NO_ID).to_list(200)
    relations = await db.relations.find({}, NO_ID).to_list(200)
    return {"jumeaux": jumeaux, "relations": relations, "regions": REGIONS, "parcours": PARCOURS}


# ---------- Jumeaux (Registry) ----------

@api_router.get("/jumeaux")
async def lister_jumeaux():
    return await db.jumeaux.find({}, NO_ID).to_list(200)


class JumeauCreate(BaseModel):
    nom: str
    proprietaire: str
    mission: str
    environnement: str = "production"
    sources: Dict[str, bool] = {}


@api_router.post("/jumeaux", status_code=201)
async def creer_jumeau(payload: JumeauCreate):
    jid = slugify(payload.nom)
    if await db.jumeaux.find_one({"id": jid}):
        raise HTTPException(409, "Un jumeau porte déjà ce nom")
    couverture = 20 + sum(1 for v in payload.sources.values() if v) * 12
    doc = {
        "id": jid,
        "nom": payload.nom,
        "domaine": "Non classé",
        "mission": payload.mission,
        "proprietaire": payload.proprietaire,
        "environnement": payload.environnement,
        "statut": "observation",
        "autonomie": "aucune",
        "couverture": min(couverture, 88),
        "fraicheur": "à l'instant",
        "sante": "inconnu",
        "position": {"x": 1260, "y": 40},
        "sources": payload.sources,
    }
    await db.jumeaux.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api_router.post("/jumeaux/{jid}/admettre")
async def admettre_jumeau(jid: str):
    res = await db.jumeaux.update_one(
        {"id": jid},
        {"$set": {"statut": "actif", "autonomie": "supervisé", "fraicheur": "à l'instant"}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Jumeau introuvable")
    return {"ok": True, "statut": "actif"}


@api_router.post("/jumeaux/{jid}/examiner")
async def examiner_jumeau(jid: str):
    j = await db.jumeaux.find_one({"id": jid}, NO_ID)
    if not j:
        raise HTTPException(404, "Jumeau introuvable")
    sources = j.get("sources", {})
    manquantes = [label for key, label in SOURCES_LABELS.items() if not sources.get(key)]
    pairs = await db.jumeaux.find({"id": {"$ne": jid}, "domaine": j.get("domaine")}, NO_ID).to_list(5)
    if not pairs:
        pairs = await db.jumeaux.find({"id": {"$ne": jid}}, NO_ID).to_list(2)
    relations = [
        {"jumeau": p["nom"], "confiance": random.choice([58, 64, 71, 77])} for p in pairs[:2]
    ]
    return {
        "identite": {"nom": j["nom"], "mission": j.get("mission", ""), "domaine": j.get("domaine", "Non classé")},
        "capacites": [
            "Répondre aux questions sur son périmètre",
            "Signaler ses dérives de comportement",
            "Expliquer ses relations connues",
        ],
        "comportements": [
            "Activité nominale observée sur les dernières 24 h",
            "Aucune dérive critique détectée pendant l'observation",
        ],
        "relations_supposees": relations,
        "contradictions": [] if j.get("couverture", 0) >= 60 else ["Le périmètre déclaré dépasse les comportements observés"],
        "connaissances_manquantes": manquantes or ["Aucune source critique manquante"],
    }


# ---------- Situations (Radar & Investigations) ----------

@api_router.get("/situations")
async def lister_situations():
    docs = await db.situations.find({}, NO_ID).to_list(200)
    docs.sort(key=lambda s: s.get("score", 0), reverse=True)
    return docs


@api_router.get("/situations/{sid}")
async def obtenir_situation(sid: str):
    doc = await db.situations.find_one({"id": sid}, NO_ID)
    if not doc:
        raise HTTPException(404, "Situation introuvable")
    return doc


class ActionSituation(BaseModel):
    action: str


@api_router.post("/situations/{sid}/action")
async def agir_situation(sid: str, payload: ActionSituation):
    mapping = {"ignorer": "ignorée", "surveiller": "surveillée", "investiguer": "en investigation", "examiner": None, "coincidence": "classée", "observer": "en observation"}
    if payload.action not in mapping:
        raise HTTPException(400, "Action inconnue")
    nouveau = mapping[payload.action]
    if nouveau is not None:
        res = await db.situations.update_one({"id": sid}, {"$set": {"statut": nouveau}})
        if res.matched_count == 0:
            raise HTTPException(404, "Situation introuvable")
    return {"ok": True, "statut": nouveau}


class DecisionSituation(BaseModel):
    decision: str


@api_router.post("/situations/{sid}/decision")
async def decider_situation(sid: str, payload: DecisionSituation):
    res = await db.situations.update_one(
        {"id": sid},
        {"$set": {"statut": "décidée", "decision": payload.decision, "decidee_le": datetime.now(timezone.utc).isoformat()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Situation introuvable")
    return {"ok": True, "decision": payload.decision}


# ---------- Relations (mémoire du Mesh) ----------

@api_router.post("/relations/{rid}/confirmer")
async def confirmer_relation(rid: str):
    res = await db.relations.update_one(
        {"id": rid},
        {"$set": {"etat": "confirmee"}, "$addToSet": {"confirmee_par": "Validation humaine"}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Relation introuvable")
    return {"ok": True, "etat": "confirmee", "memoire": "enrichie"}


# ---------- Décisions ----------

@api_router.get("/decisions")
async def lister_decisions():
    situations = await db.situations.find(
        {"verbe": "a_decider", "statut": {"$nin": ["ignorée", "classée", "décidée"]}}, NO_ID
    ).to_list(50)
    admissions = await db.jumeaux.find({"statut": {"$ne": "actif"}}, NO_ID).to_list(50)
    relations = await db.relations.find({"etat": {"$in": ["supposee", "validation", "contestee"]}}, NO_ID).to_list(50)
    return {"situations": situations, "admissions": admissions, "relations": relations}


# ---------- Change Lab ----------

@api_router.get("/change-lab")
async def obtenir_change_lab():
    doc = await db.change_lab.find_one({}, NO_ID)
    return doc or {}


class SimulationDemande(BaseModel):
    description: str


@api_router.post("/change-lab/simuler")
async def simuler_changement(payload: SimulationDemande):
    base = await db.change_lab.find_one({}, NO_ID)
    if not base:
        raise HTTPException(404, "Aucune donnée Change Lab")
    base = dict(base)
    base["changement"] = payload.description
    return base


class DossierDemande(BaseModel):
    scenario: str
    changement: str


@api_router.post("/change-lab/dossier", status_code=201)
async def creer_dossier(payload: DossierDemande):
    doc = {
        "id": f"DC-{random.randint(1000, 9999)}",
        "changement": payload.changement,
        "scenario": payload.scenario,
        "cree_le": datetime.now(timezone.utc).isoformat(),
        "statut": "ouvert",
    }
    await db.dossiers.insert_one(doc)
    doc.pop("_id", None)
    return doc


# ---------- Aurora (copilote prescripté) ----------

class AuroraDemande(BaseModel):
    contexte: str = "global"
    question: str


@api_router.post("/aurora/demander")
async def aurora_demander(payload: AuroraDemande):
    q = payload.question.lower()
    for script in AURORA_SCRIPTS:
        if script["contexte"] in (payload.contexte, "global") and any(k in q for k in script["mots_cles"]):
            return script
    return AURORA_FALLBACK


@api_router.get("/aurora/suggestions")
async def aurora_suggestions(contexte: str = "global"):
    return AURORA_SUGGESTIONS.get(contexte, AURORA_SUGGESTIONS["global"])


# ---------- Démo & activité ----------

@api_router.get("/demo/actes")
async def demo_actes():
    return DEMO_ACTES


@api_router.get("/activite")
async def activite():
    return random.sample(ACTIVITE, 6)


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
