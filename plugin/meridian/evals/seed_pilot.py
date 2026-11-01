#!/usr/bin/env python3
"""Amorce le tenant synthétique ``pilot`` du pilote Méridian.

Le seed est idempotent et strictement séparé du tenant ``demo`` : il crée quatre
Twins, deux Situations canoniques et des Claims/Preuves minimales marquées
``synthetic``. Les preuves portent les termes des scénarios (SLA, preuve, R-118,
limite) dans un locator lisible ; aucun résultat, aucune décision et aucun
outcome ne sont inventés.

Le script écrit directement dans Postgres via les dépôts canoniques, car il
n'existe pas de route HTTP de création de Situation. Utiliser le Python du
backend, avec ``JUMEAU_PG_DSN`` défini (ou ``--dsn``).
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import json
import os
from pathlib import Path
import sys

RACINE = Path(__file__).resolve().parents[3]
BACKEND = RACINE / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

TENANT = "pilot"
FIXTURE = "pilot-2026-11-01"
SYNTHETIC = "[SYNTHÉTIQUE]"
PERSONA = "architecte"
DATE_FIXTURE = "2026-11-01T14:32:00+00:00"

TWINS = (
    {"id": "paiements", "type": "APPLICATION", "nom": "Paiements", "domaine": "Paiement",
     "mission": f"{SYNTHETIC} Parcours de paiement du pilote."},
    {"id": "comptes", "type": "APPLICATION", "nom": "Comptes", "domaine": "Client",
     "mission": f"{SYNTHETIC} Comptes et soldes du pilote."},
    {"id": "fraude", "type": "APPLICATION", "nom": "Fraude", "domaine": "Risque",
     "mission": f"{SYNTHETIC} Contrôles Fraude du pilote."},
    {"id": "support", "type": "APPLICATION", "nom": "Support", "domaine": "Support",
     "mission": f"{SYNTHETIC} Support client du pilote."},
)

SITUATIONS = (
    {
        "id": "sit-latence-paiements",
        "titre": f"{SYNTHETIC} Latence du parcours de paiement depuis 14 h 32",
        "donnees": {
            "synthetic": True,
            "fixture": FIXTURE,
            "score": 94,
            "verbe": "a_decider",
            "nature": "incident",
            "resume": (
                f"{SYNTHETIC} La latence de paiement a dérivé de 240 ms à 1,9 s. "
                "Le SLA n'est pas prouvé sur la fenêtre observée ; la piste R-118 reste "
                "une hypothèse et la limite de mesure est explicite."
            ),
            "statut": "ACTIVE",
            "priorite": "CRITIQUE",
            "question": "Pourquoi le parcours de paiement ralentit-il ?",
            "twin_ids": ["paiements", "comptes", "fraude", "support"],
            "preuves": [
                {"detail": "Preuve synthétique SLA : dérive de latence sur 14 h 32–14 h 45",
                 "source": "Fixture pilote synthétique"},
                {"detail": "Preuve synthétique R-118 : contrôle synchrone modifié à 13 h 58",
                 "source": "Fixture pilote synthétique"},
            ],
            "hypotheses": [
                {"id": "h1", "texte": "Contrôles synchrones R-118", "confiance": 78,
                 "pour": ["4 traces synthétiques d'attente sur Fraude"],
                 "contre": ["Causalité non confirmée"], "verifications": ["Comparer avec un témoin"]},
            ],
            "chronologie": [
                {"heure": "14 h 32", "texte": "Dérive de latence détectée", "jumeau": "paiements",
                 "nature": "signal"},
                {"heure": "14 h 39", "texte": "Premiers tickets Support", "jumeau": "support",
                 "nature": "signal"},
            ],
            "actions_proposees": ["Basculer R-118 en asynchrone après approbation"],
            "decisions_attendues": ["Valider le basculement R-118", "Surveiller sans action immédiate"],
            "limites": ["Fenêtre d'observation courte", "Preuve R-118 à revérifier"],
        },
    },
    {
        "id": "sit-anomalie-fraude",
        "titre": f"{SYNTHETIC} Contrôles Fraude en hausse depuis la règle R-118",
        "donnees": {
            "synthetic": True,
            "fixture": FIXTURE,
            "score": 61,
            "verbe": "a_comprendre",
            "nature": "comportement",
            "resume": (
                f"{SYNTHETIC} Les contrôles synchrones par transaction sont passés de 1,2 à 3,4. "
                "L'impact et l'interface restent à confirmer ; toute écriture exige une approbation."
            ),
            "statut": "ACTIVE",
            "priorite": "MOYENNE",
            "question": "Pourquoi les contrôles Fraude ont-ils augmenté ?",
            "twin_ids": ["fraude", "paiements"],
            "preuves": [
                {"detail": "Preuve synthétique R-118 : règle modifiée à 13 h 58",
                 "source": "Fixture pilote synthétique"},
            ],
            "hypotheses": [
                {"id": "h1", "texte": "R-118 déclenche des contrôles supplémentaires", "confiance": 78,
                 "pour": ["Corrélation temporelle synthétique"], "contre": ["Comportement déclaré nominal"],
                 "verifications": ["Confirmer le périmètre R-118"]},
            ],
            "chronologie": [
                {"heure": "13 h 58", "texte": "Règle R-118 modifiée", "jumeau": "fraude",
                 "nature": "signal"},
            ],
            "actions_proposees": ["Ouvrir une investigation après approbation"],
            "decisions_attendues": ["Ouvrir une investigation", "Surveiller"],
            "limites": ["Périmètre exact de R-118 inconnu", "Preuve à revérifier"],
        },
    },
)

CLAIMS = (
    {
        "twin_id": "paiements",
        "predicat": "SLA_PAIEMENT",
        "objet": "SLA de 99,9 % non prouvé sur la fenêtre 14 h 32–14 h 45",
        "confiance": 0.45,
        "locator": "synthetic://pilot/sit-latence-paiements/SLA-preuve-limite#L1-L1",
        "chemin": "pilot/sit-latence-paiements/SLA-preuve-limite.md",
        "texte": ("Preuve synthétique : le SLA de paiement n'est pas prouvé sur la fenêtre observée ; "
                  "la limite de mesure est la durée de 13 minutes."),
    },
    {
        "twin_id": "fraude",
        "predicat": "APPLIQUE_REGLE",
        "objet": "R-118 — contrôle synchrone, preuve et limite à confirmer",
        "confiance": 0.45,
        "locator": "synthetic://pilot/sit-latence-paiements/R-118-preuve-limite#L1-L1",
        "chemin": "pilot/sit-latence-paiements/R-118-preuve-limite.md",
        "texte": ("Preuve synthétique : la règle R-118 a été modifiée à 13 h 58 ; "
                  "la preuve reste déclarative et la limite est l'absence de trace directe."),
    },
    {
        "twin_id": "comptes",
        "predicat": "DEPEND_DE",
        "objet": "paiements — dépendance observée pendant l'incident",
        "confiance": 0.55,
        "locator": "synthetic://pilot/sit-latence-paiements/comptes-preuve#L1-L1",
        "chemin": "pilot/sit-latence-paiements/comptes-preuve.md",
        "texte": "Preuve synthétique : les appels Comptes augmentent pendant la dérive de paiement.",
    },
    {
        "twin_id": "support",
        "predicat": "RECOIT_TICKETS",
        "objet": "tickets liés aux délais de paiement",
        "confiance": 0.55,
        "locator": "synthetic://pilot/sit-latence-paiements/support-preuve#L1-L1",
        "chemin": "pilot/sit-latence-paiements/support-preuve.md",
        "texte": "Preuve synthétique : des tickets Support apparaissent après la dérive de paiement.",
    },
    {
        "twin_id": "fraude",
        "predicat": "CHANGEMENT_REGLEMENTAIRE",
        "objet": "R-118 — impact, interface et approbation requise",
        "confiance": 0.4,
        "locator": ("synthetic://pilot/sit-anomalie-fraude/"
                    "R-118-impact-interface-approbation-preuve-limite#L1-L1"),
        "chemin": "pilot/sit-anomalie-fraude/R-118-impact-interface-approbation-preuve-limite.md",
        "texte": ("Preuve synthétique : le changement R-118 touche l'interface de contrôle ; "
                  "l'impact reste inféré, la preuve est déclarative, l'approbation est requise "
                  "et la limite est le périmètre exact de la règle."),
    },
    {
        "twin_id": "paiements",
        "predicat": "IMPACTE_PAR",
        "objet": "R-118 impacte le parcours de paiement",
        "confiance": 0.4,
        "locator": "synthetic://pilot/sit-anomalie-fraude/R-118-paiements-impact-preuve-limite#L1-L1",
        "chemin": "pilot/sit-anomalie-fraude/R-118-paiements-impact-preuve-limite.md",
        "texte": ("Preuve synthétique : l'impact de R-118 sur les paiements est inféré ; "
                  "la preuve et la limite de mesure sont explicites."),
    },
)


def _dsn(valeur: str | None = None) -> str:
    """Résout le DSN sans jamais l'afficher."""
    if valeur:
        return valeur
    charge = os.environ.get("JUMEAU_PG_DSN")
    if charge:
        return charge
    try:
        from dotenv import load_dotenv
    except ImportError:
        pass
    else:
        load_dotenv(BACKEND / ".env")
        charge = os.environ.get("JUMEAU_PG_DSN")
        if charge:
            return charge
    raise SystemExit("JUMEAU_PG_DSN absent : définir l'environnement ou passer --dsn")


