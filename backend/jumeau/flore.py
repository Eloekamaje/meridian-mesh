"""Pont entre Flore et un jumeau réel : Flore mobilise le jumeau pour répondre (Architecture Jumeau §4.3).

La réponse du jumeau reprend le format des réponses de Flore (reponse, contributions, preuves) : elle s'affiche
dans les conversations existantes (panneau Flore, fil d'un Travail) sans écran dédié.
"""
import asyncio
import itertools
import os
import re

import psycopg

from jumeau import agent, carte, connaissance, contradicteur, depot, gardien, mobilisation
from jumeau.connaissance import RE_CITATION
from jumeau.travail import EcritureTravail, etat_texte

MAX_PREUVES = 8
FILS = agent.FilsActifs()


def preuves_depuis(texte, sources, exclure=()):
    """Citations de la réponse → preuves affichables sous le message, au commit de leur dépôt, sans doublon.

    Une citation dont le dépôt ne peut être déterminé, ou qui figure dans `exclure`, n'est pas retenue.
    """
    preuves, vues = [], set()
    for m in RE_CITATION.finditer(texte):
        depot_cite, chemin, debut, fin = connaissance.decouper(m)
        if connaissance.cle_citation(depot_cite, chemin, debut, fin) in exclure:
            continue
        try:
            source = connaissance.resoudre_source(sources, depot_cite, chemin)
        except (LookupError, ValueError):
            continue
        locator = f"git://{source['nom']}@{source['curseur'][:12]}:{chemin}#L{debut}-L{fin}"
        if locator in vues:
            continue
        vues.add(locator)
        etiquette = f"{chemin}:{debut}" + (f"-{fin}" if fin != debut else "")
        preuves.append({"source": f"{source['nom']} · {etiquette}" if len(sources) > 1 else etiquette, "detail": locator})
        if len(preuves) == MAX_PREUVES:
            break
    return preuves


# Un groupe de citations (« a.py#L1, b.py#L2 et c.py#L3 »), éventuellement entre accents graves ou parenthèses.
_CIT = r"`?" + connaissance.MOTIF_CITATION + r"`?"
_GROUPE = _CIT + r"(?:\s*(?:,|et|·)\s*" + _CIT + r")*"
RE_GROUPE_ENTRE_PARENTHESES = re.compile(r"\s*\(\s*(?:voir\s+)?" + _GROUPE + r"\s*\)")
RE_GROUPE = re.compile(r"[ \t]*(?:[—·][ \t]*)?" + _GROUPE)


def retirer_citations(texte):
    """Les preuves vont dans le volet sous le message (charte de Flore) : le texte reste lisible, sans restes."""
    propre = RE_GROUPE.sub("", RE_GROUPE_ENTRE_PARENTHESES.sub("", texte))
    propre = re.sub(r"[ \t]+([.,;:])", r"\1", propre)
    return re.sub(r",([.;:])", r"\1", propre)


def fiche_affichable(fiche, sources):
    """Fiche vivante pour l'interface : texte lisible, preuves à part (comme les réponses de Flore)."""
    return {"sha": fiche["sha"], "contenu": retirer_citations(fiche["contenu"]),
            "preuves": preuves_depuis(fiche["contenu"], sources),
            "depots": [{"nom": s["nom"], "branche": s.get("branche"), "commit": s["curseur"][:12]} for s in sources]}


def vers_reponse_flore(jumeau, sources, texte, invalides=()):
    """Format d'une réponse de Flore ; les citations introuvables dans le code n'entrent pas dans le volet."""
    return {
        "comportement": "expliquer",
        "reponse": retirer_citations(texte),
        "contributions": [{"jumeau": jumeau["nom"], "texte": "Connaissances et code de l'application consultés."}],
        "preuves": preuves_depuis(texte, sources, invalides),
    }


