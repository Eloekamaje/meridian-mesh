"""Évaluation du jumeau : un jeu de référence tiré du jumeau lui-même (Jumeau Harness v3 §6).

    python -m jumeau.evaluation --jumeau tbt [--max 10]

Deux étages : l'exactitude (les connaissances validées sont les réponses attendues) et l'ancrage (les sept
questions de la méthode comprendre-application). Chaque réponse passe par le vrai chemin de Flore ; un juge sans
outils rend une décision structurée. Chaque passe est enregistrée (table evaluation) pour suivre la tendance.
"""
import argparse
import asyncio
import json
import hashlib
import logging
import os
import re
import time
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field
from strands import Agent

from jumeau import agent, comprendre, connaissance, depot, flore, methodes
from jumeau.connaissance import RE_CITATION
from jumeau.lecteurs import RE_CITATION_SOURCE

journal = logging.getLogger("meridian.evaluation")
MAX_PAR_DEFAUT = 10
RE_QUESTION = re.compile(r"^\d+\.\s+\*\*(?P<titre>[^*]+)\*\*\s*:\s*(?P<corps>.+?)(?:\s+Prédicat\b.*)?$")
TITRES = {predicat: titre for _, titre, predicat, _ in comprendre.QUESTIONS if predicat}

PROMPT_JUGE = """Tu juges la réponse de Flore à une question sur une application. Tu ne réécris rien et tu n'enquêtes pas.
- contient_attendu : la réponse dit-elle, même avec d'autres mots, l'information attendue (faux si rien n'est attendu) ?
- contredit : la réponse affirme-t-elle le contraire de l'information attendue ?
- affirmations : nombre d'affirmations factuelles sur l'application dans la réponse.
- appuyees : parmi elles, combien sont suivies d'une citation `chemin#Ldébut-Lfin` ou d'une citation de source."""


class Jugement(BaseModel):
    contient_attendu: bool = Field(description="la réponse contient l'information attendue")
    contredit: bool = Field(description="la réponse contredit l'information attendue")
    affirmations: int = Field(description="nombre d'affirmations factuelles")
    appuyees: int = Field(description="affirmations appuyées par une citation")


def questions_ancrage():
    """Les sept questions, lues dans la méthode (titre et description, sans le prédicat)."""
    section = (methodes.lire("comprendre-application") or "").partition("## Les sept questions")[2]
    trouvees = (RE_QUESTION.match(l.strip()) for l in section.splitlines())
    return [f"{m['titre'].strip()} : {m['corps'].strip()}" for m in trouvees if m]


REFERENCES = Path(__file__).with_name("references")  # questions/réponses écrites à la main, par jumeau


def questions_reference(jumeau_id):
    """Le jeu d'exactitude ne pouvait pas se déduire du jumeau : il repose sur ses connaissances **validées**, et la
    base en compte une seule. Faute de vérité de référence, la mesure valait `null` (plan de remédiation L2.2) ;
    ces couples question/réponse sont donc écrits à la main, dans `jumeau/references/<jumeau>.json`."""
    fichier = REFERENCES / f"{jumeau_id}.json"
    if not fichier.exists():
        return []
    return [{"etage": "exactitude", "question": d["question"], "attendu": d["attendu"]}
            for d in json.loads(fichier.read_text(encoding="utf-8"))]