def _contexte(conn, tenant: str):
    from meridian.adapters.outbound.postgres import rls

    return rls.contexte_tenant(conn, tenant) if rls.est_actif() else nullcontext()


def _situation_existe(conn, tenant: str, identifiant: str):
    from meridian.adapters.outbound.postgres import entreprise_depot

    return entreprise_depot.lire_objet(conn, tenant, identifiant)


def _ecrire_situations(conn, tenant: str) -> list[dict]:
    from meridian.adapters.outbound.postgres import entreprise_depot

    resultats = []
    for situation in SITUATIONS:
        existant = _situation_existe(conn, tenant, situation["id"])
        payload = {
            "id": situation["id"],
            "famille": "emergence",
            "type": "SITUATION",
            "mode": "OBSERVED",
            "titre": situation["titre"],
            "donnees": situation["donnees"],
            "observe_le": DATE_FIXTURE,
            "valide_depuis": DATE_FIXTURE,
        }
        if existant is not None:
            payload["version"] = existant["version"]
        ligne = entreprise_depot.enregistrer_objet(conn, tenant, payload)
        resultats.append({
            "id": ligne["id"],
            "created": existant is None,
            "version": ligne["version"],
            "synthetic": True,
        })
    return resultats


def _ecrire_claims(conn, tenant: str) -> list[dict]:
    from meridian.adapters.outbound.postgres import twins_types

    resultats = []
    for claim in CLAIMS:
        ligne = twins_types.creer_claim(
            conn, tenant, claim["twin_id"], claim["predicat"], claim["objet"],
            source="Fixture pilote synthétique",
            preuve={
                "type": "DOCUMENTATION",
                "locator": claim["locator"],
                "chemin": claim["chemin"],
                "citation": claim["texte"],
                "activite": {"extracteur": "seed_pilot", "fixture": FIXTURE,
                             "synthetic": True},
            },
            mode="DECLARED",
            confiance=claim["confiance"],
            acteur=PERSONA,
            texte=claim["texte"],
        )
        resultats.append({
            "id": ligne["id"],
            "twin_id": claim["twin_id"],
            "predicat": claim["predicat"],
            "statut": ligne.get("statut"),
            "synthetic": True,
        })
    return resultats


