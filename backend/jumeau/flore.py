"""Pont entre Flore et un jumeau réel : Flore mobilise le jumeau pour répondre (Architecture Jumeau §4.3).

La réponse du jumeau reprend le format des réponses de Flore (reponse, contributions, preuves) : elle s'affiche
dans les conversations existantes (panneau Flore, fil d'un Travail) sans écran dédié.
"""
import asyncio
import difflib
import itertools
import os
import re
import time
import unicodedata

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
    """Une panne du relecteur (délai, quota) ne doit jamais faire perdre une réponse déjà produite. Elle ne doit pas
    non plus se faire passer pour une relecture : l'état `indisponible` le dit (plan de remédiation L0.1)."""
    try:
        return await contradicteur.relire(question, texte, sources, profil, modele, charte, lecteurs, validees)
    except Exception:
        agent.journal.warning("relecture impossible, réponse envoyée sans relecture", exc_info=True)
        return {"ok": True, "problemes": [], "etat": "indisponible"}


# Ce que la relecture garantit vraiment sur le texte envoyé (plan de remédiation L0.1).
# `relue` seul autorise le badge « relu » ; une correction n'est jamais relue (une seule révision au plus).
ETATS_RELECTURE = ("relue", "corrigee_non_relue", "objection_sans_effet", "indisponible", "verdict_illisible")


def etat_relecture(verdict, corrige):
    """État lisible de la relecture pour une réponse donnée."""
    etat = (verdict or {}).get("etat") or "relue"
    if etat in ("indisponible", "verdict_illisible"):
        return etat
    if verdict["ok"]:
        return "relue"
    return "corrigee_non_relue" if corrige else "objection_sans_effet"


async def reviser(a, texte, verdict, chrono, emit, libelle=""):
    """Une seule révision au plus. Rend (texte, corrige) ; `corrige` n'est vrai que si le texte a réellement changé
    (plan de remédiation L0.2 : une révision qui échoue ne s'affiche pas comme une correction)."""
    if verdict["ok"]:
        return texte, False
    agent.journal.info("révision %s : %s", libelle, verdict["problemes"])
    await _annoncer(emit, {"type": "etape", "libelle": "Je corrige après relecture…"})
    avant = texte
    try:
        with chrono.phase("agent"):
            texte = str(await a.invoke_async(contradicteur.consigne_revision(verdict["problemes"]))).strip()
    except Exception:
        agent.journal.warning("révision impossible, première réponse conservée", exc_info=True)
        return avant, False
    return texte, texte.strip() != avant.strip()


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


# Ce que fait Flore, dit simplement, à mesure qu'elle appelle ses outils (la vraie activité, pas un défilé écrit
# d'avance). Un outil absent de la liste n'est pas annoncé.
ETAPES = {
    "mes_connaissances": "Je consulte ce que l'on sait de l'application…",
    "architecture": "Je regarde de quoi l'application est faite…",
    "chercher_texte": "Je cherche dans le code…", "chercher_symbole": "Je cherche dans le code…",
    "tracer_appels": "Je regarde qui appelle quoi…",
    "suivre_appels": "Je suis l'enchaînement dans le code…",
    "lire_code": "Je lis le code concerné…",
    "historique_du_code": "Je regarde l'histoire du code…", "ce_qui_a_change": "Je regarde ce qui a changé…",
    "chercher_dans": "Je cherche dans la documentation et les outils de l'équipe…",
    "lire_dans": "Je lis la documentation concernée…",
    "dessiner_schema": "Je dessine le schéma…",
    "consulter_jumeau": "Je consulte l'application concernée…",
    "montrer_sur_atlas": "Je prépare la carte…",
    "consulter_methode": "Je choisis comment m'y prendre…",
    "proposer_connaissance": "Je consigne ce que j'ai appris…", "recouper_connaissance": "Je recoupe avec une autre source…",
}


EXTRAIT_OUTIL = 300  # caractères du résultat d'un outil montrés à l'écran (le reste est dans la réponse, cité)