def construire_jeu(nom, claims, maximum=MAX_PAR_DEFAUT, jumeau_id=None):
    """Exactitude (au plus la moitié du budget, un prédicat après l'autre) puis ancrage, en tout ≤ `maximum`.
    Les couples écrits à la main passent en premier : ce sont les seuls qui ne dépendent d'aucune validation."""
    par_predicat = [[c for c in claims if c["statut"] == "ACCEPTED" and c["predicat"] == p] for p in TITRES]
    exacts = [{"etage": "exactitude", "question": f"{nom} — {TITRES[c['predicat']].lower()} ?", "attendu": c["objet"]}
              for rang in zip(*(l + [None] * (max(map(len, par_predicat)) - len(l)) for l in par_predicat))
              for c in rang if c][: maximum // 2]
    ecrits = questions_reference(jumeau_id)[: maximum // 2] if jumeau_id else []
    ancrage = [{"etage": "ancrage", "question": q, "attendu": None} for q in questions_ancrage()]
    return (ecrits + [e for e in exacts if len(ecrits) + len(exacts) <= maximum])[:maximum] + \
        ancrage[: max(0, maximum - len(ecrits) - len(exacts))]


def empreinte_methodes(dossier=methodes.DOSSIER, charte=agent.CHARTE):
    h = hashlib.sha256()
    for chemin in [*sorted(dossier.glob("*.md")), charte]:
        h.update(chemin.name.encode() + b"\0" + chemin.read_bytes())
    return h.hexdigest()[:12]


def _nom_modele():
    try:
        return str(agent.modele().get_config().get("model_id"))
    except Exception:
        return os.environ.get("JUMEAU_MODELE", "deepseek")


async def _juger(question, reponse, attendu):
    juge = Agent(model=agent.modele(), system_prompt=PROMPT_JUGE, callback_handler=None)
    consigne = f"Question : {question}\nInformation attendue : {attendu or '(aucune)'}\n\nRéponse :\n{reponse}"
    # Structure imposée par un appel d'outil (structured_output_async ne marche pas avec DeepSeek).
    return (await juge.invoke_async(consigne, structured_output_model=Jugement)).structured_output


def _citations(texte):
    return ({connaissance.cle_citation(*connaissance.decouper(m)) for m in RE_CITATION.finditer(texte)}
            | {m.group(0) for m in RE_CITATION_SOURCE.finditer(texte)})


async def _poser(jumeau_id, cas):
    """Une question : réponse par Flore, jugement, durée. Toute panne est consignée, elle ne propage pas."""
    detail = {"etage": cas["etage"], "question": cas["question"], "attendu": cas["attendu"]}
    debut, trace = time.monotonic(), {}
    try:
        reponse = await flore.repondre(jumeau_id, cas["question"], acteur="evaluation", trace=trace)
        if not reponse or reponse.get("comportement") == "signaler" or "texte" not in trace:
            raise RuntimeError((reponse or {}).get("reponse") or "jumeau non mobilisable")
        detail["duree_s"] = round(time.monotonic() - debut, 2)
        citations = _citations(trace["texte"])
        detail["citations"], detail["invalides"] = len(citations), len(set(trace["invalides"]) & citations)
        detail["jugement"] = (await _juger(cas["question"], trace["texte"], cas["attendu"])).model_dump()
    except Exception as e:
        journal.warning("évaluation : question en panne : %s", cas["question"], exc_info=True)
        detail["panne"] = f"{type(e).__name__}: {e}"
    return detail


def _part(num, den):
    return round(num / den, 3) if den else None


async def passe(jumeau_id, jeu):
    """(scores, détails) d'une passe sur `jeu`, question après question."""
    details = [await _poser(jumeau_id, cas) for cas in jeu]
    juges = [d for d in details if "jugement" in d]
    exacts = [d["jugement"] for d in juges if d["etage"] == "exactitude"]
    ancres = [d["jugement"] for d in juges if d["etage"] == "ancrage"]
    repondus = [d for d in details if "duree_s" in d]
    citations = sum(d["citations"] for d in repondus)
    scores = {
        "questions": len(jeu),
        "pannes": sum(1 for d in details if "panne" in d),
        "exactitude": _part(sum(j["contient_attendu"] and not j["contredit"] for j in exacts), len(exacts)),
        "contradictions": sum(j["contredit"] for j in exacts),
        "citations_valides": _part(citations - sum(d["invalides"] for d in repondus), citations),
        "affirmations_appuyees": _part(sum(j["appuyees"] for j in ancres), sum(j["affirmations"] for j in ancres)),
        "duree_moyenne_s": _part(sum(d["duree_s"] for d in repondus), len(repondus)),
    }
    return scores, details


def enregistrer(conn, jumeau_id, version, modele, scores, details):
    conn.execute("INSERT INTO evaluation (jumeau_id, version_methodes, modele, scores, details) VALUES (%s, %s, %s, %s, %s)",
                 (jumeau_id, version, modele, Jsonb(scores), Jsonb(details)))


async def evaluer(conn, jumeau_id, maximum=MAX_PAR_DEFAUT):
    jumeau = depot.jumeau_par_id(conn, jumeau_id)
    if not jumeau:
        raise LookupError(f"jumeau inconnu : {jumeau_id}")
    claims = connaissance.connaissances(conn, jumeau_id, limite=1000)
    scores, details = await passe(jumeau_id, construire_jeu(jumeau["nom"], claims, maximum, jumeau_id))
    enregistrer(conn, jumeau_id, empreinte_methodes(), _nom_modele(), scores, details)
    return scores


MAX_QUESTIONS = 50  # coût borné : deux appels au modèle par question


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--jumeau", required=True)
    p.add_argument("--max", type=int, default=MAX_PAR_DEFAUT, help="questions au plus (une réponse + un jugement chacune)")
    a = p.parse_args()
    if not 1 <= a.max <= MAX_QUESTIONS:
        p.error(f"--max entre 1 et {MAX_QUESTIONS}")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    with psycopg.connect(os.environ["JUMEAU_PG_DSN"], autocommit=True) as conn:
        print(asyncio.run(evaluer(conn, a.jumeau, a.max)))


if __name__ == "__main__":
    main()
