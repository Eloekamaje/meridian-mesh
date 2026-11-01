"""Cas d'usage `cognitif.analyser` exécutable hors FastAPI.

La route HTTP et le worker partagent ce service. Il ne prend ni `Request` ni dépendance
de transport : tenant, acteur et payload suffisent.
"""
from __future__ import annotations

import asyncio
import os
from contextlib import nullcontext
from dataclasses import replace
from types import SimpleNamespace
from typing import Any, Mapping

import psycopg

import auth as auth_identite
import boucle_routes
from jumeau import calibration, composition, contexte as contexte_module, decision_cognitive, evaluation_cognitive
from jumeau.execution.modele import AnnulationExecution, ApprobationRequise
from jumeau import graph_store, portefeuille, profils, raisonnement as raisonnement_module
from jumeau import reponse_cognitive, resolveur_contexte, retrieval_memoire, rls
from jumeau import session_memoire, specialistes
from jumeau import specialiste_decouverte, specialiste_impact, specialiste_preuve


class ConfigurationManquante(RuntimeError):
    """Configuration runtime absente (DSN)."""


def _objet(payload: Mapping[str, Any] | Any) -> Any:
    if hasattr(payload, "question"):
        return payload
    return SimpleNamespace(**dict(payload or {}))


def _contexte(conn, tenant):
    return rls.contexte_tenant(conn, tenant) if rls.est_actif() else nullcontext()


def _dsn() -> str:
    dsn = os.environ.get("JUMEAU_PG_DSN")
    if not dsn:
        raise ConfigurationManquante("JUMEAU_PG_DSN non défini")
    return dsn


def _assainir(valeur):
    return boucle_routes._assainir(valeur)


def _proximite_graphe(tenant: str, twin_ids: list[str]) -> dict[str, float]:
    """Scores 1/(1+distance) pour les voisins des Twins actifs, sans rendre le graphe obligatoire."""
    if not twin_ids:
        return {}
    contexte = None
    try:
        from jumeau import graph_store
        contexte = graph_store.ouvrir()
        scores: dict[str, float] = {}
        for twin_id in twin_ids[:10]:
            for voisin in contexte["store"].voisins(tenant, twin_id, profondeur=2):
                identifiant = str(voisin.get("id") or "")
                if identifiant:
                    scores[identifiant] = max(scores.get(identifiant, 0.0),
                                              1.0 / (1.0 + max(1, int(voisin.get("profondeur") or 1))))
        return scores
    except Exception:
        return {}
    finally:
        if contexte is not None:
            contexte["fermer"]()


async def _avec_connexion(tenant: str, action):
    def executer():
        with psycopg.connect(_dsn(), connect_timeout=5) as conn:
            with _contexte(conn, tenant):
                return action(conn)

    return await asyncio.to_thread(executer)


SPECIALISTES = {
    "decouverte": specialiste_decouverte.SpecialisteDecouverte,
    "preuve": specialiste_preuve.SpecialistePreuve,
    "impact": specialiste_impact.SpecialisteImpact,
    "outcome": specialiste_impact.SpecialisteOutcome,
}


async def _lancer_specialistes(noms, base, tenant, dsn):
    async def lancer(nom):
        instance = SPECIALISTES[nom]()
        graph_context = None
        try:
            if nom in {"impact", "decouverte"}:
                try:
                    graph_context = graph_store.ouvrir()
                except Exception:
                    graph_context = None
            magasin = graph_context["store"] if graph_context is not None else None
            with psycopg.connect(dsn, connect_timeout=5) as conn:
                with _contexte(conn, tenant):
                    contexte = replace(base, conn=conn, store=magasin)
                    orchestrateur = specialistes.OrchestrateurSpecialistes([instance], timeout_s=8.0)
                    dossier = await orchestrateur.analyser(contexte)
                    return dossier["specialistes"][0]
        finally:
            if graph_context is not None:
                graph_context["fermer"]()

    return await asyncio.gather(*(lancer(nom) for nom in noms))


def _fusionner_dossiers(dossiers, tenant):
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
        "propositions": _assainir(ordonnees),
        "specialistes": _assainir(dossiers),
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


