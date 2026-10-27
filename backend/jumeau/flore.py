"""Pont entre Flore et un jumeau réel : Flore mobilise le jumeau pour répondre (Architecture Jumeau §4.3).

La réponse du jumeau reprend le format des réponses de Flore (reponse, contributions, preuves) : elle s'affiche
dans les conversations existantes (panneau Flore, fil d'un Travail) sans écran dédié.
"""
import asyncio
import os
import re

import psycopg

from jumeau import agent, connaissance, contradicteur, depot, gardien
from jumeau.connaissance import RE_CITATION
from jumeau.travail import EcritureTravail, etat_texte

# Forme longue git://depot@sha:chemin#La-Lb ou forme courte chemin#La[-Lb] : toutes deux relues au commit du jumeau.
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


# Un groupe de citations (« a.py#L1, b.py#L2 et c.py#L3 »), éventuellement entre accents graves ou parenthèses.
_CIT = r"`?" + RE_CITATION.pattern + r"`?"
_GROUPE = _CIT + r"(?:\s*(?:,|et)\s*" + _CIT + r")*"
RE_GROUPE_ENTRE_PARENTHESES = re.compile(r"\s*\(\s*(?:voir\s+)?" + _GROUPE + r"\s*\)")
RE_GROUPE = re.compile(r"\s*(?:—\s*)?" + _GROUPE)


def retirer_citations(texte):
    """Les preuves vont dans le volet sous le message (charte de Flore) : le texte reste lisible, sans restes."""
    propre = RE_GROUPE.sub("", RE_GROUPE_ENTRE_PARENTHESES.sub("", texte))
    propre = re.sub(r"[ \t]+([.,;:])", r"\1", propre)
    return re.sub(r",([.;:])", r"\1", propre)


def vers_reponse_flore(jumeau, source, texte, invalides=()):
    """Format d'une réponse de Flore ; les citations introuvables dans le code n'entrent pas dans le volet."""
    preuves = [p for p in preuves_depuis(texte, source) if not any(p["detail"].endswith(f":{i}") for i in invalides)]
    return {
        "comportement": "expliquer",
        "reponse": retirer_citations(texte),
        "contributions": [{"jumeau": jumeau["nom"], "texte": "Connaissances et code de l'application consultés."}],
        "preuves": preuves,
    }


async def relire_sans_risque(question, texte, source, profil, modele, charte=""):
    """Une panne du relecteur (délai, quota) ne doit jamais faire perdre une réponse déjà produite."""
    try:
        return await contradicteur.relire(question, texte, source, profil, modele, charte)
    except Exception:
        agent.journal.warning("relecture impossible, réponse envoyée sans relecture", exc_info=True)
        return {"ok": True, "problemes": []}


def cle_fil(acteur, travail):
    """Dans un Travail, le fil est celui du Travail (partagé selon sa portée) ; ailleurs, il est personnel."""
    return f"travail:{travail}" if travail else f"membre:{acteur}"


def _contexte(jumeau_id, acteur, profil):
    dsn = os.environ.get("JUMEAU_PG_DSN")
    if not dsn:
        return None, None
    with psycopg.connect(dsn) as conn:
        jumeau = depot.jumeau_par_id(conn, jumeau_id)
        source = depot.source_du_jumeau(conn, jumeau_id)
        if not jumeau or not source or not source["index_code"]:
            return None, None
        claims = connaissance.connaissances(conn, jumeau_id, limite=500)
        fiche = gardien.fiche_courante(conn, jumeau_id)
    return {"jumeau": jumeau, "source": source, "claims": claims, "acteur": acteur, "profil": profil,
            "fiche": fiche["contenu"] if fiche else None}, dsn


def _indisponible(nom, raison):
    return {"comportement": "signaler", "reponse": f"Je ne peux pas mobiliser le jumeau **{nom}** pour le moment : {raison}",
            "contributions": [], "preuves": []}


async def repondre(jumeau_id, question, acteur, travail=None, profil=None, db=None):
    """Réponse de Flore mobilisant un jumeau réel, ou None si `jumeau_id` n'est pas un jumeau réel ingéré.

    Dans un Travail (`travail` et `db`), Flore reçoit son état et les outils pour y écrire (plan, hypothèses,
    options, livrables, résumé) : elle travaille dans le Travail, elle ne fait pas que répondre.
    """
    ctx, dsn = await asyncio.to_thread(_contexte, jumeau_id, acteur, profil)
    if not ctx:
        return None
    nom = ctx["jumeau"]["nom"]
    cle = cle_fil(acteur, travail)
    if not FILS.prendre(jumeau_id, cle):
        return _indisponible(nom, "une réponse est déjà en cours sur ce fil.")
    try:
        modele = agent.modele()
        ecriture = EcritureTravail(db, travail) if travail and db is not None else None
        if ecriture:
            ctx["travail"] = etat_texte(await ecriture.etat())
        a = agent.construire(ctx, dsn, session=connaissance.id_session(jumeau_id, cle), modele=modele,
                             ecriture=ecriture)
        texte = str(await a.invoke_async(question)).strip()
        # Relecture avant envoi ; une seule révision au plus.
        # ponytail: la consigne de révision reste dans le fil (brouillon, critique, correction) : historique cohérent,
        # mais plus long ; fil séparé si elle gêne la mémoire.
        verdict = await relire_sans_risque(question, texte, ctx["source"], ctx.get("profil"), modele,
                                           agent.CHARTE.read_text(encoding="utf-8"))
        if not verdict["ok"]:
            agent.journal.info("révision %s : %s", jumeau_id, verdict["problemes"])
            try:
                texte = str(await a.invoke_async(contradicteur.consigne_revision(verdict["problemes"]))).strip()
            except Exception:
                agent.journal.warning("révision impossible, première réponse conservée", exc_info=True)
        invalides = await asyncio.to_thread(contradicteur.citations_invalides, texte, ctx["source"])
        return vers_reponse_flore(ctx["jumeau"], ctx["source"], texte, invalides)
    except RuntimeError as e:  # modèle non configuré
        return _indisponible(nom, str(e))
    except Exception:
        agent.journal.exception("jumeau %s", jumeau_id)
        return _indisponible(nom, "erreur pendant la réponse.")
    finally:
        FILS.rendre(jumeau_id, cle)
