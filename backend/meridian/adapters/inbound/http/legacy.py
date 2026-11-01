from fastapi import Depends, FastAPI, APIRouter, HTTPException, Header, Query, Request, Response
from dotenv import load_dotenv
from starlette.middleware.body_limit import RequestBodyLimitMiddleware
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from typing import Optional, Dict
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import random
import signal
import sys
import logging
import threading
import unicodedata
from pathlib import Path
from uuid import uuid4

ROOT_DIR = Path(__file__).resolve().parents[4]
load_dotenv(ROOT_DIR / ".env")  # avant les modules qui lisent leur configuration à l'import (auth, pieces, limites)

import auth as auth_identite  # noqa: E402
import limites  # noqa: E402
import pieces  # noqa: E402
from meridian.adapters.inbound.http.cases import build_cases_router  # noqa: E402
from meridian.adapters.inbound.http.actualites import build_actualites_router  # noqa: E402
from meridian.adapters.inbound.http.initiatives import build_initiatives_router  # noqa: E402
from meridian.adapters.inbound.http.mesh_vue import build_mesh_vue_router  # noqa: E402
from meridian.adapters.inbound.http.boucle import router as boucle_router, _tenant as resoudre_tenant_boucle  # noqa: E402
from meridian.adapters.inbound.http.cognitif import router as cognitif_router  # noqa: E402
from meridian.adapters.inbound.http.runs import construire_router as construire_runs_router
from meridian.adapters.inbound.http.interfaces import router as jumeau_router  # noqa: E402
from meridian.adapters.inbound.http.sources import construire_router as construire_sources_router  # noqa: E402
from meridian.adapters.outbound.connectors import cbm as jumeau_cbm
from meridian.adapters.outbound.redis import evenements as jumeau_evenements
from meridian.adapters.outbound.redis import partage as jumeau_partage
from meridian.adapters.outbound.redis import tours_redis as jumeau_tours_redis
from meridian.adapters.outbound.llm import flore as jumeau_flore
from meridian.adapters.outbound.postgres import identite_depot as jumeau_identite_depot
from meridian.adapters.outbound.llm import conception as jumeau_conception
from meridian.adapters.outbound.llm import orchestrateur as jumeau_orchestrateur
from meridian.adapters.outbound.postgres import audit_harness as jumeau_audit_harness
from meridian.domain import capacites as jumeau_capacites
from meridian.adapters.outbound.connectors import chargeur_manifestes as jumeau_chargeur_manifestes
from meridian.domain import import_identite as jumeau_import_identite
from meridian.adapters.outbound.mongo.commandes_depot import CommandesDepot  # noqa: E402
from meridian.adapters.outbound.mongo import travail_proxy  # noqa: E402
from meridian.adapters.outbound.naissance_runtime import NaissanceRuntimeLocal  # noqa: E402
from meridian.application.commandes import (  # noqa: E402
    CHAMPS_SECRETS, CommandeIntrouvable, CommandeModifiee, EtapeInvalide,
    JumeauExistant, LancementRefuse, NaissanceIndisponible,
    apercu_import as apercu_commande,
    creer_commande as creer_commande_metier,
    lancer_commande as lancer_commande_metier,
    lister_commandes as lister_commandes_metier,
    lire_commande as lire_commande_metier,
    maj_commande as maj_commande_metier,
    naissance_possible,
    proteger_source as _proteger_source_metier,
    sans_secrets as _sans_secrets,
    suivre_naissance as suivre_naissance_metier,
    statut_serveur as _statut_serveur,
    tester_sources as tester_sources_metier,
)
from meridian.domain.import_identite import ImportInvalide as ImportIdentiteInvalide  # noqa: E402
from meridian.adapters.outbound.llm import harness as jumeau_harness
from meridian.application import ingestion_outils as jumeau_ingestion_outils
from meridian.application import interface_outils as jumeau_interface_outils
from meridian.adapters.outbound.postgres import rls as jumeau_rls
from meridian.adapters.outbound.postgres import decouverte_interfaces as jumeau_decouverte_interfaces
from meridian.adapters.outbound.postgres import interfaces_depot as jumeau_interfaces_depot
from meridian.adapters.outbound.connectors import connecteurs_runtime as jumeau_connecteurs_runtime
from meridian.adapters.outbound.connectors import connecteurs_runtime_pull as jumeau_connecteurs_runtime_pull
from meridian.adapters.outbound.postgres import pulls_runtime as jumeau_pulls_runtime
from meridian.adapters.outbound.postgres import depot as jumeau_depot
from meridian.adapters.outbound.postgres import connaissance as jumeau_connaissance
from meridian.adapters.inbound.http import flux as jumeau_flux  # noqa: E402
from meridian.adapters.outbound.mongo import registre as jumeau_registre
from meridian.adapters.outbound.connectors import connecteurs as jumeau_connecteurs
from meridian.domain import origine as jumeau_origine
from meridian.adapters.outbound.connectors import naissance as jumeau_naissance
from meridian.adapters.outbound.postgres import examen as jumeau_examen
from meridian.adapters.outbound.connectors.systemes import SYSTEMES
from meridian.adapters.outbound.connectors import github as jumeau_github
import asyncio  # noqa: E402
import psycopg  # noqa: E402
from pymongo.errors import DuplicateKeyError  # noqa: E402
from seed_data import (  # noqa: E402
    AURORA_FALLBACK, AURORA_SUGGESTIONS, SOURCES_LABELS,
    ESPACES, CONNECTEURS, CONTRIBUTIONS, PROFILS,
)

CORS_ORIGINES = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()] or ["*"]

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="Méridian")


auth_identite.installer(app)


api_router = APIRouter(prefix="/api")

NO_ID = {"_id": 0}
logger = logging.getLogger("meridian")


SEED_VERSION = 13


async def projeter_jumeaux_reels():
    """Les jumeaux réels (couche cognitive Postgres) rejoignent le registre après chaque (ré)initialisation."""
    dsn = os.environ.get("JUMEAU_PG_DSN")
    if not dsn:
        return
    try:
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            n = await jumeau_registre.projeter(db, conn)
        logger.info("Jumeaux réels projetés dans le registre : %d", n)
    except psycopg.Error:
        logger.exception("Projection des jumeaux réels impossible ; le registre de démo reste utilisable")


def _nombre_workers():
    nombres = []
    for cle in ("WEB_CONCURRENCY", "UVICORN_WORKERS", "GUNICORN_WORKERS"):
        valeur = os.getenv(cle)
        if not valeur:
            continue
        try:
            nombres.append(int(valeur))
        except ValueError:
            pass

    def ajouter(argv):
        for i, arg in enumerate(argv):
            if arg in ("--workers", "-w") and i + 1 < len(argv):
                try:
                    nombres.append(int(argv[i + 1]))
                except ValueError:
                    pass
            elif arg.startswith("--workers=") or arg.startswith("-w="):
                try:
                    nombres.append(int(arg.split("=", 1)[1]))
                except ValueError:
                    pass

    ajouter(sys.argv)
    try:  # worker uvicorn : le nombre de workers vit dans la ligne de commande du superviseur
        cmd = Path(f"/proc/{os.getppid()}/cmdline").read_bytes().replace(b"\0", b" ").decode()
        ajouter(cmd.split())
    except OSError:
        pass
    return max(nombres or [1])


@app.on_event("startup")
async def demarrer_partage():
    auth_identite.verifier_config()
    limites.verifier_cors(CORS_ORIGINES)  # un joker CORS ne démarre jamais en production
    if _nombre_workers() > 1 and not jumeau_partage.actif():
        raise RuntimeError("REDIS_URL est requis avec plusieurs workers uvicorn")
    await jumeau_partage.verifier()
    await jumeau_tours_redis.demarrer_taches()
    await jumeau_flux.demarrer_controle()


@app.on_event("startup")
async def activer_double_ecriture_travail():
    try:
        travail_proxy.installer(db)
    except Exception:  # noqa: BLE001 - le drapeau ne doit pas empêcher l'API de démarrer
        logger.exception("Double écriture Travail indisponible ; écritures Mongo seules")


@app.on_event("startup")
async def seed_database():
    jumeau_cbm.verifier_cache()
    meta = await db.meta.find_one({"id": "seed"})
    if not meta or meta.get("version") != SEED_VERSION:
        for col in ["jumeaux", "relations", "situations", "change_lab", "dossiers", "vues", "journal", "commandes", "cases", "notifications", "initiatives", "delegations", "actualites_ecartees"]:
            await (db.cases if col == "cases" else db[col]).delete_many({})
        await pieces.reinitialiser(db)
        await db.meta.replace_one({"id": "seed"}, {"id": "seed", "version": SEED_VERSION}, upsert=True)
        logger.info("Seed version %s — réinitialisation des données de démo", SEED_VERSION)
    await projeter_jumeaux_reels()
    try:
        await db.jumeaux.create_index("id", unique=True, name="jumeau_id_unique")
    except Exception:  # noqa: BLE001 - des doublons historiques ne doivent pas empêcher le démarrage
        logger.warning("Index unique jumeaux.id non créé : vérifier les doublons historiques", exc_info=True)
    # Pièces jointes : quota atomique par Travail. Les cases antérieurs n'ont pas de compteur — on l'initialise
    # avec leur nombre réel de pièces, sans réinitialiser quoi que ce soit.
    async for case in db.cases.find({"pieces_count": {"$exists": False}}, {"_id": 0, "id": 1}):
        compte = await db.pieces.count_documents({"case_id": case["id"]})
        await db.cases.update_one({"id": case["id"]}, {"$set": {"pieces_count": compte}})
    # Découpage des pièces antérieures : le texte reste intact, seules les bornes de sections sont ajoutées.
    await pieces.migrer_sections(db)
    # Index idempotents : une pièce est unique dans son Travail, et la liste se lit par Travail.
    await db.pieces.create_index([("case_id", 1), ("id", 1)], unique=True, name="piece_par_case")
    await db.pieces.create_index("case_id", name="pieces_par_case")


