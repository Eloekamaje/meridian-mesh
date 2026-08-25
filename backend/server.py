from fastapi import FastAPI, APIRouter, HTTPException, Header
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
    PERSONAS, ESPACES, VUES,
)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="Méridian")
api_router = APIRouter(prefix="/api")

NO_ID = {"_id": 0}
logger = logging.getLogger("meridian")


SEED_VERSION = 3


@app.on_event("startup")
async def seed_database():
    meta = await db.meta.find_one({"id": "seed"})
    if not meta or meta.get("version") != SEED_VERSION:
        for col in ["jumeaux", "relations", "situations", "change_lab", "dossiers", "vues", "journal"]:
            await db[col].delete_many({})
        await db.meta.replace_one({"id": "seed"}, {"id": "seed", "version": SEED_VERSION}, upsert=True)
        logger.info("Seed version %s — réinitialisation des données de démo", SEED_VERSION)
    for name, docs in [("jumeaux", TWINS), ("relations", RELATIONS), ("situations", SITUATIONS), ("vues", VUES)]:
        if await db[name].count_documents({}) == 0:
            await db[name].insert_many([dict(d) for d in docs])
            logger.info("Seeded %s (%d documents)", name, len(docs))
    if await db.change_lab.count_documents({}) == 0:
        await db.change_lab.insert_one(dict(CHANGE_LAB))


def slugify(nom: str) -> str:
    s = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


# ---------- Moteur de périmètres (Mesh global / Espace / Vue / Investigation) ----------

NIVEAUX = ["existence", "resume", "relations", "preuves", "complet"]


def resoudre_perimetre(persona_id: str, espace_id):
    persona = next((p for p in PERSONAS if p["id"] == persona_id), PERSONAS[0])
    if not espace_id or espace_id not in persona["espaces"]:
        espace_id = persona["par_defaut"]
    espace = next(e for e in ESPACES if e["id"] == espace_id)
    return persona, espace


def autorisations(espace: dict, tous_ids):
    regles = espace["jumeaux"]
    if regles == "*":
        return {i: "complet" for i in tous_ids}
    if "*" in regles:
        return {i: regles["*"] for i in tous_ids}
    return {k: v for k, v in regles.items() if k in tous_ids}


def niveau_au_moins(niveau, seuil):
    return NIVEAUX.index(niveau) >= NIVEAUX.index(seuil)


def projete_jumeau(j: dict, niveau: str):
    base = {"id": j["id"], "nom": j["nom"], "domaine": j.get("domaine"), "statut": j.get("statut"), "position": j.get("position")}
    if niveau_au_moins(niveau, "resume"):
        base.update({"mission": j.get("mission"), "sante": j.get("sante"), "couverture": j.get("couverture"), "fraicheur": j.get("fraicheur")})
    if niveau_au_moins(niveau, "preuves"):
        base["sources"] = j.get("sources")
    if niveau == "complet":
        base.update({"proprietaire": j.get("proprietaire"), "autonomie": j.get("autonomie"), "environnement": j.get("environnement")})
    return base


def filtre_situation(s: dict, aut: dict, nom_vers_id: dict):
    autorises = [j for j in s.get("jumeaux", []) if j in aut]
    if not autorises:
        return None
    out = dict(s)
    out["restreinte"] = len(autorises) != len(s.get("jumeaux", []))
    out["jumeaux"] = autorises
    if not any(niveau_au_moins(aut[j], "preuves") for j in autorises):
        out["preuves"] = []
    out["contributions"] = [c for c in s.get("contributions", []) if nom_vers_id.get(c.get("jumeau", "")) in aut]
    return out


async def journaler(persona_id: str, espace_id, action: str, cible: str, detail: str = ""):
    await db.journal.insert_one({
        "quand": datetime.now(timezone.utc).isoformat(),
        "persona": persona_id, "espace": espace_id or "",
        "action": action, "cible": cible, "detail": detail,
    })


HORS_PERIMETRE = {
    "comportement": "expliquer",
    "reponse": "Cette question sort de votre périmètre d'autorisation. Aurora construit ses réponses uniquement depuis le sous-graphe autorisé de votre espace actif — demandez un élargissement de périmètre au propriétaire du jumeau concerné.",
    "contributions": [],
    "preuves": [],
    "indicateurs": {"confiance": 0, "couverture": 0, "fraicheur": "—", "contradictions": 0},
    "hors_perimetre": True,
}


