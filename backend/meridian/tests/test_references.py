"""Le jeu d'exactitude a une vérité de référence écrite à la main (plan de remédiation L2.2).

Il se déduisait des connaissances **validées** du jumeau — la base en compte une seule —, d'où un score
`exactitude: null` : une mesure qui n'existait pas. Les couples question/réponse vivent maintenant dans
`meridian/adapters/outbound/llm/references/<jumeau>.json`, écrits par un humain.
"""
import json
from pathlib import Path

from meridian.adapters.outbound.llm import evaluation


def test_le_jeu_commence_par_les_references_ecrites_a_la_main():
    jeu = evaluation.construire_jeu("Conduit", [], 10, "conduit")
    exacts = [q for q in jeu if q["etage"] == "exactitude"]
    assert len(exacts) == 5 and all(q["attendu"] for q in exacts)
    assert jeu[0]["question"].startswith("Sur quel moteur")


def test_un_jumeau_sans_reference_n_invente_pas_d_exactitude():
    jeu = evaluation.construire_jeu("Conduit", [], 10, "inconnu")
    assert not [q for q in jeu if q["etage"] == "exactitude"]


def test_les_references_sont_des_questions_reelles_et_verifiables():
    for fichier in sorted((Path(evaluation.__file__).parent / "references").glob("*.json")):
        if fichier.name == "verdicts.json":
            continue  # autre format : cas de verdicts du juge (test_verdicts.py)
        couples = json.loads(fichier.read_text(encoding="utf-8"))
        assert couples, fichier
        for c in couples:
            # Une question doit finir par un point d'interrogation et sa réponse attendue être courte et parlante.
            assert c["question"].strip().endswith("?") and 2 <= len(c["attendu"]) <= 40, (fichier.name, c)
