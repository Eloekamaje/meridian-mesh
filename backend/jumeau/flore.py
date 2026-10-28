"""Pont entre Flore et un jumeau réel : Flore mobilise le jumeau pour répondre (Architecture Jumeau §4.3).

La réponse du jumeau reprend le format des réponses de Flore (reponse, contributions, preuves) : elle s'affiche
dans les conversations existantes (panneau Flore, fil d'un Travail) sans écran dédié.
"""
import asyncio
import itertools
import os
import re

import psycopg

from jumeau import agent, carte, connaissance, contradicteur, depot, gardien, lecteurs, mesure, mobilisation, schemas
from jumeau.connaissance import RE_CITATION
from jumeau.lecteurs import RE_CITATION_SOURCE
from jumeau.travail import EcritureTravail, etat_texte

MAX_PREUVES = 8
FILS = agent.FilsActifs()


def preuves_depuis(texte, sources, exclure=(), fraicheur=None):
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
            return preuves
    # Citations d'une source branchée (documentation, trajectoire…) : déjà au format vérifiable systeme://…@version.
    for m in RE_CITATION_SOURCE.finditer(texte):
        if m.group(0) in exclure or m.group(0) in vues:
            continue
        vues.add(m.group(0))
        lignes = m["debut"] + (f"-{m['fin']}" if m["fin"] and m["fin"] != m["debut"] else "")
        mention = (fraicheur or {}).get(m.group(0))
        preuves.append({"source": f"{m['systeme'].capitalize()} · {m['espace']} · {m['ref']} (v{m['version']}) L{lignes}"
                                  + (f" — {mention}" if mention else ""),
                        "detail": m.group(0)})
        if len(preuves) == MAX_PREUVES:
            break
    return preuves


# Un groupe de citations (« a.py#L1, b.py#L2 et c.py#L3 »), éventuellement entre accents graves ou parenthèses.
_CIT = r"`?(?:" + connaissance.MOTIF_CITATION + "|" + re.sub(r"\(\?P<\w+>", "(?:", RE_CITATION_SOURCE.pattern) + r")`?"
_GROUPE = _CIT + r"(?:\s*(?:,|et|·)\s*" + _CIT + r")*"
RE_GROUPE_ENTRE_PARENTHESES = re.compile(r"\s*\(\s*(?:voir\s+)?" + _GROUPE + r"\s*\)")
RE_GROUPE = re.compile(r"[ \t]*(?:[—·][ \t]*)?" + _GROUPE)


def retirer_citations(texte):
    """Les preuves vont dans le volet sous le message (charte de Flore) : le texte reste lisible, sans restes."""
    propre = RE_GROUPE.sub("", RE_GROUPE_ENTRE_PARENTHESES.sub("", texte))
    propre = re.sub(r"[ \t]*\[[cr]:[\w.-]+\]", "", propre)  # marques de fondement de schéma (cartes), pas pour le lecteur
    propre = re.sub(r"[ \t]+([.,;:])", r"\1", propre)
    return re.sub(r",([.;:])", r"\1", propre)


def fiche_affichable(fiche, sources):
    """Fiche vivante pour l'interface : texte lisible, preuves à part (comme les réponses de Flore)."""
    return {"sha": fiche["sha"], "contenu": retirer_citations(fiche["contenu"]),
            "preuves": preuves_depuis(fiche["contenu"], sources),
            "depots": [{"nom": s["nom"], "branche": s.get("branche"), "commit": s["curseur"][:12]} for s in sources]}


def vers_reponse_flore(jumeau, sources, texte, invalides=(), fraicheur=None):
    """Format d'une réponse de Flore ; les citations introuvables dans le code n'entrent pas dans le volet."""
    return {
        "comportement": "expliquer",
        "reponse": retirer_citations(texte),
        "contributions": [{"jumeau": jumeau["nom"], "texte": "Connaissances et code de l'application consultés."}],
        "preuves": preuves_depuis(texte, sources, invalides, fraicheur),
    }


def validees(claims):
    return sum(c.get("statut") == "ACCEPTED" for c in claims)


async def relire_sans_risque(question, texte, sources, profil, modele, charte="", lecteurs=(), validees=None):
    """Une panne du relecteur (délai, quota) ne doit jamais faire perdre une réponse déjà produite."""
    try:
        return await contradicteur.relire(question, texte, sources, profil, modele, charte, lecteurs, validees)
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
        lecteurs_branches = lecteurs.lecteurs_de(depot.toutes_les_sources(conn, jumeau_id))
        if not jumeau or not (sources or lecteurs_branches):
            return None, None
        claims = connaissance.connaissances(conn, jumeau_id, limite=500)
        fiche = gardien.fiche_courante(conn, jumeau_id)
        consignes = depot.consignes_du_jumeau(conn, jumeau)
    return {"jumeau": jumeau, "consignes": consignes, "sources": sources, "claims": claims, "acteur": acteur, "profil": profil,
            "lecteurs": lecteurs_branches, "fiche": fiche["contenu"] if fiche else None}, dsn


