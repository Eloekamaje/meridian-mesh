"""Cas d'usage `cognitif.analyser` exécutable hors FastAPI.

La route HTTP et le worker partagent ce service. Il ne prend ni `Request` ni dépendance
de transport : tenant, acteur, payload et runtime injecté suffisent.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, Mapping

from meridian.application import composition, evaluation_cognitive, reponse_cognitive
from meridian.application import resolveur_contexte
from meridian.application.execution.modele import AnnulationExecution, ApprobationRequise
from meridian.domain import contexte as contexte_module
from meridian.domain import profils, raisonnement, specialistes
from meridian.ports.analyse import ConfigurationManquante, RuntimeAnalyse


def _objet(payload: Mapping[str, Any] | Any) -> Any:
    if hasattr(payload, "question"):
        return payload
    return SimpleNamespace(**dict(payload or {}))


def _fusionner_dossiers(dossiers, tenant, runtime: RuntimeAnalyse):
    propositions = {}
    limites = []
    for dossier in dossiers:
        limites.extend(dossier.get("limites") or [])
        for proposition in dossier.get("propositions") or []:
            cle = (proposition["specialiste"], proposition["type"], proposition["titre"])
            precedent = propositions.get(cle)
            if precedent is None or proposition["confiance"] > precedent["confiance"]:
                propositions[cle] = proposition
    ordonnees = sorted(propositions.values(),
                       key=lambda p: (-p["confiance"], p["type"], p["titre"], p["specialiste"]))
    return {
        "tenant": tenant,
        "statut": "ok" if all(d.get("statut") == "ok" for d in dossiers) else "partiel",
        "propositions": runtime.assainir(ordonnees),
        "specialistes": runtime.assainir(dossiers),
        "limites": list(dict.fromkeys(limites)),
    }


async def _phase(processus, nom: str, seq: int, entree, fonction, *, sortie,
                 reprise: bool = True):
    """Exécute une phase en journalisant son état et son checkpoint.

    `processus` est un `ProcessManager` (ou None pour l'usage HTTP synchrone). Une
    phase TERMINE est rendue depuis son checkpoint quand `reprise=True`.
    """
    if processus is None:
        return await fonction()
    if reprise:
        existante = await asyncio.to_thread(processus.lire, nom)
        if existante is not None and existante.get("etat") == "TERMINE":
            return existante.get("sortie")
    await asyncio.to_thread(processus.demarrer, nom, entree=entree, seq=seq,
                            forcer=not reprise)
    try:
        resultat = await fonction()
    except AnnulationExecution as exc:
        await asyncio.to_thread(processus.annuler, nom, exc)
        raise
    except ApprobationRequise as exc:
        await asyncio.to_thread(processus.suspendre, nom, exc)
        raise
    except Exception as exc:  # noqa: BLE001 - journalisé puis relancé
        await asyncio.to_thread(processus.echouer, nom, f"{type(exc).__name__}: {exc}")
        raise
    await asyncio.to_thread(processus.terminer, nom, sortie(resultat))
    return resultat


async def executer(tenant: str, acteur: str, payload: Mapping[str, Any] | Any, *,
                   runtime: RuntimeAnalyse | None = None, run_id: str | None = None,
                   verifier_annulation=None, processus=None) -> dict:
    """Exécute la même analyse cognitive que la route `/analyser`, sans transport HTTP.

    Les étapes `contexte`, `specialistes`, `reponse` et `evaluation` sont journalisées
    quand un `ProcessManager` est fourni. Seules `specialistes`, `reponse` et
    `evaluation` sont reprises depuis leur checkpoint : la résolution de contexte est
    volontairement recalculée pour rester bon marché et toujours fraîche.
    """
    if runtime is None:
        raise ConfigurationManquante("runtime d'analyse non configuré")

    def verifier():
        if verifier_annulation is not None and verifier_annulation():
            raise AnnulationExecution("analyse annulée")

    verifier()
    p = _objet(payload)

    async def resoudre_contexte():
        profil_demande = p.profil if runtime.mode_auth() == "demo" else None
        profil_local = profils.resoudre_profil(
            profil=profil_demande, identite={"role": acteur},
            question=p.question, autorite_max="proposition")
        twin_ids_local = list(dict.fromkeys(
            [identifiant for identifiant in (*p.twin_ids, p.twin_id) if identifiant]))
        plan_local = composition.planifier(
            profil_local, p.question, autorite_max="proposition",
            application_id=p.application_id, situation_id=p.situation_id,
            twin_ids=tuple(twin_ids_local))
        global_local = (
            p.scope in {"enterprise", "portfolio"}
            or p.domaine is not None
            or (not p.application_id and not twin_ids_local and not p.situation_id)
        )
        surface_local = p.surface or (
            "situation" if p.situation_id else
            "twin" if (twin_ids_local or p.application_id) else
            "atlas" if p.domaine else "global")
        try:
            contexte_local = resolveur_contexte.resoudre(
                tenant, surface_local,
                twin_id=(twin_ids_local[0] if twin_ids_local else p.application_id),
                situation_id=p.situation_id,
                domaine=p.domaine if surface_local == "atlas" else None,
                date=p.date, utilisateur=acteur, perimetre=p.scope)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        return {
            "profil": profil_local,
            "twin_ids": twin_ids_local,
            "plan": plan_local,
            "global_scope": global_local,
            "surface": surface_local,
            "contexte_resolu": contexte_local,
        }

    def sortie_contexte(valeur_locale):
        return runtime.assainir({
            "profil": valeur_locale["profil"].as_dict(),
            "composition": valeur_locale["plan"].as_dict(),
            "twin_ids": valeur_locale["twin_ids"],
            "global_scope": valeur_locale["global_scope"],
            "surface": valeur_locale["surface"],
            "contexte_resolu": valeur_locale["contexte_resolu"].as_dict(),
        })

    contexte = await _phase(
        processus, "contexte", 0, {"run_id": run_id, "question": p.question},
        resoudre_contexte, sortie=sortie_contexte, reprise=False)
    profil, plan = contexte["profil"], contexte["plan"]
    twin_ids = contexte["twin_ids"]
    global_scope = contexte["global_scope"]
    contexte_resolu = contexte["contexte_resolu"]

    verifier()

    async def executer_specialistes():
        noms_local: list[str] = []
        valeur_locale = None
        if global_scope:
            agregat = await runtime.agreger_portefeuille(
                tenant, domaine=p.domaine, limite=100)
            dossier_local = {
                "tenant": tenant, "statut": "ok",
                "propositions": agregat["propositions"],
                "specialistes": [{"specialiste": "portefeuille", "statut": "ok",
                                  "propositions": agregat["propositions"],
                                  "limites": list(agregat["limites"])}],
                "limites": list(agregat["limites"]),
            }
            valeur_locale = agregat["valeur"]
        else:
            noms_local = list(plan.specialistes_socle)
            base = specialistes.ContexteSpecialiste(
                tenant=tenant, question=p.question, situation_id=p.situation_id,
                twin_ids=tuple(twin_ids), application_id=p.application_id,
                claim_ids=tuple(p.claim_ids), profondeur=p.profondeur)
            dossiers = (await runtime.lancer_specialistes(noms_local, base, tenant)
                        if noms_local else [])
            dossier_local = _fusionner_dossiers(dossiers, tenant, runtime) if dossiers else {
                "tenant": tenant, "statut": "partiel", "propositions": [],
                "specialistes": [],
                "limites": ["aucun spécialiste mobilisé par la composition"],
            }
        return {"dossier": dossier_local, "noms": noms_local, "valeur": valeur_locale}

    specialistes_ = await _phase(
        processus, "specialistes", 1, {"run_id": run_id, "global_scope": global_scope},
        executer_specialistes, sortie=runtime.assainir)
    dossier = specialistes_["dossier"]
    noms = list(specialistes_.get("noms") or [])
    valeur = specialistes_.get("valeur")

    verifier()

    async def composer_reponse():
        reponse = reponse_cognitive.composer(
            p.question, profil, plan, dossier, autorite_max="proposition")
        max_tokens = max(200, min(int(getattr(p, "max_tokens", None) or 6000), 20000))
        proximite = runtime.proximite_graphe(tenant, twin_ids)
        entites = tuple(getattr(contexte_resolu, "entites", ()) or ())
        contexte_pack = contexte_module.construire(
            p.question, profil, dossier, max_tokens=max_tokens,
            entites=entites, proximite=proximite)
        try:
            candidats = await runtime.recuperer_memoire(
                tenant, question=p.question, twin_ids=tuple(twin_ids),
                situation_id=p.situation_id,
                scope=("session" if p.session_id else None),
                scope_id=p.session_id, limite=12, proximite=proximite)
            contexte_pack = runtime.enrichir_pack(
                contexte_pack.as_dict(), candidats, max_tokens=max_tokens)
        except Exception:
            contexte_pack = contexte_pack.as_dict()
        reponse_dict = reponse.as_dict()
        reponse_dict["decision_support"] = runtime.decision_support_enrichi(
            reponse_dict.get("decision_support"), options=p.options or None,
            changements=p.changements, criteres=p.criteres)
        session_resultat = None
        if p.session_id:
            try:
                resume_session = " | ".join(
                    str(fait.get("titre") or "")
                    for fait in (contexte_pack.get("faits") or ())[:3]
                ) or str(reponse_dict.get("decision_support", {}).get("abstention")
                         or "Analyse cognitive")
                session_resultat = await runtime.memoriser_session(
                    tenant, p.session_id, p.question, resume_session,
                    acteur=acteur,
                    donnees={"fingerprint": contexte_pack.get("fingerprint")})
            except Exception:
                session_resultat = None
        prediction = None
        if p.decision_id and p.confidence is not None:
            try:
                prediction_id = None
                if run_id:
                    import hashlib
                    prediction_id = "pred-" + hashlib.sha256(
                        f"{tenant}:{run_id}:{p.decision_id}".encode("utf-8")).hexdigest()[:32]
                if prediction_id:
                    prediction = await runtime.lire_calibration(tenant, prediction_id)
                if prediction is None:
                    prediction = await runtime.calibrer_decision(
                        tenant, reponse_dict.get("decision_support"),
                        decision_id=p.decision_id, confidence=p.confidence,
                        prediction_id=prediction_id)
            except Exception:
                prediction = None
        return {
            "reponse": reponse_dict,
            "contexte": contexte_pack,
            "session": session_resultat,
            "prediction": prediction.as_dict() if prediction is not None else None,
        }

    reponse_phase = await _phase(
        processus, "reponse", 2, {"run_id": run_id, "specialistes": noms},
        composer_reponse, sortie=runtime.assainir)
    reponse_dict = reponse_phase["reponse"]
    contexte_pack = reponse_phase["contexte"]
    session_resultat = reponse_phase.get("session")
    prediction = reponse_phase.get("prediction")

    trace = raisonnement.construire(
        p.question, profil, plan, contexte_pack, dossier, reponse_dict)
    socle = reponse_dict.get("socle") or {}
    resultat = {
        "tenant": tenant,
        "scope": ("enterprise" if global_scope and not p.domaine else "portfolio")
        if global_scope else "application",
        "domaine": p.domaine,
        "profil": runtime.assainir(profil.as_dict()),
        "composition": runtime.assainir(plan.as_dict()),
        "specialistes_executes": list(noms),
        "dossier": runtime.assainir(dossier),
        "reponse": runtime.assainir(reponse_dict),
        "contexte": runtime.assainir(contexte_pack),
        "contexte_resolu": runtime.assainir(contexte_resolu.as_dict()),
        "raisonnement": runtime.assainir(trace.as_dict()),
        "prediction": runtime.assainir(prediction),
        "memoire_session": (runtime.assainir(session_resultat)
                            if session_resultat is not None else None),
        "qualite": {
            "faits": len(socle.get("faits") or ()),
            "preuves": len(socle.get("preuves") or ()),
            "specialistes_ok": sum(
                1 for d in dossier.get("specialistes") or [] if d.get("statut") == "ok"),
            "limites": len(socle.get("limites") or ()),
            "memoire": len(contexte_pack.get("memoire") or ()),
            "autorite": reponse_dict.get("autorite"),
        },
    }
    if valeur is not None:
        resultat["valeur"] = runtime.assainir(valeur)
    verifier()

    async def evaluer():
        return evaluation_cognitive.evaluer(resultat)

    resultat["evaluation"] = await _phase(
        processus, "evaluation", 3, {"run_id": run_id}, evaluer,
        sortie=runtime.assainir)
    return resultat