async def relire_sans_risque(question, texte, sources, profil, modele, charte=""):
    """Une panne du relecteur (délai, quota) ne doit jamais faire perdre une réponse déjà produite."""
    try:
        return await contradicteur.relire(question, texte, sources, profil, modele, charte)
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
        sources = [s for s in depot.sources_du_jumeau(conn, jumeau_id) if s["index_code"]]
        if not jumeau or not sources:
            return None, None
        claims = connaissance.connaissances(conn, jumeau_id, limite=500)
        fiche = gardien.fiche_courante(conn, jumeau_id)
    return {"jumeau": jumeau, "sources": sources, "claims": claims, "acteur": acteur, "profil": profil,
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
        verdict = await relire_sans_risque(question, texte, ctx["sources"], ctx.get("profil"), modele,
                                           agent.CHARTE.read_text(encoding="utf-8"))
        if not verdict["ok"]:
            agent.journal.info("révision %s : %s", jumeau_id, verdict["problemes"])
            try:
                texte = str(await a.invoke_async(contradicteur.consigne_revision(verdict["problemes"]))).strip()
            except Exception:
                agent.journal.warning("révision impossible, première réponse conservée", exc_info=True)
        invalides = await asyncio.to_thread(contradicteur.citations_invalides, texte, ctx["sources"])
        return vers_reponse_flore(ctx["jumeau"], ctx["sources"], texte, invalides)
    except RuntimeError as e:  # modèle non configuré
        return _indisponible(nom, str(e))
    except Exception:
        agent.journal.exception("jumeau %s", jumeau_id)
        return _indisponible(nom, "erreur pendant la réponse.")
    finally:
        FILS.rendre(jumeau_id, cle)


async def _cartes(ctxs, dsn, db):
    """Cartes des jumeaux autorisés ; sans registre (db), pas de voisins."""
    textes = []
    for jid, ctx in ctxs.items():
        if db is None:
            c = carte.carte(ctx["jumeau"], ctx["sources"], ctx["claims"], [], {})
        else:
            conn = await asyncio.to_thread(psycopg.connect, dsn)
            try:
                c = await carte.carte_du_jumeau(conn, db, jid, visibles=set(ctxs))
            finally:
                await asyncio.to_thread(conn.close)
        textes.append(carte.texte(c))
    return "\n\n".join(textes)


async def mobiliser(jumeau_ids, question, acteur, travail=None, profil=None, db=None):
    """Réponse de Flore qui mobilise plusieurs jumeaux réels (étoile) ; None si aucun n'est un jumeau réel ingéré.

    Seuls `jumeau_ids` (déjà filtrés par le serveur selon les droits) sont mobilisables.
    """
    ctxs, dsn = {}, None
    for jid in dict.fromkeys(jumeau_ids):
        ctx, dsn_jumeau = await asyncio.to_thread(_contexte, jid, acteur, profil)
        if ctx:
            ctxs[jid], dsn = ctx, dsn_jumeau
    if not ctxs:
        return None
    cle = cle_fil(acteur, travail)
    noms = " et ".join(c["jumeau"]["nom"] for c in ctxs.values())
    if not FILS.prendre("mobilisation", cle):
        return _indisponible(noms, "une réponse est déjà en cours sur ce fil.")
    try:
        modele = agent.modele()
        ecriture = EcritureTravail(db, travail) if travail and db is not None else None
        etat = etat_texte(await ecriture.etat()) if ecriture else None
        mob = mobilisation.Mobilisation(ctxs, dsn, modele)
        outils = [mob.outil()] + (agent.outils_travail(ecriture, agent.Budget()) if ecriture else [])
        a = mobilisation.orchestrateur(modele, mobilisation.prompt(etat), outils)
        # Durée bornée : chaque outil a son plafond, mais pas le nombre de tours de l'orchestratrice.
        texte = str(await asyncio.wait_for(a.invoke_async(mobilisation.demande(await _cartes(ctxs, dsn, db), question)),
                                           mobilisation.DUREE_MAX)).strip()
        sources = [s for ctx in ctxs.values() for s in ctx["sources"]]
        verdict = await relire_sans_risque(question, texte, sources, profil, modele,
                                           agent.CHARTE.read_text(encoding="utf-8"))
        if not verdict["ok"]:
            try:
                texte = str(await a.invoke_async(contradicteur.consigne_revision(verdict["problemes"]))).strip()
            except Exception:
                agent.journal.warning("révision impossible, première réponse conservée", exc_info=True)
        invalides = await asyncio.to_thread(contradicteur.citations_invalides, texte, sources)
        # Preuves de chaque jumeau, étiquetées à son nom, prises à tour de rôle : le volet ne se remplit pas avec
        # le premier jumeau seulement, et l'on sait de quelle application vient chaque ligne.
        par_jumeau = [[{**p, "source": f"{ctxs[j]['jumeau']['nom']} · {p['source']}"}
                       for p in preuves_depuis("\n".join(mob.contributions[j].preuves + [texte]), ctxs[j]["sources"],
                                               invalides)]
                      for j in mob.contributions]
        preuves, vus = [], set()
        for p in (p for rang in itertools.zip_longest(*par_jumeau) for p in rang if p):
            if p["detail"] not in vus:
                vus.add(p["detail"])
                preuves.append(p)
        return {
            "comportement": "expliquer",
            "reponse": retirer_citations(texte),
            "contributions": [{"jumeau": ctxs[j]["jumeau"]["nom"], "texte": retirer_citations(c.constat)}
                              for j, c in mob.contributions.items()],
            "preuves": preuves[:MAX_PREUVES],
        }
    except asyncio.TimeoutError:
        agent.journal.warning("mobilisation %s : durée dépassée", list(ctxs))
        return _indisponible(noms, "la mobilisation a dépassé sa durée maximale.")
    except RuntimeError as e:  # modèle non configuré
        return _indisponible(noms, str(e))
    except Exception:
        agent.journal.exception("mobilisation %s", list(ctxs))
        return _indisponible(noms, "erreur pendant la réponse.")
    finally:
        FILS.rendre("mobilisation", cle)
