"""Pont entre Flore et un jumeau réel : Flore mobilise le jumeau pour répondre (Architecture Jumeau §4.3).

La réponse du jumeau reprend le format des réponses de Flore (reponse, contributions, preuves) : elle s'affiche
dans les conversations existantes (panneau Flore, fil d'un Travail) sans écran dédié.
"""
import asyncio
import os
import re

import psycopg

from jumeau import agent, connaissance, depot

# Forme longue git://depot@sha:chemin#La-Lb ou forme courte chemin#La[-Lb] : toutes deux relues au commit du jumeau.
# Le chemin doit commencer un mot (ni URL « https://… », ni « v1.2 ») et contenir un dossier ou une extension de fichier.
RE_CITATION = re.compile(r"(?:git://[^\s@`]+@[0-9a-f]+:|(?<![\w/:.-]))([A-Za-z_][\w.-]*(?:/[\w.-]+)*\.[A-Za-z]\w*)#L(\d+)(?:-L(\d+))?")
MAX_PREUVES = 8
FILS = agent.FilsActifs()


def preuves_depuis(texte, source):
    """Citations de la réponse → preuves affichables sous le message, au commit ingéré, sans doublon."""
    preuves, vues = [], set()
    sha = source["curseur"][:12]
    for m in RE_CITATION.finditer(texte):
        chemin, debut = m.group(1), int(m.group(2))
        fin = int(m.group(3) or debut)
        locator = f"git://{source['nom']}@{sha}:{chemin}#L{debut}-L{fin}"
        if locator in vues:
            continue
        vues.add(locator)
        preuves.append({"source": f"{chemin}:{debut}" + (f"-{fin}" if fin != debut else ""), "detail": locator})
        if len(preuves) == MAX_PREUVES:
            break
    return preuves


def vers_reponse_flore(jumeau, source, texte):
    sha = source["curseur"][:12]
    preuves = preuves_depuis(texte, source)
    return {
        "comportement": "expliquer",
        "reponse": texte,
        "contributions": [{"jumeau": jumeau["nom"],
                           "texte": f"Connaissances et code de l'application au commit {sha} ({len(preuves)} preuves)."}],
        "preuves": preuves,
    }


def cle_fil(acteur, travail):
    """Dans un Travail, le fil est celui du Travail (partagé selon sa portée) ; ailleurs, il est personnel."""
    return f"travail:{travail}" if travail else f"membre:{acteur}"


def _contexte(jumeau_id, acteur):
    dsn = os.environ.get("JUMEAU_PG_DSN")
    if not dsn:
        return None, None
    with psycopg.connect(dsn) as conn:
        jumeau = depot.jumeau_par_id(conn, jumeau_id)
        source = depot.source_du_jumeau(conn, jumeau_id)
        if not jumeau or not source or not source["index_code"]:
            return None, None
        claims = connaissance.connaissances(conn, jumeau_id, limite=500)
    return {"jumeau": jumeau, "source": source, "claims": claims, "acteur": acteur}, dsn


def _indisponible(nom, raison):
    return {"comportement": "signaler", "reponse": f"Je ne peux pas mobiliser le jumeau **{nom}** pour le moment : {raison}",
            "contributions": [], "preuves": []}


async def repondre(jumeau_id, question, acteur, travail=None):
    """Réponse du jumeau réel à une question, ou None si `jumeau_id` n'est pas un jumeau réel ingéré."""
    ctx, dsn = await asyncio.to_thread(_contexte, jumeau_id, acteur)
    if not ctx:
        return None
    nom = ctx["jumeau"]["nom"]
    cle = cle_fil(acteur, travail)
    if not FILS.prendre(jumeau_id, cle):
        return _indisponible(nom, "une réponse est déjà en cours sur ce fil.")
    try:
        a = agent.construire(ctx, dsn, session=connaissance.id_session(jumeau_id, cle))
        resultat = await a.invoke_async(question)
        return vers_reponse_flore(ctx["jumeau"], ctx["source"], str(resultat).strip())
    except RuntimeError as e:  # modèle non configuré
        return _indisponible(nom, str(e))
    except Exception:
        agent.journal.exception("jumeau %s", jumeau_id)
        return _indisponible(nom, "erreur pendant la réponse.")
    finally:
        FILS.rendre(jumeau_id, cle)
