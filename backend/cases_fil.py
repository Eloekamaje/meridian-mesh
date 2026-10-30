"""Versions, branches, régénération, modification, arrêt et approbation en ligne dans le fil d'un Travail
(contrat Conversation v1, §3).
La logique des messages est dans conversation.py (pure) ; ici, seulement les routes et la persistance."""
from datetime import datetime, timezone
import asyncio
from typing import Literal, Optional

from fastapi import Header, HTTPException
from pydantic import BaseModel, Field

import conversation as fil
from jumeau import flux


class Params(BaseModel):
    """Ce que le panneau Flore ajoute à une question ; absent, Flore répond comme dans le Travail."""
    contexte: Optional[str] = None
    selection: Optional[list] = None
    domaine: Optional[str] = None
    # Sans autorisation explicite, une régénération ne modifie pas le Travail quand des pièces sont présentes.
    autoriser_ecriture: bool = False


class Modification(Params):
    texte: str


class Choix(BaseModel):
    index: int


class Approbation(BaseModel):
    """La décision humaine sur une connaissance que Flore a proposée pendant ce tour (mêmes valeurs que la Revue)."""
    claim: int
    decision: Literal["ACCEPTED", "CONTESTED"]
    motif: Optional[str] = Field(default=None, max_length=2000)