def slugify(nom: str) -> str:
    s = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


# ---------- Moteur de périmètres (Mesh global / Espace / Vue / Investigation) ----------

NIVEAUX = ["existence", "resume", "relations", "preuves", "complet"]


def resoudre_perimetre(acteur: str, espace_id):
    espace = next((e for e in ESPACES if e["id"] == espace_id), None)
    if espace is None:
        espace = next(e for e in ESPACES if e.get("global"))
    return acteur, espace


def autorisations(espace: dict, tous_ids):
    regles = espace["jumeaux"]
    if regles == "*":
        return {i: "complet" for i in tous_ids}
    if "*" in regles:
        return {i: regles["*"] for i in tous_ids}
    return {k: v for k, v in regles.items() if k in tous_ids}


def niveau_au_moins(niveau, seuil):
    return NIVEAUX.index(niveau) >= NIVEAUX.index(seuil)


def _resume_projets(projets: list) -> dict:
    """Ce que le Mesh retient des chantiers d'un jumeau : combien sont vivants, combien sont bloqués, le prochain jalon."""
    vivants = [p for p in projets if p.get("statut") != "termine"]
    echeances = sorted(p["echeance"] for p in vivants if p.get("echeance"))
    return {"n": len(vivants), "bloques": sum(1 for p in vivants if p.get("statut") == "bloque" or p.get("tickets", {}).get("bloques")), "prochaine": echeances[0] if echeances else None}


def projete_jumeau(j: dict, niveau: str, aut: Optional[dict] = None):
    # Tous les jumeaux affichés naissent d'une source réelle ; le registre ne contient plus de seed mocké.
    base = {"id": j["id"], "nom": j["nom"], "domaine": j.get("domaine"), "statut": j.get("statut"),
            "position": j.get("position"), "reel": bool(j.get("reel")),
            "origine": "reel" if j.get("reel") else "demonstration"}
    if niveau_au_moins(niveau, "resume"):
        base.update({"mission": j.get("mission"), "sante": j.get("sante"), "couverture": j.get("couverture"), "fraicheur": j.get("fraicheur"), "strates": j.get("strates"), "fraicheur_etat": j.get("fraicheur_etat"), "capacites": j.get("capacites"), "candidat": j.get("candidat"),
                     "projets_resume": _resume_projets(j.get("projets", []))})
    if niveau_au_moins(niveau, "preuves"):
        base["sources"] = j.get("sources")
        base["sources_detail"] = j.get("sources_detail")
        # Chantiers (Jira) : les jumeaux touchés que la personne n'a pas le droit de voir n'apparaissent pas
        # (un chantier porté par un jumeau que la personne ne voit pas reste connu, mais son porteur ne l'est pas)
        base["projets"] = [{**p, "impacte": [i for i in p.get("impacte", []) if aut is None or i in aut], "porteur": p["porteur"] if aut is None or p["porteur"] in aut else None}
                           for p in j.get("projets", [])]
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


async def journaler(acteur: str, espace_id, action: str, cible: str, detail: str = ""):
    await db.journal.insert_one({
        "quand": datetime.now(timezone.utc).isoformat(),
        "acteur": acteur, "espace": espace_id or "",
        "action": action, "cible": cible, "detail": detail,
    })


async def notifier(type_, texte, lien):
    now = datetime.now(timezone.utc).isoformat()
    doc = {"id": f"notif-{uuid4().hex[:8]}", "type": type_, "texte": texte, "lien": lien, "lu": False, "quand": now}
    await db.notifications.insert_one(doc)
    jumeau_evenements.publier("*", "notification.creee",
                              notification={k: doc[k] for k in ("id", "type", "texte", "lien", "lu", "quand")})


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
        await notifier("a_revoir", f"Le travail « {case['titre']} » est à revoir : {raison}", f"/travaux/{case['id']}")


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


# ---------- Périmètres : espace, vues, journal ----------

@api_router.get("/moi")
async def moi(request: Request):
    return {
        "acteur": getattr(request.state, "utilisateur", None) or "demo",
        "tenant": getattr(request.state, "tenant", None),
        "auth_mode": getattr(request.state, "auth_mode", "demo"),
    }


@api_router.get("/espaces")
async def lister_espaces():
    return [
        {"id": e["id"], "label": e["label"], "description": e["description"], "global": e.get("global", False)}
        for e in ESPACES
    ]


@api_router.get("/perimetre")
async def obtenir_perimetre(acteur: str = Depends(auth_identite.acteur)):
    espace = next(e for e in ESPACES if e.get("global"))
    tous = await db.jumeaux.find({}, {"_id": 0, "id": 1}).to_list(200)
    aut = autorisations(espace, [j["id"] for j in tous])
    return {
        "acteur": acteur,
        "espace": {"id": espace["id"], "label": espace["label"], "global": espace.get("global", False), "politique_dependances": espace.get("politique_dependances")},
        "autorisations": aut,
        "nb_autorises": len(aut),
    }


@api_router.get("/vues")
async def lister_vues():
    return await db.vues.find({}, NO_ID).to_list(50)


class VueCreate(BaseModel):
    nom: str
    type: str = "selection"
    jumeaux: list = []


@api_router.post("/vues", status_code=201)
async def creer_vue(payload: VueCreate):
    doc = {"id": f"vue-{slugify(payload.nom)}-{random.randint(100, 999)}", "nom": payload.nom, "type": payload.type, "jumeaux": payload.jumeaux}
    await db.vues.insert_one(doc)
    doc.pop("_id", None)
    return doc


ACTIONS_JOURNAL_CLIENT = {"changement de périmètre"}


def filtre_journal(acteur: str, espace: dict):
    """Un espace global voit tout ; sinon le journal reste borné à l'acteur et à son espace."""
    if espace.get("global"):
        return {}
    return {"$or": [{"acteur": acteur}, {"espace": espace["id"]}]}


@api_router.get("/journal")
async def lire_journal(response: Response, acteur: str = Depends(auth_identite.acteur), x_espace: Optional[str] = Header(None)):
    _, espace = resoudre_perimetre(acteur, x_espace)
    response.headers["Cache-Control"] = "private, no-store"
    return await db.journal.find(filtre_journal(acteur, espace), NO_ID).sort("quand", -1).to_list(30)


class JournalEntree(BaseModel):
    action: str
    detail: str = ""  # ignoré : le détail est toujours dérivé côté serveur


@api_router.post("/journal", status_code=201)
async def ecrire_journal(payload: JournalEntree, acteur: str = Depends(auth_identite.acteur), x_espace: Optional[str] = Header(None)):
    if payload.action not in ACTIONS_JOURNAL_CLIENT:
        raise HTTPException(400, "Action de journal inconnue")
    _, espace = resoudre_perimetre(acteur, x_espace)
    await journaler(acteur, espace["id"], payload.action, "", f"{espace['id']} — {espace['label']}")
    return {"ok": True}


# ---------- Mesh ----------

@api_router.get("/mesh")
async def get_mesh(acteur: str = Depends(auth_identite.acteur), x_espace: Optional[str] = Header(None)):
    _, espace = resoudre_perimetre(acteur, x_espace)
    tous = await db.jumeaux.find({}, NO_ID).to_list(200)
    par_id = {j["id"]: j for j in tous}
    aut = autorisations(espace, list(par_id))
    visibles = [projete_jumeau(j, aut[j["id"]], aut) for j in tous if j["id"] in aut]
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
        "regions": [],
        "perimetre": {"espace": espace["label"], "global": espace.get("global", False), "politique": politique, "nb_autorises": len(visibles), "nb_restreints": len(anon)},
    }


@api_router.get("/mesh/interfaces")
async def get_mesh_interfaces(acteur: str = Depends(auth_identite.acteur),
                              x_espace: Optional[str] = Header(None)):
    """Le graphe d'interfaces du Mesh visible : applications, opérations, arêtes consommateur→producteur, impacts.

    Le tenant est lu dans Postgres pour les seules applications autorisées. S'il en couvre plusieurs, la lecture est
    refusée plutôt que de mélanger deux graphes. Aucune application hors périmètre n'entre dans la réponse.
    """
    _, espace = resoudre_perimetre(acteur, x_espace)
    tous = await db.jumeaux.find({}, {"_id": 0, "id": 1}).to_list(None)
    aut = autorisations(espace, [j["id"] for j in tous])
    visibles = sorted(aut)
    dsn = os.environ.get("JUMEAU_PG_DSN")
    if not dsn:
        raise HTTPException(503, "Couche cognitive non configurée (JUMEAU_PG_DSN)")

    def lire():
        with psycopg.connect(dsn) as conn:
            tenants = jumeau_interfaces_depot.tenants_pour(conn, visibles)
            if len(tenants) > 1:
                raise HTTPException(409, "Périmètre couvrant plusieurs tenants : lecture refusée")
            if not tenants:
                return {"tenant": None, "applications": visibles, "operations": [], "edges": [],
                        "impacts": [], "runs": []}
            tenant = tenants[0]
            graphe = jumeau_interfaces_depot.lire_graph_pour(conn, tenant, visibles)
            runs = jumeau_interfaces_depot.derniers_runs_pour(conn, tenant, visibles)
            return {
                "tenant": tenant,
                "applications": visibles,
                "operations": jumeau_interfaces_depot.operations_publiques(graphe, visibles),
                "edges": jumeau_interfaces_depot.deriver_aretes(graphe, visibles),
                "impacts": jumeau_interfaces_depot.impacts_des_runs(runs, visibles),
                "runs": jumeau_interfaces_depot.runs_publiques(runs, visibles),
            }

    try:
        return await asyncio.to_thread(lire)
    except psycopg.Error:
        raise HTTPException(503, "Couche cognitive indisponible")


# ---------- Jumeaux (Registry) ----------