def _extrait(resultat):
    """Le début du résultat d'un outil, en texte : une donnée lue, affichée comme telle, jamais une instruction."""
    texte = " ".join(b["text"] for b in resultat.get("content") or [] if isinstance(b, dict) and isinstance(b.get("text"), str))
    return texte if len(texte) <= EXTRAIT_OUTIL else texte[:EXTRAIT_OUTIL] + "…"


async def executer(a, message, emit=None, chrono=None):
    """Le tour de l'agent ; avec `emit`, son brouillon et chacun de ses outils (début, arguments, issue, durée)
    partent au fil de l'eau. `chrono` reçoit l'instant du premier mot — la latence ressentie."""
    if emit is None:
        return str(await a.invoke_async(message)).strip()
    resultat, debuts = None, {}
    async for e in a.stream_async(message):
        if "data" in e and isinstance(e["data"], str):
            if chrono is not None:
                chrono.texte()
            await emit({"type": "texte", "delta": e["data"]})
        elif (outil := e.get("current_tool_use")) and (oid := outil.get("toolUseId")) and oid not in debuts:
            debuts[oid] = time.monotonic()  # Strands répète l'appel pendant que ses arguments arrivent : annoncé une fois
            await emit({"type": "outil", "id": oid, "nom": outil.get("name"), "libelle": ETAPES.get(outil.get("name")),
                        "etat": "en_cours"})
        elif isinstance(m := e.get("message"), dict):
            for bloc in m.get("content") or []:
                if (u := bloc.get("toolUse")) and u.get("toolUseId") in debuts:
                    debuts[u["toolUseId"]] = time.monotonic()  # arguments complets : l'outil s'exécute maintenant
                    await emit({"type": "outil", "id": u["toolUseId"], "arguments": u.get("input")})
                elif (r := bloc.get("toolResult")) and (oid := r.get("toolUseId")) in debuts:
                    await emit({"type": "outil", "id": oid, "etat": "erreur" if r.get("status") == "error" else "fait",
                                "duree": round(time.monotonic() - debuts[oid], 2), "extrait": _extrait(r)})
        elif "result" in e:
            resultat = e["result"]
    return str(resultat).strip()


async def _annoncer(emit, evenement):
    if emit is not None:
        await emit(evenement)


SEUIL_FAUTE = 0.85  # « conduite » ↔ « conduit » : 0,93 ; « conduire » ↔ « conduit » : 0,80 (refusé)


def _mots(texte):
    sans_accents = unicodedata.normalize("NFKD", texte.lower()).encode("ascii", "ignore").decode()
    return re.findall(r"[a-z0-9]+", sans_accents)


def application_nommee(question, jumeaux):
    """[id] de l'application que la question nomme, s'il n'y en a qu'une, sinon [] : nom complet ou identifiant ; pour
    un nom d'un seul mot, une faute de frappe proche (« conduite » → Conduit). Le système route lui-même vers son
    jumeau : l'interlocuteur n'a pas à sélectionner ni à rattacher l'application."""
    mots = _mots(question)
    phrase = f" {' '.join(mots)} "
    trouves = []
    for j in jumeaux:
        for nom in {" ".join(_mots(j.get("nom") or "")), " ".join(_mots(j["id"]))} - {""}:
            exact = f" {nom} " in phrase
            proche = (" " not in nom and len(nom) >= 5
                      and any(len(m) >= 5 and difflib.SequenceMatcher(None, nom, m).ratio() >= SEUIL_FAUTE for m in mots))
            if exact or proche:
                trouves.append(j["id"])
                break
    return trouves if len(trouves) == 1 else []


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


