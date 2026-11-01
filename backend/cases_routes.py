from datetime import datetime, timedelta, timezone
from inspect import Parameter, signature
from typing import Literal, Optional
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from auth import acteur as acteur_courant

import conversation as fil
import maturation
import pieces
import portee as portees
import re
from seed_data import EPICS, EPIC_PAR_REF
import veille as moteur_veille
from jumeau import flux as jumeau_flux
from jumeau.travail import EcritureTravail
from cases_fil import ajouter_routes_fil
from pieces_routes import ajouter_routes_pieces


ROLES_IMPORTES = {"utilisateur", "flore", "evenement"}
CHAMPS_NON_IMPORTES = {
    # Ce qu'un message importé ne peut pas transporter : preuves, effets serveur, états de relecture, versions,
    # propositions à approuver, décisions déjà prises, sorties d'interface.
    "preuves", "a_approuver", "activite", "retour", "versions", "version", "version_active",
    "documentCanvas", "documentTexte", "livrable_id", "schemas", "resolution", "proposition", "intention",
    "orchestration", "kpis", "tableauComparatif", "contributions", "termes",
    "relecture_etat", "relu", "corrige", "decisions", "precision", "origine", "durees",
    "hors_perimetre", "jumeaux_participants", "reponses", "propose_passation", "interrompu",
    "branche", "branches", "suite", "importe",
}


def normaliser_conversation_importee(messages) -> list:
    """La conversation reçue du client (création, fusion) : uniquement des messages du contrat, sans aucun champ
    de confiance ou d'effet serveur. Un message de Flore importé est marqué comme tel."""
    propres = []
    for message in messages or []:
        if not isinstance(message, dict) or message.get("role") not in ROLES_IMPORTES:
            continue
        texte = message.get("texte")
        if not isinstance(texte, str) or len(texte) > 20_000:
            continue
        propre = {k: v for k, v in message.items() if k not in CHAMPS_NON_IMPORTES}
        if propre["role"] == "flore":
            propre["importe"] = True
        propres.append(propre)
    return propres


def _nouveaux_livrables(avant, apres) -> list:
    """Les livrables déposés pendant ce tour : les mêmes titres sont des versions, pas des documents neufs."""
    connus = {livrable.get("id") for livrable in (avant or []) if isinstance(livrable, dict)}
    return [livrable for livrable in (apres or [])
            if isinstance(livrable, dict) and livrable.get("id") not in connus]


def _accepte_autorisation_ecriture(fonction) -> bool:
    """Vrai si le générateur de réponse accepte le drapeau (nommé, ou via **kwargs)."""
    try:
        parametres = signature(fonction).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(p.name == "autoriser_ecriture" or p.kind == Parameter.VAR_KEYWORD for p in parametres)


class CaseCreate(BaseModel):
    titre: str
    type: str = "demande"
    objectif: str = ""
    portee: str = "personnel"  # personnel | entreprise
    jumeaux: list = []
    situations: list = []
    espace: Optional[str] = None
    sensibilite: str = "interne"
    conversation: list = []
    statut: Optional[str] = None  # seulement "conversation" : un Travail privé à son auteur, conservé à la demande


class CasePatch(BaseModel):
    statut: Optional[str] = None
    objectif: Optional[str] = None
    questions: Optional[list] = None
    jumeaux: Optional[list] = None
    situations: Optional[list] = None
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
    texte: str = Field(..., max_length=20_000)
    # Le panneau Flore y ajoute son contexte ; absents, Flore répond comme dans le Travail.
    contexte: Optional[str] = None
    selection: Optional[list] = None
    mentions: Optional[list] = Field(default=None, max_length=8)  # jumeaux explicitement mentionnés (@Nom)
    domaine: Optional[str] = None
    # Avec des pièces jointes, l'humain autorise explicitement Flore à modifier le Travail pour ce tour.
    autoriser_ecriture: bool = False


class RetourMessage(BaseModel):
    """👍/👎 sur une réponse de Flore : enregistré, pour l'évaluation (jamais un simple message de remerciement)."""
    valeur: Literal["utile", "faux"]
    motif: Optional[str] = Field(default=None, max_length=500)


class Passation(BaseModel):
    """Note de passage d'une décision : ce qu'on attend, ce qu'on surveille, quand on revoit."""
    hypotheses: list = []
    attendus: list = []
    risques: list = []
    inconnues: list = []
    revue_le: Optional[str] = None
    reference: Optional[dict] = None  # chantier externe qui porte l'action : {"systeme": "Jira", "ref": "PAY-140"} (Méridian n'en garde que la référence)


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
    reference = None
    if p.reference and str(p.reference.get("ref", "")).strip():
        ref = str(p.reference["ref"]).strip().upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9]+-\d+", ref):
            raise HTTPException(400, "Référence de chantier illisible (attendu : PAY-140)")
        connu = EPIC_PAR_REF.get(ref)
        reference = {"systeme": str(p.reference.get("systeme") or "Jira"), "ref": ref, **({"titre": connu["titre"]} if connu else {})}
    return {"hypotheses": hyp, "attendus": attendus, "risques": risques, "inconnues": inconnues, "revue_le": revue, "reference": reference}


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