# ---------- Santé ----------

@api_router.get("/")
async def root():
    return {"message": "Méridian API"}

@api_router.get("/health")
async def health():
    return {"status": "ok", "service": "meridian"}


# ---------- Périmètres : personas, espaces, vues, journal ----------

@api_router.get("/personas")
async def lister_personas():
    return [{"id": p["id"], "nom": p["nom"], "role": p["role"]} for p in PERSONAS]


@api_router.get("/espaces")
async def lister_espaces(x_persona: str = Header("architecte")):
    persona = next((p for p in PERSONAS if p["id"] == x_persona), PERSONAS[0])
    return [
        {"id": e["id"], "label": e["label"], "description": e["description"], "global": e.get("global", False)}
        for e in ESPACES if e["id"] in persona["espaces"]
    ]


@api_router.get("/perimetre")
async def obtenir_perimetre(x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
    persona, espace = resoudre_perimetre(x_persona, x_espace)
    tous = await db.jumeaux.find({}, {"_id": 0, "id": 1}).to_list(200)
    aut = autorisations(espace, [j["id"] for j in tous])
    return {
        "persona": {"id": persona["id"], "nom": persona["nom"], "role": persona["role"]},
        "espace": {"id": espace["id"], "label": espace["label"], "global": espace.get("global", False), "politique_dependances": espace.get("politique_dependances")},
        "autorisations": aut,
        "nb_autorises": len(aut),
    }


@api_router.get("/vues")
async def lister_vues(x_persona: str = Header("architecte")):
    return await db.vues.find({"persona": x_persona}, NO_ID).to_list(50)


class VueCreate(BaseModel):
    nom: str
    type: str = "selection"
    jumeaux: list = []


@api_router.post("/vues", status_code=201)
async def creer_vue(payload: VueCreate, x_persona: str = Header("architecte")):
    doc = {"id": f"vue-{slugify(payload.nom)}-{random.randint(100, 999)}", "persona": x_persona, "nom": payload.nom, "type": payload.type, "jumeaux": payload.jumeaux}
    await db.vues.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api_router.get("/journal")
async def lire_journal():
    return await db.journal.find({}, NO_ID).sort("quand", -1).to_list(30)


class JournalEntree(BaseModel):
    action: str
    detail: str = ""


@api_router.post("/journal", status_code=201)
async def ecrire_journal(payload: JournalEntree, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
    await journaler(x_persona, x_espace, payload.action, "", payload.detail)
    return {"ok": True}


# ---------- Mesh ----------

@api_router.get("/mesh")
async def get_mesh(x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
    _, espace = resoudre_perimetre(x_persona, x_espace)
    tous = await db.jumeaux.find({}, NO_ID).to_list(200)
    par_id = {j["id"]: j for j in tous}
    aut = autorisations(espace, list(par_id))
    visibles = [projete_jumeau(j, aut[j["id"]]) for j in tous if j["id"] in aut]
    ids = set(aut)
    politique = espace.get("politique_dependances", "masquage")
    relations = await db.relations.find({}, NO_ID).to_list(200)
    rels_out = []
    anon = {}
    for r in relations:
        s_ok, c_ok = r["source"] in ids, r["cible"] in ids
        if s_ok and c_ok:
            rels_out.append(r)
            continue
        if not s_ok and not c_ok:
            continue
        if politique == "masquage":
            continue
        ext = r["cible"] if s_ok else r["source"]
        jext = par_id.get(ext, {})
        aid = f"restreint-{ext}"
        if politique == "anonymisee":
            label = "Dépendance externe restreinte"
        else:
            label = f"Application restreinte — domaine {jext.get('domaine', 'inconnu')}"
        if aid not in anon:
            anon[aid] = {"id": aid, "nom": label, "domaine": jext.get("domaine", "Non classé"), "anonyme": True, "statut": "restreint", "position": jext.get("position", {"x": 0, "y": 0})}
        r2 = dict(r)
        r2["id"] = f"{r['id']}-restreint"
        r2["restreinte"] = True
        if s_ok:
            r2["cible"] = aid
        else:
            r2["source"] = aid
        rels_out.append(r2)
    return {
        "jumeaux": visibles + list(anon.values()),
        "relations": rels_out,
        "regions": REGIONS,
        "parcours": PARCOURS,
        "perimetre": {"espace": espace["label"], "global": espace.get("global", False), "politique": politique, "nb_autorises": len(visibles), "nb_restreints": len(anon)},
    }


# ---------- Jumeaux (Registry) ----------

@api_router.get("/jumeaux")
async def lister_jumeaux(x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
    _, espace = resoudre_perimetre(x_persona, x_espace)
    tous = await db.jumeaux.find({}, NO_ID).to_list(200)
    aut = autorisations(espace, [j["id"] for j in tous])
    out = []
    for j in tous:
        if j["id"] in aut and niveau_au_moins(aut[j["id"]], "resume"):
            p = projete_jumeau(j, aut[j["id"]])
            p["niveau"] = aut[j["id"]]
            out.append(p)
    return out


class JumeauCreate(BaseModel):
    nom: str
    proprietaire: str
    mission: str
    environnement: str = "production"
    sources: Dict[str, bool] = {}


@api_router.post("/jumeaux", status_code=201)
async def creer_jumeau(payload: JumeauCreate, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
    _, espace = resoudre_perimetre(x_persona, x_espace)
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
    if isinstance(espace.get("jumeaux"), dict) and "*" not in espace["jumeaux"]:
        espace["jumeaux"][jid] = "complet"
    await journaler(x_persona, espace["id"], "commande d'un jumeau", jid, payload.nom)
    doc.pop("_id", None)
    return doc


@api_router.post("/jumeaux/{jid}/admettre")
async def admettre_jumeau(jid: str, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
    _, espace = resoudre_perimetre(x_persona, x_espace)
    aut = autorisations(espace, [jid])
    if aut.get(jid) is None:
        raise HTTPException(404, "Jumeau introuvable")
    if aut[jid] != "complet":
        raise HTTPException(403, "Niveau « complet » requis pour admettre ce jumeau")
    res = await db.jumeaux.update_one(
        {"id": jid},
        {"$set": {"statut": "actif", "autonomie": "supervisé", "fraicheur": "à l'instant"}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Jumeau introuvable")
    await journaler(x_persona, espace["id"], "admission d'un jumeau", jid)
    return {"ok": True, "statut": "actif"}


@api_router.post("/jumeaux/{jid}/examiner")
async def examiner_jumeau(jid: str, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
    _, espace = resoudre_perimetre(x_persona, x_espace)
    aut = autorisations(espace, [jid])
    if aut.get(jid) is None:
        raise HTTPException(404, "Jumeau introuvable")
    if not niveau_au_moins(aut[jid], "preuves"):
        raise HTTPException(403, "Niveau « preuves » requis pour examiner ce jumeau")
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
async def lister_situations(x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
    _, espace = resoudre_perimetre(x_persona, x_espace)
    tous = await db.jumeaux.find({}, {"_id": 0, "id": 1, "nom": 1}).to_list(200)
    aut = autorisations(espace, [j["id"] for j in tous])
    nom_vers_id = {j["nom"]: j["id"] for j in tous}
    docs = await db.situations.find({}, NO_ID).to_list(200)
    out = [f for f in (filtre_situation(d, aut, nom_vers_id) for d in docs) if f]
    out.sort(key=lambda s: s.get("score", 0), reverse=True)
    return out


@api_router.get("/situations/{sid}")
async def obtenir_situation(sid: str, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
    _, espace = resoudre_perimetre(x_persona, x_espace)
    tous = await db.jumeaux.find({}, {"_id": 0, "id": 1, "nom": 1}).to_list(200)
    aut = autorisations(espace, [j["id"] for j in tous])
    nom_vers_id = {j["nom"]: j["id"] for j in tous}
    doc = await db.situations.find_one({"id": sid}, NO_ID)
    if not doc:
        raise HTTPException(404, "Situation introuvable")
    filtre = filtre_situation(doc, aut, nom_vers_id)
    if not filtre:
        raise HTTPException(404, "Situation introuvable")
    return filtre


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
async def decider_situation(sid: str, payload: DecisionSituation, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
    res = await db.situations.update_one(
        {"id": sid},
        {"$set": {"statut": "décidée", "decision": payload.decision, "decidee_le": datetime.now(timezone.utc).isoformat()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Situation introuvable")
    await journaler(x_persona, x_espace, "décision", sid, payload.decision)
    return {"ok": True, "decision": payload.decision}


# ---------- Relations (mémoire du Mesh) ----------

@api_router.post("/relations/{rid}/confirmer")
async def confirmer_relation(rid: str, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
    _, espace = resoudre_perimetre(x_persona, x_espace)
    rel = await db.relations.find_one({"id": rid}, NO_ID)
    if not rel:
        raise HTTPException(404, "Relation introuvable")
    aut = autorisations(espace, [rel["source"], rel["cible"]])
    if not any(aut.get(x) == "complet" for x in (rel["source"], rel["cible"])):
        raise HTTPException(403, "Permission « Valider » requise sur l'un des jumeaux de la relation")
    await db.relations.update_one(
        {"id": rid},
        {"$set": {"etat": "confirmee"}, "$addToSet": {"confirmee_par": "Validation humaine"}},
    )
    await journaler(x_persona, espace["id"], "confirmation d'une relation", rid, f"{rel['source']} → {rel['cible']}")
    return {"ok": True, "etat": "confirmee", "memoire": "enrichie"}


# ---------- Décisions ----------

@api_router.get("/decisions")
async def lister_decisions(x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
    _, espace = resoudre_perimetre(x_persona, x_espace)
    tous = await db.jumeaux.find({}, {"_id": 0, "id": 1, "nom": 1}).to_list(200)
    aut = autorisations(espace, [j["id"] for j in tous])
    nom_vers_id = {j["nom"]: j["id"] for j in tous}
    situations = await db.situations.find(
        {"verbe": "a_decider", "statut": {"$nin": ["ignorée", "classée", "décidée"]}}, NO_ID
    ).to_list(50)
    situations = [f for f in (filtre_situation(s, aut, nom_vers_id) for s in situations) if f]
    admissions = [j for j in await db.jumeaux.find({"statut": {"$ne": "actif"}}, NO_ID).to_list(50) if aut.get(j["id"]) == "complet"]
    relations = [
        r for r in await db.relations.find({"etat": {"$in": ["supposee", "validation", "contestee"]}}, NO_ID).to_list(50)
        if r["source"] in aut and r["cible"] in aut
    ]
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
async def aurora_demander(payload: AuroraDemande, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
    _, espace = resoudre_perimetre(x_persona, x_espace)
    tous = await db.jumeaux.find({}, {"_id": 0, "id": 1, "nom": 1}).to_list(200)
    aut = autorisations(espace, [j["id"] for j in tous])
    nom_vers_id = {j["nom"]: j["id"] for j in tous}
    q = payload.question.lower()
    for j in tous:
        if j["id"] not in aut and len(j["nom"]) > 4 and j["nom"].lower() in q:
            return HORS_PERIMETRE
    for script in AURORA_SCRIPTS:
        if script["contexte"] in (payload.contexte, "global") and any(k in q for k in script["mots_cles"]):
            out = dict(script)
            out["contributions"] = [c for c in script.get("contributions", []) if nom_vers_id.get(c.get("jumeau", "")) in aut]
            if not any(niveau_au_moins(n, "preuves") for n in aut.values()):
                out["preuves"] = []
            return out
    return AURORA_FALLBACK


@api_router.get("/aurora/suggestions")
async def aurora_suggestions(contexte: str = "global", x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
    _, espace = resoudre_perimetre(x_persona, x_espace)
    tous = await db.jumeaux.find({}, {"_id": 0, "id": 1, "nom": 1}).to_list(200)
    aut = autorisations(espace, [j["id"] for j in tous])
    sugs = AURORA_SUGGESTIONS.get(contexte, AURORA_SUGGESTIONS["global"])
    return [
        s for s in sugs
        if not any(j["id"] not in aut and len(j["nom"]) > 4 and j["nom"].lower() in s.lower() for j in tous)
    ]


# ---------- Démo & activité ----------

@api_router.get("/demo/actes")
async def demo_actes():
    return DEMO_ACTES


@api_router.get("/activite")
async def activite(x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
    _, espace = resoudre_perimetre(x_persona, x_espace)
    tous = await db.jumeaux.find({}, {"_id": 0, "id": 1}).to_list(200)
    aut = autorisations(espace, [j["id"] for j in tous])
    pool = [e for e in ACTIVITE if e["jumeau"] in aut]
    return random.sample(pool, min(6, len(pool))) if pool else []


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
