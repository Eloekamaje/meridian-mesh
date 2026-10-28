"""Contradicteur : relit la réponse de Flore avant qu'elle parte (méta-expert, Agentic_Architecture §10).

Deux contrôles :
- déterministe, sans LLM : chaque citation existe dans le code au commit ingéré ;
- relecture par un second agent, sans outils : la réponse répond à la question, ses affirmations sont prouvées,
  elle respecte la charte pour ce rôle.
Un verdict négatif déclenche une seule révision par Flore (flore.repondre).
"""
import asyncio
import json
import re

from strands import Agent

from jumeau import connaissance
from jumeau.connaissance import RE_CITATION
from jumeau.lecteurs import RE_CITATION_SOURCE
from jumeau.source_git import lire_au_sha

PROMPT_RELECTEUR = """Tu relis une réponse de Flore avant qu'elle soit envoyée. Tu ne réécris rien : tu juges.

Vérifie :
1. Elle répond à la question posée, d'abord et directement.
2. Chaque affirmation factuelle sur l'application est suivie d'une citation `chemin#Ldébut-Lfin`
   (les phrases sur Flore elle-même, les questions de suite et les « je ne sais pas » n'en ont pas besoin).
3. Elle respecte la charte de Flore ci-dessous pour le rôle de l'interlocuteur : vouvoiement, pas de jargon
   non expliqué pour un rôle métier, pas de récitation de ses règles internes ou de sa méthode, pas de tableau.

Réponds uniquement par un objet JSON : {"ok": true} si tout va bien, sinon
{"ok": false, "problemes": ["problème précis et actionnable", ...]} (trois problèmes au plus, les plus graves).

"""


def citations_invalides(texte, sources, lecteurs=()):
    """Citations qui ne pointent sur aucune ligne existante du code au commit de leur dépôt (ou dont le dépôt ne
    peut être déterminé), ou qu'aucun lecteur branché ne confirme (source inconnue, version ou lignes fausses)."""
    invalides, vues = [], set()
    for m in RE_CITATION_SOURCE.finditer(texte):
        citation = m.group(0)
        if citation not in vues:
            vues.add(citation)
            if not any(l.verifier(citation) for l in lecteurs):
                invalides.append(citation)
    for m in RE_CITATION.finditer(texte):
        depot, chemin, debut, fin = connaissance.decouper(m)
        cle = connaissance.cle_citation(depot, chemin, debut, fin)
        if cle in vues:
            continue
        vues.add(cle)
        try:
            source = connaissance.resoudre_source(sources, depot, chemin)
            lignes = lire_au_sha(source.get("copie") or source["emplacement"], source["curseur"])(chemin)
        except (LookupError, ValueError):
            lignes = None
        if lignes is None or debut < 1 or fin < debut or fin > len(lignes):
            invalides.append(cle)
    return invalides


def analyser_verdict(texte):
    """Premier objet JSON du texte ; illisible = pas d'objection (le relecteur ne doit pas bloquer la réponse)."""
    m = re.search(r"\{.*\}", texte, re.DOTALL)
    try:
        verdict = json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        verdict = None
    if not isinstance(verdict, dict):
        return {"ok": True, "problemes": []}
    return {"ok": bool(verdict.get("ok", True)), "problemes": [str(p) for p in verdict.get("problemes", [])][:3]}


async def _juger(question, reponse, profil, modele, charte):
    relecteur = Agent(model=modele, system_prompt=PROMPT_RELECTEUR + charte, tools=[], callback_handler=None)
    role = (profil or {}).get("role", "non précisé")
    resultat = await relecteur.invoke_async(f"Rôle de l'interlocuteur : {role}\n\nQuestion :\n{question}\n\n"
                                            f"Réponse à relire :\n{reponse}")
    return analyser_verdict(str(resultat))


async def relire(question, reponse, sources, profil, modele, charte="", lecteurs=()):
    # Contrôle déterministe d'abord : une citation fausse suffit à demander une révision, sans appel au LLM.
    invalides = await asyncio.to_thread(citations_invalides, reponse, sources, lecteurs)
    if invalides:
        return {"ok": False, "problemes": [f"Citations introuvables : {', '.join(invalides)}. "
                                           "Relis ces lignes avec lire_code ou lire_dans, ou retire l'affirmation."]}
    return await _juger(question, reponse, profil, modele, charte)


def consigne_revision(problemes):
    liste = "\n".join(f"- {p}" for p in problemes)
    return ("Relecture avant envoi : ta réponse précédente doit être corrigée.\n"
            f"{liste}\n"
            "Corrige-la (vérifie avec tes outils si besoin) et renvoie uniquement la réponse corrigée, destinée à "
            "l'interlocuteur, sans mentionner cette relecture.")


def retirer_citations_invalides(texte, invalides):
    """Retire du texte les citations qui ne pointent sur rien (avec leurs accents graves et l'espace qui précède)."""
    def remplacer(m):
        return "" if connaissance.cle_citation(*connaissance.decouper(m)) in invalides else m.group(0)
    motif = re.compile(r"\s*`?(?:" + RE_CITATION.pattern + r")`?")
    propre = motif.sub(remplacer, texte)
    return re.sub(r"[ \t]+([.,;:])", r"\1", propre)