def ajouter_routes_fil(router, deps):
    """deps : db, charger_case(cid, espace, persona), resoudre_perimetre, repondre(cid, case, question, params,
    persona, espace, emit) -> la réponse brute de Flore ; autorisations(espace, ids) -> {id: niveau} ;
    reviser(claim, jumeau, persona, decision, motif) : la revue humaine (LookupError, ValueError si déjà revue)."""
    db, charger_case, repondre = deps["db"], deps["charger_case"], deps["repondre"]
    resoudre_perimetre, autorisations, reviser = deps["resoudre_perimetre"], deps["autorisations"], deps["reviser"]
    exiger_contributeur = deps["exiger_contributeur"]
    prevenir_fin = deps.get("prevenir_fin") or (lambda cid, persona: None)

    async def ouvrir(cid, persona, espace_hdr):
        """Charger le fil pour une mutation : seuls le responsable et les participants y écrivent."""
        _, espace = resoudre_perimetre(persona, espace_hdr)
        case = await charger_case(cid, espace, persona)
        exiger_contributeur(case, persona)
        return case, list(case.get("conversation") or [])

    async def ecrire(cid, messages):
        await db.cases.update_one({"id": cid}, {"$set": {"conversation": messages,
                                                         "maj_le": datetime.now(timezone.utc).isoformat()}})

    def valider(messages, n, regle):
        if not 0 <= n < len(messages):
            raise HTTPException(404, "Message introuvable")
        try:
            return regle()
        except ValueError as e:
            raise HTTPException(400, str(e))

    def question_avant(messages, n):
        q = next((m.get("texte") for m in reversed(messages[:n]) if m.get("role") == "utilisateur"), None)
        if not q:
            raise HTTPException(400, "Aucune question ne précède cette réponse")
        return q

    @router.post("/cases/{cid}/messages/{n}/version")
    async def choisir_version(cid: str, n: int, payload: Choix, x_persona: str = Header("architecte"),
                              x_espace: Optional[str] = Header(None)):
        _, messages = await ouvrir(cid, x_persona, x_espace)
        nouveau = valider(messages, n, lambda: fil.choisir_version(messages[n], payload.index))
        await ecrire(cid, messages[:n] + [nouveau] + messages[n + 1:])
        return nouveau

    @router.post("/cases/{cid}/messages/{n}/branche")
    async def choisir_branche(cid: str, n: int, payload: Choix, x_persona: str = Header("architecte"),
                              x_espace: Optional[str] = Header(None)):
        _, messages = await ouvrir(cid, x_persona, x_espace)
        nouveaux = valider(messages, n, lambda: fil.choisir_branche(messages, n, payload.index))
        await ecrire(cid, nouveaux)
        return {"messages": nouveaux}

    @router.post("/cases/{cid}/messages/{n}/regenerer/flux")
    async def regenerer(cid: str, n: int, payload: Optional[Params] = None, x_persona: str = Header("architecte"),
                        x_espace: Optional[str] = Header(None)):
        case, messages = await ouvrir(cid, x_persona, x_espace)
        valider(messages, n, lambda: fil.choisir_version(messages[n], messages[n].get("version", 0)))
        question = question_avant(messages, n)

        async def ajouter(reponse):
            _, courants = await ouvrir(cid, x_persona, x_espace)
            if n >= len(courants):
                raise HTTPException(404, "Message introuvable")
            nouveau = fil.ajouter_version(courants[n], reponse)
            await ecrire(cid, courants[:n] + [nouveau] + courants[n + 1:])
            return nouveau

        async def produire(emit):
            return await ajouter(await repondre(cid, case, question, payload or Params(), x_persona, x_espace, emit))

        async def interrompu(brouillon, activite=None):
            if brouillon:  # rien d'écrit : rien n'est ajouté
                await ajouter(fil.message_interrompu(brouillon, activite))
        return flux.en_flux(produire, sur_interruption=interrompu, fil=cid, proprietaire=x_persona,
                            si_seul=prevenir_fin(cid, x_persona))

    @router.post("/cases/{cid}/messages/{n}/modifier/flux")
    async def modifier(cid: str, n: int, payload: Modification, x_persona: str = Header("architecte"),
                       x_espace: Optional[str] = Header(None)):
        case, messages = await ouvrir(cid, x_persona, x_espace)
        nouveaux = valider(messages, n, lambda: fil.ranger_branche_et_modifier(messages, n, payload.texte))
        await ecrire(cid, nouveaux)  # la branche est rangée d'abord : rien n'est perdu quoi qu'il arrive ensuite

        async def ajouter(message):
            _, courants = await ouvrir(cid, x_persona, x_espace)
            suite = courants + [message]
            await ecrire(cid, suite)
            return {"messages": suite}

        async def produire(emit):
            rep = await repondre(cid, case, nouveaux[n]["texte"], payload, x_persona, x_espace, emit)
            return await ajouter(fil.message_flore(rep))

        async def interrompu(brouillon, activite=None):
            await ajouter(fil.message_interrompu(brouillon, activite))
        return flux.en_flux(produire, sur_interruption=interrompu, fil=cid, proprietaire=x_persona,
                            si_seul=prevenir_fin(cid, x_persona))

    @router.post("/cases/{cid}/messages/{n}/approbation")
    async def approuver(cid: str, n: int, payload: Approbation, x_persona: str = Header("architecte"),
                        x_espace: Optional[str] = Header(None)):
        """Approbation en ligne (P2) : exécutée une seule fois côté serveur (verrou dans la revue), réservée à qui
        peut « Valider » ce jumeau, puis inscrite dans le message (les boutons disparaissent, panneau comme Travail)."""
        _, espace = resoudre_perimetre(x_persona, x_espace)
        case = await charger_case(cid, espace, x_persona)
        messages = list(case.get("conversation") or [])
        m = messages[n] if 0 <= n < len(messages) else {}
        prop = next((p for p in m.get("a_approuver") or [] if p.get("claim") == payload.claim), None)
        if m.get("role") != "flore" or prop is None:
            raise HTTPException(404, "Proposition introuvable")
        if prop.get("decision"):
            raise HTTPException(409, "Proposition déjà tranchée")
        if autorisations(espace, [prop["jumeau"]]).get(prop["jumeau"]) != "complet":
            raise HTTPException(403, f"Permission « Valider » requise sur {prop.get('nom') or prop['jumeau']}")
        try:
            await asyncio.to_thread(reviser, payload.claim, prop["jumeau"], x_persona, payload.decision, payload.motif)
        except LookupError:
            raise HTTPException(404, "Connaissance introuvable")
        except RuntimeError as e:
            raise HTTPException(503, str(e))
        except ValueError as e:  # déjà revue (page Revue, autre onglet) : rien n'est inscrit ici
            raise HTTPException(409, str(e))
        nouveau = fil.decider_proposition(m, payload.claim, payload.decision, x_persona)
        await db.cases.update_one({"id": cid}, {"$set": {f"conversation.{n}": nouveau,
                                                         "maj_le": datetime.now(timezone.utc).isoformat()}})
        return nouveau