@api_router.get("/jumeaux")
async def lister_jumeaux(acteur: str = Depends(auth_identite.acteur), x_espace: Optional[str] = Header(None)):
    _, espace = resoudre_perimetre(acteur, x_espace)
    tous = await db.jumeaux.find({}, NO_ID).to_list(200)
    aut = autorisations(espace, [j["id"] for j in tous])
    out = []
    for j in tous:
        if j["id"] in aut and niveau_au_moins(aut[j["id"]], "resume"):
            p = projete_jumeau(j, aut[j["id"]], aut)
            p["niveau"] = aut[j["id"]]
            out.append(p)
    return out


class JumeauCreate(BaseModel):
    nom: str
    proprietaire: str
    mission: str
    environnement: str = "production"
    sources: Dict[str, bool] = {}


class Promotion(BaseModel):
    nom: str
    mission: str
    motif: Optional[str] = None


class ObservationsRuntime(BaseModel):
    observations: list[dict] = Field(default_factory=list, max_length=50000)
    otlp: Optional[dict] = None
    format: str = "normalise"
    source: str = "apm"
    environment: str = "production"


class TirageRuntime(BaseModel):
    url: str
    secret_ref: Optional[str] = None
    environment: str = "production"
    source: str = "apm"


@api_router.post("/jumeaux", status_code=201)
async def creer_jumeau(payload: JumeauCreate, acteur: str = Depends(auth_identite.acteur), x_espace: Optional[str] = Header(None)):
    _, espace = resoudre_perimetre(acteur, x_espace)
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
    try:
        await db.jumeaux.insert_one(doc)
    except DuplicateKeyError as exc:
        raise HTTPException(409, "Un jumeau porte déjà ce nom") from exc
    if isinstance(espace.get("jumeaux"), dict) and "*" not in espace["jumeaux"]:
        espace["jumeaux"][jid] = "complet"
    await journaler(acteur, espace["id"], "commande d'un jumeau", jid, payload.nom)
    doc.pop("_id", None)
    return doc


@api_router.post("/jumeaux/{jid}/admettre")
async def admettre_jumeau(jid: str, acteur: str = Depends(auth_identite.acteur), x_espace: Optional[str] = Header(None)):
    _, espace = resoudre_perimetre(acteur, x_espace)
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
    await journaler(acteur, espace["id"], "admission d'un jumeau", jid)
    jumeau = await db.jumeaux.find_one({"id": jid}, NO_ID)
    await marquer_cases_a_revoir([jid], f"le jumeau {jumeau['nom'] if jumeau else jid} a été admis dans le Mesh")
    return {"ok": True, "statut": "actif"}


@api_router.post("/jumeaux/{jid}/interfaces/observer")
async def observer_interfaces_du_jumeau(jid: str, payload: ObservationsRuntime,
                                        acteur: str = Depends(auth_identite.acteur),
                                        x_espace: Optional[str] = Header(None)):
    """Ingère un export APM/gateway normalisé en mode ombre : assertions observées, jamais promues."""
    _, espace = resoudre_perimetre(acteur, x_espace)
    tous = await db.jumeaux.find({}, {"_id": 0, "id": 1}).to_list(200)
    aut = autorisations(espace, [j["id"] for j in tous])
    if jid not in aut or not niveau_au_moins(aut[jid], "complet"):
        raise HTTPException(404, "Jumeau introuvable")
    dsn = os.environ.get("JUMEAU_PG_DSN")
    if not dsn:
        raise HTTPException(503, "Couche cognitive non configurée (JUMEAU_PG_DSN)")

    def ingerer():
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            jumeau = jumeau_depot.jumeau_par_id(conn, jid)
            if not jumeau:
                raise LookupError(jid)
            if payload.format == "otlp":
                if not payload.otlp:
                    raise ValueError("format otlp : payload otlp absent")
                graph = jumeau_connecteurs_runtime.depuis_otlp(
                    jid, payload.otlp, payload.environment, payload.source)
            elif payload.format == "normalise":
                graph = jumeau_connecteurs_runtime.depuis_observations(
                    jid, payload.observations, payload.environment, payload.source)
            else:
                raise ValueError("format attendu : normalise ou otlp")
            stats = jumeau_interfaces_depot.enregistrer(conn, jumeau["tenant_id"], graph, remplacer=False)
            return {"jumeau_id": jid, "mode": "shadow", "source": payload.source,
                    "environment": payload.environment, "stats": stats,
                    "resume": jumeau_connecteurs_runtime.resume(graph),
                    "graphe": graph.as_dict()}

    try:
        return await asyncio.to_thread(ingerer)
    except LookupError:
        raise HTTPException(404, "Jumeau introuvable")
    except ValueError as e:
        raise HTTPException(400, str(e))
    except psycopg.Error:
        logger.exception("Observations runtime du jumeau %s impossibles", jid)
        raise HTTPException(503, "Couche cognitive indisponible")