class ObservationJumeau(BaseModel):
    """Ce qu'un jumeau (ou le moteur de raisonnement) rapporte : Méridian l'aiguille vers les travaux en veille que cela concerne."""
    jumeau: str
    source: str = ""
    quand: Optional[str] = None
    relation_id: Optional[str] = None  # phénomène qui mûrit : la relation observée…
    effet: Optional[float] = None  # … et ce que cela change à la confiance (points)
    texte: str = ""
    indicateur: Optional[str] = None  # décision en veille : l'indicateur, le risque ou l'inconnue observé (par son libellé)…
    valeur: Optional[float] = None
    unite: str = ""
    conclusion: str = ""


class PorteeCase(BaseModel):
    portee: str  # personnel | entreprise


class FusionCase(BaseModel):
    source_cid: str


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


def reviser_proposee(claim, jumeau, acteur, decision, motif):
    """La revue humaine d'une connaissance proposée (approbation en ligne), dans la couche cognitive."""
    import os
    import psycopg
    from jumeau import depot
    dsn = os.environ.get("JUMEAU_PG_DSN")
    if not dsn:
        raise RuntimeError("Couche cognitive non configurée (JUMEAU_PG_DSN)")
    with psycopg.connect(dsn, autocommit=True) as conn:
        depot.reviser(conn, claim, acteur, decision, motif, proposee_de=jumeau)


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

    @router.on_event("startup")
    async def reconcilier_les_compteurs():
        """Après les migrations de server.py (dont celle des sections) : recale les réservations de quota orphelines."""
        await pieces.reconcilier_compteurs(db)

    async def charger_case(cid: str, espace: dict, acteur_id: str = ""):
        case = await db.cases.find_one({"id": cid}, NO_ID)
        if not case:
            raise HTTPException(404, "Case introuvable")
        if case.get("statut") == "conversation" and case.get("auteur") != acteur_id:
            raise HTTPException(404, "Case introuvable")  # privée à son auteur : on ne révèle pas qu'elle existe
        tous = await db.jumeaux.find({}, {"_id": 0, "id": 1}).to_list(200)
        aut = autorisations(espace, [j["id"] for j in tous])
        if case.get("jumeaux") and not any(j in aut for j in case["jumeaux"]):
            raise HTTPException(403, "Ce case est hors de votre périmètre")
        if not portees.acces(case, acteur_id):
            raise HTTPException(403, "Ce travail n'est pas partagé avec vous")
        return case

    async def jumeaux_autorises(espace):
        tous = await db.jumeaux.find({}, {"_id": 0, "id": 1}).to_list(200)
        return autorisations(espace, [j["id"] for j in tous])

    def exiger_contributeur(case, acteur_id):
        """Une écriture dans un Travail : son responsable ou l'un de ses participants. Un lecteur simple ne modifie
        jamais la conversation ni les champs du Travail."""
        if acteur_id == case.get("responsable") or acteur_id in (case.get("participants") or []):
            return
        raise HTTPException(403, "Seuls le responsable et les participants peuvent modifier ce travail")

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

    def vue_case(case, aut):
        """La vue d'un Travail pour une personne : jamais le document brut, et jamais un jumeau hors de son
        périmètre (fil, jumeaux, participants)."""
        vue = dict(case)
        conversation = visible_pour(case, aut)
        vue["conversation"] = [
            ({**message,
              "jumeaux_participants": [p for p in message["jumeaux_participants"] or []
                                       if (p.get("app_id") or p.get("id")) in aut]}
             if message.get("jumeaux_participants") else message)
            for message in conversation
        ]
        vue["jumeaux"] = [j for j in case.get("jumeaux") or [] if j in aut]
        if "jumeaux_participants" in case:
            vue["jumeaux_participants"] = [p for p in case["jumeaux_participants"] or []
                                           if p.get("app_id") in aut]
        return vue

    @router.get("/cases")
    async def lister_cases(q: Optional[str] = None, inclure_conversations: bool = False, acteur: str = Depends(acteur_courant), x_espace: Optional[str] = Header(None)):
        _, espace = resoudre_perimetre(acteur, x_espace)
        tous = await db.jumeaux.find({}, {"_id": 0, "id": 1}).to_list(200)
        aut = autorisations(espace, [j["id"] for j in tous])
        cases = await db.cases.find({}, NO_ID).to_list(200)
        visibles = [c for c in cases if (
            (not c.get("jumeaux") or any(j in aut for j in c["jumeaux"])) and portees.acces(c, acteur))]
        visibles = [vue_case(await materialiser_veille(c), aut) for c in visibles]
        if not inclure_conversations:  # les Travaux conservés ; les conversations (de l'auteur seul) sur demande
            visibles = [c for c in visibles if c.get("statut") != "conversation"]
        if q and q.strip():  # titre et texte des messages visibles ; sous-chaîne, jamais une expression du client
            visibles = [c for c in visibles if fil.correspond(c.get("titre"), visible_pour(c, aut), q)]
        visibles.sort(key=lambda c: c.get("maj_le", ""), reverse=True)
        for c in visibles:
            c["conversation"] = visible_pour(c, aut)
            if c.get("veille"):
                evs = [m for m in c["conversation"] if moteur_veille.est_veille(m)]
                c["mouvement"] = moteur_veille.mouvement(evs, (c.get("visites") or {}).get(acteur))
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
            visite = (c.get("visites") or {}).get(acteur)
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
    async def creer_case(payload: CaseCreate, acteur: str = Depends(acteur_courant), x_espace: Optional[str] = Header(None)):
        _, espace = resoudre_perimetre(acteur, x_espace)
        base = slugify(payload.titre) or "case"
        cid = base
        n = 2
        while await db.cases.find_one({"id": cid}):
            cid = f"{base}-{n}"
            n += 1
        now = datetime.now(timezone.utc).isoformat()
        if payload.portee not in portees.PORTEES:
            raise HTTPException(400, "Portée inconnue")
        if payload.statut not in (None, "conversation"):
            raise HTTPException(400, "Statut de création inconnu")
        responsable = acteur
        dernier = await db.cases.find({}, {"_id": 0, "num": 1}).sort("num", -1).to_list(1)
        num = (dernier[0]["num"] if dernier and dernier[0].get("num") else 40) + 1
        doc = {
            "id": cid,
            "num": num,
            "titre": payload.titre.strip(),
            "type": payload.type,
            "statut": payload.statut or "ouvert",
            **({"auteur": acteur} if payload.statut == "conversation" else {}),
            "sensibilite": payload.sensibilite,
            "objectif": payload.objectif,
            "resume": "",
            "prochaine_etape": "",
            "questions": [],
            "hypotheses": [],
            "jumeaux": payload.jumeaux,
            "situations": payload.situations,
            "participants": [acteur],
            "responsable": responsable,
            "portee": payload.portee,
            "espace": payload.espace or espace["id"],
            "conversation": normaliser_conversation_importee(payload.conversation),
            "options": [],
            "decisions": [],
            "livrables": [],
            "pieces_count": 0,
            "a_revoir": False,
            "visites": {},
            "historique": [{"quand": now, "texte": "Travail conservé"}],
            "cree_le": now,
            "maj_le": now,
        }
        await db.cases.insert_one(doc)
        if payload.statut == "conversation":  # le titre (et le slug) d'une conversation privée ne fuit pas dans l'espace
            await journaler(acteur, "", "création d'un case", "", "conversation privée")
        else:
            await journaler(acteur, espace["id"], "création d'un case", cid, doc["titre"])
        doc.pop("_id", None)
        doc["peut_deposer"] = True  # le créateur est responsable (ou participant) : il peut joindre
        return doc

    @router.get("/cases/{cid}")
    async def obtenir_case(cid: str, acteur: str = Depends(acteur_courant), x_espace: Optional[str] = Header(None)):
        _, espace = resoudre_perimetre(acteur, x_espace)
        case = await charger_case(cid, espace, acteur)
        case = await materialiser_veille(case)
        aut = await jumeaux_autorises(espace)
        case["conversation"] = visible_pour(case, aut)
        case["pieces"] = await pieces.lister(db, cid)  # sources du Travail, jamais des connaissances
        # Évolution depuis la dernière visite de cet acteur, puis la visite est enregistrée
        visites = case.get("visites", {})
        precedentes = case.get("visites_precedentes", {})
        derniere = visites.get(acteur)
        # Plusieurs lectures rapprochées (page + panneau Flore…) sont UNE même visite : on garde le repère de la visite
        # précédente tant que la dernière date de moins d'une minute, sinon le « nouveau depuis » disparaît à la 2e lecture.
        recente = bool(derniere) and (datetime.now(timezone.utc) - datetime.fromisoformat(derniere.replace("Z", "+00:00"))).total_seconds() < 60
        if recente:
            derniere = precedentes.get(acteur)  # aucune visite avant celle-ci (travail tout juste ouvert) : rien n'est « nouveau »
        evolutions = [h for h in case.get("historique", []) if derniere and h.get("quand", "") > derniere]
        case["evolutions_recentes"] = evolutions
        case["derniere_visite"] = derniere
        case["portee"] = portees.portee_de(case)
        case["peut_partager"] = acteur == case.get("responsable")
        case["peut_deposer"] = (acteur == case.get("responsable")
                                or acteur in (case.get("participants") or []))
        if (case.get("veille") or {}).get("mode") == "maturation":
            m = case["veille"]["maturation"]
            case["veille"]["confiance"] = round(maturation.confiance_a(m, datetime.now(timezone.utc)))

        # Résolution des jumeaux participants (identifiés par app_id dans case["jumeaux"])
        if case.get("jumeaux"):
            jumeaux_docs = await db.jumeaux.find({"id": {"$in": case["jumeaux"]}}, NO_ID).to_list(len(case["jumeaux"]))
            docs_par_id = {j["id"]: j for j in jumeaux_docs}
            case["jumeaux_participants"] = [
                {
                    "app_id": jid,
                    "nom": docs_par_id.get(jid, {}).get("nom", jid),
                    "domaine": docs_par_id.get(jid, {}).get("domaine", "Général"),
                    "statut": docs_par_id.get(jid, {}).get("statut", "actif"),
                    "role": docs_par_id.get(jid, {}).get("mission", "Composant SI participant"),
                    "sources": docs_par_id.get(jid, {}).get("sources") or {},
                    "sources_detail": docs_par_id.get(jid, {}).get("sources_detail") or [],
                    "participe": True,
                }
                for jid in case["jumeaux"]
            ]
        else:
            case["jumeaux_participants"] = []

        if not recente:
            miseajour = {f"visites.{acteur}": datetime.now(timezone.utc).isoformat()}
            if visites.get(acteur):
                miseajour[f"visites_precedentes.{acteur}"] = visites[acteur]
            await db.cases.update_one({"id": cid}, {"$set": miseajour})
        return vue_case(case, aut)

    @router.patch("/cases/{cid}")
    async def maj_case(cid: str, payload: CasePatch, acteur: str = Depends(acteur_courant), x_espace: Optional[str] = Header(None)):
        _, espace = resoudre_perimetre(acteur, x_espace)
        case = await charger_case(cid, espace, acteur)
        exiger_contributeur(case, acteur)
        champs = {k: v for k, v in payload.model_dump().items() if v is not None}
        if "conversation" in champs:
            raise HTTPException(400, "La conversation s'ajoute par /messages ou /fusion")
        proteges = {"jumeaux", "statut", "sensibilite"}
        if proteges & champs.keys() and case.get("responsable") != acteur:
            raise HTTPException(403, "Seul le responsable du travail peut modifier les jumeaux, le statut ou la sensibilité")
        if champs.get("statut") == "conversation":
            raise HTTPException(400, "Un travail ne redevient pas une conversation")
        if not champs:
            return vue_case(case, await jumeaux_autorises(espace))
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
        update = {"$set": {**champs, "maj_le": now}}
        if histo:
            update["$push"] = {"historique": {"$each": histo}}
        await db.cases.update_one({"id": cid}, update)
        return vue_case(await db.cases.find_one({"id": cid}, NO_ID), await jumeaux_autorises(espace))

    @router.delete("/cases/{cid}", status_code=204)
    async def supprimer_conversation(cid: str, acteur: str = Depends(acteur_courant), x_espace: Optional[str] = Header(None)):
        """Retirer une conversation (contrat §2) ; charger_case la cache déjà à tout autre que son auteur."""
        _, espace = resoudre_perimetre(acteur, x_espace)
        case = await charger_case(cid, espace, acteur)
        if case.get("statut") != "conversation":
            raise HTTPException(400, "Seule une conversation se supprime ici ; un travail conservé se clôt")
        await pieces.supprimer_case(db, cid)
        await db.cases.delete_one({"id": cid})

    @router.post("/cases/{cid}/fusion")
    async def fusionner_conversation(cid: str, payload: FusionCase, acteur: str = Depends(acteur_courant),
                                     x_espace: Optional[str] = Header(None)):
        """Fusionne une conversation personnelle dans un Travail : les messages normalisés s'ajoutent à la fin, la
        source disparaît. Seul le responsable de la cible fusionne (un participant pourrait injecter de faux
        messages de Flore) ; la source est réservée atomiquement et ses pièces déplacées avant les messages.

        Une double requête est idempotente : le marqueur `fusion_id` n'est poussé qu'une fois dans la cible, donc les
        messages ne sont jamais dupliqués. Sans transaction Mongo, chaque étape se reprend sans recommencer la
        précédente."""
        _, espace = resoudre_perimetre(acteur, x_espace)
        # Identifiant stable de la fusion : une reprise (ou une seconde requête après la suppression de la source)
        # retrouve le marqueur déjà poussé dans la cible.
        fusion_id = str(uuid5(NAMESPACE_URL, f"meridian:fusion:{payload.source_cid}:{cid}"))
        cible = await charger_case(cid, espace, acteur)
        if payload.source_cid == cid:
            raise HTTPException(400, "La source et la cible sont le même travail")
        try:
            source = await charger_case(payload.source_cid, espace, acteur)
        except HTTPException as e:
            # Seule une première requête du responsable a pu poser le marqueur ; les autres gardent le 404
            # (une conversation privée ne révèle pas son existence).
            if e.status_code == 404 and acteur == cible.get("responsable"):
                frais = await db.cases.find_one({"id": cid}, NO_ID)
                if frais and fusion_id in (frais.get("fusions") or []):
                    return vue_case(frais, await jumeaux_autorises(espace))
            raise
        if source.get("statut") != "conversation":
            raise HTTPException(400, "La source doit être une conversation")
        if cible.get("statut") == "conversation":
            raise HTTPException(400, "La cible doit être un Travail conservé")
        if acteur != cible.get("responsable"):
            raise HTTPException(403, "Seul le responsable du travail peut fusionner une conversation")

        async def liberer():
            await db.cases.update_one(
                {"id": payload.source_cid},
                {"$unset": {"fusion_vers": "", "fusion_id": "", "fusion_etat": ""}},
            )

        reserve = await db.cases.update_one(
            {"id": payload.source_cid,
             "$or": [{"fusion_vers": None}, {"fusion_vers": {"$exists": False}}]},
            {"$set": {"fusion_vers": cid, "fusion_id": fusion_id, "fusion_etat": "en_cours"}},
        )
        if not getattr(reserve, "modified_count", 0):
            actuel = await db.cases.find_one({"id": payload.source_cid}, NO_ID)
            if not actuel or actuel.get("fusion_vers") != cid:
                raise HTTPException(409, "Cette conversation est déjà fusionnée ou en cours de fusion")
            fusion_id = str(actuel.get("fusion_id") or fusion_id)  # reprise de la même fusion
            if not actuel.get("fusion_id"):
                await db.cases.update_one({"id": payload.source_cid},
                                          {"$set": {"fusion_id": fusion_id, "fusion_etat": "en_cours"}})

        messages = normaliser_conversation_importee(source.get("conversation") or [])
        now = datetime.now(timezone.utc).isoformat()
        texte = f"Conversation fusionnée — {len(messages)} message(s)" if messages else "Conversation fusionnée — aucun message"
        # Les pièces passent avant les messages : une cible pleine refuse la fusion sans rien déplacer.
        try:
            await pieces.deplacer_pieces(db, payload.source_cid, cid)
        except ValueError as e:
            await liberer()
            raise HTTPException(400, str(e))
        except Exception:
            await liberer()
            raise HTTPException(409, "Fusion impossible ; la conversation source est intacte, réessayez.")
        # Marqueur atomique : la même fusion ne pousse ses messages qu'une fois (filtre sur `fusions`).
        # matched 0 : les messages sont déjà poussés (reprise) — on continue sans les dupliquer.
        try:
            await db.cases.update_one(
                {"id": cid, "fusions": {"$ne": fusion_id}},
                {"$push": {"conversation": {"$each": messages}, "historique": {"quand": now, "texte": texte}},
                 "$addToSet": {"fusions": fusion_id},
                 "$set": {"maj_le": now}},
            )
        except Exception:
            await liberer()
            raise HTTPException(409, "Fusion impossible ; la conversation source est intacte, réessayez.")
        await db.cases.delete_one({"id": payload.source_cid})
        await pieces.supprimer_case(db, payload.source_cid)  # pièces arrivées entre le déplacement et la suppression
        await journaler(acteur, "", "fusion de conversation", cid, "conversation privée")
        return vue_case(await db.cases.find_one({"id": cid}, NO_ID), await jumeaux_autorises(espace))

    @router.post("/cases/{cid}/messages", status_code=201)
    async def message_case(cid: str, payload: MessageCase, acteur: str = Depends(acteur_courant), x_espace: Optional[str] = Header(None)):
        return await traiter_message(cid, payload, acteur, x_espace)

    @router.post("/cases/{cid}/messages/flux")
    async def message_case_flux(cid: str, payload: MessageCase, acteur: str = Depends(acteur_courant), x_espace: Optional[str] = Header(None)):
        """Le même échange, au fil de l'eau (étapes réelles, brouillon en relecture, puis le message enregistré)."""
        from jumeau import flux

        async def interrompu(brouillon, activite=None):
            """Arrêt par l'interlocuteur : la question et ce que Flore avait écrit, marqué interrompu."""
            _, espace = resoudre_perimetre(acteur, x_espace)
            await charger_case(cid, espace, acteur)  # jamais d'écriture hors des droits
            now = datetime.now(timezone.utc).isoformat()
            msg_user = {"role": "utilisateur", "texte": payload.texte.strip(), "quand": now}
            await db.cases.update_one({"id": cid}, {"$push": {"conversation": {"$each": [msg_user, fil.message_interrompu(brouillon, activite)]}},
                                                    "$set": {"maj_le": now}})
        return flux.en_flux(lambda emit: traiter_message(cid, payload, acteur, x_espace, emit), sur_interruption=interrompu, fil=cid, proprietaire=acteur,
                            si_seul=prevenir_fin(cid))

    async def repondre_dans_travail(cid, case, question, params, acteur, x_espace, emit=None):
        """La réponse brute de Flore dans un Travail (hors scripts de démonstration), avec ce qui l'accompagne."""
        await EcritureTravail(db, cid).retirer_precision()  # reste d'un tour échoué : jamais rattaché à ce tour-ci
        selection = list(params.selection if params.selection is not None else case.get("jumeaux", []))
        for mention in (getattr(params, "mentions", None) or []):
            if isinstance(mention, str) and mention and mention not in selection:
                selection.append(mention)  # route explicitement vers le jumeau mentionné ; les droits filtrent ensuite
        suivi = jumeau_flux.Activite()  # ce que Flore a fait, gardé avec la réponse (relu au rechargement)

        async def suivre(e):
            suivi.suivre(e)
            await emit(e)
        appel = {"travail": cid, "emit": suivre if emit else None}
        if _accepte_autorisation_ecriture(generer_reponse_flore):
            appel["autoriser_ecriture"] = getattr(params, "autoriser_ecriture", False)
        rep = await generer_reponse_flore(params.contexte or "case", question, selection, params.domaine, acteur,
                                          x_espace, **appel)
        # Les jumeaux du Travail et ceux réellement consultés (mention, routage automatique) : tous avec leurs sources.
        ids = []
        base_participants = [] if rep.get("proposition") else (case.get("jumeaux") or [])
        for participant in [*base_participants, *(rep.get("jumeaux_participants") or [])]:
            cle = participant if isinstance(participant, str) else (participant.get("id") or participant.get("app_id"))
            if cle and cle not in ids:
                ids.append(cle)
        participants = []
        if ids:
            docs = await db.jumeaux.find({"id": {"$in": ids}}, NO_ID).to_list(len(ids))
            par_id = {j["id"]: j for j in docs}
            noms = {p.get("id") or p.get("app_id"): p.get("nom") for p in rep.get("jumeaux_participants") or []}
            for jid in ids:
                doc = par_id.get(jid, {})
                participants.append({"id": jid, "app_id": jid,
                                     "nom": doc.get("nom") or noms.get(jid) or jid,
                                     "domaine": doc.get("domaine") or "Général",
                                     "statut": doc.get("statut", "actif"),
                                     "role": doc.get("mission", "Composant SI participant"),
                                     "sources": doc.get("sources") or {},
                                     "sources_detail": doc.get("sources_detail") or [],
                                     "participe": True})
        vus, fusion = set(), []
        for participant in [*participants, *(rep.get("jumeaux_participants") or [])]:
            cle = participant.get("app_id") or participant.get("id")
            if cle and cle not in vus:
                vus.add(cle)
                fusion.append(participant)
        sortie = {**rep, "reponse": rep.get("reponse", ""), "propositions": rep.get("propositions") or [],
                  "jumeaux_participants": fusion, "activite": suivi.ops or None}
        # Un livrable déposé pendant le tour devient ouvrable dans le Canvas, comme un document généré.
        apres = await db.cases.find_one({"id": cid}, {"_id": 0, "livrables": 1})
        nouveaux = _nouveaux_livrables(case.get("livrables"), (apres or {}).get("livrables"))
        if nouveaux:
            dernier = nouveaux[-1]
            sortie["documentCanvas"] = dernier.get("titre")
            sortie["documentTexte"] = dernier.get("contenu")
            sortie["livrable_id"] = dernier.get("id")
        # question à options posée par Flore (demander_precision) : mêmes réponses rapides que les décisions attendues
        precision = await EcritureTravail(db, cid).retirer_precision()
        if precision:
            sortie["decisions"], sortie["precision"] = precision["options"], True
            if precision["question"] not in sortie["reponse"]:
                sortie["reponse"] = f"{sortie['reponse']}\n\n{precision['question']}".strip()
        return sortie

    jumeau_flux.ajouter_routes_tours(router)  # arrêter / reprendre un tour de Flore (P2)

    def prevenir_fin(cid):
        """Le tour a fini sans personne pour le lire (page quittée) : la notification « investigation terminée »
        (UX §134) renvoie au fil, qui reprend là où il en est."""
        async def prevenir(reponse):
            case = await db.cases.find_one({"id": cid}, {"_id": 0, "titre": 1}) or {}
            await notifier("investigation_terminee", f"Flore a terminé sa réponse — « {case.get('titre', 'Travail')} »",
                           f"/travaux/{cid}")
        return prevenir

    ajouter_routes_fil(router, {"db": db, "charger_case": charger_case, "resoudre_perimetre": resoudre_perimetre,
                                "autorisations": autorisations, "reviser": lambda *a: reviser_proposee(*a),
                                "prevenir_fin": prevenir_fin, "exiger_contributeur": exiger_contributeur,
                                "repondre": repondre_dans_travail})
    ajouter_routes_pieces(router, {"db": db, "charger_case": charger_case,
                                   "resoudre_perimetre": resoudre_perimetre, "journaler": journaler})

    async def traiter_message(cid, payload, acteur, x_espace, emit=None):
        _, espace = resoudre_perimetre(acteur, x_espace)
        case = await charger_case(cid, espace, acteur)
        exiger_contributeur(case, acteur)
        if not payload.texte.strip():
            raise HTTPException(400, "Message vide")
        now = datetime.now(timezone.utc).isoformat()
        msg_user = {"role": "utilisateur", "texte": payload.texte.strip(), "quand": now}
        msg_flore = fil.message_flore(await repondre_dans_travail(cid, case, payload.texte, payload, acteur, x_espace, emit))
        msg_flore = fil.normaliser(msg_flore)
        await db.cases.update_one(
            {"id": cid},
            {
                "$push": {"conversation": {"$each": [msg_user, msg_flore]}, "historique": {"quand": now, "texte": "Échange avec Flore"}},
                "$set": {"maj_le": now},
            },
        )
        return {"utilisateur": msg_user, "flore": msg_flore, "reponse_complete": msg_flore}

    @router.post("/cases/{cid}/messages/{n}/retour")
    async def retour_message(cid: str, n: int, payload: RetourMessage, acteur: str = Depends(acteur_courant),
                             x_espace: Optional[str] = Header(None)):
        _, espace = resoudre_perimetre(acteur, x_espace)
        case = await charger_case(cid, espace, acteur)
        conversation = case.get("conversation") or []
        if not 0 <= n < len(conversation) or conversation[n].get("role") != "flore":
            raise HTTPException(404, "Réponse de Flore introuvable")
        retour = {"valeur": payload.valeur, "motif": (payload.motif or "").strip() or None, "par": acteur,
                  "quand": datetime.now(timezone.utc).isoformat()}
        await db.cases.update_one({"id": cid}, {"$set": {f"conversation.{n}.retour": retour}})
        # Le jeu des retours nourrit l'évaluation : la question, la réponse et ce qu'en a dit l'humain.
        question = next((m.get("texte") for m in reversed(conversation[:n]) if m.get("role") == "utilisateur"), None)
        await db.retours.insert_one({"travail": cid, "message": n, "question": question,
                                     "reponse": conversation[n].get("texte"), **retour})
        return retour

    @router.post("/cases/{cid}/decisions", status_code=201)
    async def decider_case(cid: str, payload: DecisionCase, acteur: str = Depends(acteur_courant), x_espace: Optional[str] = Header(None)):
        _, espace = resoudre_perimetre(acteur, x_espace)
        await charger_case(cid, espace, acteur)
        if not payload.texte.strip():
            raise HTTPException(400, "Décision vide")
        now = datetime.now(timezone.utc).isoformat()
        dec = {"texte": payload.texte.strip(), "type": payload.type, "quand": now, "par": acteur}
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
        await journaler(acteur, espace["id"], "décision sur un case", cid, payload.texte.strip()[:120])
        return dec

    @router.get("/cases/{cid}/passation/brouillon")
    async def brouillon_passation(cid: str, acteur: str = Depends(acteur_courant), x_espace: Optional[str] = Header(None)):
        """Ce que Flore propose de consigner avec une décision : la décision elle-même, ce sur quoi elle repose, ce qui reste inconnu, une date
        de revue à 30 jours. Les cibles chiffrées et les seuils restent à la personne : Flore n'invente pas de mesure."""
        _, espace = resoudre_perimetre(acteur, x_espace)
        case = await charger_case(cid, espace, acteur)
        sit = await db.situations.find_one({"id": (case.get("situations") or [None])[0]}, NO_ID) if case.get("situations") else None
        decision = (case.get("decisions") or [{}])[-1].get("texte") or (sit or {}).get("decision") or ""
        pq = (sit or {}).get("decouverte_pourquoi") or []
        hyp = [pq] if isinstance(pq, str) else list(pq)
        inconnues = [{"texte": t} for t in ((sit or {}).get("reste_a_comprendre") or [])]
        opp = (sit or {}).get("opportunite") or {}
        revue = (datetime.now(timezone.utc) + timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
        lie = next((e for e in EPICS if e.get("travail") == cid), None)  # un chantier Jira déjà rattaché à ce travail
        return {"reference": {"systeme": "Jira", "ref": lie["ref"], "titre": lie["titre"]} if lie else None, "decision": decision, "hypotheses": hyp, "gain": opp.get("gain"), "attendus": [], "risques": [], "inconnues": inconnues, "revue_le": revue.isoformat(),
                "jumeaux": [j for j in (case.get("jumeaux") or [])]}

    @router.post("/observations")
    async def rapporter_observation(payload: ObservationJumeau, acteur: str = Depends(acteur_courant), x_espace: Optional[str] = Header(None)):
        """Point d'entrée des observations des jumeaux : le moteur de raisonnement rapporte UNE mesure, Méridian la confronte à toutes les veilles
        ouvertes qu'elle concerne (notes de passation des décisions, vérifications de phénomènes). Réservé aux rôles du Mesh global."""
        _, espace = resoudre_perimetre(acteur, x_espace)
        if not espace.get("global"):
            raise HTTPException(403, "Seuls les rôles du Mesh global rapportent des observations")
        if not await db.jumeaux.find_one({"id": payload.jumeau}, {"_id": 1}):
            raise HTTPException(404, "Jumeau inconnu")
        maintenant = datetime.now(timezone.utc)
        quand = payload.quand or maintenant.isoformat()
        acheminees = []
        async for c in db.cases.find({"veille.statut": "en_veille"}, NO_ID):
            v = c["veille"]
            if c.get("jumeaux") and payload.jumeau not in c["jumeaux"]:
                continue
            if v.get("mode") == "maturation":
                m = v["maturation"]
                if payload.relation_id and payload.relation_id == m.get("relation_id") and payload.effet is not None and -40 <= payload.effet <= 40 and payload.texte.strip():
                    obs = {"id": f"m{len(m.get('observations', [])) + 1}-{int(maintenant.timestamp() * 1000)}", "quand": quand, "jumeau": payload.jumeau, "source": payload.source,
                           "effet": payload.effet, "texte": payload.texte.strip()}
                    await db.cases.update_one({"id": c["id"]}, {"$push": {"veille.maturation.observations": obs}})
                    acheminees.append({"travail_id": c["id"], "cible": "confiance", "observation": obs["id"]})
                continue
            if not payload.indicateur:
                continue
            p = v.get("passation") or {}
            libelle = payload.indicateur.strip().lower()
            cible = next((x["id"] for k, cle in (("attendus", "indicateur"), ("risques", "texte"), ("inconnues", "texte")) for x in p.get(k, []) if str(x.get(cle, "")).strip().lower() == libelle), None)
            if cible and (payload.valeur is not None or payload.conclusion.strip()):
                obs = {"id": f"{int(maintenant.timestamp() * 1000)}", "cible": cible, "jumeau": payload.jumeau, "valeur": payload.valeur, "unite": payload.unite, "conclusion": payload.conclusion,
                       "source": payload.source, "quand": quand}
                await db.cases.update_one({"id": c["id"]}, {"$push": {"veille.observations": obs}})
                acheminees.append({"travail_id": c["id"], "cible": cible, "observation": obs["id"]})
        await journaler(acteur, espace["id"], "observation d'un jumeau", payload.jumeau, f"{len(acheminees)} veille(s) concernée(s)")
        return {"acheminees": acheminees}

    @router.post("/cases/{cid}/portee")
    async def changer_portee(cid: str, payload: PorteeCase, acteur: str = Depends(acteur_courant), x_espace: Optional[str] = Header(None)):
        """Partager un travail avec l'entreprise (ou le reprendre pour soi). Seul le responsable le décide."""
        _, espace = resoudre_perimetre(acteur, x_espace)
        case = await charger_case(cid, espace, acteur)
        if payload.portee not in portees.PORTEES:
            raise HTTPException(400, "Portée inconnue")
        if case.get("responsable") != acteur:
            raise HTTPException(403, "Seul le responsable du travail décide de qui le voit")
        if portees.portee_de(case) == payload.portee:
            return await obtenir_case(cid, acteur, x_espace)
        now = datetime.now(timezone.utc).isoformat()
        libelle = {"personnel": "réservé au responsable",
                   "entreprise": "partagé avec toute l'entreprise (dans les limites des droits de chacun)"}[payload.portee]
        await db.cases.update_one({"id": cid}, {"$set": {"portee": payload.portee, "maj_le": now}, "$unset": {"equipe": ""}, "$push": {"historique": {"quand": now, "texte": f"Travail {libelle}"}}})
        await journaler(acteur, espace["id"], "portée d'un travail", cid, payload.portee)
        return await obtenir_case(cid, acteur, x_espace)

    @router.post("/cases/{cid}/decision-attendue")
    async def decision_attendue(cid: str, payload: DecisionAttendue, acteur: str = Depends(acteur_courant), x_espace: Optional[str] = Header(None)):
        """Réponse à l'une des « décisions attendues » d'une situation, depuis le fil du travail : mêmes effets que l'ancienne page Investigation
        (statut de la situation, confirmation de la relation, décision enregistrée), écrits dans la conversation."""
        _, espace = resoudre_perimetre(acteur, x_espace)
        case = await charger_case(cid, espace, acteur)
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
            push["decisions"] = {"texte": payload.texte, "type": "arbitrage", "quand": now, "par": acteur}
        # le message qui portait les décisions attendues reçoit sa réponse (les réponses rapides disparaissent), puis la conversation s'allonge
        await db.cases.update_one(
            {"id": cid}, {"$set": {"conversation.$[q].reponse": payload.texte}},
            array_filters=[{"q.decisions": {"$exists": True}, "q.reponse": {"$exists": False}}],
        )
        await db.cases.update_one({"id": cid}, {"$set": {"maj_le": now}, "$push": push})
        await journaler(acteur, espace["id"], "décision attendue", cid, payload.texte[:120])
        rep = await obtenir_case(cid, acteur, x_espace)
        if lien:
            rep["lien"] = lien
        return rep

    @router.post("/cases/{cid}/veille/observations", status_code=201)
    async def observer_case(cid: str, payload: ObservationVeille, acteur: str = Depends(acteur_courant), x_espace: Optional[str] = Header(None)):
        """Un jumeau rapporte une observation liée à la note de passation (attendu, risque ou inconnue)."""
        _, espace = resoudre_perimetre(acteur, x_espace)
        case = await charger_case(cid, espace, acteur)
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

    async def agir_sur_maturation(cid, case, v, action, espace, acteur, x_espace):
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
            push_extra["decisions"] = {"texte": f"Confirmer : {sujet}", "type": "arbitrage", "quand": now, "par": acteur}
            histo = "Vérification terminée — confirmé"
        elif action == "ecarter":
            texte_flore = "Écarté. Je garde la trace des indices contraires pour ne pas le reproposer sans élément nouveau. Je n'ai plus rien à vérifier ici."
            maj.update({"veille.statut": "terminee", "statut": "clos"})
            for sid in case.get("situations") or []:
                await db.situations.update_one({"id": sid}, {"$set": {"statut": "classée"}})
            push_extra["decisions"] = {"texte": f"Écarter : {sujet}", "type": "arbitrage", "quand": now, "par": acteur}
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
        await journaler(acteur, espace["id"], f"vérification : {action}", cid, sujet[:120])
        return await obtenir_case(cid, acteur, x_espace)

    @router.post("/cases/{cid}/veille/decision")
    async def agir_sur_decision(cid: str, payload: ActionVeille, acteur: str = Depends(acteur_courant), x_espace: Optional[str] = Header(None)):
        """Réponse humaine à une revue : rouvrir la décision, la maintenir (nouvelle date de revue), ou clore la veille."""
        _, espace = resoudre_perimetre(acteur, x_espace)
        case = await charger_case(cid, espace, acteur)
        v = case.get("veille")
        if not v or v.get("statut") != "en_veille":
            raise HTTPException(409, "Ce travail n'est pas en veille")
        if v.get("mode") == "maturation":
            return await agir_sur_maturation(cid, case, v, payload.action, espace, acteur, x_espace)
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
        await journaler(acteur, espace["id"], f"veille : décision {payload.action}", cid, "")
        return await obtenir_case(cid, acteur, x_espace)

    @router.post("/cases/{cid}/options", status_code=201)
    async def ajouter_option_case(cid: str, payload: OptionCase, acteur: str = Depends(acteur_courant), x_espace: Optional[str] = Header(None)):
        _, espace = resoudre_perimetre(acteur, x_espace)
        case = await charger_case(cid, espace, acteur)
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
    async def produire_synthese_case(cid: str, acteur: str = Depends(acteur_courant), x_espace: Optional[str] = Header(None)):
        _, espace = resoudre_perimetre(acteur, x_espace)
        case = await charger_case(cid, espace, acteur)
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
        await journaler(acteur, espace["id"], "production d'un livrable", cid, liv["titre"])
        return liv

    @router.post("/cases/{cid}/resume", status_code=201)
    async def actualiser_resume_case(cid: str, acteur: str = Depends(acteur_courant), x_espace: Optional[str] = Header(None)):
        _, espace = resoudre_perimetre(acteur, x_espace)
        case = await charger_case(cid, espace, acteur)
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
    async def ajouter_hypothese_case(cid: str, payload: HypotheseCase, acteur: str = Depends(acteur_courant), x_espace: Optional[str] = Header(None)):
        _, espace = resoudre_perimetre(acteur, x_espace)
        case = await charger_case(cid, espace, acteur)
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
    async def ouvrir_investigation_case(cid: str, payload: InvestigationCase, acteur: str = Depends(acteur_courant), x_espace: Optional[str] = Header(None)):
        _, espace = resoudre_perimetre(acteur, x_espace)
        case = await charger_case(cid, espace, acteur)
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
        await journaler(acteur, espace["id"], "ouverture d'une investigation", sid, payload.texte.strip()[:120])
        situation.pop("_id", None)
        return situation

    return router