def plan() -> dict:
    """Rend le plan du fixture sans toucher à la base."""
    return {
        "tenant": TENANT,
        "synthetic": True,
        "fixture": FIXTURE,
        "twins": [dict(twin) for twin in TWINS],
        "situations": [{"id": s["id"], "titre": s["titre"]} for s in SITUATIONS],
        "claims": [
            {"twin_id": c["twin_id"], "predicat": c["predicat"], "locator": c["locator"]}
            for c in CLAIMS
        ],
    }


def executer(dsn: str | None = None, tenant: str = TENANT, dry_run: bool = False) -> dict:
    """Applique le fixture et retourne un résumé JSON-compatible."""
    if tenant != TENANT:
        raise ValueError(f"tenant refusé : {tenant!r} (le seed ne touche que {TENANT!r})")
    resume = {
        "tenant": tenant,
        "synthetic": True,
        "fixture": FIXTURE,
        "dry_run": bool(dry_run),
        "twins": [],
        "situations": [],
        "claims": [],
        "ok": True,
    }
    if dry_run:
        resume.update(plan())
        return resume

    import psycopg
    from meridian.adapters.outbound.postgres import twins_types

    with psycopg.connect(_dsn(dsn), connect_timeout=5) as conn:
        with _contexte(conn, tenant):
            for twin in TWINS:
                ligne = twins_types.creer_twin(
                    conn, tenant, twin["id"], twin["type"], twin["nom"],
                    mission=twin["mission"], domaine=twin["domaine"],
                    equipe="Fixture pilote", acteur=PERSONA,
                    preuve={"fixture": FIXTURE, "synthetic": True},
                )
                resume["twins"].append({
                    "id": ligne["id"], "type": ligne["type"], "nom": ligne["nom"],
                    "tenant": ligne["tenant_id"], "synthetic": True,
                })
            resume["situations"] = _ecrire_situations(conn, tenant)
            resume["claims"] = _ecrire_claims(conn, tenant)
    return resume


def main(argv: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(
        description="Amorce le tenant synthétique pilot du pilote Méridian.")
    analyseur.add_argument("--dsn", help="DSN Postgres (défaut : JUMEAU_PG_DSN).")
    analyseur.add_argument("--tenant", default=TENANT,
                           help=f"Tenant cible (seul {TENANT} est accepté).")
    analyseur.add_argument("--dry-run", action="store_true",
                           help="Affiche le fixture sans écrire dans Postgres.")
    arguments = analyseur.parse_args(argv)
    try:
        resume = executer(dsn=arguments.dsn, tenant=arguments.tenant,
                          dry_run=arguments.dry_run)
    except (OSError, RuntimeError, ValueError) as exc:
        resume = {
            "tenant": arguments.tenant,
            "synthetic": True,
            "dry_run": bool(arguments.dry_run),
            "ok": False,
            "erreurs": [str(exc)],
        }
    print(json.dumps(resume, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if resume.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
