from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel


class CaseCreate(BaseModel):
    titre: str
    type: str = "demande"
    objectif: str = ""
    jumeaux: list = []
    situations: list = []
    participants: list = []
    responsable: Optional[str] = None
    espace: Optional[str] = None
    conversation: list = []


class CasePatch(BaseModel):
    statut: Optional[str] = None
    objectif: Optional[str] = None
    questions: Optional[list] = None
    jumeaux: Optional[list] = None
    situations: Optional[list] = None
    responsable: Optional[str] = None
    participants: Optional[list] = None
    a_revoir: Optional[bool] = None


class MessageCase(BaseModel):
    texte: str


class DecisionCase(BaseModel):
    texte: str
    type: str = "arbitrage"


class OptionCase(BaseModel):
    titre: str
    description: str = ""
    impacts: list = []
    risque: str = "moyen"


def build_cases_router(deps):
    db = deps["db"]
    resoudre_perimetre = deps["resoudre_perimetre"]
    autorisations = deps["autorisations"]
    journaler = deps["journaler"]
    notifier = deps["notifier"]
    generer_reponse_flore = deps["generer_reponse_flore"]
    slugify = deps["slugify"]
    NO_ID = deps["NO_ID"]
    datetime = deps["datetime"]
    timezone = deps["timezone"]

    router = APIRouter()

    async def charger_case(cid: str, espace: dict):
        case = await db.cases.find_one({"id": cid}, NO_ID)
        if not case:
            raise HTTPException(404, "Case introuvable")
        tous = await db.jumeaux.find({}, {"_id": 0, "id": 1}).to_list(200)
        aut = autorisations(espace, [j["id"] for j in tous])
        if case.get("jumeaux") and not any(j in aut for j in case["jumeaux"]):
            raise HTTPException(403, "Ce case est hors de votre périmètre")
        return case

    @router.get("/cases")
    async def lister_cases(x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
        _, espace = resoudre_perimetre(x_persona, x_espace)
        tous = await db.jumeaux.find({}, {"_id": 0, "id": 1}).to_list(200)
        aut = autorisations(espace, [j["id"] for j in tous])
        cases = await db.cases.find({}, NO_ID).to_list(200)
        visibles = [c for c in cases if not c.get("jumeaux") or any(j in aut for j in c["jumeaux"])]
        visibles.sort(key=lambda c: c.get("maj_le", ""), reverse=True)
        for c in visibles:
            c["nb_messages"] = len(c.get("conversation", []))
            c["nb_decisions"] = len(c.get("decisions", []))
            c["nb_options"] = len(c.get("options", []))
            c.pop("conversation", None)
            c.pop("historique", None)
        return visibles

    @router.post("/cases", status_code=201)
    async def creer_case(payload: CaseCreate, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
        _, espace = resoudre_perimetre(x_persona, x_espace)
        base = slugify(payload.titre) or "case"
        cid = base
        n = 2
        while await db.cases.find_one({"id": cid}):
            cid = f"{base}-{n}"
            n += 1
        now = datetime.now(timezone.utc).isoformat()
        responsable = payload.responsable or x_persona
        doc = {
            "id": cid,
            "titre": payload.titre.strip(),
            "type": payload.type,
            "statut": "ouvert",
            "objectif": payload.objectif,
            "questions": [],
            "jumeaux": payload.jumeaux,
            "situations": payload.situations,
            "participants": list({*payload.participants, x_persona, responsable}),
            "responsable": responsable,
            "espace": payload.espace or espace["id"],
            "conversation": payload.conversation,
            "options": [],
            "decisions": [],
            "livrables": [],
            "a_revoir": False,
            "historique": [{"quand": now, "texte": "Case créé"}],
            "cree_le": now,
            "maj_le": now,
        }
        await db.cases.insert_one(doc)
        if responsable != x_persona:
            await notifier([responsable], "assignation", f"Vous êtes responsable du case « {doc['titre']} »", f"/cases/{cid}")
        await journaler(x_persona, espace["id"], "création d'un case", cid, doc["titre"])
        doc.pop("_id", None)
        return doc

    @router.get("/cases/{cid}")
    async def obtenir_case(cid: str, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
        _, espace = resoudre_perimetre(x_persona, x_espace)
        return await charger_case(cid, espace)

    @router.patch("/cases/{cid}")
    async def maj_case(cid: str, payload: CasePatch, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
        _, espace = resoudre_perimetre(x_persona, x_espace)
        case = await charger_case(cid, espace)
        champs = {k: v for k, v in payload.model_dump().items() if v is not None}
        if not champs:
            return case
        now = datetime.now(timezone.utc).isoformat()
        histo = []
        if "statut" in champs and champs["statut"] != case.get("statut"):
            histo.append({"quand": now, "texte": f"Statut : {case.get('statut')} → {champs['statut']}"})
        if "objectif" in champs and champs["objectif"] != case.get("objectif"):
            histo.append({"quand": now, "texte": "Objectif mis à jour"})
        if "jumeaux" in champs and champs["jumeaux"] != case.get("jumeaux"):
            histo.append({"quand": now, "texte": "Contexte SI ajusté"})
        if "a_revoir" in champs and champs["a_revoir"] is False and case.get("a_revoir"):
            histo.append({"quand": now, "texte": "Revue effectuée — hypothèses confirmées à jour"})
        nouveau_resp = champs.get("responsable")
        if nouveau_resp and nouveau_resp != case.get("responsable"):
            histo.append({"quand": now, "texte": f"Responsable : {nouveau_resp}"})
            if nouveau_resp != x_persona:
                await notifier([nouveau_resp], "assignation", f"Vous êtes responsable du case « {case['titre']} »", f"/cases/{cid}")
        update = {"$set": {**champs, "maj_le": now}}
        if histo:
            update["$push"] = {"historique": {"$each": histo}}
        await db.cases.update_one({"id": cid}, update)
        return await db.cases.find_one({"id": cid}, NO_ID)

    @router.post("/cases/{cid}/messages", status_code=201)
    async def message_case(cid: str, payload: MessageCase, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
        _, espace = resoudre_perimetre(x_persona, x_espace)
        case = await charger_case(cid, espace)
        if not payload.texte.strip():
            raise HTTPException(400, "Message vide")
        now = datetime.now(timezone.utc).isoformat()
        msg_user = {"role": "utilisateur", "texte": payload.texte.strip(), "quand": now}
        rep = await generer_reponse_flore("case", payload.texte, case.get("jumeaux", []), None, x_persona, x_espace)
        msg_flore = {"role": "flore", "texte": rep.get("reponse", ""), "comportement": rep.get("comportement"), "quand": datetime.now(timezone.utc).isoformat()}
        await db.cases.update_one(
            {"id": cid},
            {
                "$push": {"conversation": {"$each": [msg_user, msg_flore]}, "historique": {"quand": now, "texte": "Échange avec Flore"}},
                "$set": {"maj_le": now},
            },
        )
        return {"utilisateur": msg_user, "flore": msg_flore, "reponse_complete": rep}

    @router.post("/cases/{cid}/decisions", status_code=201)
    async def decider_case(cid: str, payload: DecisionCase, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
        _, espace = resoudre_perimetre(x_persona, x_espace)
        await charger_case(cid, espace)
        if not payload.texte.strip():
            raise HTTPException(400, "Décision vide")
        now = datetime.now(timezone.utc).isoformat()
        dec = {"texte": payload.texte.strip(), "type": payload.type, "quand": now, "par": x_persona}
        await db.cases.update_one(
            {"id": cid},
            {"$push": {"decisions": dec, "historique": {"quand": now, "texte": f"Décision enregistrée — {payload.type}"}}, "$set": {"maj_le": now}},
        )
        await journaler(x_persona, espace["id"], "décision sur un case", cid, payload.texte.strip()[:120])
        return dec

    @router.post("/cases/{cid}/options", status_code=201)
    async def ajouter_option_case(cid: str, payload: OptionCase, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
        _, espace = resoudre_perimetre(x_persona, x_espace)
        case = await charger_case(cid, espace)
        if not payload.titre.strip():
            raise HTTPException(400, "Option sans titre")
        now = datetime.now(timezone.utc).isoformat()
        opt = {
            "id": f"opt-{len(case.get('options', [])) + 1}-{slugify(payload.titre)[:24]}",
            "titre": payload.titre.strip(),
            "description": payload.description,
            "impacts": payload.impacts,
            "risque": payload.risque,
            "statut": "a_evaluer",
        }
        await db.cases.update_one(
            {"id": cid},
            {"$push": {"options": opt, "historique": {"quand": now, "texte": f"Option ajoutée — {opt['titre']}"}}, "$set": {"maj_le": now}},
        )
        return opt

    @router.post("/cases/{cid}/livrables", status_code=201)
    async def produire_synthese_case(cid: str, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
        _, espace = resoudre_perimetre(x_persona, x_espace)
        case = await charger_case(cid, espace)
        now = datetime.now(timezone.utc).isoformat()
        questions = case.get("questions", [])
        resolues = [q for q in questions if q.get("resolue")]
        lignes = [
            f"Synthèse du Case « {case['titre']} »",
            f"Objectif : {case.get('objectif') or '—'}",
            f"Jumeaux mobilisés : {len(case.get('jumeaux', []))} · Questions : {len(resolues)}/{len(questions)} résolues · Options : {len(case.get('options', []))} · Décisions : {len(case.get('decisions', []))}",
        ]
        if case.get("decisions"):
            lignes.append("Décision retenue : " + case["decisions"][-1]["texte"])
        if case.get("options"):
            lignes.append("Options étudiées : " + " · ".join(o["titre"] for o in case["options"]))
        restantes = [q["texte"] for q in questions if not q.get("resolue")]
        lignes.append("Inconnues restantes : " + (" · ".join(restantes) if restantes else "aucune"))
        liv = {
            "id": f"liv-{len(case.get('livrables', [])) + 1}",
            "titre": f"Synthèse — {case['titre']}",
            "contenu": "\n".join(lignes),
            "cree_le": now,
        }
        await db.cases.update_one(
            {"id": cid},
            {"$push": {"livrables": liv, "historique": {"quand": now, "texte": "Synthèse produite par Flore"}}, "$set": {"maj_le": now}},
        )
        await journaler(x_persona, espace["id"], "production d'un livrable", cid, liv["titre"])
        return liv

    return router
