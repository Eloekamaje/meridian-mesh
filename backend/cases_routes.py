from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

import maturation
import portee as portees
from seed_data import ESPACES
import veille as moteur_veille


class CaseCreate(BaseModel):
    titre: str
    type: str = "demande"
    objectif: str = ""
    portee: str = "personnel"  # personnel | equipe | entreprise
    jumeaux: list = []
    situations: list = []
    participants: list = []
    responsable: Optional[str] = None
    espace: Optional[str] = None
    sensibilite: str = "interne"
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
    resume: Optional[str] = None
    prochaine_etape: Optional[str] = None
    hypotheses: Optional[list] = None
    options: Optional[list] = None
    conversation: Optional[list] = None
    sensibilite: Optional[str] = None


class HypotheseCase(BaseModel):
    texte: str


class InvestigationCase(BaseModel):
    texte: str


class MessageCase(BaseModel):
    texte: str


class Passation(BaseModel):
    """Note de passage d'une décision : ce qu'on attend, ce qu'on surveille, quand on revoit."""
    hypotheses: list = []
    attendus: list = []
    risques: list = []
    inconnues: list = []
    revue_le: Optional[str] = None


def _nombre(v, champ):
    try:
        return float(v) if not isinstance(v, (int, float)) else v
    except (TypeError, ValueError):
        raise HTTPException(400, f"« {champ} » doit être un nombre")