async def repondre(jumeau_id, question, acteur, travail=None, profil=None, db=None, trace=None, emit=None):
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
        await _annoncer(emit, {"type": "etape", "libelle": f"Je regarde {nom}…"})
        modele = agent.modele()
        ecriture = EcritureTravail(db, travail) if travail and db is not None else None
        if ecriture:
            ctx["travail"] = etat_texte(await ecriture.etat())
        ctx["dessin"] = dessin = dessin_pour(ctx) if ctx["sources"] else None
        a = agent.construire(ctx, dsn, session=connaissance.id_session(jumeau_id, cle), modele=modele,
                             ecriture=ecriture)
        with chrono.phase("agent"):
            texte = await executer(a, question, emit, chrono)
        await _annoncer(emit, {"type": "relecture"})
        # Relecture avant envoi ; une seule révision au plus.
        # ponytail: la consigne de révision reste dans le fil (brouillon, critique, correction) : historique cohérent,
        # mais plus long ; fil séparé si elle gêne la mémoire.
        with chrono.phase("relecture"):
            verdict = await relire_sans_risque(question, texte, ctx["sources"], ctx.get("profil"), modele,
                                               agent.CHARTE.read_text(encoding="utf-8"), ctx.get("lecteurs", []),
                                               validees(ctx["claims"]))
        texte, corrige = await reviser(a, texte, verdict, chrono, emit, jumeau_id)
        chrono.agent(a)
        with chrono.phase("controles"):
            invalides = await asyncio.to_thread(contradicteur.citations_invalides, texte, ctx["sources"],
                                               ctx.get("lecteurs", []))
            if trace is not None:
                trace.update(texte=texte, invalides=list(invalides))
            fraiches = await asyncio.to_thread(contradicteur.fraicheur, texte, ctx.get("lecteurs", []))
            texte = avec_schema(schemas.verifier(texte, {c["id"]: c for c in ctx["claims"] if c.get("id")},
                                                 deja_dessine=bool(dessin and dessin.mermaid)), dessin)
        reponse = vers_reponse_flore(ctx["jumeau"], ctx["sources"], texte, invalides, fraiches)
        if dessin and dessin.preuves:  # chaque flèche du schéma renvoie à sa ligne, dans le volet des preuves
            reponse["preuves"] = (reponse["preuves"] + dessin.preuves)[:MAX_PREUVES + len(dessin.preuves)]
        reponse["durees"] = chrono.bilan()
        reponse["relecture_etat"] = etat = etat_relecture(verdict, corrige)
        reponse["relu"], reponse["corrige"] = etat == "relue", corrige
        if ctx.get("proposees"):
            reponse["a_approuver"] = ctx["proposees"]  # les connaissances proposées pendant ce tour, à trancher
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


async def mobiliser(jumeau_ids, question, acteur, travail=None, profil=None, db=None, emit=None):
    """Réponse de Flore qui mobilise plusieurs jumeaux réels (étoile) ; None si aucun n'est un jumeau réel ingéré.

    Seuls `jumeau_ids` (déjà filtrés par le serveur selon les droits) sont mobilisables.
    """
    ctxs, dsn, chrono = {}, None, mesure.Chrono()
    await _annoncer(emit, {"type": "etape", "libelle": "Je regarde les applications concernées…"})
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
            texte = await asyncio.wait_for(executer(a, mobilisation.demande(cartes, question), emit, chrono),
                                           mobilisation.DUREE_MAX)
        await _annoncer(emit, {"type": "relecture"})
        sources = [s for ctx in ctxs.values() for s in ctx["sources"]]
        branches = [l for ctx in ctxs.values() for l in ctx.get("lecteurs", [])]
        with chrono.phase("relecture"):
            verdict = await relire_sans_risque(question, texte, sources, profil, modele,
                                               agent.CHARTE.read_text(encoding="utf-8"), branches,
                                               sum(validees(ctx["claims"]) for ctx in ctxs.values()))
        texte, corrige = await reviser(a, texte, verdict, chrono, emit, "mobilisation")
        chrono.agent(a)  # « outils » comprend la consultation des jumeaux (leur propre modèle et leurs outils)
        with chrono.phase("controles"):
            invalides = await asyncio.to_thread(contradicteur.citations_invalides, texte, sources, branches)
            texte = avec_schema(schemas.verifier(texte, {c["id"]: c for ctx in ctxs.values() for c in ctx["claims"]
                                                         if c.get("id")}, relations,
                                                 deja_dessine=bool(dessin and dessin.mermaid)), dessin)
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
            "durees": chrono.bilan(), "relecture_etat": etat_relecture(verdict, corrige),
            "relu": etat_relecture(verdict, corrige) == "relue", "corrige": corrige,
        }
        if proposees := [p for ctx in ctxs.values() for p in ctx.get("proposees", [])]:
            reponse["a_approuver"] = proposees  # proposées par les sous-agents : chacune à trancher
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
