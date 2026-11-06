#!/usr/bin/env python3
"""Vérifie l'accès Bedrock réel : identité, catalogue, Converse/ConverseStream, embeddings.

Aucun secret n'est journalisé. Le profil vient de `--profil` ou de `AWS_PROFILE` ;
à défaut, la chaîne AWS standard (profil `default`, rôle d'instance, etc.).

Sortie :
- 0 : au moins un modèle de chat répond et les embeddings fonctionnent ;
- 2 : accès runtime bloqué (compte en vérification, formulaire, paiement, droits) ;
- 1 : erreur inattendue.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(RACINE / "backend" / ".env")

MODELES_CHAT = (
    "ca.amazon.nova-lite-v1:0",
    "anthropic.claude-3-sonnet-20240229-v1:0",
    "anthropic.claude-3-haiku-20240307-v1:0",
    "ca.anthropic.claude-haiku-5-5",
    "mistral.mistral-large-2402-v1:0",
    "meta.llama3-70b-instruct-v1:0",
    "openai.gpt-oss-120b-1:0",
    "openai.gpt-oss-20b-1:0",
    "us.moonshotai.kimi-k3",
    "global.moonshotai.kimi-k3",
    "us.openai.gpt-5.5",
    "us.openai.gpt-6-sol",
    "us.openai.gpt-6.1-sol",
)
MODELE_EMBEDDING = "amazon.titan-embed-text-v2:0"
PROMPT = "Réponds uniquement: ok"


def _session(profil, region):
    import boto3

    if profil:
        return boto3.Session(profile_name=profil, region_name=region)
    return boto3.Session(region_name=region)


def _essai_chat(runtime, modele):
    resultat = {"modele": modele}
    for operation in ("converse", "converse_stream"):
        debut = time.monotonic()
        try:
            if operation == "converse":
                reponse = runtime.converse(
                    modelId=modele,
                    messages=[{"role": "user", "content": [{"text": PROMPT}]}],
                    inferenceConfig={"maxTokens": 16},
                )
                texte = "".join(bloc.get("text", "")
                                 for bloc in reponse["output"]["message"]["content"])
            else:
                reponse = runtime.converse_stream(
                    modelId=modele,
                    messages=[{"role": "user", "content": [{"text": PROMPT}]}],
                    inferenceConfig={"maxTokens": 16},
                )
                evenements = list(reponse["stream"])
                texte = "".join(
                    evenement.get("contentBlockDelta", {}).get("delta", {}).get("text", "")
                    for evenement in evenements)
            resultat[operation] = {"ok": True, "duree_s": round(time.monotonic() - debut, 2),
                                   "extrait": texte[:80]}
        except Exception as exc:
            resultat[operation] = {"ok": False, "duree_s": round(time.monotonic() - debut, 2),
                                   "erreur": f"{type(exc).__name__}: {str(exc)[:220]}"}
    return resultat


def _essai_embeddings(runtime):
    debut = time.monotonic()
    try:
        reponse = runtime.invoke_model(
            modelId=MODELE_EMBEDDING,
            body=json.dumps({"inputText": "Conduit publie des articles.",
                             "dimensions": 1024, "normalize": True}),
        )
        donnees = json.loads(reponse["body"].read())
        return {"ok": True, "modele": MODELE_EMBEDDING,
                "dimension": len(donnees.get("embedding") or []),
                "duree_s": round(time.monotonic() - debut, 2)}
    except Exception as exc:
        return {"ok": False, "modele": MODELE_EMBEDDING,
                "erreur": f"{type(exc).__name__}: {str(exc)[:220]}",
                "duree_s": round(time.monotonic() - debut, 2)}


def main(argv=None) -> int:
    analyseur = argparse.ArgumentParser(description="Vérifie l'accès Bedrock réel.")
    analyseur.add_argument("--profil", default=os.environ.get("AWS_PROFILE") or None,
                           help="Profil AWS (défaut : AWS_PROFILE ou chaîne standard).")
    analyseur.add_argument("--region", default=os.environ.get("BEDROCK_REGION") or "ca-central-1")
    analyseur.add_argument("--sortie", type=Path, help="Écrit le résultat JSON.")
    args = analyseur.parse_args(argv)

    try:
        session = _session(args.profil, args.region)
        identite = session.client("sts").get_caller_identity()
        print(f"compte={identite['Account']} arn={identite['Arn']} region={args.region}")
        try:
            catalogue = session.client("bedrock").list_foundation_models()
            print(f"catalogue={len(catalogue.get('modelSummaries', []))} modeles")
        except Exception as exc:
            print(f"catalogue=indisponible ({type(exc).__name__}: {str(exc)[:160]})")
        runtime = session.client("bedrock-runtime")
    except Exception as exc:
        print(f"identité AWS indisponible : {type(exc).__name__}: {str(exc)[:220]}", file=sys.stderr)
        return 1

    resultats = {"identite": {"compte": identite["Account"], "arn": identite["Arn"],
                              "region": args.region},
                 "chat": [], "embeddings": None}
    for modele in MODELES_CHAT:
        resultat = _essai_chat(runtime, modele)
        resultats["chat"].append(resultat)
        etats = " ".join(f"{operation}={'ok' if resultat[operation]['ok'] else 'FAIL'}"
                         for operation in ("converse", "converse_stream"))
        print(f"- {modele:52s} {etats}")
        for operation in ("converse", "converse_stream"):
            if not resultat[operation]["ok"]:
                print(f"    {operation}: {resultat[operation]['erreur']}")

    resultats["embeddings"] = _essai_embeddings(runtime)
    emb = resultats["embeddings"]
    print(f"- {MODELE_EMBEDDING:52s} "
          + ("ok dim=" + str(emb["dimension"]) if emb["ok"] else "FAIL " + emb["erreur"]))

    if args.sortie:
        args.sortie.write_text(json.dumps(resultats, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
        print(f"écrit {args.sortie}")

    chat_ok = any(resultat["converse"]["ok"] or resultat["converse_stream"]["ok"]
                  for resultat in resultats["chat"])
    if chat_ok and emb["ok"]:
        return 0
    print("Accès Bedrock runtime incomplet : voir les erreurs ci-dessus.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
