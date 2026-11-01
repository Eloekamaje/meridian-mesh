"""Contradicteur : relit la réponse de Flore avant qu'elle parte (méta-expert, Agentic_Architecture §10).

Deux contrôles :
- déterministe, sans LLM : chaque citation existe dans le code au commit ingéré ;
- relecture par un second agent, sans outils : la réponse répond à la question, ses affirmations sont prouvées,
  elle respecte la charte pour ce rôle.
Un verdict négatif déclenche une seule révision par Flore (flore.repondre).
"""
import asyncio
import json
import logging
import re

from strands import Agent

from meridian.adapters.outbound.postgres import connaissance
from meridian.application import mesure
from meridian.adapters.outbound.postgres.connaissance import RE_CITATION
from meridian.adapters.outbound.connectors.lecteurs import RE_CITATION_SOURCE
from meridian.adapters.outbound.connectors.source_git import lire_au_sha

PROMPT_RELECTEUR = """Tu relis une réponse de Flore avant qu'elle soit envoyée. Tu ne réécris rien : tu juges.

Vérifie :
1. Elle répond à la question posée, d'abord et directement.
2. Chaque affirmation factuelle sur l'application est suivie d'une citation `chemin#Ldébut-Lfin`
   (les phrases sur Flore elle-même, les questions de suite et les « je ne sais pas » n'en ont pas besoin).
   Une affirmation tirée d'une pièce jointe du Travail est fondée par `pièce:<id_pièce>#<id_section>` (ou
   `pièce:<id>#document` pour le texte intégral) : c'est une source du Travail, pas une connaissance validée.
   Une phrase explicitement attribuée à une pièce n'a donc pas besoin de `chemin#L` ; une pièce jointe ne remplace
   jamais une preuve de code pour une affirmation générale sur l'application.
3. Elle respecte la charte de Flore ci-dessous pour le rôle de l'interlocuteur : vouvoiement, pas de jargon
   non expliqué pour un rôle métier, pas de récitation de ses règles internes ou de sa méthode, pas de tableau.

Réponds uniquement par un objet JSON : {"ok": true} si tout va bien, sinon
{"ok": false, "problemes": ["problème précis et actionnable", ...]} (trois problèmes au plus, les plus graves).

"""


MAX_FRAICHEUR = 8  # au plus autant de documents relus que de preuves affichées


def fraicheur(texte, lecteurs=()):
    """Vérifier avant de citer (Harness v3 §4) : {citation: mention} pour chaque citation de source dont le document a
    changé depuis la version citée, ou qui n'a pas pu être revérifiée. Le texte de la réponse n'est pas modifié."""
    mentions, vues = {}, set()
    for m in RE_CITATION_SOURCE.finditer(texte):
        citation = m.group(0)
        if citation in vues or len(vues) == MAX_FRAICHEUR:
            continue
        vues.add(citation)
        lecteur = next((trouve for trouve in lecteurs
                        if trouve.systeme == m["systeme"] and trouve.espace == m["espace"]), None)
        if lecteur is None or not lecteur.perissable:
            continue
        try:
            actuelle = lecteur.version_actuelle(m["ref"])
        except Exception:  # source injoignable : la réponse part, la preuve le dit
            logging.getLogger("meridian.jumeau").warning("fraîcheur de %s non revérifiée", citation, exc_info=True)
            mentions[citation] = "non revérifiée"
            continue
        if actuelle is None:
            mentions[citation] = "n'existe plus"
        elif actuelle != m["version"]:
            mentions[citation] = f"a changé depuis (v{m['version']} → v{actuelle})"
    return mentions


def citations_invalides(texte, sources, lecteurs=()):
    """Citations qui ne pointent sur aucune ligne existante du code au commit de leur dépôt (ou dont le dépôt ne
    peut être déterminé), ou qu'aucun lecteur branché ne confirme (source inconnue, version ou lignes fausses)."""
    invalides, vues = [], set()
    for m in RE_CITATION_SOURCE.finditer(texte):
        citation = m.group(0)
        if citation not in vues:
            vues.add(citation)
            if not any(trouve.verifier(citation) for trouve in lecteurs):
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