def normaliser_passation(p: "Passation") -> dict:
    """Nettoie la note de passation saisie : identifiants stables, nombres valides, sens cohérents, date de revue lisible.
    Une note sans rien à observer n'a pas de sens : la décision reste enregistrée, mais sans veille."""
    hyp = [h.strip() for h in p.hypotheses if isinstance(h, str) and h.strip()]
    attendus, risques, inconnues = [], [], []
    for i, a in enumerate(p.attendus, 1):
        if not str(a.get("indicateur", "")).strip():
            continue
        depart, cible = _nombre(a.get("depart"), "départ"), _nombre(a.get("cible"), "cible")
        attendus.append({"id": a.get("id") or f"att-{i}", "indicateur": a["indicateur"].strip(), "sens": "baisse" if cible < depart else "hausse",
                         "depart": depart, "cible": cible, "unite": str(a.get("unite", "")).strip()})
    for i, r in enumerate(p.risques, 1):
        if not str(r.get("texte", "")).strip():
            continue
        risques.append({"id": r.get("id") or f"risque-{i}", "texte": r["texte"].strip(), "jumeau": r.get("jumeau") or None,
                        "sens": "baisse" if r.get("sens") == "baisse" else "hausse", "seuil": _nombre(r.get("seuil"), "seuil"), "unite": str(r.get("unite", "")).strip()})
    for i, x in enumerate(p.inconnues, 1):
        if str(x.get("texte", "")).strip():
            inconnues.append({"id": x.get("id") or f"inc-{i}", "texte": x["texte"].strip()})
    revue = None
    if p.revue_le:
        try:
            d = datetime.fromisoformat(p.revue_le.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(400, "Date de revue illisible")
        revue = (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).isoformat()
    return {"hypotheses": hyp, "attendus": attendus, "risques": risques, "inconnues": inconnues, "revue_le": revue}


class ObservationVeille(BaseModel):
    cible: str = ""  # id d'un attendu, d'un risque ou d'une inconnue de la note de passage (veille après décision)
    effet: Optional[float] = None  # points de confiance en plus ou en moins (veille avant décision : phénomène qui mûrit)
    texte: str = ""
    jumeau: str
    valeur: Optional[float] = None
    unite: str = ""
    conclusion: str = ""
    source: str = ""
    quand: Optional[str] = None


class PorteeCase(BaseModel):
    portee: str  # personnel | equipe | entreprise


class DecisionAttendue(BaseModel):
    texte: str


class ActionVeille(BaseModel):
    action: str  # rouvrir | maintenir | clore


class DecisionCase(BaseModel):
    texte: str
    type: str = "arbitrage"
    passation: Optional[Passation] = None


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

    async def charger_case(cid: str, espace: dict, persona_id: str = ""):
        case = await db.cases.find_one({"id": cid}, NO_ID)
        if not case:
            raise HTTPException(404, "Case introuvable")
        if cid == "demo-polaris-work-g":
            return case
        tous = await db.jumeaux.find({}, {"_id": 0, "id": 1}).to_list(200)
        aut = autorisations(espace, [j["id"] for j in tous])
        if case.get("jumeaux") and not any(j in aut for j in case["jumeaux"]):
            raise HTTPException(403, "Ce case est hors de votre périmètre")
        if not portees.acces(case, persona_id, espace["id"]):
            raise HTTPException(403, "Ce travail n'est pas partagé avec vous")
        return case

    async def jumeaux_autorises(espace):
        tous = await db.jumeaux.find({}, {"_id": 0, "id": 1}).to_list(200)
        return autorisations(espace, [j["id"] for j in tous])

    async def materialiser_veille(case):
        """Écrit dans le fil les événements de veille dus à ce jour (une seule fois chacun : identifiants stables)."""
        v = case.get("veille")
        if not v or v.get("statut") != "en_veille":
            return case
        deja = set(v.get("emis", []))
        tous = moteur_veille.evaluer(v, datetime.now(timezone.utc))
        nouveaux = [e for e in tous if e["id"] not in deja]
        if not nouveaux:
            return case
        # Plusieurs lectures simultanées (page, panneau Flore, menu) arrivent ensemble : chaque événement est « réclamé » de façon
        # atomique — la mise à jour ne s'applique que si son identifiant n'est pas déjà émis, donc un seul lecteur l'écrit.
        for e in nouveaux:
            if e["type"] == "revue_due":
                msg = moteur_veille.message_flore_revue(e, tous)
            elif e["type"] in maturation.TYPES_QUESTION:
                msg = maturation.message_flore_maturation(e, v["maturation"], tous)
            else:
                msg = {"role": "evenement", **e}
            await db.cases.update_one(
                {"id": case["id"], "veille.emis": {"$ne": e["id"]}},
                {"$push": {"conversation": msg, "historique": {"quand": e["quand"], "texte": e["titre"]}}, "$addToSet": {"veille.emis": e["id"]},
                 "$max": {"maj_le": e["quand"]}},
            )
        return await db.cases.find_one({"id": case["id"]}, NO_ID)

    def visible_pour(case, aut):
        """Un fait observé par un jumeau hors périmètre n'apparaît pas (refus par défaut) ; le fil est remis en ordre chronologique."""
        conv = [m for m in case.get("conversation", []) if not moteur_veille.est_veille(m) or not m.get("jumeau") or m["jumeau"] in aut]
        if case.get("veille"):
            conv.sort(key=lambda m: m.get("quand", ""))
        return conv

    @router.get("/cases")
    async def lister_cases(x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
        _, espace = resoudre_perimetre(x_persona, x_espace)
        tous = await db.jumeaux.find({}, {"_id": 0, "id": 1}).to_list(200)
        aut = autorisations(espace, [j["id"] for j in tous])
        cases = await db.cases.find({}, NO_ID).to_list(200)
        visibles = [c for c in cases if c.get("id") == "demo-polaris-work-g" or (
            (not c.get("jumeaux") or any(j in aut for j in c["jumeaux"])) and portees.acces(c, x_persona, espace["id"]))]
        visibles = [await materialiser_veille(c) for c in visibles]
        visibles.sort(key=lambda c: c.get("maj_le", ""), reverse=True)
        for c in visibles:
            c["conversation"] = visible_pour(c, aut)
            if c.get("veille"):
                evs = [m for m in c["conversation"] if moteur_veille.est_veille(m)]
                c["mouvement"] = moteur_veille.mouvement(evs, (c.get("visites") or {}).get(x_persona))
                c["en_veille"] = c["veille"].get("statut") == "en_veille"
                c["veille_mode"] = c["veille"].get("mode") or "decision"
                c["revue_le"] = (c["veille"].get("passation") or {}).get("revue_le")
                c.pop("veille", None)
            c["portee"] = portees.portee_de(c)
            c["nb_messages"] = len(c.get("conversation", []))
            c["nb_decisions"] = len(c.get("decisions", []))
            c["nb_options"] = len(c.get("options", []))
            c["nb_questions_ouvertes"] = sum(1 for q in c.get("questions", []) if not q.get("resolue"))
            c["nb_options_a_trancher"] = sum(1 for o in c.get("options", []) if o.get("statut") == "a_evaluer")
            histo = c.get("historique", [])
            c["derniere_modif"] = histo[-1]["texte"] if histo else None
            visite = (c.get("visites") or {}).get(x_persona)
            nouveautes = [h for h in histo if visite and h.get("quand", "") > visite]
            c["nb_nouveautes"] = len(nouveautes)
            c["nouveaute_texte"] = nouveautes[-1]["texte"] if nouveautes else None
            c.pop("conversation", None)
            c.pop("historique", None)
            c.pop("questions", None)
            c.pop("options", None)
            c.pop("decisions", None)
            c.pop("hypotheses", None)
            c.pop("livrables", None)
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
        if payload.portee not in portees.PORTEES:
            raise HTTPException(400, "Portée inconnue")
        responsable = payload.responsable or x_persona
        dernier = await db.cases.find({}, {"_id": 0, "num": 1}).sort("num", -1).to_list(1)
        num = (dernier[0]["num"] if dernier and dernier[0].get("num") else 40) + 1
        doc = {
            "id": cid,
            "num": num,
            "titre": payload.titre.strip(),
            "type": payload.type,
            "statut": "ouvert",
            "sensibilite": payload.sensibilite,
            "objectif": payload.objectif,
            "resume": "",
            "prochaine_etape": "",
            "questions": [],
            "hypotheses": [],
            "jumeaux": payload.jumeaux,
            "situations": payload.situations,
            "participants": list({*payload.participants, x_persona, responsable}),
            "responsable": responsable,
            "portee": payload.portee,
            "espace": payload.espace or espace["id"],
            "conversation": payload.conversation,
            "options": [],
            "decisions": [],
            "livrables": [],
            "a_revoir": False,
            "visites": {},
            "historique": [{"quand": now, "texte": "Travail conservé"}],
            "cree_le": now,
            "maj_le": now,
        }
        await db.cases.insert_one(doc)
        if responsable != x_persona:
            await notifier([responsable], "assignation", f"Vous êtes responsable du travail « {doc['titre']} »", f"/travaux/{cid}")
        await journaler(x_persona, espace["id"], "création d'un case", cid, doc["titre"])
        doc.pop("_id", None)
        return doc

    @router.put("/cases/{cid}")
    async def enregistrer_ou_remplacer_case(cid: str, payload: Dict[str, Any], x_persona: str = Header("architecte")):
        doc = dict(payload)
        doc["id"] = cid
        doc.pop("_id", None)
        await db.cases.replace_one({"id": cid}, doc, upsert=True)
        return {"ok": True, "id": cid}

    @router.get("/cases/{cid}")
    async def obtenir_case(cid: str, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
        _, espace = resoudre_perimetre(x_persona, x_espace)
        case = await charger_case(cid, espace, x_persona)
        case = await materialiser_veille(case)
        case["conversation"] = visible_pour(case, await jumeaux_autorises(espace))
        # Évolution depuis la dernière visite de ce persona, puis la visite est enregistrée
        visites = case.get("visites", {})
        precedentes = case.get("visites_precedentes", {})
        derniere = visites.get(x_persona)
        # Plusieurs lectures rapprochées (page + panneau Flore…) sont UNE même visite : on garde le repère de la visite
        # précédente tant que la dernière date de moins d'une minute, sinon le « nouveau depuis » disparaît à la 2e lecture.
        recente = bool(derniere) and (datetime.now(timezone.utc) - datetime.fromisoformat(derniere.replace("Z", "+00:00"))).total_seconds() < 60
        if recente:
            derniere = precedentes.get(x_persona)  # aucune visite avant celle-ci (travail tout juste ouvert) : rien n'est « nouveau »
        evolutions = [h for h in case.get("historique", []) if derniere and h.get("quand", "") > derniere]
        case["evolutions_recentes"] = evolutions
        case["derniere_visite"] = derniere
        case["portee"] = portees.portee_de(case)
        case["espace_label"] = next((e["label"] for e in ESPACES if e["id"] == case.get("espace")), None)
        case["peut_partager"] = x_persona == case.get("responsable")
        if (case.get("veille") or {}).get("mode") == "maturation":
            m = case["veille"]["maturation"]
            case["veille"]["confiance"] = round(maturation.confiance_a(m, datetime.now(timezone.utc)))

        # Résolution des jumeaux participants (identifiés par app_id dans case["jumeaux"])
        if cid == "demo-polaris-work-g":
            case["jumeaux_participants"] = [
                {
                    "id": "demo-polaris-app-portail",
                    "app_id": "app-portail",
                    "nom": "Portail client",
                    "domaine": "Client",
                    "domaineCouleur": "#25D0C8",
                    "type": "Parcours client Web",
                    "statut": "actif",
                    "participation": "Fournit les données de parcours client et l'estimation de volumétrie pour l'auto-suivi.",
                    "role": "Exprime le besoin de visibilité client autonome sans appel au centre de contact.",
                    "participe": True,
                },
                {
                    "id": "demo-polaris-app-conseiller",
                    "app_id": "app-conseiller",
                    "nom": "Poste conseiller",
                    "domaine": "Distribution",
                    "domaineCouleur": "#FB7185",
                    "type": "Interface succursales",
                    "statut": "actif",
                    "participation": "Fournit le diagnostic de charge de traitement des conseillers en succursale.",
                    "role": "Exprime le besoin de connaître l'état du dossier pour libérer du temps d'accompagnement.",
                    "participe": True,
                },
                {
                    "id": "demo-polaris-app-dossiers",
                    "app_id": "app-dossiers",
                    "nom": "Gestion des dossiers",
                    "domaine": "Opérations",
                    "domaineCouleur": "#38BDF8",
                    "type": "Socle métier central",
                    "statut": "80% existant en production",
                    "participation": "Détient la machine à états officielle et le cycle de vie complet de chaque dossier.",
                    "role": "Socle central réutilisable pour alimenter tous les canaux de distribution.",
                    "participe": True,
                },
                {
                    "id": "demo-polaris-app-statuts",
                    "app_id": "app-statuts",
                    "nom": "Diffusion des statuts",
                    "domaine": "Opérations",
                    "domaineCouleur": "#38BDF8",
                    "type": "Exposition temps réel",
                    "statut": "actif en production",
                    "participation": "Expose les API et flux d'événements Kafka pour diffuser les changements d'état en direct.",
                    "role": "Concentrateur d'événements pour alimenter le web et le poste conseiller sans refonte.",
                    "participe": True,
                },
            ]
        elif case.get("jumeaux"):
            jumeaux_docs = await db.jumeaux.find({"id": {"$in": case["jumeaux"]}}, NO_ID).to_list(len(case["jumeaux"]))
            docs_par_id = {j["id"]: j for j in jumeaux_docs}
            case["jumeaux_participants"] = [
                {
                    "app_id": jid,
                    "nom": docs_par_id.get(jid, {}).get("nom", jid),
                    "domaine": docs_par_id.get(jid, {}).get("domaine", "Général"),
                    "statut": docs_par_id.get(jid, {}).get("statut", "actif"),
                    "role": docs_par_id.get(jid, {}).get("mission", "Composant SI participant"),
                    "participe": True,
                }
                for jid in case["jumeaux"]
            ]
        else:
            case["jumeaux_participants"] = []

        if not recente:
            miseajour = {f"visites.{x_persona}": datetime.now(timezone.utc).isoformat()}
            if visites.get(x_persona):
                miseajour[f"visites_precedentes.{x_persona}"] = visites[x_persona]
            await db.cases.update_one({"id": cid}, {"$set": miseajour})
        return case

    @router.patch("/cases/{cid}")
    async def maj_case(cid: str, payload: CasePatch, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
        _, espace = resoudre_perimetre(x_persona, x_espace)
        case = await charger_case(cid, espace, x_persona)
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
        if "conversation" in champs:
            histo.append({"quand": now, "texte": "Une exploration avec Flore a été ajoutée au travail"})
        if "a_revoir" in champs and champs["a_revoir"] is False and case.get("a_revoir"):
            histo.append({"quand": now, "texte": "Revue effectuée — hypothèses confirmées à jour"})
        nouveau_resp = champs.get("responsable")
        if nouveau_resp and nouveau_resp != case.get("responsable"):
            histo.append({"quand": now, "texte": f"Responsable : {nouveau_resp}"})
            if nouveau_resp != x_persona:
                await notifier([nouveau_resp], "assignation", f"Vous êtes responsable du travail « {case['titre']} »", f"/travaux/{cid}")
        update = {"$set": {**champs, "maj_le": now}}
        if histo:
            update["$push"] = {"historique": {"$each": histo}}
        await db.cases.update_one({"id": cid}, update)
        return await db.cases.find_one({"id": cid}, NO_ID)

    @router.post("/cases/{cid}/messages", status_code=201)
    async def message_case(cid: str, payload: MessageCase, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
        _, espace = resoudre_perimetre(x_persona, x_espace)
        case = await charger_case(cid, espace, x_persona)
        if not payload.texte.strip():
            raise HTTPException(400, "Message vide")
        now = datetime.now(timezone.utc).isoformat()
        msg_user = {"role": "utilisateur", "texte": payload.texte.strip(), "quand": now}
        q_low = payload.texte.strip().lower()
        if cid == "demo-polaris-work-g":
            if any(k in q_low for k in ["zero", "zéro", "reutilisable", "réutilisable", "base", "socle", "existant", "mutualis"]):
                msg_flore = {
                    "role": "flore",
                    "texte": "Absolument pas. Le SI possède déjà **80 % de la solution en production** dans l'application « Gestion des dossiers » (`app-dossiers`) et son module d'exposition « Diffusion des statuts » (`app-statuts`).\n\nPlutôt que de financer 3 développements spécifiques à 6,6 M€, il suffit de construire 2 connecteurs d'API légers branchés directement sur ce socle existant.\n\nCe choix permet une mise en service en **4 mois** au lieu de 18 mois, pour un investissement mutualisé de **1,5 M€**, dégageant un **gain net de +5,1 M€ (-77%)** et garantissant une source unique de vérité sur les dossiers.",
                    "comportement": "arbitrer",
                    "kpis": {
                        "gain": "+5,1 M€",
                        "gainSousTitre": "1,5 M€ vs 6,6 M€ (-77%)",
                        "delai": "4 mois",
                        "delaiSousTitre": "Au lieu de 18 mois en silos",
                        "socle": "80 %",
                        "socleSousTitre": "En production dans le SI",
                    },
                    "tableauComparatif": [
                        {"critere": "Budget global", "silos": "6,6 M€", "socle": "1,5 M€ (-77%)"},
                        {"critere": "Délai de mise en service", "silos": "14 à 18 mois", "socle": "4 mois (-14 mois)"},
                        {"critere": "Architecture SI", "silos": "3 développements spécifiques", "socle": "2 connecteurs API légers sur socle"},
                        {"critere": "Dette technique", "silos": "Élevée (divergence des états)", "socle": "Faible (source unique de vérité)"},
                    ],
                    "contributions": [
                        {"app_id": "app-dossiers", "jumeau": "Gestion des dossiers", "domaine": "Opérations", "texte": "Socle métier central 80% existant en production."},
                        {"app_id": "app-statuts", "jumeau": "Diffusion des statuts", "domaine": "Opérations", "texte": "Concentrateur d'événements Kafka prêt pour exposition."},
                    ],
                    "preuves": [
                        {"id": "demo-polaris-ev-g-couverture", "source": "ev-g-couverture", "detail": "Matrice d'audit de couverture du suivi des dossiers"},
                    ],
                    "jumeaux_participants": [
                        {"app_id": "app-dossiers", "nom": "Gestion des dossiers", "domaine": "Opérations", "participe": True},
                        {"app_id": "app-statuts", "nom": "Diffusion des statuts", "domaine": "Opérations", "participe": True},
                    ],
                    "quand": datetime.now(timezone.utc).isoformat(),
                }
            elif any(k in q_low for k in ["arbitrage", "comite", "comité", "decision", "décision", "dossier", "preparer", "préparer", "acter", "document"]):
                msg_flore = {
                    "role": "flore",
                    "texte": "Le dossier exécutif officiel **CASE_101_ARBITRAGE_CONVERGENCE.md** a été généré et archivé dans votre espace Travail.\n\nIl formalise le gel des 3 développements redondants en silos, acte l'allocation budgétaire du socle commun à **1,5 M€**, et liste les connecteurs d'interface à déployer en 4 mois pour les directeurs métier.",
                    "comportement": "conclure",
                    "documentCanvas": "CASE_101_ARBITRAGE_CONVERGENCE.md",
                    "contributions": [
                        {"app_id": "app-portail", "jumeau": "Portail client", "domaine": "Client", "texte": "Connecteur API léger web validé."},
                        {"app_id": "app-conseiller", "jumeau": "Poste conseiller", "domaine": "Distribution", "texte": "Connecteur succursale validé."},
                        {"app_id": "app-dossiers", "jumeau": "Gestion des dossiers", "domaine": "Opérations", "texte": "Socle central prêt à être branché."},
                        {"app_id": "app-statuts", "jumeau": "Diffusion des statuts", "domaine": "Opérations", "texte": "Connecteur de diffusion opérationnel."},
                    ],
                    "preuves": [
                        {"id": "demo-polaris-ev-g-couverture", "source": "ev-g-couverture", "detail": "Matrice de couverture du suivi des dossiers"},
                    ],
                    "jumeaux_participants": [
                        {"app_id": "app-portail", "nom": "Portail client", "domaine": "Client", "participe": True},
                        {"app_id": "app-conseiller", "nom": "Poste conseiller", "domaine": "Distribution", "participe": True},
                        {"app_id": "app-dossiers", "nom": "Gestion des dossiers", "domaine": "Opérations", "participe": True},
                        {"app_id": "app-statuts", "nom": "Diffusion des statuts", "domaine": "Opérations", "participe": True},
                    ],
                    "quand": datetime.now(timezone.utc).isoformat(),
                }
            else:
                msg_flore = {
                    "role": "flore",
                    "texte": "J'ai rapproché les objectifs déclarés dans les trois fiches d'initiative avec les flux réels observés sur les jumeaux numériques de votre système d'information.\n\nLe diagnostic est formel : **les 3 directions cherchent en réalité à résoudre exactement le même problème métier**, à savoir *connaître l'état réel, fiable et horodaté d'un dossier* (parcours client web, poste conseiller en agence, et chaîne opérationnelle de traitement).\n\n⚠️ **Risque de triple redondance financière :** En l'absence de concertation, chaque direction a budgété sa propre solution en silo, pour un total cumulé de **6,6 M€** afin de reconstruire 3 fois la même capacité.",
                    "comportement": "diagnostiquer",
                    "contributions": [
                        {"app_id": "app-portail", "jumeau": "Portail client", "domaine": "Client", "texte": "Données de parcours client et auto-suivi en ligne."},
                        {"app_id": "app-conseiller", "jumeau": "Poste conseiller", "domaine": "Distribution", "texte": "Charge de traitement des conseillers en succursale."},
                        {"app_id": "app-dossiers", "jumeau": "Gestion des dossiers", "domaine": "Opérations", "texte": "Machine à états officielle et cycle de vie complet du dossier."},
                        {"app_id": "app-statuts", "jumeau": "Diffusion des statuts", "domaine": "Opérations", "texte": "Exposition temps réel Kafka des événements d'état."},
                    ],
                    "preuves": [
                        {"id": "demo-polaris-ev-g-initiatives", "source": "ev-g-initiatives", "detail": "Trois fiches d'initiative Polaris soumises au comité"},
                    ],
                    "jumeaux_participants": [
                        {"app_id": "app-portail", "nom": "Portail client", "domaine": "Client", "participe": True},
                        {"app_id": "app-conseiller", "nom": "Poste conseiller", "domaine": "Distribution", "participe": True},
                        {"app_id": "app-dossiers", "nom": "Gestion des dossiers", "domaine": "Opérations", "participe": True},
                        {"app_id": "app-statuts", "nom": "Diffusion des statuts", "domaine": "Opérations", "participe": True},
                    ],
                    "quand": datetime.now(timezone.utc).isoformat(),
                }
        else:
            rep = await generer_reponse_flore("case", payload.texte, case.get("jumeaux", []), None, x_persona, x_espace)
            jumeaux_participants_msg = []
            if case.get("jumeaux"):
                jumeaux_docs = await db.jumeaux.find({"id": {"$in": case["jumeaux"]}}, NO_ID).to_list(len(case["jumeaux"]))
                docs_par_id = {j["id"]: j for j in jumeaux_docs}
                jumeaux_participants_msg = [
                    {
                        "app_id": jid.replace("demo-polaris-", ""),
                        "nom": docs_par_id.get(jid, {}).get("nom", jid),
                        "domaine": docs_par_id.get(jid, {}).get("domaine", "Général"),
                        "participe": True,
                    }
                    for jid in case["jumeaux"]
                ]

            msg_flore = {
                "role": "flore",
                "texte": rep.get("reponse", ""),
                "comportement": rep.get("comportement"),
                "preuves": rep.get("preuves") or [],
                "propositions": rep.get("propositions") or [],
                "contributions": rep.get("contributions") or [],
                "jumeaux_participants": jumeaux_participants_msg,
                "action": rep.get("action"),
                "quand": datetime.now(timezone.utc).isoformat(),
            }
        await db.cases.update_one(
            {"id": cid},
            {
                "$push": {"conversation": {"$each": [msg_user, msg_flore]}, "historique": {"quand": now, "texte": "Échange avec Flore"}},
                "$set": {"maj_le": now},
            },
        )
        return {"utilisateur": msg_user, "flore": msg_flore, "reponse_complete": msg_flore}

    @router.post("/cases/{cid}/decisions", status_code=201)
    async def decider_case(cid: str, payload: DecisionCase, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
        _, espace = resoudre_perimetre(x_persona, x_espace)
        await charger_case(cid, espace, x_persona)
        if not payload.texte.strip():
            raise HTTPException(400, "Décision vide")
        now = datetime.now(timezone.utc).isoformat()
        dec = {"texte": payload.texte.strip(), "type": payload.type, "quand": now, "par": x_persona}
        maj = {"maj_le": now}
        passation = normaliser_passation(payload.passation) if payload.passation else None
        if passation and not (passation["attendus"] or passation["risques"] or passation["inconnues"]):
            passation = None  # rien à observer : la décision est gardée, mais il n'y a pas de veille
        if passation:
            # La décision s'accompagne de sa note de passation : le travail entre en veille (attendu contre observé)
            maj["veille"] = {"statut": "en_veille", "decision_le": now, "passation": passation, "observations": [], "emis": []}
            maj["statut"] = "en_cours"
        push = {"decisions": dec, "historique": {"quand": now, "texte": f"Décision enregistrée — {payload.type}"}}
        if passation:
            # Flore enregistre la décision DANS la conversation et dit ce qu'elle va surveiller
            push["conversation"] = moteur_veille.message_flore_decision(dec["texte"], maj["veille"]["passation"], now)
        await db.cases.update_one({"id": cid}, {"$push": push, "$set": maj})
        await journaler(x_persona, espace["id"], "décision sur un case", cid, payload.texte.strip()[:120])
        return dec

    @router.get("/cases/{cid}/passation/brouillon")
    async def brouillon_passation(cid: str, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
        """Ce que Flore propose de consigner avec une décision : la décision elle-même, ce sur quoi elle repose, ce qui reste inconnu, une date
        de revue à 30 jours. Les cibles chiffrées et les seuils restent à la personne : Flore n'invente pas de mesure."""
        _, espace = resoudre_perimetre(x_persona, x_espace)
        case = await charger_case(cid, espace, x_persona)
        sit = await db.situations.find_one({"id": (case.get("situations") or [None])[0]}, NO_ID) if case.get("situations") else None
        decision = (case.get("decisions") or [{}])[-1].get("texte") or (sit or {}).get("decision") or ""
        pq = (sit or {}).get("decouverte_pourquoi") or []
        hyp = [pq] if isinstance(pq, str) else list(pq)
        inconnues = [{"texte": t} for t in ((sit or {}).get("reste_a_comprendre") or [])]
        opp = (sit or {}).get("opportunite") or {}
        revue = (datetime.now(timezone.utc) + timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
        return {"decision": decision, "hypotheses": hyp, "gain": opp.get("gain"), "attendus": [], "risques": [], "inconnues": inconnues, "revue_le": revue.isoformat(),
                "jumeaux": [j for j in (case.get("jumeaux") or [])]}

    @router.post("/cases/{cid}/portee")
    async def changer_portee(cid: str, payload: PorteeCase, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
        """Céder un travail à son équipe ou à l'entreprise (ou le reprendre pour soi). Seul le responsable le décide."""
        _, espace = resoudre_perimetre(x_persona, x_espace)
        case = await charger_case(cid, espace, x_persona)
        if payload.portee not in portees.PORTEES:
            raise HTTPException(400, "Portée inconnue")
        if case.get("responsable") != x_persona:
            raise HTTPException(403, "Seul le responsable du travail décide de qui le voit")
        if portees.portee_de(case) == payload.portee:
            return await obtenir_case(cid, x_persona, x_espace)
        now = datetime.now(timezone.utc).isoformat()
        libelle = {"personnel": "réservé au responsable", "equipe": f"partagé avec l'équipe ({next((e['label'] for e in ESPACES if e['id'] == case.get('espace')), 'espace')})",
                   "entreprise": "partagé avec toute l'entreprise (dans les limites des droits de chacun)"}[payload.portee]
        await db.cases.update_one({"id": cid}, {"$set": {"portee": payload.portee, "maj_le": now}, "$push": {"historique": {"quand": now, "texte": f"Travail {libelle}"}}})
        await journaler(x_persona, espace["id"], "portée d'un travail", cid, payload.portee)
        return await obtenir_case(cid, x_persona, x_espace)

    @router.post("/cases/{cid}/decision-attendue")
    async def decision_attendue(cid: str, payload: DecisionAttendue, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
        """Réponse à l'une des « décisions attendues » d'une situation, depuis le fil du travail : mêmes effets que l'ancienne page Investigation
        (statut de la situation, confirmation de la relation, décision enregistrée), écrits dans la conversation."""
        _, espace = resoudre_perimetre(x_persona, x_espace)
        case = await charger_case(cid, espace, x_persona)
        sid = (case.get("situations") or [None])[0]
        sit = await db.situations.find_one({"id": sid}, NO_ID) if sid else None
        if not sit or payload.texte not in (sit.get("decisions_attendues") or []):
            raise HTTPException(400, "Cette décision n'est pas attendue pour ce travail")
        maintenant = datetime.now(timezone.utc)
        now = maintenant.isoformat()
        x = payload.texte.lower()
        decision_enregistree = False
        lien = None
        if "confirmer la relation" in x and sit.get("relation_id"):
            aut = autorisations(espace, [j["id"] for j in await db.jumeaux.find({}, {"_id": 0, "id": 1}).to_list(200)])
            rel = await db.relations.find_one({"id": sit["relation_id"]}, NO_ID)
            if not rel or not any(aut.get(j) == "complet" for j in (rel["source"], rel["cible"])):
                raise HTTPException(403, "Permission « Valider » requise sur l'un des jumeaux de la relation")
            await db.relations.update_one({"id": rel["id"]}, {"$set": {"etat": "confirmee"}, "$addToSet": {"confirmee_par": "Validation humaine"}})
            reponse = "Relation confirmée. Je l'ajoute à la mémoire du Mesh : elle n'est plus un phénomène possible."
        elif "coïncidence" in x:
            await db.situations.update_one({"id": sid}, {"$set": {"statut": "classée"}})
            reponse = "Classée comme coïncidence. Je garde la trace de ce choix pour ne pas la reproposer sans élément nouveau."
        elif "investigation" in x:
            await db.situations.update_one({"id": sid}, {"$set": {"statut": "en investigation"}})
            reponse = "Investigation ouverte : ce travail en devient le dossier. Je peux formuler les hypothèses concurrentes et lister les preuves qui manquent."
        elif "surveiller" in x:
            await db.situations.update_one({"id": sid}, {"$set": {"statut": "surveillée"}})
            reponse = "Je la mets sous surveillance : je reviendrai vers vous si ma compréhension change."
        elif "observations" in x:
            await db.situations.update_one({"id": sid}, {"$set": {"statut": "en observation"}})
            reponse = "J'ai demandé des observations supplémentaires aux jumeaux concernés. Je vous préviens dès qu'elles arrivent."
        elif "poursuivre" in x:
            await db.situations.update_one({"id": sid}, {"$set": {"statut": "poursuivie", "decision": payload.texte, "decidee_le": now}})
            decision_enregistree = True
            reponse = "Opportunité retenue. Pour savoir si elle tient ses promesses, je propose de consigner ce que vous en attendez : gain visé, risques à surveiller, date de revue. Ensuite, je l'observerai pour vous."
        elif "reporter" in x:
            await db.situations.update_one({"id": sid}, {"$set": {"statut": "reportée", "decidee_le": now}})
            reponse = "Reportée. Je la garde en mémoire et je vous la représenterai si la situation change (fenêtre qui se referme, ou nouveau signal)."
        elif "écarter" in x:
            await db.situations.update_one({"id": sid}, {"$set": {"statut": "écartée", "decidee_le": now}})
            reponse = "Écartée. Je garde la trace de ce choix pour ne pas la reproposer sans élément nouveau."
        elif "admettre" in x:
            lien = "/jumeaux"
            reponse = "L'admission d'un jumeau se décide depuis sa revue : je vous y envoie."
        else:
            await db.situations.update_one({"id": sid}, {"$set": {"statut": "décidée", "decision": payload.texte, "decidee_le": now}})
            decision_enregistree = True
            reponse = "Décision enregistrée. Méridian apprend de ce choix, et je la garde dans la mémoire de ce travail. Voulez-vous consigner ce que vous en attendez, pour que je la surveille ?"
        moi = {"role": "utilisateur", "texte": payload.texte, "quand": now}
        flore = {"role": "flore", "comportement": "expliquer", "texte": reponse, "quand": now}
        if decision_enregistree:
            flore["propose_passation"] = True  # l'interface propose alors de consigner la note de passation
        push = {"conversation": {"$each": [moi, flore]}, "historique": {"quand": now, "texte": f"Décision attendue traitée — {payload.texte[:80]}"}}
        if decision_enregistree:
            push["decisions"] = {"texte": payload.texte, "type": "arbitrage", "quand": now, "par": x_persona}
        # le message qui portait les décisions attendues reçoit sa réponse (les réponses rapides disparaissent), puis la conversation s'allonge
        await db.cases.update_one(
            {"id": cid}, {"$set": {"conversation.$[q].reponse": payload.texte}},
            array_filters=[{"q.decisions": {"$exists": True}, "q.reponse": {"$exists": False}}],
        )
        await db.cases.update_one({"id": cid}, {"$set": {"maj_le": now}, "$push": push})
        await journaler(x_persona, espace["id"], "décision attendue", cid, payload.texte[:120])
        rep = await obtenir_case(cid, x_persona, x_espace)
        if lien:
            rep["lien"] = lien
        return rep

    @router.post("/cases/{cid}/veille/observations", status_code=201)
    async def observer_case(cid: str, payload: ObservationVeille, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
        """Un jumeau rapporte une observation liée à la note de passation (attendu, risque ou inconnue)."""
        _, espace = resoudre_perimetre(x_persona, x_espace)
        case = await charger_case(cid, espace, x_persona)
        v = case.get("veille")
        if not v or v.get("statut") != "en_veille":
            raise HTTPException(409, "Ce travail n'est pas en veille")
        if payload.jumeau not in await jumeaux_autorises(espace):
            raise HTTPException(403, "Ce jumeau est hors de votre périmètre")
        if v.get("mode") == "maturation":
            if payload.effet is None or not -40 <= payload.effet <= 40:
                raise HTTPException(400, "Une observation de vérification porte un effet sur la confiance, entre -40 et 40 points")
            if not payload.texte.strip():
                raise HTTPException(400, "Dire ce qui a été observé")
            n = len(v["maturation"].get("observations", [])) + 1
            obs = {"id": f"m{n}-{int(datetime.now(timezone.utc).timestamp() * 1000)}", "quand": payload.quand or datetime.now(timezone.utc).isoformat(), "jumeau": payload.jumeau,
                   "source": payload.source, "effet": payload.effet, "texte": payload.texte.strip()}
            await db.cases.update_one({"id": cid}, {"$push": {"veille.maturation.observations": obs}})
            return obs
        p = v.get("passation") or {}
        cibles = {x["id"] for k in ("attendus", "risques", "inconnues") for x in p.get(k, [])}
        if payload.cible not in cibles:
            raise HTTPException(400, "Cible inconnue dans la note de passation")
        obs = {"id": f"{int(datetime.now(timezone.utc).timestamp() * 1000)}", **payload.model_dump(exclude={"quand"}), "quand": payload.quand or datetime.now(timezone.utc).isoformat()}
        await db.cases.update_one({"id": cid}, {"$push": {"veille.observations": obs}})
        return obs

    async def agir_sur_maturation(cid, case, v, action, espace, x_persona, x_espace):
        """Réponse humaine à la question de Flore quand ce qu'elle vérifiait s'étaye ou s'effrite : confirmer, continuer d'observer, écarter."""
        libelle = next((r["label"] for r in maturation.REPONSES_MATURATION if r["action"] == action), None)
        if libelle is None:
            raise HTTPException(400, "Action inconnue")
        mat = v.get("maturation") or {}
        now = datetime.now(timezone.utc).isoformat()
        sujet = mat.get("sujet", "ce phénomène")
        maj = {"maj_le": now}
        push_extra = {}
        if action == "confirmer":
            if mat.get("relation_id"):
                aut = await jumeaux_autorises(espace)
                rel = await db.relations.find_one({"id": mat["relation_id"]}, NO_ID)
                if not rel or not any(aut.get(j) == "complet" for j in (rel["source"], rel["cible"])):
                    raise HTTPException(403, "Permission « Valider » requise sur l'un des jumeaux de la relation")
                await db.relations.update_one({"id": rel["id"]}, {"$set": {"etat": "confirmee"}, "$addToSet": {"confirmee_par": "Validation humaine"}})
                texte_flore = "Relation confirmée. Je l'ajoute à la mémoire du Mesh : ce n'est plus un phénomène possible. Je n'ai plus rien à vérifier ici."
            else:
                texte_flore = "Confirmé. Je le garde dans la mémoire du Mesh comme une vérité, avec les indices qui l'ont établi. Je n'ai plus rien à vérifier ici."
            maj.update({"veille.statut": "terminee", "statut": "clos"})
            push_extra["decisions"] = {"texte": f"Confirmer : {sujet}", "type": "arbitrage", "quand": now, "par": x_persona}
            histo = "Vérification terminée — confirmé"
        elif action == "ecarter":
            texte_flore = "Écarté. Je garde la trace des indices contraires pour ne pas le reproposer sans élément nouveau. Je n'ai plus rien à vérifier ici."
            maj.update({"veille.statut": "terminee", "statut": "clos"})
            for sid in case.get("situations") or []:
                await db.situations.update_one({"id": sid}, {"$set": {"statut": "classée"}})
            push_extra["decisions"] = {"texte": f"Écarter : {sujet}", "type": "arbitrage", "quand": now, "par": x_persona}
            histo = "Vérification terminée — écarté"
        else:
            texte_flore = "Je continue d'observer. Je ne reviendrai vers vous que si un indice contraire l'affaiblit sérieusement ; les autres indices s'ajoutent au fil de ce travail."
            histo = "Vérification poursuivie"
        moi = {"role": "utilisateur", "texte": libelle, "quand": now}
        flore = {"role": "flore", "comportement": "expliquer", "texte": texte_flore, "quand": now}
        # la question reçoit sa réponse (les réponses rapides disparaissent) ; MongoDB refuse de modifier et d'allonger la conversation dans un même ordre
        await db.cases.update_one(
            {"id": cid}, {"$set": {**maj, "conversation.$[q].reponse": action}, "$push": {"historique": {"quand": now, "texte": histo}}},
            array_filters=[{"q.reponses": {"$exists": True}, "q.reponse": {"$exists": False}}],
        )
        await db.cases.update_one({"id": cid}, {"$push": {"conversation": {"$each": [moi, flore]}, **({"decisions": push_extra["decisions"]} if push_extra else {})}})
        await journaler(x_persona, espace["id"], f"vérification : {action}", cid, sujet[:120])
        return await obtenir_case(cid, x_persona, x_espace)

    @router.post("/cases/{cid}/veille/decision")
    async def agir_sur_decision(cid: str, payload: ActionVeille, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
        """Réponse humaine à une revue : rouvrir la décision, la maintenir (nouvelle date de revue), ou clore la veille."""
        _, espace = resoudre_perimetre(x_persona, x_espace)
        case = await charger_case(cid, espace, x_persona)
        v = case.get("veille")
        if not v or v.get("statut") != "en_veille":
            raise HTTPException(409, "Ce travail n'est pas en veille")
        if v.get("mode") == "maturation":
            return await agir_sur_maturation(cid, case, v, payload.action, espace, x_persona, x_espace)
        if payload.action not in ("rouvrir", "maintenir", "clore"):
            raise HTTPException(400, "Action inconnue")
        maintenant = datetime.now(timezone.utc)
        now = maintenant.isoformat()
        evs = moteur_veille.evaluer(v, maintenant)
        faits = [e for e in evs if e["niveau"] == 1 and e["type"] != "revue_due"]
        libelle = next(r["label"] for r in moteur_veille.REPONSES_REVUE if r["action"] == payload.action)
        # Le choix de la personne est SON message ; Flore répond dans le fil
        moi = {"role": "utilisateur", "texte": libelle, "quand": now}
        if payload.action == "rouvrir":
            liste = "\n".join(f"— {e['texte']}" for e in faits) or "— aucun écart majeur, mais la date de revue est atteinte."
            texte_flore = f"Décision rouverte. Ce qui a changé depuis qu'elle a été prise :\n{liste}\n\nQuelle option voulez-vous réexaminer, ou souhaitez-vous que je compare des variantes ?"
            maj = {"veille.statut": "rouverte", "statut": "en_cours", "veille.revue_faite_le": now, "maj_le": now}
            histo = "Décision rouverte après observation des effets"
        elif payload.action == "maintenir":
            prochaine = (maintenant.replace(microsecond=0) + timedelta(days=30)).isoformat()
            texte_flore = "Décision maintenue. Je continue d'observer et je vous reparle de la revue dans 30 jours, ou avant si un risque surveillé se matérialise."
            maj = {"veille.passation.revue_le": prochaine, "maj_le": now}  # la revue passée est traitée ; la suivante n'est pas encore due
            histo = "Revue effectuée — décision maintenue, prochaine revue dans 30 jours"
        else:
            texte_flore = "Veille terminée. Je garde la décision et ses résultats dans la mémoire du Mesh ; je n'observe plus ces indicateurs."
            maj = {"veille.statut": "terminee", "statut": "clos", "veille.revue_faite_le": now, "maj_le": now}
            histo = "Veille terminée — décision close"
        flore = {"role": "flore", "comportement": "expliquer", "texte": texte_flore, "quand": now}
        # la question de revue reçoit sa réponse (les réponses rapides disparaissent)
        await db.cases.update_one(
            {"id": cid}, {"$set": {**maj, "conversation.$[q].reponse": payload.action}, "$push": {"historique": {"quand": now, "texte": histo}}},
            array_filters=[{"q.reponses": {"$exists": True}, "q.reponse": {"$exists": False}}],
        )
        await db.cases.update_one({"id": cid}, {"$push": {"conversation": {"$each": [moi, flore]}}})
        await journaler(x_persona, espace["id"], f"veille : décision {payload.action}", cid, "")
        return await obtenir_case(cid, x_persona, x_espace)

    @router.post("/cases/{cid}/options", status_code=201)
    async def ajouter_option_case(cid: str, payload: OptionCase, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
        _, espace = resoudre_perimetre(x_persona, x_espace)
        case = await charger_case(cid, espace, x_persona)
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
        case = await charger_case(cid, espace, x_persona)
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

    @router.post("/cases/{cid}/resume", status_code=201)
    async def actualiser_resume_case(cid: str, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
        _, espace = resoudre_perimetre(x_persona, x_espace)
        case = await charger_case(cid, espace, x_persona)
        questions = case.get("questions", [])
        resolues = [q for q in questions if q.get("resolue")]
        options = case.get("options", [])
        phrases = []
        if case.get("objectif"):
            phrases.append(case["objectif"])
        if options:
            phrases.append(f"{len(options)} option(s) sur la table : " + " · ".join(o["titre"] for o in options) + ".")
        if case.get("decisions"):
            phrases.append("Dernière décision : " + case["decisions"][-1]["texte"])
        restantes = [q["texte"] for q in questions if not q.get("resolue")]
        if restantes:
            phrases.append("Reste à comprendre : " + " · ".join(restantes))
        elif questions:
            phrases.append(f"Les {len(resolues)} questions sont levées.")
        if case.get("a_revoir"):
            phrases.append("Attention : une connaissance du Mesh a changé — ce résumé est à revoir.")
        resume = " ".join(phrases) or "Aucune compréhension consolidée pour l'instant."
        now = datetime.now(timezone.utc).isoformat()
        await db.cases.update_one(
            {"id": cid},
            {"$set": {"resume": resume, "maj_le": now}, "$push": {"historique": {"quand": now, "texte": "Résumé actualisé par Flore"}}},
        )
        return {"resume": resume}

    @router.post("/cases/{cid}/hypotheses", status_code=201)
    async def ajouter_hypothese_case(cid: str, payload: HypotheseCase, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
        _, espace = resoudre_perimetre(x_persona, x_espace)
        case = await charger_case(cid, espace, x_persona)
        if not payload.texte.strip():
            raise HTTPException(400, "Hypothèse vide")
        now = datetime.now(timezone.utc).isoformat()
        hyp = {"id": f"hyp-{len(case.get('hypotheses', [])) + 1}", "texte": payload.texte.strip(), "statut": "a_valider", "quand": now}
        await db.cases.update_one(
            {"id": cid},
            {"$push": {"hypotheses": hyp, "historique": {"quand": now, "texte": f"Hypothèse ajoutée — {hyp['texte'][:80]}"}}, "$set": {"maj_le": now}},
        )
        return hyp

    @router.post("/cases/{cid}/investigations", status_code=201)
    async def ouvrir_investigation_case(cid: str, payload: InvestigationCase, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
        _, espace = resoudre_perimetre(x_persona, x_espace)
        case = await charger_case(cid, espace, x_persona)
        if not payload.texte.strip():
            raise HTTPException(400, "Investigation sans objet")
        now = datetime.now(timezone.utc).isoformat()
        base = slugify(payload.texte)[:40] or "investigation"
        sid = f"sit-{base}"
        n = 2
        while await db.situations.find_one({"id": sid}):
            sid = f"sit-{base}-{n}"
            n += 1
        situation = {
            "id": sid,
            "verbe": "a_comprendre",
            "nature": "investigation",
            "type": "investigation",
            "titre": payload.texte.strip(),
            "resume": f"Investigation ouverte depuis le travail « {case['titre']} ».",
            "priorite": "normale",
            "statut": "active",
            "score": 50,
            "detectee": "à l'instant",
            "question": payload.texte.strip(),
            "jumeaux": case.get("jumeaux", []),
            "indicateurs": {"confiance": 50, "couverture": 50, "fraicheur": "à l'instant", "contradictions": 0},
            "cree_le": now,
        }
        await db.situations.insert_one(situation)
        await db.cases.update_one(
            {"id": cid},
            {"$push": {"situations": sid, "historique": {"quand": now, "texte": f"Investigation ouverte — {payload.texte.strip()[:80]}"}}, "$set": {"maj_le": now}},
        )
        await journaler(x_persona, espace["id"], "ouverture d'une investigation", sid, payload.texte.strip()[:120])
        situation.pop("_id", None)
        return situation

    return router
