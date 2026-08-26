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
import secrets
import unicodedata
from pathlib import Path
from uuid import uuid4

from cases_routes import build_cases_router
from actualites_routes import build_actualites_router
from initiatives_routes import build_initiatives_router
from seed_data import (
    TWINS, RELATIONS, REGIONS, SITUATIONS, CHANGE_LAB, ACTIVITE,
    AURORA_SCRIPTS, AURORA_FALLBACK, AURORA_SUGGESTIONS, DEMO_ACTES, SOURCES_LABELS,
    PERSONAS, ESPACES, VUES, CONNECTEURS, CONTRIBUTIONS, PROFILS, COMMANDE_DEMO, CASES, NOTIFS,
    INITIATIVES, DELEGATIONS,
)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="Méridian")
api_router = APIRouter(prefix="/api")

NO_ID = {"_id": 0}
logger = logging.getLogger("meridian")


SEED_VERSION = 9


async def peupler_demo():
    for name, docs in [("jumeaux", TWINS), ("relations", RELATIONS), ("situations", SITUATIONS), ("vues", VUES), ("cases", CASES), ("notifications", NOTIFS), ("initiatives", INITIATIVES), ("delegations", DELEGATIONS)]:
        if await db[name].count_documents({}) == 0:
            await db[name].insert_many([dict(d) for d in docs])
            logger.info("Seeded %s (%d documents)", name, len(docs))
    if await db.change_lab.count_documents({}) == 0:
        await db.change_lab.insert_one(dict(CHANGE_LAB))
    if await db.commandes.count_documents({}) == 0:
        await db.commandes.insert_one(dict(COMMANDE_DEMO))


@app.on_event("startup")
async def seed_database():
    meta = await db.meta.find_one({"id": "seed"})
    if not meta or meta.get("version") != SEED_VERSION:
        for col in ["jumeaux", "relations", "situations", "change_lab", "dossiers", "vues", "journal", "commandes", "cases", "notifications", "initiatives", "delegations"]:
            await db[col].delete_many({})
        await db.meta.replace_one({"id": "seed"}, {"id": "seed", "version": SEED_VERSION}, upsert=True)
        logger.info("Seed version %s — réinitialisation des données de démo", SEED_VERSION)
    await peupler_demo()


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
        base.update({"mission": j.get("mission"), "sante": j.get("sante"), "couverture": j.get("couverture"), "fraicheur": j.get("fraicheur"), "strates": j.get("strates"), "fraicheur_etat": j.get("fraicheur_etat")})
    if niveau_au_moins(niveau, "preuves"):
        base["sources"] = j.get("sources")
        base["sources_detail"] = j.get("sources_detail")
    if niveau == "complet":
        base.update({"proprietaire": j.get("proprietaire"), "autonomie": j.get("autonomie"), "environnement": j.get("environnement"), "gouvernance": j.get("gouvernance")})
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


async def notifier(persona_ids, type_, texte, lien):
    now = datetime.now(timezone.utc).isoformat()
    docs = [
        {"id": f"notif-{uuid4().hex[:8]}", "persona": p, "type": type_, "texte": texte, "lien": lien, "lu": False, "quand": now}
        for p in set(persona_ids or []) if p
    ]
    if docs:
        await db.notifications.insert_many(docs)


async def marquer_cases_a_revoir(jumeaux_ids, raison):
    now = datetime.now(timezone.utc).isoformat()
    cibles = set(jumeaux_ids)
    async for case in db.cases.find({"statut": {"$ne": "clos"}}, NO_ID):
        if not cibles & set(case.get("jumeaux", [])):
            continue
        await db.cases.update_one(
            {"id": case["id"]},
            {"$set": {"a_revoir": True, "maj_le": now}, "$push": {"historique": {"quand": now, "texte": f"À revoir — {raison}"}}},
        )
        await notifier(case.get("participants", []), "a_revoir", f"Le travail « {case['titre']} » est à revoir : {raison}", f"/travaux/{case['id']}")