def dessin_pour(ctx):
    """Le schéma d'une réponse : flèches fondées sur la ligne d'appel au commit ingéré ou sur une connaissance."""
    def lire_lignes(citation):
        m = schemas.RE_CITATION_CODE.match(citation)
        source = connaissance.resoudre_source(ctx["sources"], m["depot"], m["chemin"])
        debut = int(m["debut"])
        lu = connaissance.lire_code(source, m["chemin"], debut, int(m["fin"] or debut))
        return [l["texte"] for l in lu["lignes"]], lu["locator"], f"{m['chemin']}:{debut}"
    return schemas.Dessin({c["id"]: c for c in ctx["claims"] if c.get("id")}, lire_lignes)


def avec_schema(texte, dessin):
    """Le schéma dessiné par le harness prend place après le premier paragraphe (la réponse d'abord)."""
    bloc = dessin.bloc() if dessin else ""
    if not bloc:
        return texte
    tete, sep, reste = texte.partition("\n\n")
    return f"{tete}\n\n{bloc}\n\n{reste}" if sep else f"{texte}\n\n{bloc}"


def _indisponible(nom, raison):
    return {"comportement": "signaler", "reponse": f"Je ne peux pas mobiliser le jumeau **{nom}** pour le moment : {raison}",
            "contributions": [], "preuves": []}


async def repondre(jumeau_id, question, acteur, travail=None, profil=None, db=None, trace=None):
    """Réponse de Flore mobilisant un jumeau réel, ou None si `jumeau_id` n'est pas un jumeau réel ingéré.

    Dans un Travail (`travail` et `db`), Flore reçoit son état et les outils pour y écrire (plan, hypothèses,
    options, livrables, résumé) : elle travaille dans le Travail, elle ne fait pas que répondre.
    `trace` (dict facultatif) reçoit le texte brut, avec ses citations, et les citations invalides (évaluations).
    """
    chrono = mesure.Chrono()
    with chrono.phase("contexte"):
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
        ctx["dessin"] = dessin = dessin_pour(ctx) if ctx["sources"] else None
        a = agent.construire(ctx, dsn, session=connaissance.id_session(jumeau_id, cle), modele=modele,
                             ecriture=ecriture)
        with chrono.phase("agent"):
            texte = str(await a.invoke_async(question)).strip()
        # Relecture avant envoi ; une seule révision au plus.
        # ponytail: la consigne de révision reste dans le fil (brouillon, critique, correction) : historique cohérent,
        # mais plus long ; fil séparé si elle gêne la mémoire.
        with chrono.phase("relecture"):
            verdict = await relire_sans_risque(question, texte, ctx["sources"], ctx.get("profil"), modele,
                                               agent.CHARTE.read_text(encoding="utf-8"), ctx.get("lecteurs", []),
                                               validees(ctx["claims"]))
        if not verdict["ok"]:
            agent.journal.info("révision %s : %s", jumeau_id, verdict["problemes"])
            try:
                with chrono.phase("agent"):
                    texte = str(await a.invoke_async(contradicteur.consigne_revision(verdict["problemes"]))).strip()
            except Exception:
                agent.journal.warning("révision impossible, première réponse conservée", exc_info=True)
        chrono.agent(a)
        with chrono.phase("controles"):
            invalides = await asyncio.to_thread(contradicteur.citations_invalides, texte, ctx["sources"],
                                               ctx.get("lecteurs", []))
            if trace is not None:
                trace.update(texte=texte, invalides=list(invalides))
            fraiches = await asyncio.to_thread(contradicteur.fraicheur, texte, ctx.get("lecteurs", []))
            texte = avec_schema(schemas.verifier(texte, {c["id"]: c for c in ctx["claims"] if c.get("id")}), dessin)
        reponse = vers_reponse_flore(ctx["jumeau"], ctx["sources"], texte, invalides, fraiches)
        if dessin and dessin.preuves:  # chaque flèche du schéma renvoie à sa ligne, dans le volet des preuves
            reponse["preuves"] = (reponse["preuves"] + dessin.preuves)[:MAX_PREUVES + len(dessin.preuves)]
        reponse["durees"] = chrono.bilan()
        agent.journal.info("durées %s : %s", jumeau_id, reponse["durees"])
        return reponse
    except RuntimeError as e:  # modèle non configuré
        return _indisponible(nom, str(e))
    except Exception:
        agent.journal.exception("jumeau %s", jumeau_id)
        return _indisponible(nom, "erreur pendant la réponse.")
    finally:
        FILS.rendre(jumeau_id, cle)