async def executer(tenant: str, acteur: str, payload: Mapping[str, Any] | Any,
                   run_id: str | None = None, verifier_annulation=None,
                   processus=None) -> dict:
    """Exécute la même analyse cognitive que la route `/analyser`, sans transport HTTP.

    Les étapes `contexte`, `specialistes`, `reponse` et `evaluation` sont journalisées
    quand un `ProcessManager` est fourni. Seules `specialistes`, `reponse` et
    `evaluation` sont reprises depuis leur checkpoint : la résolution de contexte est
    volontairement recalculée pour rester bon marché et toujours fraîche.
    """
    def verifier():
        if verifier_annulation is not None and verifier_annulation():
            raise AnnulationExecution("analyse annulée")

    verifier()
    p = _objet(payload)

    async def resoudre_contexte():
        profil_demande = p.profil if auth_identite.mode() == "demo" else None
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
        return _assainir({
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
            agregat = await _avec_connexion(tenant, lambda conn: portefeuille.agreger(
                conn, tenant, domaine=p.domaine, limite=100))
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
            dossiers = (await _lancer_specialistes(noms_local, base, tenant, _dsn())
                        if noms_local else [])
            dossier_local = _fusionner_dossiers(dossiers, tenant) if dossiers else {
                "tenant": tenant, "statut": "partiel", "propositions": [],
                "specialistes": [],
                "limites": ["aucun spécialiste mobilisé par la composition"],
            }
        return {"dossier": dossier_local, "noms": noms_local, "valeur": valeur_locale}

    specialistes_ = await _phase(
        processus, "specialistes", 1, {"run_id": run_id, "global_scope": global_scope},
        executer_specialistes, sortie=_assainir)
    dossier = specialistes_["dossier"]
    noms = list(specialistes_.get("noms") or [])
    valeur = specialistes_.get("valeur")

    verifier()

    async def composer_reponse():
        reponse = reponse_cognitive.composer(
            p.question, profil, plan, dossier, autorite_max="proposition")
        max_tokens = max(200, min(int(getattr(p, "max_tokens", None) or 6000), 20000))
        proximite = _proximite_graphe(tenant, twin_ids)
        entites = tuple(getattr(contexte_resolu, "entites", ()) or ())
        contexte_pack = contexte_module.construire(
            p.question, profil, dossier, max_tokens=max_tokens,
            entites=entites, proximite=proximite)
        try:
            candidats = await _avec_connexion(tenant, lambda conn: retrieval_memoire.recuperer(
                conn, tenant, question=p.question, twin_ids=tuple(twin_ids),
                situation_id=p.situation_id,
                scope=("session" if p.session_id else None),
                scope_id=p.session_id, limite=12, proximite=proximite))
            contexte_pack = retrieval_memoire.enrichir_pack(
                contexte_pack.as_dict(), candidats, max_tokens=max_tokens)
        except Exception:
            contexte_pack = contexte_pack.as_dict()
        reponse_dict = reponse.as_dict()
        reponse_dict["decision_support"] = decision_cognitive.decision_support_enrichi(
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
                session_resultat = await _avec_connexion(
                    tenant, lambda conn: session_memoire.memoriser_session(
                        conn, tenant, p.session_id, p.question, resume_session,
                        acteur=acteur,
                        donnees={"fingerprint": contexte_pack.get("fingerprint")}))
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
                    prediction = await _avec_connexion(
                        tenant, lambda conn: calibration.lire(conn, tenant, prediction_id))
                if prediction is None:
                    prediction = await _avec_connexion(
                        tenant, lambda conn: decision_cognitive.calibrer_decision_support(
                            conn, tenant, reponse_dict.get("decision_support"),
                            decision_id=p.decision_id, confidence=p.confidence,
                            prediction_id=prediction_id))
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
        composer_reponse, sortie=_assainir)
    reponse_dict = reponse_phase["reponse"]
    contexte_pack = reponse_phase["contexte"]
    session_resultat = reponse_phase.get("session")
    prediction = reponse_phase.get("prediction")

    trace = raisonnement_module.construire(
        p.question, profil, plan, contexte_pack, dossier, reponse_dict)
    socle = reponse_dict.get("socle") or {}
    resultat = {
        "tenant": tenant,
        "scope": ("enterprise" if global_scope and not p.domaine else "portfolio")
        if global_scope else "application",
        "domaine": p.domaine,
        "profil": _assainir(profil.as_dict()),
        "composition": _assainir(plan.as_dict()),
        "specialistes_executes": list(noms),
        "dossier": _assainir(dossier),
        "reponse": _assainir(reponse_dict),
        "contexte": _assainir(contexte_pack),
        "contexte_resolu": _assainir(contexte_resolu.as_dict()),
        "raisonnement": _assainir(trace.as_dict()),
        "prediction": _assainir(prediction),
        "memoire_session": _assainir(session_resultat) if session_resultat is not None else None,
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
        resultat["valeur"] = _assainir(valeur)
    verifier()

    async def evaluer():
        return evaluation_cognitive.evaluer(resultat)

    resultat["evaluation"] = await _phase(
        processus, "evaluation", 3, {"run_id": run_id}, evaluer, sortie=_assainir)
    return resultat
