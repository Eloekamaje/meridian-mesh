from datetime import timedelta
from typing import Optional, Dict, Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

import veille as moteur_veille


class CaseCreate(BaseModel):
    titre: str
    type: str = "demande"
    objectif: str = ""
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


class ObservationVeille(BaseModel):
    cible: str  # id d'un attendu, d'un risque ou d'une inconnue de la note de passage
    jumeau: str
    valeur: Optional[float] = None
    unite: str = ""
    conclusion: str = ""
    source: str = ""
    quand: Optional[str] = None


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

    async def charger_case(cid: str, espace: dict):
        case = await db.cases.find_one({"id": cid}, NO_ID)
        if not case:
            raise HTTPException(404, "Case introuvable")
        if cid == "demo-polaris-work-g":
            return case
        tous = await db.jumeaux.find({}, {"_id": 0, "id": 1}).to_list(200)
        aut = autorisations(espace, [j["id"] for j in tous])
        if case.get("jumeaux") and not any(j in aut for j in case["jumeaux"]):
            raise HTTPException(403, "Ce case est hors de votre périmètre")
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
            msg = moteur_veille.message_flore_revue(e, tous) if e["type"] == "revue_due" else {"role": "evenement", **e}
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
        visibles = [c for c in cases if c.get("id") == "demo-polaris-work-g" or not c.get("jumeaux") or any(j in aut for j in c["jumeaux"])]
        visibles = [await materialiser_veille(c) for c in visibles]
        visibles.sort(key=lambda c: c.get("maj_le", ""), reverse=True)
        for c in visibles:
            c["conversation"] = visible_pour(c, aut)
            if c.get("veille"):
                evs = [m for m in c["conversation"] if moteur_veille.est_veille(m)]
                c["mouvement"] = moteur_veille.mouvement(evs, (c.get("visites") or {}).get(x_persona))
                c["en_veille"] = c["veille"].get("statut") == "en_veille"
                c["revue_le"] = (c["veille"].get("passation") or {}).get("revue_le")
                c.pop("veille", None)
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
        case = await charger_case(cid, espace)
        case = await materialiser_veille(case)
        case["conversation"] = visible_pour(case, await jumeaux_autorises(espace))
        # Évolution depuis la dernière visite de ce persona, puis la visite est enregistrée
        visites = case.get("visites", {})
        precedentes = case.get("visites_precedentes", {})
        derniere = visites.get(x_persona)
        # Plusieurs lectures rapprochées (page + panneau Flore…) sont UNE même visite : on garde le repère de la visite
        # précédente tant que la dernière date de moins d'une minute, sinon le « nouveau depuis » disparaît à la 2e lecture.
        recente = bool(derniere) and (datetime.now(timezone.utc) - datetime.fromisoformat(derniere.replace("Z", "+00:00"))).total_seconds() < 60
        if recente and precedentes.get(x_persona):
            derniere = precedentes[x_persona]
        evolutions = [h for h in case.get("historique", []) if derniere and h.get("quand", "") > derniere]
        case["evolutions_recentes"] = evolutions
        case["derniere_visite"] = derniere

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
        case = await charger_case(cid, espace)
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
        await charger_case(cid, espace)
        if not payload.texte.strip():
            raise HTTPException(400, "Décision vide")
        now = datetime.now(timezone.utc).isoformat()
        dec = {"texte": payload.texte.strip(), "type": payload.type, "quand": now, "par": x_persona}
        maj = {"maj_le": now}
        if payload.passation:
            # La décision s'accompagne de sa note de passation : le travail entre en veille (attendu contre observé)
            maj["veille"] = {"statut": "en_veille", "decision_le": now, "passation": payload.passation.model_dump(), "observations": [], "emis": []}
        await db.cases.update_one(
            {"id": cid},
            {"$push": {"decisions": dec, "historique": {"quand": now, "texte": f"Décision enregistrée — {payload.type}"}}, "$set": maj},
        )
        await journaler(x_persona, espace["id"], "décision sur un case", cid, payload.texte.strip()[:120])
        return dec

    @router.post("/cases/{cid}/veille/observations", status_code=201)
    async def observer_case(cid: str, payload: ObservationVeille, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
        """Un jumeau rapporte une observation liée à la note de passation (attendu, risque ou inconnue)."""
        _, espace = resoudre_perimetre(x_persona, x_espace)
        case = await charger_case(cid, espace)
        v = case.get("veille")
        if not v or v.get("statut") != "en_veille":
            raise HTTPException(409, "Ce travail n'est pas en veille")
        if payload.jumeau not in await jumeaux_autorises(espace):
            raise HTTPException(403, "Ce jumeau est hors de votre périmètre")
        p = v.get("passation") or {}
        cibles = {x["id"] for k in ("attendus", "risques", "inconnues") for x in p.get(k, [])}
        if payload.cible not in cibles:
            raise HTTPException(400, "Cible inconnue dans la note de passation")
        obs = {"id": f"{int(datetime.now(timezone.utc).timestamp() * 1000)}", **payload.model_dump(exclude={"quand"}), "quand": payload.quand or datetime.now(timezone.utc).isoformat()}
        await db.cases.update_one({"id": cid}, {"$push": {"veille.observations": obs}})
        return obs

    @router.post("/cases/{cid}/veille/decision")
    async def agir_sur_decision(cid: str, payload: ActionVeille, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
        """Réponse humaine à une revue : rouvrir la décision, la maintenir (nouvelle date de revue), ou clore la veille."""
        _, espace = resoudre_perimetre(x_persona, x_espace)
        case = await charger_case(cid, espace)
        v = case.get("veille")
        if not v or v.get("statut") != "en_veille":
            raise HTTPException(409, "Ce travail n'est pas en veille")
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
            array_filters=[{"q.type": "revue_due", "q.reponse": {"$exists": False}}],
        )
        await db.cases.update_one({"id": cid}, {"$push": {"conversation": {"$each": [moi, flore]}}})
        await journaler(x_persona, espace["id"], f"veille : décision {payload.action}", cid, "")
        return await obtenir_case(cid, x_persona, x_espace)

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

    @router.post("/cases/{cid}/resume", status_code=201)
    async def actualiser_resume_case(cid: str, x_persona: str = Header("architecte"), x_espace: Optional[str] = Header(None)):
        _, espace = resoudre_perimetre(x_persona, x_espace)
        case = await charger_case(cid, espace)
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
        case = await charger_case(cid, espace)
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
        case = await charger_case(cid, espace)
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
