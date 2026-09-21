from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

import maturation
import portee as portees
import ouverture_travail

GENRES_A_TRAITER = {"a_confirmer", "investigation_recommandee", "decision_a_examiner", "action_proposee"}
GENRES_RADAR = {"a_surveiller", "information"}


class ReponseInitiative(BaseModel):
    choix: str
    motif: Optional[str] = None
    travail_id: Optional[str] = None


class OuvertureInitiative(BaseModel):
    intention: str = "comprendre"  # comprendre | suivre | investiguer


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

    async def travail_de_initiative(init, intention, persona, espace, suite=None):
        """Le travail d'une proposition du Mesh pour cette personne : créé avec la parole de Flore, ou rouvert (sans doublon).
        `suite` : messages à écrire ensuite dans le fil (la réponse de la personne et celle de Flore)."""
        now = datetime.now(timezone.utc).isoformat()
        msg = ouverture_travail.message_flore_initiative(init, intention if intention in ouverture_travail.INTENTIONS else "comprendre", now)
        messages = [msg]
        veille = None
        if intention == "suivre":
            # suivre = vérifier : une veille AVANT la décision, Flore dit ce qu'elle guette
            veille = maturation.nouvelle_veille(init["titre"], maturation.confiance_depuis_libelle(init.get("confiance", "")))
            m = veille["maturation"]
            messages.append(maturation.message_flore_suivi(init["titre"], m["confiance_depart"], m["seuil"], m["plancher"], now))
        existant = await db.cases.find_one({"origine.initiative_id": init["id"], "responsable": persona["id"]}, NO_ID)
        if existant:
            maj = {"maj_le": now}
            if intention not in existant["origine"].get("intentions", []):
                if veille and not existant.get("veille"):
                    maj["veille"] = veille
                else:
                    messages = messages[:1]
                await db.cases.update_one({"id": existant["id"]}, {"$push": {"conversation": {"$each": messages + (suite or [])}, "historique": {"quand": now, "texte": f"Proposition du Mesh reprise — {intention}"}},
                                                                   "$addToSet": {"origine.intentions": intention}, "$set": maj})
            elif suite:
                await db.cases.update_one({"id": existant["id"]}, {"$push": {"conversation": {"$each": suite}}, "$set": maj})
            return existant["id"], False
        cid = f"case-{slugify(init['titre'])[:40]}-{int(datetime.now(timezone.utc).timestamp()) % 100000}"
        dernier = await db.cases.find({}, {"_id": 0, "num": 1}).sort("num", -1).to_list(1)
        num = (dernier[0]["num"] if dernier and dernier[0].get("num") else 40) + 1
        await db.cases.insert_one({
            "id": cid, "num": num, "titre": init["titre"], "type": "investigation" if intention == "investiguer" else "decouverte", "statut": "ouvert",
            "sensibilite": "interne", "portee": "personnel", "objectif": init.get("raison", ""), "resume": "", "prochaine_etape": "", "questions": [], "hypotheses": [],
            "jumeaux": init.get("jumeaux", []), "situations": [], "participants": [persona["id"]], "responsable": persona["id"], "espace": espace["id"],
            "conversation": messages + (suite or []), "options": [], "decisions": [], "livrables": [], "a_revoir": False, "visites": {},
            **({"veille": veille} if veille else {}),
            "origine": {"initiative_id": init["id"], "genre": init.get("genre"), "intentions": [intention], "quand": now},
            "historique": [{"quand": now, "texte": f"Travail ouvert depuis la proposition du Mesh « {init['titre']} »"}],
            "cree_le": now, "maj_le": now,
        })
        return cid, True

    @router.post("/initiatives/{iid}/travail")
    async def ouvrir_travail_initiative(iid: str, payload: OuvertureInitiative, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
        """« Comprendre » une proposition du Mesh : elle devient un travail, dont Flore ouvre la conversation. La proposition, elle, reste en attente."""
        if payload.intention not in ouverture_travail.INTENTIONS:
            raise HTTPException(400, "Intention inconnue")
        persona, espace, aut = await contexte(x_persona, x_espace)
        init = await db.initiatives.find_one({"id": iid}, NO_ID)
        if not init or not visible(init, persona, espace, aut):
            raise HTTPException(404, "Initiative introuvable ou hors périmètre")
        cid, cree = await travail_de_initiative(init, payload.intention, persona, espace)
        return {"id": cid, "cree": cree}

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
            travail_cree, _ = await travail_de_initiative(init, "suivre", persona, espace)  # surveiller = un travail en veille
        elif low == "ignorer" or "rejeter" in low:
            statut = "refusee"
        elif low.startswith("créer") or low.startswith("creer"):
            statut = "acceptee"
            travail_cree, _ = await travail_de_initiative(init, "investiguer", persona, espace)
        elif "ajouter" in low:
            statut = "acceptee"
            tid = payload.travail_id or init.get("travail_id")
            if not tid:
                raise HTTPException(400, "Aucun travail cible")
            case = await db.cases.find_one({"id": tid})
            if not case:
                raise HTTPException(404, "Travail introuvable")
            if not portees.acces(case, persona["id"], espace["id"]):
                raise HTTPException(403, "Ce travail n'est pas partagé avec vous")
            histo = case.get("historique", []) + [{"quand": now, "texte": f"Initiative du Mesh ajoutée : {init['titre']}"}]
            jumeaux = sorted(set(case.get("jumeaux", [])) | set(init.get("jumeaux", [])))
            ajout = ouverture_travail.message_flore_initiative(init, "comprendre", now)
            ajout["texte"] = f"J'ai ajouté à ce travail une proposition du Mesh.\n\n" + ajout["texte"]
            await db.cases.update_one({"id": tid}, {"$set": {"historique": histo, "jumeaux": jumeaux, "maj_le": now}, "$push": {"conversation": ajout}})
            travail_cree = tid
        else:
            # Toute autre réponse acceptée (choisir une option, comparer, demander une validation) se passe DANS un travail :
            # la proposition est rattachée à son travail s'il existe, sinon elle en ouvre un
            statut = "acceptee"
            nature = "comparaison" if "comparer" in low else "validation" if "validation" in low or "valider" in low else "incertain" if ("ne sais pas" in low or "ne peux pas" in low) else "decision"
            suite = ouverture_travail.messages_reponse_initiative(init, choix, nature, now)
            lie = await db.cases.find_one({"id": init["travail_id"]}, {"_id": 0, "id": 1}) if init.get("travail_id") else None
            if lie:
                travail_cree = lie["id"]
                await db.cases.update_one({"id": travail_cree}, {"$push": {"conversation": {"$each": suite}, "historique": {"quand": now, "texte": f"Proposition du Mesh traitée : {init['titre']}"}}, "$set": {"maj_le": now}})
            else:
                travail_cree, _ = await travail_de_initiative(init, "decider", persona, espace, suite=suite)
            if nature == "decision":
                await db.cases.update_one({"id": travail_cree}, {"$push": {"decisions": {"texte": choix, "type": "arbitrage", "quand": now, "par": persona["id"]}}})

        reponse = {"choix": choix, "motif": payload.motif, "par": persona["id"], "quand": now, **({"travail_id": travail_cree} if travail_cree else {})}
        await db.initiatives.update_one({"id": iid}, {"$set": {"statut": statut, "reponse": reponse, "maj_le": now}})
        await journaler(persona["id"], "reponse_initiative", iid, f"{choix}" + (f" — motif : {payload.motif}" if payload.motif else ""))

        maj = await db.initiatives.find_one({"id": iid}, NO_ID)
        maj["vue"] = vue_de(maj)
        return {"initiative": maj, "travail_id": travail_cree}

    async def travail_de_delegation(d, persona, espace):
        """Une délégation est un travail : Flore y dit le mandat reçu (tâche, périmètre, durée, ce qu'elle produira, les limites), et y rend compte.
        Idempotent : le travail est rattaché à la délégation (`travail_id`)."""
        if d.get("travail_id") and await db.cases.find_one({"id": d["travail_id"]}, {"_id": 1}):
            return d["travail_id"]
        now = datetime.now(timezone.utc).isoformat()
        noms = {j["id"]: j["nom"] for j in await db.jumeaux.find({}, NO_ID).to_list(200)}
        jusqu = datetime.fromisoformat(d["jusqu_a"])
        mandat = ouverture_travail.message_flore_delegation(d, [noms.get(j, j) for j in d.get("jumeaux", [])], now)
        cid = f"case-{slugify(d['tache'])[:40]}-{int(datetime.now(timezone.utc).timestamp()) % 100000}"
        dernier = await db.cases.find({}, {"_id": 0, "num": 1}).sort("num", -1).to_list(1)
        num = (dernier[0]["num"] if dernier and dernier[0].get("num") else 40) + 1
        conversation = [mandat]
        if jusqu <= datetime.now(timezone.utc):
            conversation.append(ouverture_travail.message_flore_delegation_terminee(d, jusqu.isoformat()))
        await db.cases.insert_one({
            "id": cid, "num": num, "titre": d["tache"], "type": "demande", "statut": "en_cours" if len(conversation) == 1 else "clos",
            "sensibilite": "interne", "portee": "personnel", "objectif": d.get("livrable", ""), "resume": "", "prochaine_etape": "", "questions": [], "hypotheses": [],
            "jumeaux": d.get("jumeaux", []), "situations": [], "participants": [d["demandeur"]], "responsable": d["demandeur"], "espace": espace["id"],
            "conversation": conversation, "options": [], "decisions": [], "livrables": [], "a_revoir": False, "visites": {},
            "origine": {"delegation_id": d["id"], "genre": "delegation", "quand": now},
            "historique": [{"quand": d["cree_le"], "texte": f"Mandat confié à Flore — {d['tache']}"}], "cree_le": d["cree_le"], "maj_le": now,
        })
        await db.delegations.update_one({"id": d["id"]}, {"$set": {"travail_id": cid}})
        return cid

    @router.get("/delegations")
    async def lister_delegations(x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
        persona, espace, aut = await contexte(x_persona, x_espace)
        out = []
        async for d in db.delegations.find({}, NO_ID):
            if d.get("jumeaux") and not any(j in aut for j in d["jumeaux"]):
                continue
            if d.get("demandeur") == persona["id"]:
                d["travail_id"] = await travail_de_delegation(d, persona, espace)  # les délégations d'avant sont rattachées à un travail à la lecture
            if d["statut"] == "active" and datetime.fromisoformat(d["jusqu_a"]) <= datetime.now(timezone.utc):
                d["statut"] = "terminee"
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
        doc["travail_id"] = await travail_de_delegation(doc, persona, espace)
        await journaler(persona["id"], "delegation", doc["id"], tache)
        doc.pop("_id", None)
        return doc

    return router