HORS_PERIMETRE = {
    "comportement": "expliquer",
    "reponse": "Cette question sort de votre périmètre d'autorisation. Flore construit ses réponses uniquement depuis le sous-graphe autorisé de votre espace actif — demandez un élargissement de périmètre au propriétaire du jumeau concerné.",
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
    jumeau = await db.jumeaux.find_one({"id": jid}, NO_ID)
    await marquer_cases_a_revoir([jid], f"le jumeau {jumeau['nom'] if jumeau else jid} a été admis dans le Mesh")
    return {"ok": True, "statut": "actif"}


@api_router.delete("/jumeaux/{jid}")
async def supprimer_jumeau(jid: str, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
    _, espace = resoudre_perimetre(x_persona, x_espace)
    aut = autorisations(espace, [jid])
    if aut.get(jid) is None:
        raise HTTPException(404, "Jumeau introuvable")
    if aut[jid] != "complet":
        raise HTTPException(403, "Niveau « complet » requis pour retirer ce jumeau")
    res = await db.jumeaux.delete_one({"id": jid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Jumeau introuvable")
    await db.relations.delete_many({"$or": [{"source": jid}, {"cible": jid}]})
    await db.cases.update_many({}, {"$pull": {"jumeaux": jid}})
    await journaler(x_persona, espace["id"], "retrait d'un jumeau", jid)
    return {"ok": True}


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
    await marquer_cases_a_revoir([rel["source"], rel["cible"]], f"la relation {rel['source']} → {rel['cible']} a été confirmée")
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
    question: str = ""
    selection: list = []
    domaine: Optional[str] = None


ETAT_REL_LABELS = {"observee": "observée", "supposee": "supposée", "validation": "validation A2A", "contestee": "contestée", "obsolete": "obsolète", "confirmee": "confirmée"}


def intention_selection(q: str):
    if any(k in q for k in ["inconnue", "inconnu", "non documente", "cache"]):
        return "inconnues"
    if any(k in q for k in ["connaissance", "faible", "admis", "admission", "blocage", "sources"]):
        return "registre"
    if any(k in q for k in ["impact", "changement"]):
        return "impact"
    if any(k in q for k in ["critique", "fragile"]):
        return "critiques"
    if any(k in q for k in ["parcours", "chemin"]):
        return "parcours"
    if "investigation" in q:
        return "investigation"
    if any(k in q for k in ["comprendre", "relation", "relient", "connecte"]):
        return "relations"
    return None


async def liens_selection(sel, aut):
    relations = await db.relations.find({}, NO_ID).to_list(200)
    sset = set(sel)
    internes = [r for r in relations if r["source"] in sset and r["cible"] in sset]
    externes = [r for r in relations if (r["source"] in sset) != (r["cible"] in sset) and r["source"] in aut and r["cible"] in aut]
    return internes, externes


async def reponse_selection(intent, sel, aut, tous, id_vers_nom):
    par_id = {j["id"]: j for j in tous}
    noms = [par_id[j]["nom"] for j in sel if j in par_id]
    internes, externes = await liens_selection(sel, aut)
    sset = set(sel)

    def nom_rel(r):
        return id_vers_nom.get(r["source"], r["source"]) + " → " + id_vers_nom.get(r["cible"], r["cible"])

    indicateurs = {"confiance": 72, "couverture": 64, "fraicheur": "à l'instant", "contradictions": len([r for r in internes if r["etat"] == "contestee"])}

    if intent == "registre":
        twins = [par_id[j] for j in sel if j in par_id]
        lignes = []
        for t in twins[:6]:
            det = t.get("sources_detail") or []
            nb_ok = sum(1 for s in det if s.get("statut") == "prete")
            lignes.append(f"{t['nom']} — connaissance {t.get('couverture', 0)} %, sources {nb_ok}/{len(det)} prêtes, autonomie {t.get('autonomie', '—')}")
        txt = "Registre — " + " · ".join(lignes) + "."
        admissibles = [t for t in twins if t.get("statut") == "observation"]
        if admissibles:
            txt += f" Prêt(s) pour une revue d'admission : {', '.join(t['nom'] for t in admissibles)}."
        faibles = [t for t in twins if t.get("couverture", 100) < 60]
        if faibles:
            txt += f" Connaissance insuffisante : {', '.join(t['nom'] for t in faibles)} — leurs sources méritent d'être complétées."
        blocages = [s for t in twins for s in (t.get("sources_detail") or []) if s.get("statut") not in (None, "prete")]
        if blocages:
            txt += f" Blocage(s) commun(s) : {', '.join(sorted({s['nom'] + ' (' + s['statut'] + ')' for s in blocages}))}."
        return {
            "comportement": "expliquer", "reponse": txt, "contributions": [],
            "preuves": [{"source": "Registre des jumeaux", "detail": f"{len(twins)} jumeau(x) analysé(s) dans votre périmètre"}],
            "indicateurs": {"confiance": 85, "couverture": round(sum(t.get("couverture", 0) for t in twins) / max(len(twins), 1)), "fraicheur": "à l'instant", "contradictions": 0},
            "action": {"route": "/jumeaux", "label": "Ouvrir le registre"},
        }

    if intent == "relations":
        if not internes:
            return {
                "comportement": "expliquer",
                "reponse": f"Aucune relation n'est encore connue entre {', '.join(noms)} — c'est une zone inconnue du Mesh. Je peux surveiller leurs émissions pour détecter une relation émergente.",
                "contributions": [], "preuves": [{"source": "Mesh", "detail": "0 relation connue dans la sélection"}],
                "indicateurs": indicateurs,
            }
        lignes = [f"{nom_rel(r)} ({ETAT_REL_LABELS.get(r['etat'], 'confirmée')})" for r in internes]
        txt = f"{len(internes)} relation(s) connue(s) au sein de la sélection : " + " · ".join(lignes) + "."
        contestees = [r for r in internes if r["etat"] == "contestee"]
        if contestees:
            txt += f" Contradiction active sur {nom_rel(contestees[0])} — à trancher."
        return {
            "comportement": "expliquer", "reponse": txt,
            "contributions": [
                {"jumeau": par_id[r["source"]]["nom"], "domaine": par_id[r["source"]].get("domaine", ""), "texte": f"Relation vers {id_vers_nom.get(r['cible'], r['cible'])} ({ETAT_REL_LABELS.get(r['etat'], 'confirmée')})"}
                for r in internes[:3] if r["source"] in par_id
            ],
            "preuves": [{"source": "Mesh", "detail": f"{len(internes)} relation(s) éclairée(s) sur la carte"}],
            "indicateurs": indicateurs,
            "commande_carte": {"type": "relations", "ids": [r["id"] for r in internes]},
        }

    if intent == "inconnues":
        non_conf = [r for r in internes + externes if r["etat"] != "confirmee"]
        compte_ext = {}
        for r in externes:
            if r["etat"] == "confirmee":
                continue
            autre = r["cible"] if r["source"] in sset else r["source"]
            compte_ext[autre] = compte_ext.get(autre, 0) + 1
        out = {
            "comportement": "explorer",
            "reponse": (
                f"{len(non_conf)} relation(s) non confirmée(s) autour de la sélection : "
                + " · ".join(f"{nom_rel(r)} ({ETAT_REL_LABELS.get(r['etat'], '')})" for r in non_conf[:4]) + "."
                if non_conf else
                f"Aucune relation douteuse autour de {', '.join(noms)} — la zone est entièrement confirmée."
            ),
            "contributions": [], "preuves": [{"source": "Mesh", "detail": f"{len(non_conf)} relation(s) à l'état observé, supposé, validé A2A ou contesté"}],
            "indicateurs": indicateurs,
        }
        if non_conf:
            out["commande_carte"] = {"type": "relations", "ids": [r["id"] for r in non_conf]}
        if compte_ext:
            candidat = max(compte_ext, key=compte_ext.get)
            if candidat in par_id:
                j = par_id[candidat]
                out["propositions"] = [{"jumeau_id": candidat, "nom": j["nom"], "domaine": j.get("domaine", ""), "justification": f"{compte_ext[candidat]} relation(s) non confirmée(s) avec votre sélection — l'ajouter éclairerait la zone"}]
        return out

    if intent == "impact":
        voisins = sorted({(r["cible"] if r["source"] in sset else r["source"]) for r in externes})
        noms_v = [id_vers_nom.get(v, v) for v in voisins]
        risque = [r for r in externes if r["etat"] in ("contestee", "validation", "supposee")]
        txt = f"Un changement sur {', '.join(noms)} exposerait directement {len(voisins)} voisin(s) : {', '.join(noms_v) if noms_v else 'aucun'}."
        if risque:
            txt += f" Point de vigilance : {nom_rel(risque[0])} ({ETAT_REL_LABELS.get(risque[0]['etat'], '')}) — non confirmée, dans la zone d'impact."
        out = {
            "comportement": "recommander", "reponse": txt,
            "contributions": [], "preuves": [{"source": "Mesh", "detail": f"{len(externes)} relation(s) entrante(s) ou sortante(s)"}],
            "indicateurs": indicateurs,
            "action": {"route": "/decisions", "label": "Approfondir dans Change Lab"},
        }
        if externes:
            out["commande_carte"] = {"type": "relations", "ids": [r["id"] for r in externes]}
        return out

    if intent == "critiques":
        touches = sorted({*sel, *(r["source"] for r in externes), *(r["cible"] for r in externes)})
        degrades = [par_id[t] for t in touches if t in par_id and par_id[t].get("sante") == "dégradé"]
        contest = [r for r in internes + externes if r["etat"] in ("contestee", "validation")]
        elements = []
        if degrades:
            elements.append("santé dégradée : " + ", ".join(j["nom"] for j in degrades))
        if contest:
            elements.append("relations à trancher : " + " · ".join(nom_rel(r) for r in contest[:3]))
        out = {
            "comportement": "recommander",
            "reponse": ("Points critiques autour de la sélection — " + " ; ".join(elements) + ".") if elements else f"Aucun point critique détecté autour de {', '.join(noms)} — santé nominale, relations confirmées.",
            "contributions": [], "preuves": [{"source": "Mesh", "detail": "Santé des jumeaux et états des relations croisés"}],
            "indicateurs": indicateurs,
        }
        if contest:
            out["commande_carte"] = {"type": "relations", "ids": [r["id"] for r in contest]}
        ajout = next((j for j in degrades if j["id"] not in sset), None)
        if ajout:
            out["propositions"] = [{"jumeau_id": ajout["id"], "nom": ajout["nom"], "domaine": ajout.get("domaine", ""), "justification": "Santé dégradée et directement lié à votre sélection"}]
        return out

    if intent == "parcours":
        confirmees = [r for r in internes if r["etat"] == "confirmee"]
        return {
            "comportement": "recommander",
            "reponse": f"Parcours proposé : {' → '.join(noms)} — {len(confirmees)} relation(s) confirmée(s), {len(internes) - len(confirmees)} à vérifier. La carte isole ce parcours.",
            "contributions": [], "preuves": [{"source": "Mesh", "detail": f"{len(internes)} relation(s) entre les étapes"}],
            "indicateurs": indicateurs,
            "commande_carte": {"type": "parcours", "ids": sel},
        }

    if intent == "investigation":
        return {
            "comportement": "recommander",
            "reponse": f"Cette sélection peut devenir une investigation : je conserve les {len(sel)} jumeaux, la question posée, la période observée et les preuves déjà rassemblées — rien n'est perdu. L'investigation reprendra ce fil avec hypothèses et contradictoires.",
            "contributions": [], "preuves": [{"source": "Sélection", "detail": f"{len(sel)} jumeau(x), {len(internes)} relation(s) interne(s)"}],
            "indicateurs": indicateurs,
            "action": {"route": "/investigations", "label": "Transformer en investigation"},
        }

    return {
        "comportement": "explorer",
        "reponse": f"Contexte actif : {len(sel)} jumeau(x) — {', '.join(noms)}. {len(internes)} relation(s) connue(s) entre eux, {len(externes)} vers l'extérieur. Choisissez une intention ou précisez votre question.",
        "contributions": [], "preuves": [],
        "indicateurs": {"confiance": 100, "couverture": 64, "fraicheur": "à l'instant", "contradictions": 0},
    }


AURORA_STOPWORDS = {
    "que", "qui", "quoi", "dont", "pour", "avec", "dans", "sur", "les", "des", "une", "est", "sont", "quel", "quelle",
    "quels", "quelles", "pourquoi", "comment", "combien", "entre", "vers", "chez", "aux", "par", "pas", "plus", "tout",
    "tous", "toute", "toutes", "cette", "cet", "ces", "mon", "ma", "mes", "ton", "ta", "tes", "son", "sa", "ses",
    "leur", "leurs", "notre", "nos", "votre", "vos", "ils", "elles", "elle", "nous", "vous", "ont", "fait", "faire",
}


def normalise_txt(t) -> str:
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()


async def recherche_plein_texte(q: str, aut: dict):
    tokens = [t for t in re.split(r"[^a-z0-9]+", normalise_txt(q)) if len(t) > 2 and t not in AURORA_STOPWORDS]
    tokens = [t[:-1] if t.endswith("s") and len(t) > 3 else t for t in tokens]
    if not tokens:
        return None

    def corresponde(texte) -> bool:
        t = normalise_txt(texte)
        return any(tok in t for tok in tokens)

    def score_champs(champs_poids):
        texte = normalise_txt(" ".join(c for c, _ in champs_poids))
        distincts = sum(1 for tok in tokens if tok in texte)
        poids = 0
        for texte_c, p in champs_poids:
            t = normalise_txt(texte_c)
            poids += sum(p for tok in tokens if tok in t)
        return (distincts, poids)

    jumeaux = await db.jumeaux.find({}, NO_ID).to_list(200)
    id_vers_nom = {j["id"]: j["nom"] for j in jumeaux}
    champs_j = lambda j: [(j.get("nom", ""), 3), (j.get("mission", ""), 2), (j.get("domaine", ""), 1), (j.get("proprietaire", ""), 1)]
    twins = [j for j in jumeaux if j["id"] in aut and score_champs(champs_j(j))[0] > 0]
    twins.sort(key=lambda j: score_champs(champs_j(j)), reverse=True)
    relations = await db.relations.find({}, NO_ID).to_list(200)
    rels = [
        r for r in relations
        if r["source"] in aut and r["cible"] in aut
        and corresponde(" ".join([id_vers_nom.get(r["source"], r["source"]), id_vers_nom.get(r["cible"], r["cible"]), r.get("label") or "", " ".join(r.get("claims", []))]))
    ]
    situations = await db.situations.find({}, NO_ID).to_list(100)
    sits = [s for s in situations if any(j in aut for j in s.get("jumeaux", [])) and corresponde(s.get("titre", ""))]
    if not twins and not rels and not sits:
        return None
    morceaux = []
    if twins:
        morceaux.append(f"{len(twins)} jumeau(x) ({', '.join(j['nom'] for j in twins[:4])})")
    if rels:
        noms_rels = [id_vers_nom.get(r["source"], r["source"]) + " → " + id_vers_nom.get(r["cible"], r["cible"]) for r in rels[:3]]
        morceaux.append(f"{len(rels)} relation(s) ({', '.join(noms_rels)})")
    if sits:
        morceaux.append(f"{len(sits)} situation(s) ({', '.join(s['titre'] for s in sits[:2])})")
    action = None
    if twins:
        action = {"route": f"/atlas?focus={twins[0]['id']}", "label": f"Centrer l'Atlas sur {twins[0]['nom']}"}
    elif sits:
        action = {"route": "/investigations", "label": "Ouvrir les investigations"}
    out = {
        "comportement": "explorer",
        "reponse": "Recherche dans votre périmètre — " + " · ".join(morceaux) + ".",
        "contributions": [{"jumeau": j["nom"], "domaine": j["domaine"], "texte": j.get("mission", "")} for j in twins[:3]],
        "preuves": [{"source": "Recherche plein texte", "detail": f"{len(twins) + len(rels) + len(sits)} élément(s) du Mesh correspondent aux termes de la question"}],
        "indicateurs": {"confiance": 61, "couverture": 58, "fraicheur": "à l'instant", "contradictions": 0},
    }
    if action:
        out["action"] = action
    return out


# ---------- Atelier de commande d'un jumeau ----------

class CommandeCreate(BaseModel):
    nom: str = "Nouveau jumeau"
    domaine: str = "Non classé"
    mission: str = ""
    proprietaire: str = ""
    environnement: str = "production"


class CommandePatch(BaseModel):
    jumeau: Optional[dict] = None
    etape: Optional[int] = None
    sources: Optional[list] = None


class TestLot(BaseModel):
    ids: list


class ImportApercu(BaseModel):
    mode: str = "cmdb"


@api_router.get("/connecteurs")
async def lister_connecteurs():
    return {"connecteurs": CONNECTEURS, "contributions": CONTRIBUTIONS, "profils": PROFILS}


@api_router.post("/commandes", status_code=201)
async def creer_commande(payload: CommandeCreate, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
    _, espace = resoudre_perimetre(x_persona, x_espace)
    cid = f"cmd-{secrets.token_hex(4)}"
    doc = {
        "id": cid,
        "etat": "brouillon",
        "etape": 1,
        "jumeau": {"nom": payload.nom, "domaine": payload.domaine, "mission": payload.mission, "proprietaire": payload.proprietaire, "environnement": payload.environnement},
        "sources": [],
        "cree_par": x_persona,
        "cree_le": datetime.now(timezone.utc).isoformat(),
    }
    await db.commandes.insert_one(doc)
    await journaler(x_persona, espace["id"], "ouverture d'une commande", cid, payload.nom)
    doc.pop("_id", None)
    return doc


@api_router.get("/commandes")
async def lister_commandes():
    return await db.commandes.find({"etat": "brouillon"}, NO_ID).to_list(50)


@api_router.get("/commandes/{cid}")
async def lire_commande(cid: str):
    doc = await db.commandes.find_one({"id": cid}, NO_ID)
    if not doc:
        raise HTTPException(404, "Commande introuvable")
    return doc


@api_router.patch("/commandes/{cid}")
async def maj_commande(cid: str, payload: CommandePatch):
    patch = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not patch:
        return {"ok": True}
    patch["maj_le"] = datetime.now(timezone.utc).isoformat()
    res = await db.commandes.update_one({"id": cid}, {"$set": patch})
    if res.matched_count == 0:
        raise HTTPException(404, "Commande introuvable")
    return {"ok": True, "maj_le": patch["maj_le"]}


def _simuler_test(source):
    """Test de connexion simulé mais déterministe : champs requis manquants → configuration incomplète ; sinon échec réaliste pour certains, succès pour la plupart."""
    conn = next((c for c in CONNECTEURS if c["id"] == source["connecteur"]), None)
    manquants = [ch["label"] for ch in (conn["champs"] if conn else []) if ch.get("requis") and not source.get("config", {}).get(ch["cle"])]
    maintenant = datetime.now(timezone.utc).strftime("%d/%m %H:%M")
    if manquants:
        return {"statut": "configuration_incomplete", "erreur": {"titre": "Configuration incomplète", "detail": f"Champs requis manquants : {', '.join(manquants)}.", "action": "Compléter la configuration"}, "dernier_test": {"date": maintenant, "resultat": "echec"}}
    if not source.get("perimetre"):
        return {"statut": "perimetre_vide", "erreur": {"titre": "Périmètre vide", "detail": "Aucun schéma, projet ou index n'est renseigné — la découverte ne rapporterait rien.", "action": "Définir le périmètre"}, "dernier_test": {"date": maintenant, "resultat": "echec"}}
    if "legacy" in (source.get("config", {}).get("hote") or ""):
        return {"statut": "erreur_connexion", "erreur": {"titre": "Erreur de connexion", "detail": "L'hôte ne répond pas (délai dépassé sur le port configuré).", "action": "Vérifier le réseau et le port"}, "dernier_test": {"date": maintenant, "resultat": "echec"}}
    return {"statut": "prete", "erreur": None, "dernier_test": {"date": maintenant, "resultat": "ok"}}


@api_router.post("/commandes/{cid}/tester")
async def tester_sources(cid: str, payload: TestLot, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
    _, espace = resoudre_perimetre(x_persona, x_espace)
    doc = await db.commandes.find_one({"id": cid}, NO_ID)
    if not doc:
        raise HTTPException(404, "Commande introuvable")
    resultats = {}
    modifie = False
    for s in doc["sources"]:
        if s["id"] in payload.ids:
            resultats[s["id"]] = _simuler_test(s)
            s.update(resultats[s["id"]])
            modifie = True
    if modifie:
        await db.commandes.update_one({"id": cid}, {"$set": {"sources": doc["sources"], "maj_le": datetime.now(timezone.utc).isoformat()}})
        await journaler(x_persona, espace["id"], "test de connexions", cid, f"{len(resultats)} source(s) testée(s)")
    return {"resultats": resultats}


@api_router.post("/commandes/{cid}/import/apercu")
async def apercu_import(cid: str, payload: ImportApercu):
    doc = await db.commandes.find_one({"id": cid}, NO_ID)
    if not doc:
        raise HTTPException(404, "Commande introuvable")
    existants = {(s["connecteur"], s["nom"]) for s in doc["sources"]}
    candidats = [
        {"connecteur": "postgresql", "nom": "PostgreSQL Settlement", "environnement": "production", "perimetre": "schéma settlement", "proprietaire": "Équipe Finance", "config": {"hote": "pg-settle.intra", "port": 5432, "base": "settlement", "schemas": "settlement", "frequence": "quotidienne"}},
        {"connecteur": "oracle", "nom": "Oracle Clearing", "environnement": "production", "perimetre": "schéma CLEARING", "proprietaire": "Équipe Finance", "config": {"hote": "ora-clear.intra", "service": "CLEARING", "schemas": "CLEARING", "frequence": "quotidienne"}},
        {"connecteur": "jira", "nom": "Jira Projet CORE", "environnement": "production", "perimetre": "projet CORE", "proprietaire": "Équipe Paiements", "config": {"site": "banque.atlassian.net", "projets": "CORE", "periode": "12 mois", "auth": "jeton API"}},
        {"connecteur": "confluence", "nom": "Confluence Espace PAY", "environnement": "production", "perimetre": "espace PAY", "proprietaire": "Équipe Paiements", "config": {"site": "banque.atlassian.net/wiki", "espaces": "PAY", "periode": "24 mois"}},
        {"connecteur": "cmdb", "nom": "CMDB Centrale", "environnement": "production", "perimetre": "classe Application", "proprietaire": "Équipe Architecture", "config": {"instance": "cmdb.intra", "classes": "Application", "filtre": "domaine=Paiement"}},
        {"connecteur": "postgresql", "nom": "PostgreSQL Production", "environnement": "production", "perimetre": "schémas public, pay", "proprietaire": "Équipe Paiements", "config": {}},
    ]
    nouvelles, presentes, a_mapper = [], [], []
    for c in candidats:
        if (c["connecteur"], c["nom"]) in existants:
            presentes.append(c)
        else:
            nouvelles.append(c)
    a_mapper.append({"connecteur": "sap", "nom": "SAP FI", "note": "Connecteur à correspondre manuellement"})
    return {"mode": payload.mode, "detectees": len(candidats) + 1, "nouvelles": nouvelles, "presentes": presentes, "a_mapper": a_mapper}


@api_router.post("/commandes/{cid}/lancer")
async def lancer_commande(cid: str, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
    _, espace = resoudre_perimetre(x_persona, x_espace)
    doc = await db.commandes.find_one({"id": cid}, NO_ID)
    if not doc:
        raise HTTPException(404, "Commande introuvable")
    j = doc["jumeau"]
    if not j.get("nom") or not j.get("mission") or not j.get("proprietaire"):
        raise HTTPException(422, "Identité incomplète (nom, mission, propriétaire requis)")
    pretes = [s for s in doc["sources"] if s["statut"] == "prete"]
    if not pretes:
        raise HTTPException(422, "Au moins une source prête est requise pour lancer")
    jid = slugify(j["nom"])
    if await db.jumeaux.find_one({"id": jid}):
        raise HTTPException(409, "Un jumeau porte déjà ce nom")
    nouveau = {
        "id": jid, "nom": j["nom"], "domaine": j.get("domaine", "Non classé"), "mission": j["mission"],
        "proprietaire": j["proprietaire"], "environnement": j.get("environnement", "production"),
        "statut": "observation", "autonomie": "aucune",
        "couverture": min(20 + len(pretes) * 9, 88), "fraicheur": "à l'instant", "sante": "inconnu",
        "position": {"x": 1260, "y": 40},
        "sources": {s["connecteur"]: True for s in pretes},
    }
    await db.jumeaux.insert_one(nouveau)
    if isinstance(espace.get("jumeaux"), dict) and "*" not in espace["jumeaux"]:
        espace["jumeaux"][jid] = "complet"
    await db.commandes.update_one({"id": cid}, {"$set": {"etat": "lancee", "jumeau_id": jid, "lancee_le": datetime.now(timezone.utc).isoformat()}})
    await journaler(x_persona, espace["id"], "lancement d'une commande", jid, f"{j['nom']} — {len(pretes)} source(s) prête(s)")
    return {"ok": True, "jumeau_id": jid, "sources_lancees": len(pretes), "sources_reportees": len(doc["sources"]) - len(pretes)}


async def generer_reponse_flore(contexte, question, selection, domaine, x_persona, x_espace):
    _, espace = resoudre_perimetre(x_persona, x_espace)
    tous = await db.jumeaux.find({}, NO_ID).to_list(200)
    aut = autorisations(espace, [j["id"] for j in tous])
    nom_vers_id = {j["nom"]: j["id"] for j in tous}
    id_vers_nom = {j["id"]: j["nom"] for j in tous}
    q = normalise_txt(question)
    for j in tous:
        if j["id"] not in aut and len(j["nom"]) > 4 and normalise_txt(j["nom"]) in q:
            return HORS_PERIMETRE
    sel = [j for j in (selection or []) if j in aut and niveau_au_moins(aut[j], "resume")]
    if not sel and domaine:
        sel = [j["id"] for j in tous if j.get("domaine") == domaine and j["id"] in aut and niveau_au_moins(aut[j["id"]], "resume")]
    if sel:
        intent = intention_selection(q)
        if intent:
            return await reponse_selection(intent, sel, aut, tous, id_vers_nom)
    for script in AURORA_SCRIPTS:
        if script["contexte"] in (contexte, "global") and any(normalise_txt(k) in q for k in script["mots_cles"]):
            out = dict(script)
            out["contributions"] = [c for c in script.get("contributions", []) if nom_vers_id.get(c.get("jumeau", "")) in aut]
            if not any(niveau_au_moins(n, "preuves") for n in aut.values()):
                out["preuves"] = []
            return out
    trouve = await recherche_plein_texte(q, aut)
    if trouve:
        return trouve
    if sel:
        return await reponse_selection(None, sel, aut, tous, id_vers_nom)
    return AURORA_FALLBACK


@api_router.post("/aurora/demander")
async def aurora_demander(payload: AuroraDemande, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
    return await generer_reponse_flore(payload.contexte, payload.question, payload.selection, payload.domaine, x_persona, x_espace)


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


# ---------- Cases (module dédié) ----------

api_router.include_router(build_cases_router({
    "db": db,
    "resoudre_perimetre": resoudre_perimetre,
    "autorisations": autorisations,
    "journaler": journaler,
    "notifier": notifier,
    "generer_reponse_flore": generer_reponse_flore,
    "slugify": slugify,
    "NO_ID": NO_ID,
    "datetime": datetime,
    "timezone": timezone,
}))


# ---------- Actualités (module dédié) ----------

api_router.include_router(build_actualites_router({
    "db": db,
    "resoudre_perimetre": resoudre_perimetre,
    "autorisations": autorisations,
    "filtre_situation": filtre_situation,
    "ESPACES": ESPACES,
    "NO_ID": NO_ID,
    "timezone": timezone,
}))


# ---------- Initiatives du Mesh & délégations (grammaire d'interaction) ----------

api_router.include_router(build_initiatives_router({
    "db": db,
    "resoudre_perimetre": resoudre_perimetre,
    "autorisations": autorisations,
    "journaler": journaler,
    "slugify": slugify,
    "NO_ID": NO_ID,
}))


# ---------- Notifications ----------

@api_router.get("/notifications")
async def lister_notifications(x_persona: str = Header("architecte")):
    docs = await db.notifications.find({"persona": x_persona}, NO_ID).sort("quand", -1).to_list(30)
    return {"notifications": docs, "non_lues": sum(1 for d in docs if not d.get("lu"))}


@api_router.post("/notifications/{nid}/lue")
async def notification_lue(nid: str, x_persona: str = Header("architecte")):
    await db.notifications.update_one({"id": nid, "persona": x_persona}, {"$set": {"lu": True}})
    return {"ok": True}


@api_router.post("/notifications/tout-lire")
async def notifications_tout_lire(x_persona: str = Header("architecte")):
    await db.notifications.update_many({"persona": x_persona}, {"$set": {"lu": True}})
    return {"ok": True}

# ---------- Démo & activité ----------

@api_router.post("/demo/reinitialiser")
async def reinitialiser_demo(x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
    for col in ["jumeaux", "relations", "situations", "change_lab", "dossiers", "vues", "journal", "commandes", "cases", "notifications", "initiatives", "delegations"]:
        await db[col].delete_many({})
    await peupler_demo()
    await journaler(x_persona, x_espace, "réinitialisation de la démo", "mesh", "Données de démonstration restaurées à l'état initial")
    return {"ok": True}


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
