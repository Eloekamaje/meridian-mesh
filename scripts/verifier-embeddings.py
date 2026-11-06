#!/usr/bin/env python3
"""Vérifie le retrieval sémantique réel : provider, dimension et similarité de paraphrases.

Ne journalise aucun secret. Sort en code 2 si aucun provider sémantique n'est actif.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(RACINE / "backend" / ".env")

from meridian.adapters.outbound import embeddings  # noqa: E402
from meridian.application import retrieval_hybride  # noqa: E402

PAIRES = (
    ("Conduit permet aux auteurs de publier des articles.",
     "Les auteurs peuvent écrire et publier des textes sur Conduit."),
    ("La base de données conserve les articles et les comptes.",
     "PostgreSQL stocke les textes, les utilisateurs et les favoris."),
    ("Seul l'auteur peut modifier ou supprimer son article.",
     "Un article ne peut être corrigé que par la personne qui l'a écrit."),
    ("Un lecteur peut mettre un article en favori.",
     "Le lecteur peut garder un article pour le retrouver plus tard."),
)
HORS_SUJET = "La météo marine annonce des vents forts sur la Manche."


def main(argv=None) -> int:
    analyseur = argparse.ArgumentParser(description="Vérifie les embeddings réels.")
    analyseur.add_argument("--sortie", type=Path, help="Écrit le résultat JSON.")
    args = analyseur.parse_args(argv)
    etat = embeddings.statut()
    print(f"provider={etat['provider']} modele={etat['modele']} "
          f"dimension={etat['dimension']} semantique={etat['semantique']}")
    if not etat["semantique"]:
        print("Aucun provider sémantique actif : le retrieval reste lexical + graphe.", file=sys.stderr)
        return 2
    textes = [texte for paire in PAIRES for texte in paire] + [HORS_SUJET]
    vecteurs = embeddings.embed(textes)
    if len(vecteurs) != len(textes):
        print("Le provider n'a pas rendu un vecteur par texte.", file=sys.stderr)
        return 1
    resultats = []
    for index, (gauche, droite) in enumerate(PAIRES):
        vg, vd = vecteurs[index * 2], vecteurs[index * 2 + 1]
        vh = vecteurs[-1]
        proche = retrieval_hybride.cosinus(vg, vd)
        loin = retrieval_hybride.cosinus(vg, vh)
        resultats.append({"gauche": gauche, "droite": droite,
                          "cosinus_paraphrase": round(proche, 4),
                          "cosinus_hors_sujet": round(loin, 4)})
        print(f"- paraphrase={proche:.3f} hors_sujet={loin:.3f} :: {gauche[:60]}")
    if args.sortie:
        import json
        args.sortie.write_text(json.dumps({"statut": etat, "resultats": resultats},
                                          ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"écrit {args.sortie}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
