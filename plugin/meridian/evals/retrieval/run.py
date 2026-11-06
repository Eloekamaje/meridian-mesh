#!/usr/bin/env python3
"""Benchmark retrieval lexical + graphe vs hybride avec embeddings réels.

Le corpus et les requêtes sont synthétiques ; les embeddings sont calculés par le
provider configuré (Bedrock Titan par défaut). Aucun résultat n'est inventé : sans
provider sémantique, le runner le dit et sort en code 2.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

RACINE = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(RACINE / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(RACINE / "backend" / ".env")

from meridian.adapters.outbound import embeddings  # noqa: E402
from meridian.application import retrieval_hybride  # noqa: E402

CAS_DEFAUT = Path(__file__).with_name("cases.json")


class BenchmarkErreur(RuntimeError):
    pass


def charger(chemin: Path) -> dict:
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkErreur(f"lecture du corpus impossible: {exc}") from exc
    chunks = donnees.get("chunks") if isinstance(donnees, dict) else None
    queries = donnees.get("queries") if isinstance(donnees, dict) else None
    if not isinstance(chunks, list) or not chunks or not isinstance(queries, list) or not queries:
        raise BenchmarkErreur("corpus ou requêtes vide")
    identifiants = {str(chunk.get("id") or "") for chunk in chunks}
    if "" in identifiants or len(identifiants) != len(chunks):
        raise BenchmarkErreur("identifiants de chunks absents ou dupliqués")
    for query in queries:
        if not str(query.get("question") or "").strip():
            raise BenchmarkErreur("requête vide")
        if str(query.get("attendu") or "") not in identifiants:
            raise BenchmarkErreur(f"chunk attendu inconnu: {query.get('attendu')}")
    return {"chunks": chunks, "queries": queries}


def classer(question: str, chunks: list[dict], vecteur_question=None) -> list[dict]:
    classement = []
    for chunk in chunks:
        score = retrieval_hybride.score(
            question, chunk, vecteur_question=vecteur_question,
            proximite=None)
        classement.append({**chunk, "score": score})
    classement.sort(key=lambda chunk: (-chunk["score"], str(chunk["id"])))
    return classement


def metriques(resultats: list[dict], k: int = 3) -> dict:
    if not resultats:
        return {"n": 0, "hit1": 0.0, "hitk": 0.0, "mrr": 0.0}
    hit1 = sum(1 for resultat in resultats if resultat["rang"] == 1) / len(resultats)
    hitk = sum(1 for resultat in resultats if 1 <= resultat["rang"] <= k) / len(resultats)
    mrr = sum(1.0 / resultat["rang"] if resultat["rang"] > 0 else 0.0
              for resultat in resultats) / len(resultats)
    return {"n": len(resultats), "hit1": round(hit1, 3),
            "hitk": round(hitk, 3), "mrr": round(mrr, 3)}


def evaluer(donnees: dict, vecteurs_chunks: list[list[float]],
            vecteurs_questions: list[list[float]], k: int = 3) -> dict:
    chunks = [dict(chunk, embedding=vecteur)
              for chunk, vecteur in zip(donnees["chunks"], vecteurs_chunks)]
    resultats = []
    for query, vecteur in zip(donnees["queries"], vecteurs_questions):
        classement_lexical = classer(query["question"], chunks, None)
        classement_hybride = classer(query["question"], chunks, vecteur)
        rang_lexical = next((index for index, chunk in enumerate(classement_lexical, 1)
                             if chunk["id"] == query["attendu"]), 0)
        rang_hybride = next((index for index, chunk in enumerate(classement_hybride, 1)
                             if chunk["id"] == query["attendu"]), 0)
        resultats.append({
            "id": query["id"], "categorie": query.get("categorie") or "",
            "question": query["question"], "attendu": query["attendu"],
            "rang_lexical": rang_lexical, "rang_hybride": rang_hybride,
            "premier_lexical": classement_lexical[0]["id"] if classement_lexical else "",
            "premier_hybride": classement_hybride[0]["id"] if classement_hybride else "",
        })
    lexical = metriques([{"rang": resultat["rang_lexical"]} for resultat in resultats], k)
    hybride = metriques([{"rang": resultat["rang_hybride"]} for resultat in resultats], k)
    return {"lexical": lexical, "hybride": hybride, "resultats": resultats}


def rapport_markdown(etat: dict, evaluation: dict, k: int) -> str:
    lignes = [
        "# Benchmark retrieval — lexical vs hybride",
        "",
        f"- Provider : `{etat['provider']}`",
        f"- Modèle : `{etat['modele']}`",
        f"- Dimension : {etat['dimension']}",
        f"- Requêtes : {evaluation['lexical']['n']}",
        "",
        "| Métrique | Lexical + graphe | Hybride (Bedrock) |",
        "|---|---:|---:|",
        f"| Hit@1 | {evaluation['lexical']['hit1']:.0%} | {evaluation['hybride']['hit1']:.0%} |",
        f"| Hit@{k} | {evaluation['lexical']['hitk']:.0%} | {evaluation['hybride']['hitk']:.0%} |",
        f"| MRR | {evaluation['lexical']['mrr']:.3f} | {evaluation['hybride']['mrr']:.3f} |",
        "",
        "## Détail",
        "",
        "| Requête | Attendu | Rang lexical | Rang hybride |",
        "|---|---|---:|---:|",
    ]
    for resultat in evaluation["resultats"]:
        lignes.append(f"| `{resultat['id']}` | `{resultat['attendu']}` | "
                      f"{resultat['rang_lexical'] or '—'} | {resultat['rang_hybride'] or '—'} |")
    lignes += [
        "",
        "## Lecture",
        "",
        "- Le classement lexical seul est calculé avec `retrieval_hybride.score` sans vecteur.",
        "- Le classement hybride ajoute la similarité cosinus entre la question et chaque chunk.",
        "- Le corpus est synthétique et petit : les chiffres mesurent la plomberie et la valeur",
        "  des paraphrases, pas la qualité d'un RAG complet.",
    ]
    return "\n".join(lignes) + "\n"


def main(argv=None) -> int:
    analyseur = argparse.ArgumentParser(description="Benchmark retrieval lexical vs hybride.")
    analyseur.add_argument("--cases", type=Path, default=CAS_DEFAUT)
    analyseur.add_argument("--output", type=Path)
    analyseur.add_argument("--k", type=int, default=3)
    args = analyseur.parse_args(argv)
    etat = embeddings.statut()
    print(f"provider={etat['provider']} modele={etat['modele']} "
          f"dimension={etat['dimension']} semantique={etat['semantique']}")
    if not etat["semantique"]:
        print("Aucun provider sémantique actif : lancer avec EMBEDDING_PROVIDER=bedrock "
              "et des credentials Bedrock.", file=sys.stderr)
        return 2
    donnees = charger(args.cases)
    try:
        vecteurs_chunks = embeddings.embed([chunk["texte"] for chunk in donnees["chunks"]])
        vecteurs_questions = embeddings.embed([query["question"] for query in donnees["queries"]])
    except embeddings.EmbeddingIndisponible as exc:
        print(f"Embeddings indisponibles : {exc}", file=sys.stderr)
        return 2
    evaluation = evaluer(donnees, vecteurs_chunks, vecteurs_questions, k=args.k)
    rapport = rapport_markdown(etat, evaluation, args.k)
    print(rapport)
    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "summary.json").write_text(
            json.dumps({"statut": etat, "evaluation": evaluation}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        (args.output / "REPORT.md").write_text(rapport, encoding="utf-8")
        print(f"écrit {args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BenchmarkErreur as erreur:
        print(f"ERREUR: {erreur}", file=sys.stderr)
        raise SystemExit(2)