async def _cartes(ctxs, dsn, db, relations=None):
    """Cartes des jumeaux autorisés ; sans registre (db), pas de voisins. `relations` reçoit les relations citables
    ({id: relation}) : seules celles que montrent les cartes peuvent fonder une flèche de schéma."""
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
        if relations is not None:
            relations.update({v["relation"]: v for v in c["voisins"] if v.get("relation")})
        textes.append(carte.texte(c))
    return "\n\n".join(textes)


async def mobiliser(jumeau_ids, question, acteur, travail=None, profil=None, db=None):
    """Réponse de Flore qui mobilise plusieurs jumeaux réels (étoile) ; None si aucun n'est un jumeau réel ingéré.

    Seuls `jumeau_ids` (déjà filtrés par le serveur selon les droits) sont mobilisables.
    """
    ctxs, dsn, chrono = {}, None, mesure.Chrono()
    with chrono.phase("contexte"):
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
        scene, relations = mobilisation.Scene(ctxs), {}  # seuls les jumeaux autorisés (déjà filtrés par le serveur)
        # Un schéma peut se fonder sur le code ou les connaissances de chacun des jumeaux mobilisés.
        tous = {"sources": [s for c in ctxs.values() for s in c["sources"]],
                "claims": [c for x in ctxs.values() for c in x["claims"]]}
        dessin = dessin_pour(tous) if tous["sources"] else None
        outils = ([mob.outil(), scene.outil()] + ([agent.outil_dessin(dessin, agent.Budget())] if dessin else [])
                  + (agent.outils_travail(ecriture, agent.Budget()) if ecriture else []))
        a = mobilisation.orchestrateur(modele, mobilisation.prompt(etat), outils)
        # Durée bornée : chaque outil a son plafond, mais pas le nombre de tours de l'orchestratrice.
        with chrono.phase("cartes"):
            cartes = await _cartes(ctxs, dsn, db, relations)
        with chrono.phase("agent"):
            texte = str(await asyncio.wait_for(a.invoke_async(mobilisation.demande(cartes, question)),
                                               mobilisation.DUREE_MAX)).strip()
        sources = [s for ctx in ctxs.values() for s in ctx["sources"]]
        branches = [l for ctx in ctxs.values() for l in ctx.get("lecteurs", [])]
        with chrono.phase("relecture"):
            verdict = await relire_sans_risque(question, texte, sources, profil, modele,
                                               agent.CHARTE.read_text(encoding="utf-8"), branches,
                                               sum(validees(ctx["claims"]) for ctx in ctxs.values()))
        if not verdict["ok"]:
            try:
                with chrono.phase("agent"):
                    texte = str(await a.invoke_async(contradicteur.consigne_revision(verdict["problemes"]))).strip()
            except Exception:
                agent.journal.warning("révision impossible, première réponse conservée", exc_info=True)
        chrono.agent(a)  # « outils » comprend la consultation des jumeaux (leur propre modèle et leurs outils)
        with chrono.phase("controles"):
            invalides = await asyncio.to_thread(contradicteur.citations_invalides, texte, sources, branches)
            texte = avec_schema(schemas.verifier(texte, {c["id"]: c for ctx in ctxs.values() for c in ctx["claims"]
                                                         if c.get("id")}, relations), dessin)
            tout = "\n".join([texte, *(p for c in mob.contributions.values() for p in c.preuves)])
            fraiches = await asyncio.to_thread(contradicteur.fraicheur, tout, branches)
        # Preuves de chaque jumeau, étiquetées à son nom, prises à tour de rôle : le volet ne se remplit pas avec
        # le premier jumeau seulement, et l'on sait de quelle application vient chaque ligne.
        par_jumeau = [[{**p, "source": f"{ctxs[j]['jumeau']['nom']} · {p['source']}"}
                       for p in preuves_depuis("\n".join(mob.contributions[j].preuves + [texte]), ctxs[j]["sources"],
                                               invalides, fraiches)]
                      for j in mob.contributions]
        preuves, vus = [], set()
        for p in (p for rang in itertools.zip_longest(*par_jumeau) for p in rang if p):
            if p["detail"] not in vus:
                vus.add(p["detail"])
                preuves.append(p)
        reponse = {
            "comportement": "expliquer",
            "reponse": retirer_citations(texte),
            "contributions": [{"jumeau": ctxs[j]["jumeau"]["nom"], "texte": retirer_citations(c.constat)}
                              for j, c in mob.contributions.items()],
            "preuves": preuves[:MAX_PREUVES] + (dessin.preuves if dessin else []),
            **({"commande_carte": scene.commande} if scene.commande else {}),
            "durees": chrono.bilan(),
        }
        agent.journal.info("durées mobilisation %s : %s", list(ctxs), reponse["durees"])
        return reponse
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