@api_router.post("/jumeaux/{jid}/interfaces/observer/pull")
async def tirer_interfaces_du_jumeau(jid: str, payload: TirageRuntime,
                                     acteur: str = Depends(auth_identite.acteur),
                                     x_espace: Optional[str] = Header(None)):
    """Tire un export OTLP d'un collecteur autorisé, puis l'ingère en mode ombre (jamais promu)."""
    _, espace = resoudre_perimetre(acteur, x_espace)
    tous = await db.jumeaux.find({}, {"_id": 0, "id": 1}).to_list(200)
    aut = autorisations(espace, [j["id"] for j in tous])
    if jid not in aut or not niveau_au_moins(aut[jid], "complet"):
        raise HTTPException(404, "Jumeau introuvable")
    if not jumeau_connecteurs_runtime_pull.hotes_autorises():
        raise HTTPException(503, "Aucun hôte OTLP autorisé : définir JUMEAU_OTLP_HOTES")
    dsn = os.environ.get("JUMEAU_PG_DSN")
    if not dsn:
        raise HTTPException(503, "Couche cognitive non configurée (JUMEAU_PG_DSN)")

    def tirer():
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            jumeau = jumeau_depot.jumeau_par_id(conn, jid)
            if not jumeau:
                raise LookupError(jid)
            tenant = jumeau["tenant_id"]
        graph = jumeau_connecteurs_runtime_pull.depuis_url(
            jid, payload.url, payload.secret_ref, payload.environment, payload.source)
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            stats = jumeau_interfaces_depot.enregistrer(conn, tenant, graph, remplacer=False)
        return {"jumeau_id": jid, "mode": "shadow", "source": payload.source,
                "environment": payload.environment, "stats": stats,
                "resume": jumeau_connecteurs_runtime.resume(graph),
                "graphe": graph.as_dict()}

    try:
        return await asyncio.to_thread(tirer)
    except LookupError:
        raise HTTPException(404, "Jumeau introuvable")
    except (jumeau_connecteurs_runtime_pull.HoteRefuse,
            jumeau_connecteurs_runtime_pull.SecretRefuse,
            jumeau_connecteurs_runtime_pull.ReponseTropGrande,
            jumeau_connecteurs_runtime_pull.JSONInvalide,
            jumeau_connecteurs_runtime_pull.SchemaOTLP) as e:
        raise HTTPException(400, str(e))
    except (jumeau_connecteurs_runtime_pull.ReponseHTTP,
            jumeau_connecteurs_runtime_pull.SourceInjoignable) as e:
        raise HTTPException(502, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except psycopg.Error:
        logger.exception("Tirage OTLP du jumeau %s impossible", jid)
        raise HTTPException(503, "Couche cognitive indisponible")


@api_router.post("/jumeaux/{jid}/interfaces/observer/pull-source")
async def tirer_sources_otlp_du_jumeau(jid: str, acteur: str = Depends(auth_identite.acteur),
                                       x_espace: Optional[str] = Header(None)):
    """Tire les sources OTLP persistées du jumeau, publie les impacts et rend les runs observés.

    Aucun URL ni secret n'est accepté dans le corps : la configuration vient de `source`. Une source en panne
    n'empêche pas les autres (tirage best-effort) ; l'absence de jumeau ou de couche cognitive est explicite.
    """
    _, espace = resoudre_perimetre(acteur, x_espace)
    tous = await db.jumeaux.find({}, {"_id": 0, "id": 1}).to_list(200)
    aut = autorisations(espace, [j["id"] for j in tous])
    if jid not in aut or not niveau_au_moins(aut[jid], "complet"):
        raise HTTPException(404, "Jumeau introuvable")
    dsn = os.environ.get("JUMEAU_PG_DSN")
    if not dsn:
        raise HTTPException(503, "Couche cognitive non configurée (JUMEAU_PG_DSN)")

    try:
        conn = await asyncio.to_thread(psycopg.connect, dsn, connect_timeout=5, autocommit=True)
    except psycopg.Error:
        logger.exception("Tirage des sources OTLP du jumeau %s impossible", jid)
        raise HTTPException(503, "Couche cognitive indisponible")
    try:
        jumeau = await asyncio.to_thread(jumeau_depot.jumeau_par_id, conn, jid)
        if not jumeau:
            raise HTTPException(404, "Jumeau introuvable")
        sources = await asyncio.to_thread(jumeau_pulls_runtime.sources_otlp, conn, jid)
        if sources and not jumeau_connecteurs_runtime_pull.hotes_autorises():
            raise HTTPException(503, "Aucun hôte OTLP autorisé : définir JUMEAU_OTLP_HOTES")
        runs = await jumeau_pulls_runtime.tirer_et_publier(db, conn, jumeau, sources, force=True)
        return {"jumeau_id": jid, "runs": runs}
    except psycopg.Error:
        logger.exception("Tirage des sources OTLP du jumeau %s impossible", jid)
        raise HTTPException(503, "Couche cognitive indisponible")
    finally:
        await asyncio.to_thread(conn.close)


@api_router.post("/jumeaux/{jid}/promouvoir")
async def promouvoir_jumeau(jid: str, payload: Promotion, acteur: str = Depends(auth_identite.acteur),
                            x_espace: Optional[str] = Header(None)):
    """Promotion humaine d'un twin provisoire : même id, identité décidée, décision auditée en Postgres."""
    _, espace = resoudre_perimetre(acteur, x_espace)
    tous = await db.jumeaux.find({}, {"_id": 0, "id": 1}).to_list(200)
    aut = autorisations(espace, [j["id"] for j in tous])
    if jid not in aut or not niveau_au_moins(aut[jid], "complet"):
        raise HTTPException(404, "Jumeau introuvable")
    dsn = os.environ.get("JUMEAU_PG_DSN")
    if not dsn:
        raise HTTPException(503, "Couche cognitive non configurée (JUMEAU_PG_DSN)")

    def promouvoir():
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            jumeau = jumeau_depot.jumeau_par_id(conn, jid)
            if not jumeau:
                raise LookupError(jid)
            preuve = {"motif": payload.motif} if payload.motif else None
            return jumeau_identite_depot.promouvoir(
                conn, jumeau["tenant_id"], jid, payload.nom, payload.mission, acteur, preuve=preuve)

    try:
        resultat = await asyncio.to_thread(promouvoir)
    except LookupError:
        raise HTTPException(404, "Jumeau introuvable")
    except jumeau_identite_depot.JumeauDejaCanonique:
        raise HTTPException(409, "Ce jumeau est déjà une application canonique")
    except PermissionError:
        raise HTTPException(409, "Promotion refusée : le jumeau appartient à un autre tenant")
    except jumeau_identite_depot.PromotionRefusee as e:
        raise HTTPException(400, str(e))
    except psycopg.Error:
        logger.exception("Promotion du jumeau %s impossible", jid)
        raise HTTPException(503, "Couche cognitive indisponible")
    await db.jumeaux.update_one(
        {"id": jid},
        {"$set": {"nom": resultat["nom"], "mission": resultat["mission"], "statut": "actif"}},
    )
    await journaler(acteur, espace["id"], "promotion d'un jumeau", jid,
                    f"{resultat['avant']['nom']} → {resultat['nom']}")
    return resultat


@api_router.delete("/jumeaux/{jid}")
async def supprimer_jumeau(jid: str, acteur: str = Depends(auth_identite.acteur), x_espace: Optional[str] = Header(None)):
    _, espace = resoudre_perimetre(acteur, x_espace)
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
    await journaler(acteur, espace["id"], "retrait d'un jumeau", jid)
    return {"ok": True}


@api_router.patch("/jumeaux/{jid}")
async def deplacer_jumeau(jid: str, payload: dict, acteur: str = Depends(auth_identite.acteur), x_espace: Optional[str] = Header(None)):
    """Position cartographique (mode réorganisation) et reclassification de domaine — toujours validées par un humain."""
    _, espace = resoudre_perimetre(acteur, x_espace)
    if not await db.jumeaux.find_one({"id": jid}, {"_id": 0, "id": 1}):
        raise HTTPException(404, "Jumeau introuvable")
    aut = autorisations(espace, [jid])
    if aut.get(jid) is None:
        raise HTTPException(404, "Jumeau introuvable")
    if aut[jid] != "complet":
        raise HTTPException(403, "Niveau « complet » requis pour déplacer ce jumeau")
    champs = {}
    pos = payload.get("position")
    if pos and isinstance(pos.get("x"), (int, float)) and isinstance(pos.get("y"), (int, float)):
        champs["position"] = {"x": pos["x"], "y": pos["y"]}
    if payload.get("domaine"):
        champs["domaine"] = payload["domaine"]
    if not champs:
        raise HTTPException(400, "Rien à mettre à jour")
    await db.jumeaux.update_one({"id": jid}, {"$set": champs})
    if "domaine" in champs:
        await journaler(acteur, espace["id"], "reclassification d'un jumeau", jid)
    return {"ok": True}


@api_router.post("/jumeaux/{jid}/examiner")
async def examiner_jumeau(jid: str, acteur: str = Depends(auth_identite.acteur), x_espace: Optional[str] = Header(None)):
    _, espace = resoudre_perimetre(acteur, x_espace)
    aut = autorisations(espace, [jid])
    if aut.get(jid) is None:
        raise HTTPException(404, "Jumeau introuvable")
    if not niveau_au_moins(aut[jid], "preuves"):
        raise HTTPException(403, "Niveau « preuves » requis pour examiner ce jumeau")
    j = await db.jumeaux.find_one({"id": jid}, NO_ID)
    if not j:
        raise HTTPException(404, "Jumeau introuvable")
    if j.get("reel") and os.environ.get("JUMEAU_PG_DSN"):
        # Né du code : même examen, tiré de ses connaissances prouvées et de sa fiche vivante
        def examen_reel():
            with psycopg.connect(os.environ["JUMEAU_PG_DSN"], connect_timeout=5) as conn:
                return jumeau_examen.examiner(conn, jid, j)
        return await asyncio.to_thread(examen_reel)
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
async def lister_situations(acteur: str = Depends(auth_identite.acteur), x_espace: Optional[str] = Header(None)):
    _, espace = resoudre_perimetre(acteur, x_espace)
    tous = await db.jumeaux.find({}, {"_id": 0, "id": 1, "nom": 1}).to_list(200)
    aut = autorisations(espace, [j["id"] for j in tous])
    nom_vers_id = {j["nom"]: j["id"] for j in tous}
    docs = await db.situations.find({}, NO_ID).to_list(200)
    out = [f for f in (filtre_situation(d, aut, nom_vers_id) for d in docs) if f]
    out.sort(key=lambda s: s.get("score", 0), reverse=True)
    return out


@api_router.get("/situations/{sid}")
async def obtenir_situation(sid: str, acteur: str = Depends(auth_identite.acteur), x_espace: Optional[str] = Header(None)):
    _, espace = resoudre_perimetre(acteur, x_espace)
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


async def situation_dans_perimetre(sid: str, espace: dict):
    """La situation existe et **tous** ses jumeaux sont autorisés dans l'espace actif (écriture).

    La lecture peut montrer une situation partiellement visible ; décider ou agir engage tous ses jumeaux, donc un
    périmètre partiel ne suffit pas."""
    doc = await db.situations.find_one({"id": sid}, NO_ID)
    if not doc:
        raise HTTPException(404, "Situation introuvable")
    tous = await db.jumeaux.find({}, {"_id": 0, "id": 1}).to_list(200)
    aut = autorisations(espace, [j["id"] for j in tous])
    jumeaux = doc.get("jumeaux") or []
    if not jumeaux or not all(j in aut for j in jumeaux):
        raise HTTPException(403, "Cette situation est hors de votre périmètre")
    return doc


class ActionSituation(BaseModel):
    action: str


@api_router.post("/situations/{sid}/action")
async def agir_situation(sid: str, payload: ActionSituation, acteur: str = Depends(auth_identite.acteur),
                         x_espace: Optional[str] = Header(None)):
    _, espace = resoudre_perimetre(acteur, x_espace)
    await situation_dans_perimetre(sid, espace)
    mapping = {"ignorer": "ignorée", "surveiller": "surveillée", "investiguer": "en investigation", "examiner": None, "coincidence": "classée", "observer": "en observation", "qualifier": "qualifiée"}
    if payload.action not in mapping:
        raise HTTPException(400, "Action inconnue")
    nouveau = mapping[payload.action]
    if nouveau is not None:
        res = await db.situations.update_one({"id": sid}, {"$set": {"statut": nouveau}})
        if res.matched_count == 0:
            raise HTTPException(404, "Situation introuvable")
    await journaler(acteur, espace["id"], f"situation : {payload.action}", sid, "")
    return {"ok": True, "statut": nouveau}


class DecisionSituation(BaseModel):
    decision: str


@api_router.post("/situations/{sid}/decision")
async def decider_situation(sid: str, payload: DecisionSituation, acteur: str = Depends(auth_identite.acteur), x_espace: Optional[str] = Header(None)):
    _, espace = resoudre_perimetre(acteur, x_espace)
    await situation_dans_perimetre(sid, espace)
    res = await db.situations.update_one(
        {"id": sid},
        {"$set": {"statut": "décidée", "decision": payload.decision, "decidee_le": datetime.now(timezone.utc).isoformat()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Situation introuvable")
    await journaler(acteur, espace["id"], "décision", sid, payload.decision)
    return {"ok": True, "decision": payload.decision}


# ---------- Relations (mémoire du Mesh) ----------

@api_router.post("/relations/{rid}/confirmer")
async def confirmer_relation(rid: str, acteur: str = Depends(auth_identite.acteur), x_espace: Optional[str] = Header(None)):
    _, espace = resoudre_perimetre(acteur, x_espace)
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
    await journaler(acteur, espace["id"], "confirmation d'une relation", rid, f"{rel['source']} → {rel['cible']}")
    await marquer_cases_a_revoir([rel["source"], rel["cible"]], f"la relation {rel['source']} → {rel['cible']} a été confirmée")
    return {"ok": True, "etat": "confirmee", "memoire": "enrichie"}


# ---------- Décisions ----------

@api_router.get("/decisions")
async def lister_decisions(acteur: str = Depends(auth_identite.acteur), x_espace: Optional[str] = Header(None)):
    _, espace = resoudre_perimetre(acteur, x_espace)
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


MOTS_PROJETS = ["projet", "chantier", "jira", "trajectoire", "epic", "roadmap", "feuille de route", "echeance", "ticket", "livraison", "planifi"]


def reponse_projets(twins: list, aut: dict, id_vers_nom: dict):
    """Ce que les jumeaux savent des chantiers (Jira) : ce qui est bloqué d'abord, puis les prochaines échéances. Les jumeaux hors droits n'apparaissent pas."""
    vus, epics = set(), []
    for t in twins:
        for p in t.get("projets", []):
            if p["ref"] not in vus and p.get("statut") != "termine":
                vus.add(p["ref"])
                epics.append(p)
    if not epics:
        return {"comportement": "expliquer", "reponse": "Aucun chantier Jira n'est connu pour ces jumeaux : leur source de gestion de projet n'est pas branchée, ou rien n'est en cours.",
                "contributions": [], "preuves": [], "indicateurs": {"confiance": 70, "couverture": 50, "fraicheur": "à l'instant", "contradictions": 0}}
    bloques = [p for p in epics if p["statut"] == "bloque" or p["tickets"]["bloques"]]
    epics.sort(key=lambda p: p.get("echeance") or "9999")
    bloques.sort(key=lambda p: (p["statut"] != "bloque", p.get("echeance") or "9999"))

    def ligne(p):
        touche = [id_vers_nom.get(i, i) for i in p.get("impacte", []) if i in aut]
        porteur = id_vers_nom.get(p["porteur"], p["porteur"]) if p["porteur"] in aut else "un jumeau hors de votre périmètre"
        return f"{p['ref']} « {p['titre']} » (porté par {porteur}, échéance {p['echeance']}{', touche ' + ', '.join(touche) if touche else ''})"
    txt = f"{len(epics)} chantier(s) Jira vivant(s) concernent ces jumeaux"
    txt += f", dont {len(bloques)} avec des tickets bloqués : " + " ; ".join(ligne(p) for p in bloques[:3]) + "." if bloques else "."
    prochains = [p for p in epics if p not in bloques][:2]
    if prochains:
        txt += " Prochaines échéances : " + " ; ".join(ligne(p) for p in prochains) + "."
    txt += " Méridian ne garde pas le détail des tickets : il reste dans Jira."
    return {
        "comportement": "expliquer", "reponse": txt, "contributions": [],
        "preuves": [{"source": "Jira", "detail": f"{p['ref']} : {p['statut'].replace('_', ' ')}, {p['tickets']['ouverts']} ticket(s) ouvert(s), {p['tickets']['bloques']} bloqué(s)"} for p in epics[:5]],
        "indicateurs": {"confiance": 80, "couverture": 70, "fraicheur": "à l'instant", "contradictions": 0},
        "action": {"route": "/atlas", "label": "Voir dans l'Atlas"},
    }


def intention_selection(q: str):
    if any(k in q for k in MOTS_PROJETS):
        return "projets"
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


def preuves_relations(rels, id_vers_nom):
    # Preuves cliquables reliées à la carte : relation_id permet de centrer et illuminer le trajet
    return [
        {
            "source": r.get("source_decouverte") or "Mesh",
            "detail": f"{id_vers_nom.get(r['source'], r['source'])} → {id_vers_nom.get(r['cible'], r['cible'])} — {ETAT_REL_LABELS.get(r['etat'], 'confirmée')}",
            "relation_id": r["id"],
            "confiance": r.get("confiance"),
            "quand": r.get("decouverte_quand"),
        }
        for r in rels[:4]
    ]


async def reponse_selection(intent, sel, aut, tous, id_vers_nom):
    par_id = {j["id"]: j for j in tous}
    noms = [par_id[j]["nom"] for j in sel if j in par_id]
    internes, externes = await liens_selection(sel, aut)
    sset = set(sel)

    def nom_rel(r):
        return id_vers_nom.get(r["source"], r["source"]) + " → " + id_vers_nom.get(r["cible"], r["cible"])

    indicateurs = {"confiance": 72, "couverture": 64, "fraicheur": "à l'instant", "contradictions": len([r for r in internes if r["etat"] == "contestee"])}

    if intent == "projets":
        return reponse_projets([par_id[j] for j in sel if j in par_id], aut, id_vers_nom)

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
            "preuves": preuves_relations(internes, id_vers_nom),
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
            "contributions": [], "preuves": preuves_relations(non_conf, id_vers_nom) or [{"source": "Mesh", "detail": "Aucune relation douteuse autour de la sélection"}],
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
            "contributions": [], "preuves": preuves_relations(externes, id_vers_nom),
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
            "contributions": [], "preuves": preuves_relations(contest, id_vers_nom) or [{"source": "Mesh", "detail": "Santé des jumeaux et états des relations croisés"}],
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
    application_id: str = ""
    nom: str = ""
    proprietaire: str = ""


class CommandePatch(BaseModel):
    jumeau: Optional[dict] = None
    etape: Optional[int] = None
    sources: Optional[list] = None


class TestLot(BaseModel):
    ids: list


class ImportApercu(BaseModel):
    mode: str = "cmdb"
    contenu: str | list | dict | None = None


@api_router.get("/connecteurs")
async def lister_connecteurs():
    return {"connecteurs": [{**c, "branche": connecteur_branche(c["id"]) is not None} for c in CONNECTEURS],
            "contributions": CONTRIBUTIONS, "profils": PROFILS}


async def _connexions_commandes():
    docs = []
    for systeme in ("github", *SYSTEMES):
        async for c in _connexions(systeme).find({}, {"_id": 0, "id": 1, "reference": 1, "hote": 1}):
            docs.append(c)
    return docs


def _depot_commandes():
    return CommandesDepot(db.commandes, connexions=_connexions_commandes,
                          jumeaux=getattr(db, "jumeaux", None))


@api_router.post("/commandes", status_code=201)
async def creer_commande(payload: CommandeCreate, acteur: str = Depends(auth_identite.acteur), x_espace: Optional[str] = Header(None)):
    _, espace = resoudre_perimetre(acteur, x_espace)
    doc = await creer_commande_metier(
        _depot_commandes(),
        application_id=payload.application_id,
        nom=payload.nom,
        proprietaire=payload.proprietaire,
        acteur=acteur,
    )
    await journaler(acteur, espace["id"], "ouverture d'une commande", doc["id"], payload.nom)
    return doc


@api_router.get("/commandes")
async def lister_commandes():
    return await lister_commandes_metier(_depot_commandes())


@api_router.get("/commandes/{cid}")
async def lire_commande(cid: str):
    try:
        return await lire_commande_metier(_depot_commandes(), cid)
    except CommandeIntrouvable as exc:
        raise HTTPException(404, "Commande introuvable") from exc


@api_router.patch("/commandes/{cid}")
async def maj_commande(cid: str, payload: CommandePatch):
    patch = {k: v for k, v in payload.model_dump().items() if v is not None}
    try:
        return await maj_commande_metier(
            _depot_commandes(), cid, patch,
            prefixes=PREFIXES_CONNEXION, systemes=SYSTEMES,
        )
    except CommandeIntrouvable as exc:
        raise HTTPException(404, "Commande introuvable") from exc
    except CommandeModifiee as exc:
        raise HTTPException(409, "Commande déjà lancée : elle n'est plus modifiable") from exc
    except EtapeInvalide as exc:
        raise HTTPException(422, str(exc)) from exc


PREFIXES_CONNEXION = {"github": "gh-", "cmdb": SYSTEMES["servicenow"].PREFIXE,
                      **{nom: m.PREFIXE for nom, m in SYSTEMES.items()}}


def _proteger_source(source, connexions, hotes=None):
    """Compatibilité : la règle vit dans l'application, le registre de connecteurs reste celui du serveur."""
    return _proteger_source_metier(source, connexions, hotes,
                                   prefixes=PREFIXES_CONNEXION, systemes=SYSTEMES)


connecteur_branche = jumeau_connecteurs.connecteur_branche


def _champ_rempli(valeur):
    return any(x.get("depot") for x in valeur if isinstance(x, dict)) if isinstance(valeur, list) else bool(valeur)


def _simuler_test(source):
    """Test de connexion déterministe (meridian/adapters/outbound/connectors/connecteurs.py) : seuls les connecteurs branchés peuvent être prêts."""
    return jumeau_connecteurs.test_simule(source, CONNECTEURS)


# Connexions GitHub de l'espace : déclarées une fois (jeton vérifié puis déposé dans Vault), choisies ensuite par
# chaque commande. ponytail: jeton personnel ; GitHub App (« Se connecter avec GitHub ») sur AWS (Architecture §10.5),
# et rattachement des connexions à un espace quand l'identité OIDC arrivera.
CONNEXION_VALIDE = re.compile(r"gh-[a-z0-9-]{1,39}")


async def _appel_service(service, appel, *args):
    try:
        return await asyncio.to_thread(appel, *args)
    except jumeau_github.TropDeDemandes as e:
        raise HTTPException(429, str(e))
    except jumeau_github.JetonRefuse:
        raise HTTPException(401, f"{service} refuse ces identifiants : vérifiez-les ou leurs droits de lecture")
    except jumeau_github.Invalide as e:
        raise HTTPException(400, str(e))
    except LookupError:
        raise HTTPException(404, f"Élément introuvable dans {service}")
    except (RuntimeError, ValueError) as e:  # message générique : une erreur bas niveau peut citer le jeton
        logger.warning("appel %s impossible (%s)", service, type(e).__name__)
        raise HTTPException(400, "Jeton introuvable ou illisible : déclarez à nouveau la connexion")
    except OSError:
        logger.warning("%s injoignable", service, exc_info=True)
        raise HTTPException(502, f"{service} ne répond pas")


async def _appel_github(appel, *args):
    return await _appel_service("GitHub", appel, *args)


async def _reference_connexion(cxid: str) -> str:
    doc = await db.connexions_github.find_one({"id": cxid}, {"_id": 0, "reference": 1})
    if not doc:
        raise HTTPException(404, "Connexion GitHub introuvable")
    return doc["reference"]


class JetonGithub(BaseModel):
    jeton: str = Field(min_length=1, max_length=500)


@api_router.get("/connexions/github")
async def lister_connexions_github():
    return await db.connexions_github.find({}, {"_id": 0, "reference": 0}).sort("login", 1).to_list(100)


@api_router.post("/connexions/github", status_code=201)
async def declarer_connexion_github(payload: JetonGithub):
    """Le jeton est vérifié auprès de GitHub avant d'être conservé : un jeton refusé n'écrase rien."""
    jeton = payload.jeton.strip()
    compte = await _appel_github(jumeau_github.compte_du_jeton, jeton)
    cxid = f"gh-{compte['login'].lower()}"
    if not CONNEXION_VALIDE.fullmatch(cxid):
        raise HTTPException(400, "Compte GitHub inattendu")
    try:
        reference = await asyncio.to_thread(jumeau_naissance.deposer_jeton, f"connexions/github/{cxid}", jeton)
    except (RuntimeError, OSError) as e:
        logger.warning("connexion %s : jeton non déposé dans Vault (%s)", cxid, type(e).__name__)
        raise HTTPException(503, "Coffre de secrets indisponible : jeton non enregistré")
    jumeau_github.oublier(reference)
    doc = {"id": cxid, **compte, "maj_le": datetime.now(timezone.utc).isoformat()}
    await db.connexions_github.update_one({"id": cxid}, {"$set": {**doc, "reference": reference}}, upsert=True)
    return doc


@api_router.get("/connexions/github/{cxid}/depots")
async def depots_github(cxid: str, q: str = Query("", max_length=100)):
    return await _appel_github(jumeau_github.depots, await _reference_connexion(cxid), q)


@api_router.get("/connexions/github/{cxid}/branches")
async def branches_github(cxid: str, depot: str = Query(..., max_length=200), q: str = Query("", max_length=100)):
    return await _appel_github(jumeau_github.branches, await _reference_connexion(cxid), depot, q)


# Connexions « e-mail + jeton d'API » (Confluence, Jira…) : même principe que GitHub, une collection par système
# (registre meridian/adapters/outbound/connectors/systemes.py ; GitHub garde ses routes : jeton seul, dépôts et branches).
def _systeme(systeme: str):
    if systeme not in SYSTEMES:
        raise HTTPException(404, "Système inconnu")
    return SYSTEMES[systeme]


def _connexions(systeme: str):
    return db[f"connexions_{systeme}"]


async def _reference_connexion_de(systeme: str, cxid: str) -> dict:
    """Référence du jeton et adresse du site de la connexion (absente d'une ancienne connexion)."""
    doc = await _connexions(systeme).find_one({"id": cxid}, {"_id": 0, "reference": 1, "hote": 1})
    if not doc:
        raise HTTPException(404, f"Connexion {_systeme(systeme).SERVICE} introuvable")
    return doc


class JetonAtlassian(BaseModel):  # aussi les deux clés de Datadog (`email` = clé d'API, `jeton` = clé d'application)
    hote: Optional[str] = Field(None, max_length=300)  # adresse du site ; absente : JUMEAU_<SYSTÈME>_HOTE
    email: str = Field(min_length=3, max_length=200)
    jeton: str = Field(min_length=1, max_length=500)


@api_router.get("/connexions/{systeme}")
async def lister_connexions(systeme: str):
    _systeme(systeme)
    return await _connexions(systeme).find({}, {"_id": 0, "reference": 0}).sort("login", 1).to_list(100)


@api_router.post("/connexions/{systeme}", status_code=201)
async def declarer_connexion(systeme: str, payload: JetonAtlassian):
    """Les identifiants sont vérifiés auprès du service avant d'être conservés : un refus n'écrase rien."""
    module = _systeme(systeme)
    try:
        secret = module.identifiants(payload.email, payload.jeton)
        hote = module.hote_autorise(payload.hote)
    except jumeau_github.Invalide as e:
        raise HTTPException(400, str(e))
    try:
        compte = await _appel_service(module.SERVICE, module.compte_du_jeton, secret, hote)
    except HTTPException as e:
        if e.status_code != 404:
            raise
        # À la déclaration, « introuvable » veut dire : aucun site de ce service à cette adresse.
        raise HTTPException(404, f"Aucun site {module.SERVICE} à l'adresse {hote or 'configurée'} : vérifiez-la")
    login = compte["login"].lower()
    # Identifiant tiré du compte du service (accountId) : un autre jeton ne peut pas écraser cette connexion.
    cxid = f"{module.PREFIXE}{re.sub(r'[^a-z0-9]+', '-', login).strip('-')[:30]}-{hashlib.sha256(compte['compte'].encode()).hexdigest()[:8]}"
    if not re.fullmatch(rf"{module.PREFIXE}[a-z0-9-]{{1,50}}", cxid):
        raise HTTPException(400, "Adresse e-mail inattendue")
    try:
        reference = await asyncio.to_thread(jumeau_naissance.deposer_jeton, f"connexions/{systeme}/{cxid}", secret)
    except (RuntimeError, OSError) as e:
        logger.warning("connexion %s : jeton non déposé dans Vault (%s)", cxid, type(e).__name__)
        raise HTTPException(503, "Coffre de secrets indisponible : jeton non enregistré")
    jumeau_github.oublier(reference)
    doc = {"id": cxid, **compte, "hote": hote, "maj_le": datetime.now(timezone.utc).isoformat()}
    await _connexions(systeme).update_one({"id": cxid}, {"$set": {**doc, "reference": reference}}, upsert=True)
    return doc


@api_router.get("/connexions/{systeme}/{cxid}/perimetres")
async def perimetres_connexion(systeme: str, cxid: str, q: str = Query("", max_length=100)):
    module = _systeme(systeme)
    connexion = await _reference_connexion_de(systeme, cxid)
    return await _appel_service(module.SERVICE, module.perimetres, connexion["reference"], q, connexion.get("hote"))


async def _tester_source(source):
    # GitHub (git ls-remote) et systèmes branchés (API) : test réel avec le jeton résolu depuis Vault ; autres connecteurs : simulés
    testeurs = {"github": jumeau_naissance.tester_git, "cmdb": SYSTEMES["servicenow"].tester,
                **{nom: m.tester for nom, m in SYSTEMES.items()}}
    if source["connecteur"] in testeurs:
        return await asyncio.to_thread(testeurs[source["connecteur"]], source.get("config", {}))
    return _simuler_test(source)


@api_router.post("/commandes/{cid}/tester")
async def tester_sources(cid: str, payload: TestLot, acteur: str = Depends(auth_identite.acteur), x_espace: Optional[str] = Header(None)):
    _, espace = resoudre_perimetre(acteur, x_espace)
    try:
        resultats, modifie = await tester_sources_metier(
            _depot_commandes(), cid, payload.ids, tester=_tester_source,
        )
    except CommandeIntrouvable as exc:
        raise HTTPException(404, "Commande introuvable") from exc
    except CommandeModifiee as exc:
        raise HTTPException(409, "Commande déjà lancée : elle n'est plus modifiable") from exc
    if modifie:
        await journaler(acteur, espace["id"], "test de connexions", cid, f"{len(resultats)} source(s) testée(s)")
    return {"resultats": resultats}


@api_router.post("/commandes/{cid}/import/apercu")
async def apercu_import(cid: str, payload: ImportApercu):
    try:
        return await apercu_commande(
            _depot_commandes(), cid, payload.mode, payload.contenu,
            connus=[c["id"] for c in CONNECTEURS if connecteur_branche(c["id"])],
        )
    except CommandeIntrouvable as exc:
        raise HTTPException(404, "Commande introuvable") from exc
    except CommandeModifiee as exc:
        raise HTTPException(409, "Commande déjà lancée : elle n'est plus modifiable") from exc
    except ImportIdentiteInvalide as exc:
        raise HTTPException(400, str(exc)) from exc


# Le lancement crée le jumeau, met à jour la commande et démarre la tâche de naissance : la règle vit dans
# l'application, le runtime local (tâches, notifications, journal) reste un adapter.
@api_router.post("/commandes/{cid}/lancer")
async def lancer_commande(cid: str, acteur: str = Depends(auth_identite.acteur), x_espace: Optional[str] = Header(None)):
    _, espace = resoudre_perimetre(acteur, x_espace)
    store = _depot_commandes()
    runtime = NaissanceRuntimeLocal(db, store, notifier=notifier, journaler=journaler)
    try:
        resultat = await lancer_commande_metier(
            store, runtime, cid,
            acteur=acteur, espace_id=espace["id"],
            connecteur_branche=connecteur_branche,
        )
    except CommandeIntrouvable as exc:
        raise HTTPException(404, "Commande introuvable") from exc
    except JumeauExistant as exc:
        raise HTTPException(409, str(exc)) from exc
    except NaissanceIndisponible as exc:
        raise HTTPException(503, str(exc)) from exc
    except LancementRefuse as exc:
        raise HTTPException(422, str(exc)) from exc
    if not resultat.get("deja") and isinstance(espace.get("jumeaux"), dict) and "*" not in espace["jumeaux"]:
        espace["jumeaux"][resultat["jumeau_id"]] = "complet"
    return resultat


@api_router.get("/commandes/{cid}/naissance")
async def suivre_naissance(cid: str):
    try:
        return await suivre_naissance_metier(CommandesDepot(db.commandes), cid)
    except CommandeIntrouvable as exc:
        raise HTTPException(404, "Commande introuvable") from exc


# D'où vient une réponse de Flore (plan de remédiation L0.5) : une réponse de démonstration ne se présente jamais
# comme une réponse calculée, et les indicateurs écrits d'avance ne sont pas affichés comme des mesures.
marquer_origine = jumeau_origine.marquer_origine


def _poser_resolution(reponse, resolution):
    """La trace de résolution et son préambule accompagnent la réponse, même en cas d'ambiguïté ou d'absence."""
    if isinstance(reponse, dict) and resolution is not None:
        reponse["resolution"] = resolution.as_dict()
        preambule = resolution.preambule()
        if preambule and preambule not in str(reponse.get("reponse") or ""):
            reponse["reponse"] = f"{preambule}\n\n{reponse.get('reponse') or ''}".strip()
    return reponse


def enregistrer_lignes(dsn, tenant_id, acteur, lignes):
    """Pont testable vers l'audit persistant : une seule fonction, jamais d'exception vers l'appelant."""
    return jumeau_audit_harness.enregistrer_lignes(dsn, tenant_id, acteur, lignes)


def _persister_audit_orchestration(reponse, acteur, tenant=None):
    """Après un tour de l'orchestrateur, écrit son audit en arrière-plan ; ne bloque ni ne casse la réponse."""
    if not isinstance(reponse, dict):
        return
    orchestration = reponse.get("orchestration")
    if not isinstance(orchestration, dict):
        return
    lignes = orchestration.get("audit")
    if not isinstance(lignes, list) or not lignes:
        return
    dsn = os.environ.get("JUMEAU_PG_DSN")
    if not dsn:
        return
    tenant_id = str(tenant or os.environ.get("JUMEAU_TENANT") or "local").strip()[:128] or "local"
    acteur = str(acteur or "demo")
    instantane = [dict(ligne) for ligne in lignes if isinstance(ligne, dict)]
    if not instantane:
        return

    def ecrire():
        try:
            enregistrer_lignes(dsn, tenant_id, acteur, instantane)
        except Exception:
            logger.debug("audit orchestrateur non persisté")

    try:
        threading.Thread(target=ecrire, name="audit-orchestrateur", daemon=True).start()
    except Exception:
        logger.debug("audit orchestrateur non planifié")


async def generer_reponse_flore(contexte, question, selection, domaine, acteur, x_espace, travail=None, emit=None, *, tenant=None):
    if not await limites.autoriser(f"tours:{acteur}", limites.maxi_tours(), limites.fenetre_tours()):
        raise HTTPException(429, "Trop de tours Flore en peu de temps ; réessayez dans un instant")
    _, espace = resoudre_perimetre(acteur, x_espace)
    tous = await db.jumeaux.find({}, NO_ID).to_list(200)
    aut = autorisations(espace, [j["id"] for j in tous])
    id_vers_nom = {j["id"]: j["nom"] for j in tous}
    q = normalise_txt(question)
    for j in tous:
        if j["id"] not in aut and len(j["nom"]) > 4 and normalise_txt(j["nom"]) in q:
            return marquer_origine(dict(HORS_PERIMETRE), "refus")
    sel = [j for j in (selection or []) if j in aut and niveau_au_moins(aut[j], "resume")]
    # Un seul agent général décide : résoudre/mobiliser une app existante, concevoir une app absente, ou répondre.
    # Aucun routeur d'intention hardcodé n'est consulté ici.
    candidats = [j for j in tous if j.get("reel") and j["id"] in aut and niveau_au_moins(aut[j["id"]], "complet")]

    async def mobiliser_orchestre(ids, mission):
        ids = [i for i in ids if i in aut and i in {j["id"] for j in candidats}]
        if not ids:
            return None
        if len(ids) == 1:
            return await jumeau_flore.repondre(ids[0], mission, acteur, travail, profil=None, db=db, emit=emit)
        return await jumeau_flore.mobiliser(ids, mission, acteur, travail, profil=None, db=db, emit=emit)

    async def concevoir_orchestre(question_conception):
        return await jumeau_conception.repondre(question_conception, {"type": "concevoir", "greenfield": True})

    if not sel:
        reponse_orchestree = await jumeau_orchestrateur.executer(
            question, jumeaux=candidats, selection=sel, mobiliser=mobiliser_orchestre,
            concevoir=concevoir_orchestre)
        if reponse_orchestree:
            _persister_audit_orchestration(reponse_orchestree, acteur, tenant)
            return marquer_origine(reponse_orchestree, "modele")
        return marquer_origine({
            "comportement": "signaler",
            "reponse": "Je n'ai pas pu interpréter et traiter cette demande : l'orchestrateur général est "
                       "indisponible. Aucun jumeau n'a été mobilisé et aucune conclusion n'est tirée.",
            "preuves": [], "contributions": [], "jumeaux_participants": [],
            "orchestration": {"outils": [], "erreurs": ["orchestrateur indisponible"]},
        }, "repli")
    # Sélection explicite : le chemin direct reste borné aux applications choisies.
    reels = [j["id"] for j in tous if j.get("reel") and j["id"] in sel and niveau_au_moins(aut[j["id"]], "complet")]
    resolution = None
    if reels:
        if len(reels) == 1:
            reponse_jumeau = await jumeau_flore.repondre(reels[0], question, acteur, travail, profil=None, db=db, emit=emit)
        else:
            reponse_jumeau = await jumeau_flore.mobiliser(reels, question, acteur, travail, profil=None, db=db, emit=emit)
        if reponse_jumeau:
            return marquer_origine(_poser_resolution(reponse_jumeau, resolution), "modele")
    if sel:
        intent = intention_selection(q)
        if intent:
            return marquer_origine(await reponse_selection(intent, sel, aut, tous, id_vers_nom), "scenario")
        return marquer_origine(await reponse_selection(None, sel, aut, tous, id_vers_nom), "scenario")
    return marquer_origine(_poser_resolution(dict(AURORA_FALLBACK), resolution), "repli")


def _jumeau_visible(jid, aut):
    return jid in aut and niveau_au_moins(aut[jid], "preuves")


@api_router.get("/jumeaux/{jid}/interfaces")
async def interfaces_du_jumeau(jid: str, acteur: str = Depends(auth_identite.acteur),
                               x_espace: Optional[str] = Header(None)):
    """Le graphe d'interfaces persisté et les derniers DiscoveryRun d'un jumeau visible."""
    _, espace = resoudre_perimetre(acteur, x_espace)
    tous = await db.jumeaux.find({}, {"_id": 0, "id": 1}).to_list(200)
    aut = autorisations(espace, [j["id"] for j in tous])
    if not _jumeau_visible(jid, aut):
        raise HTTPException(404, "Jumeau introuvable")
    dsn = os.environ.get("JUMEAU_PG_DSN")
    if not dsn:
        raise HTTPException(503, "Couche cognitive non configurée (JUMEAU_PG_DSN)")

    def lire():
        with psycopg.connect(dsn) as conn:
            jumeau = jumeau_depot.jumeau_par_id(conn, jid)
            if not jumeau:
                return None
            tenant = jumeau["tenant_id"]
            return {"jumeau_id": jid, "application_id": jid, "tenant": tenant,
                    "interfaces": jumeau_interfaces_depot.lire(conn, tenant, jid),
                    "runs": jumeau_interfaces_depot.derniers_runs(conn, tenant, jid),
                    "sources": jumeau_pulls_runtime.etat_sources(conn, jid)}

    resultat = await asyncio.to_thread(lire)
    if resultat is None:
        raise HTTPException(404, "Jumeau introuvable")
    return resultat


@api_router.post("/jumeaux/{jid}/interfaces/decouvrir")
async def decouvrir_interfaces_du_jumeau(jid: str, acteur: str = Depends(auth_identite.acteur),
                                         x_espace: Optional[str] = Header(None)):
    """Déclenche un DiscoveryRun à partir des claims EXPOSE du jumeau (lecture seule sur les sources)."""
    _, espace = resoudre_perimetre(acteur, x_espace)
    tous = await db.jumeaux.find({}, {"_id": 0, "id": 1}).to_list(200)
    aut = autorisations(espace, [j["id"] for j in tous])
    if not _jumeau_visible(jid, aut):
        raise HTTPException(404, "Jumeau introuvable")
    dsn = os.environ.get("JUMEAU_PG_DSN")
    if not dsn:
        raise HTTPException(503, "Couche cognitive non configurée (JUMEAU_PG_DSN)")

    def executer():
        with psycopg.connect(dsn) as conn:
            jumeau = jumeau_depot.jumeau_par_id(conn, jid)
            if not jumeau:
                return None
            claims = jumeau_connaissance.connaissances(conn, jid, limite=1000)
            return jumeau_decouverte_interfaces.executer(
                conn, jumeau["tenant_id"], jid, claims=claims, environment="production", source="api")

    resultat = await asyncio.to_thread(executer)
    if resultat is None:
        raise HTTPException(404, "Jumeau introuvable")
    return resultat


@api_router.post("/aurora/demander")
async def aurora_demander(payload: AuroraDemande, acteur: str = Depends(auth_identite.acteur), x_espace: Optional[str] = Header(None),
                          x_tenant: Optional[str] = Header(None)):
    return await generer_reponse_flore(payload.contexte, payload.question, payload.selection, payload.domaine, acteur, x_espace,
                                       tenant=x_tenant)


@api_router.post("/aurora/demander/flux")
async def aurora_demander_flux(payload: AuroraDemande, acteur: str = Depends(auth_identite.acteur), x_espace: Optional[str] = Header(None),
                               x_tenant: Optional[str] = Header(None)):
    """La même réponse, au fil de l'eau : étapes réelles, brouillon en relecture, puis la réponse relue (meridian/adapters/inbound/http/flux.py)."""
    return jumeau_flux.en_flux(lambda emit: generer_reponse_flore(
        payload.contexte, payload.question, payload.selection, payload.domaine, acteur, x_espace, emit=emit, tenant=x_tenant),
        proprietaire=acteur)


@api_router.get("/preuves/extrait")
async def extrait_preuve(locator: str = Query(..., max_length=500), acteur: str = Depends(auth_identite.acteur),
                         x_espace: Optional[str] = Header(None)):
    """L'extrait d'une preuve citée par Flore (pastille, panneau de preuve) : les lignes citées au commit, avec leur
    contexte. Réservé à qui voit les preuves de ce jumeau ; sinon 404, sans dire que le code existe."""
    from meridian.adapters.inbound.http.interfaces import extrait_preuve as lire
    dsn = os.environ.get("JUMEAU_PG_DSN")
    if not dsn:
        raise HTTPException(503, "Couche cognitive non configurée (JUMEAU_PG_DSN)")
    _, espace = resoudre_perimetre(acteur, x_espace)

    def chercher():
        with psycopg.connect(dsn, autocommit=True) as conn:
            return lire(conn, locator)
    jid, extrait = await asyncio.to_thread(chercher)
    niveau = autorisations(espace, [jid]).get(jid) if jid else None
    if not jid or not niveau or not niveau_au_moins(niveau, "preuves"):
        raise HTTPException(404, "Preuve introuvable")
    return {"jumeau": jid, **extrait}


@api_router.get("/aurora/suggestions")
async def aurora_suggestions(contexte: str = "global", acteur: str = Depends(auth_identite.acteur), x_espace: Optional[str] = Header(None)):
    _, espace = resoudre_perimetre(acteur, x_espace)
    tous = await db.jumeaux.find({}, {"_id": 0, "id": 1, "nom": 1}).to_list(200)
    aut = autorisations(espace, [j["id"] for j in tous])
    sugs = AURORA_SUGGESTIONS.get(contexte, AURORA_SUGGESTIONS["global"])
    return [
        s for s in sugs
        if not any(j["id"] not in aut and len(j["nom"]) > 4 and j["nom"].lower() in s.lower() for j in tous)
    ]


def _chemins_manifestes():
    valeur = os.environ.get("JUMEAU_MANIFESTES")
    if not valeur:
        return []
    return [morceau.strip() for morceau in str(valeur).replace(os.pathsep, "\n").splitlines() if morceau.strip()]


def _specifications_env(nom):
    """Spécifications OpenAPI/MCP déclarées en JSON : [{application, path, version?, tenant?}]."""
    valeur = os.environ.get(nom)
    if not valeur:
        return []
    try:
        charge = json.loads(valeur)
    except ValueError:
        logger.warning("catalogue d'outils : %s n'est pas un JSON valide", nom)
        return []
    if isinstance(charge, dict):
        charge = [charge]
    return [entree for entree in charge if isinstance(entree, dict)] if isinstance(charge, list) else []


def _ingerer_specifications(registre):
    for entree in _specifications_env("JUMEAU_OPENAPI"):
        try:
            rapport = jumeau_ingestion_outils.ingerer_openapi(registre, [entree])
            if rapport["erreurs"]:
                logger.warning("catalogue d'outils : OpenAPI ignoré (%s)", rapport["erreurs"][0]["application"])
        except Exception:
            logger.warning("catalogue d'outils : spécification OpenAPI ignorée")
    for entree in _specifications_env("JUMEAU_MCP_OUTILS"):
        try:
            rapport = jumeau_ingestion_outils.ingerer_mcp(registre, [entree])
            if rapport["erreurs"]:
                logger.warning("catalogue d'outils : MCP ignoré (%s)", rapport["erreurs"][0]["application"])
        except Exception:
            logger.warning("catalogue d'outils : descripteurs MCP ignorés")
    for nom_env, fonction in (
        ("JUMEAU_INTERFACES", jumeau_ingestion_outils.ingerer_interface),
        ("JUMEAU_PROTOCOLES", jumeau_ingestion_outils.ingerer_protocoles),
    ):
        for entree in _specifications_env(nom_env):
            try:
                rapport = fonction(registre, [entree])
                if rapport["erreurs"]:
                    logger.warning("catalogue d'outils : %s ignoré (%s)", nom_env,
                                   rapport["erreurs"][0]["application"])
            except Exception:
                logger.warning("catalogue d'outils : %s ignoré", nom_env)


def _ingerer_interfaces_postgres(registre, tenant_id, acteur_id, perimetre_id):
    """Ajoute les opérations d'interface déjà découvertes, sans écraser un manifeste plus précis."""
    dsn = os.environ.get("JUMEAU_PG_DSN")
    if not dsn:
        return
    try:
        with psycopg.connect(dsn, connect_timeout=3) as conn:
            if jumeau_rls.est_actif():
                with jumeau_rls.contexte_tenant(conn, tenant_id):
                    graphe = jumeau_interfaces_depot.lire_graph(conn, tenant_id)
            else:
                graphe = jumeau_interfaces_depot.lire_graph(conn, tenant_id)
        for manifeste in jumeau_interface_outils.manifests_depuis_interface(
            graphe, tenant=tenant_id, acteur=acteur_id, perimetre=perimetre_id
        ):
            if registre.decrire(manifeste.nom) is None:
                registre.enregistrer(manifeste)
    except Exception:
        logger.warning("catalogue d'outils : opérations d'interface ignorées")


def _catalogue_outils(tenant_id, acteur_id, perimetre_id):
    """Manifestes intégrés, fichiers, protocoles et opérations d'interface connues ; aucune exécution."""
    registre = jumeau_capacites.RegistreCapacites(jumeau_capacites.manifestes_integres())
    for chemin in _chemins_manifestes():
        try:
            jumeau_chargeur_manifestes.charger(registre, chemin)
        except Exception:
            logger.warning("catalogue d'outils : manifeste externe ignoré")
    _ingerer_specifications(registre)
    _ingerer_interfaces_postgres(registre, tenant_id, acteur_id, perimetre_id)
    return [
        jumeau_harness.expurger(manifeste.as_dict())
        for manifeste in registre.lister(tenant=tenant_id, acteur=acteur_id, perimetre=perimetre_id)
    ]


@api_router.get("/outils")
async def lister_outils(
    tenant: Optional[str] = Query(None, max_length=128),
    perimetre: Optional[str] = Query(None, max_length=96),
    acteur: str = Depends(auth_identite.acteur),
    x_espace: Optional[str] = Header(None, max_length=96),
    x_tenant: Optional[str] = Header(None, max_length=128),
):
    """Catalogue read-only des outils visibles : manifestes intégrés et fichiers JUMEAU_MANIFESTES."""
    brut_tenant = tenant if tenant is not None else x_tenant
    if brut_tenant is None:
        tenant_id = os.environ.get("JUMEAU_TENANT") or "local"
    else:
        tenant_id = str(brut_tenant).strip()
        if not tenant_id:
            raise HTTPException(400, "Tenant ne peut pas être vide")
    acteur_id = str(acteur or "").strip()
    if not acteur_id:
        raise HTTPException(400, "Acteur ne peut pas être vide")
    _, espace = resoudre_perimetre(acteur_id, x_espace)
    perimetre_id = str(perimetre if perimetre is not None else espace["id"]).strip()
    if not perimetre_id:
        raise HTTPException(400, "Périmètre ne peut pas être vide")
    return {
        "tenant": jumeau_harness.expurger(tenant_id),
        "acteur": jumeau_harness.expurger(acteur_id),
        "perimetre": jumeau_harness.expurger(perimetre_id),
        "outils": _catalogue_outils(tenant_id, acteur_id, perimetre_id),
    }


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
    "slugify": slugify,
    "journaler": journaler,
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


# ---------- Vue bornée du Mesh (passage à l'échelle) ----------

api_router.include_router(build_mesh_vue_router({
    "db": db,
    "resoudre_perimetre": resoudre_perimetre,
    "autorisations": autorisations,
    "NO_ID": NO_ID,
}))

api_router.include_router(jumeau_router)
api_router.include_router(boucle_router)
api_router.include_router(construire_sources_router(resoudre_tenant=resoudre_tenant_boucle))
api_router.include_router(cognitif_router)
api_router.include_router(construire_runs_router(resoudre_tenant=resoudre_tenant_boucle))


# ---------- Notifications ----------

@api_router.get("/notifications")
async def lister_notifications():
    docs = await db.notifications.find({}, NO_ID).sort("quand", -1).to_list(30)
    return {"notifications": docs, "non_lues": sum(1 for d in docs if not d.get("lu"))}


@api_router.post("/notifications/{nid}/lue")
async def notification_lue(nid: str):
    await db.notifications.update_one({"id": nid}, {"$set": {"lu": True}})
    return {"ok": True}


@api_router.post("/notifications/tout-lire")
async def notifications_tout_lire():
    await db.notifications.update_many({}, {"$set": {"lu": True}})
    return {"ok": True}

# ---------- Activité ----------

@api_router.get("/activite")
async def activite(acteur: str = Depends(auth_identite.acteur), x_espace: Optional[str] = Header(None)):
    _, espace = resoudre_perimetre(acteur, x_espace)
    tous = await db.jumeaux.find({}, {"_id": 0, "id": 1}).to_list(200)
    aut = autorisations(espace, [j["id"] for j in tous])
    return []


app.include_router(api_router)

# Le corps de requête est borné par les octets réellement reçus : un Content-Length absent ou mensonger (envoi
# chunked) ne contourne pas la limite. La marge couvre l'enveloppe multipart d'une pièce au maximum autorisé.
# Ajouté avant CORS pour que CORS reste le middleware le plus externe (les en-têtes CORS accompagnent aussi un 413).
app.add_middleware(RequestBodyLimitMiddleware, max_body_size=pieces.MAX_OCTETS + 2 * 1024 * 1024)
# L'authentification passe par l'en-tête Authorization, jamais par un cookie : les credentials CORS sont donc
# désactivés. En production, un joker « * » est refusé au démarrage (voir demarrer_partage) : les origines
# autorisées doivent y être explicites.
app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origins=CORS_ORIGINES,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


def _fermer_flux_sur_arret():
    """Uvicorn attend les connexions avant son shutdown : on ferme les SSE dès le signal pour ne pas bloquer."""
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            precedent = signal.getsignal(sig)
        except (ValueError, OSError):
            continue
        if not callable(precedent):
            continue

        def gerer(signum, frame, precedent=precedent):
            jumeau_evenements.fermer()
            jumeau_flux.fermer_lecteurs()
            precedent(signum, frame)

        try:
            signal.signal(sig, gerer)
        except (ValueError, OSError):
            pass


@app.on_event("startup")
async def fermer_flux_sur_arret():
    _fermer_flux_sur_arret()


@app.on_event("shutdown")
async def shutdown_db_client():
    await jumeau_tours_redis.arreter_taches()
    await jumeau_flux.arreter_controle()
    jumeau_evenements.fermer()
    jumeau_flux.fermer_lecteurs()
    if jumeau_partage.actif():
        await jumeau_partage.publier_arret()
    await jumeau_partage.fermer()
    client.close()