# « Confirmé / validé par l'équipe », ou ✓ : une attribution à l'équipe, qui doit être vraie (charte, Preuves).
RE_ATTRIBUTION = re.compile(r"(?:confirm|valid)\w*\s+par\s+l['’]\s*équipe|✓", re.IGNORECASE)
RE_NEGATION = re.compile(r"\b(?:pas|rien|aucune?|jamais|ni|non)\b|\bn['’]", re.IGNORECASE)
# Ce que l'équipe a déclaré à l'admission (sa mission, qui est propriétaire) ; « l'équipe propriétaire » seule n'en est pas.
RE_DECLARE = re.compile(r"mission|déclar|(?:est|sont)\s+(?:l['’]\s*équipe\s+)?propriétaire", re.IGNORECASE)
RE_PHRASE = re.compile(r"(?<=[.!?;])\s+|\n+")


def attributions_infondees(texte, validees):
    """Phrases qui disent l'équipe d'accord alors qu'elle n'a rien validé : contrôle déterministe, sans modèle.
    Une phrase négative (« rien n'est encore confirmé par l'équipe ») ou sur ce que l'équipe a déclaré (mission,
    propriétaire) passe. ponytail: dès qu'une connaissance est validée, on ne rapproche pas phrase et connaissance
    (il faudrait citer la connaissance validée) ; seul le cas « aucune validée », celui constaté, est contrôlé."""
    if validees:
        return []
    return [p.strip()[:200] for p in RE_PHRASE.split(texte)
            if RE_ATTRIBUTION.search(p) and not RE_NEGATION.search(p) and not RE_DECLARE.search(p)]


def analyser_verdict(texte):
    """Premier objet JSON du texte ; illisible = pas d'objection, mais l'état le dit : la réponse n'est pas « relue »
    (plan de remédiation L0.1 : une étiquette ne promet jamais plus que ce que le mécanisme a fait)."""
    m = re.search(r"\{.*\}", texte, re.DOTALL)
    try:
        verdict = json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        verdict = None
    if not isinstance(verdict, dict):
        return {"ok": True, "problemes": [], "etat": "verdict_illisible"}
    return {"ok": bool(verdict.get("ok", True)), "problemes": [str(p) for p in verdict.get("problemes", [])][:3],
            "etat": "relue"}


async def _juger(question, reponse, profil, modele, charte):
    relecteur = Agent(model=modele, system_prompt=PROMPT_RELECTEUR + charte, tools=[], callback_handler=None)
    role = (profil or {}).get("role", "non précisé")
    resultat = await relecteur.invoke_async(f"Rôle de l'interlocuteur : {role}\n\nQuestion :\n{question}\n\n"
                                            f"Réponse à relire :\n{reponse}")
    verdict = analyser_verdict(str(resultat))
    verdict["usage"] = mesure.usage(relecteur)
    return verdict


async def relire(question, reponse, sources, profil, modele, charte="", lecteurs=(), validees=None,
                 pieces_jointes=None):
    # Contrôles déterministes d'abord : une citation fausse ou une confirmation inventée suffit à demander une
    # révision, sans appel au LLM. `validees` : nombre de connaissances validées (None = non contrôlé).
    invalides = await asyncio.to_thread(citations_invalides, reponse, sources, lecteurs)
    if invalides:
        return {"ok": False, "etat": "relue", "problemes": [
            f"Citations introuvables : {', '.join(invalides)}. "
            "Relis ces lignes avec lire_code ou lire_dans, ou retire l'affirmation."]}
    from pieces import citations_pieces_invalides
    invalides_pieces = await asyncio.to_thread(citations_pieces_invalides, reponse, pieces_jointes or [])
    if invalides_pieces:
        return {"ok": False, "etat": "relue", "problemes": [
            f"Citations de pièces introuvables : {', '.join(invalides_pieces)}. "
            "Utilise le sommaire fourni, sous la forme `pièce:<id_pièce>#<id_section>`."]}
    infondees = attributions_infondees(reponse, validees) if validees is not None else []
    if infondees:
        return {"ok": False, "etat": "relue", "problemes": [
            "L'équipe n'a encore validé aucune connaissance de cette application : ne dis pas « confirmé » ou "
            f"« validé par l'équipe », ni ✓, sauf pour la mission déclarée. À corriger : {' | '.join(infondees[:3])}"]}
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
    # Citations de source branchée : retirées telles quelles quand aucun lecteur ne les confirme.
    propre = re.sub(r"\s*`?(" + RE_CITATION_SOURCE.pattern + r")`?",
                    lambda m: "" if m.group(1) in invalides else m.group(0), propre)
    return re.sub(r"[ \t]+([.,;:])", r"\1", propre)
