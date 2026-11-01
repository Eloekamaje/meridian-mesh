"""Pont entre Flore et un jumeau réel : Flore mobilise le jumeau pour répondre (Architecture Jumeau §4.3).

La réponse du jumeau reprend le format des réponses de Flore (reponse, contributions, preuves) : elle s'affiche
dans les conversations existantes (panneau Flore, fil d'un Travail) sans écran dédié.
"""
import asyncio
import difflib
import itertools
import os
import re
import unicodedata

import psycopg

from meridian.adapters.outbound.llm import agent
from meridian.adapters.outbound.postgres import carte
from meridian.adapters.outbound.postgres import connaissance
from meridian.adapters.outbound.llm import contradicteur
from meridian.adapters.outbound.postgres import depot
from jumeau import flux
from meridian.adapters.outbound.llm import gardien
from meridian.adapters.outbound.connectors import lecteurs
from meridian.application import mesure
from meridian.adapters.outbound.llm import mobilisation
from meridian.domain import schemas
from meridian.adapters.outbound.postgres.connaissance import RE_CITATION
from meridian.adapters.outbound.connectors.lecteurs import RE_CITATION_SOURCE
from meridian.adapters.outbound.mongo.travail import EcritureTravail, etat_texte

MAX_PREUVES = 8
NOTE_PIECES_NON_TRANSMISES = (
    "## Pièces jointes non transmises\n\n"
    "Le modèle configuré est externe et l'envoi de pièces n'est pas autorisé pour ce Travail. "
    "Dis-le à l'interlocuteur ; ne prétends pas avoir lu les pièces."
)
SANS_ECRITURE_AVEC_PIECES = (
    "Tu ne peux pas modifier le Travail dans ce tour ; propose l'action à l'humain."
)
FILS = agent.FilsActifs()


def bloc_donnees_pieces(pieces_prompt="", avertissement=""):
    """Le contenu des pièces reste une donnée balisée, jamais une instruction du prompt système."""
    return "\n\n".join(bloc for bloc in (pieces_prompt, avertissement) if bloc)


def message_utilisateur(question, pieces_prompt="", avertissement=""):
    """La question, précédée du bloc de pièces non fiables quand il y en a un."""
    bloc = bloc_donnees_pieces(pieces_prompt, avertissement)
    if not bloc:
        return question
    return f"<donnees_pieces>\n{bloc}\n</donnees_pieces>\n\nQuestion : {question}"


def pieces_non_transmises(pieces_docs):
    """Des pièces existent, mais le modèle configuré est externe sans autorisation : rien ne part vers lui."""
    if not pieces_docs:
        return False
    try:
        from pieces import modele_externe, modele_externe_autorise
    except ImportError:
        return False
    return bool(modele_externe()) and not bool(modele_externe_autorise())


def retirer_citations_pieces(texte, pieces_docs):
    """Texte débarrassé des citations de pièces qui ne désignent aucune section réelle (contrat de pieces.py)."""
    try:
        from pieces import retirer_citations_pieces_invalides
    except ImportError:
        return texte, []
    return retirer_citations_pieces_invalides(texte, pieces_docs or [])


def preuves_depuis(texte, sources, exclure=(), fraicheur=None):
    """Citations de la réponse → preuves affichables sous le message, au commit de leur dépôt, sans doublon.

    Une citation dont le dépôt ne peut être déterminé, ou qui figure dans `exclure`, n'est pas retenue.
    """
    preuves, vues = [], set()
    for m in RE_CITATION.finditer(texte):
        depot_cite, chemin, debut, fin = connaissance.decouper(m)
        if connaissance.cle_citation(depot_cite, chemin, debut, fin) in exclure:
            continue
        locator, source = _locator(m, sources)
        if locator is None or locator in vues:
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
        etiquette = f"{m['systeme'].capitalize()} · {m['espace']} · {m['ref']} (v{m['version']}) L{lignes}"
        preuves.append({"source": etiquette + (f" — {mention}" if mention else ""), "detail": m.group(0)})
        if len(preuves) == MAX_PREUVES:
            break
    return preuves


def _locator(m, sources):
    """L'emplacement d'une citation de code au commit de son dépôt (et la source), ou (None, None)."""
    depot_cite, chemin, debut, fin = connaissance.decouper(m)
    try:
        source = connaissance.resoudre_source(sources, depot_cite, chemin)
    except (LookupError, ValueError):
        return None, None
    return f"git://{source['nom']}@{source['curseur'][:12]}:{chemin}#L{debut}-L{fin}", source


def pastiller(texte, preuves, sources):
    """Chaque groupe de citations devient ses pastilles numérotées `[n](#preuve-n)`, n étant la place de la preuve
    dans le volet (la preuve reste lisible sous le message, et chaque phrase montre la sienne). Une citation sans
    preuve dans le volet (fausse, introuvable) disparaît, comme avec retirer_citations."""
    rang = {p["detail"]: i + 1 for i, p in enumerate(preuves)}

    def pastilles(groupe):
        numeros = [rang.get(_locator(m, sources)[0]) for m in RE_CITATION.finditer(groupe.group(0))]
        numeros += [rang.get(m.group(0)) for m in RE_CITATION_SOURCE.finditer(groupe.group(0))]
        return "".join(f" [{n}](#preuve-{n})" for n in dict.fromkeys(n for n in numeros if n))
    propre = RE_GROUPE.sub(pastilles, RE_GROUPE_ENTRE_PARENTHESES.sub(pastilles, texte))
    return _nettoyer(propre)


def _nettoyer(texte):
    propre = re.sub(r"[ \t]*\[[cr]:[\w.-]+\]", "", texte)  # marques de fondement de schéma (cartes), pas pour le lecteur
    propre = re.sub(r"[ \t]+([.,;:])", r"\1", propre)
    return re.sub(r",([.;:])", r"\1", propre)


# Un groupe de citations (« a.py#L1, b.py#L2 et c.py#L3 »), éventuellement entre accents graves ou parenthèses.
_CIT = r"`?(?:" + connaissance.MOTIF_CITATION + "|" + re.sub(r"\(\?P<\w+>", "(?:", RE_CITATION_SOURCE.pattern) + r")`?"
_GROUPE = _CIT + r"(?:\s*(?:,|et|·)\s*" + _CIT + r")*"
RE_GROUPE_ENTRE_PARENTHESES = re.compile(r"\s*\(\s*(?:voir\s+)?" + _GROUPE + r"\s*\)")
RE_GROUPE = re.compile(r"[ \t]*(?:[—·][ \t]*)?" + _GROUPE)


def retirer_citations(texte):
    """Les preuves vont dans le volet sous le message (charte de Flore) : le texte reste lisible, sans restes."""
    return _nettoyer(RE_GROUPE.sub("", RE_GROUPE_ENTRE_PARENTHESES.sub("", texte)))


def fiche_affichable(fiche, sources):
    """Fiche vivante pour l'interface : texte lisible, preuves à part (comme les réponses de Flore)."""
    return {"sha": fiche["sha"], "contenu": retirer_citations(fiche["contenu"]),
            "preuves": preuves_depuis(fiche["contenu"], sources),
            "depots": [{"nom": s["nom"], "branche": s.get("branche"), "commit": s["curseur"][:12]} for s in sources]}


def vers_reponse_flore(jumeau, sources, texte, invalides=(), fraicheur=None):
    """Format d'une réponse de Flore ; les citations introuvables dans le code n'entrent pas dans le volet."""
    preuves = preuves_depuis(texte, sources, invalides, fraicheur)
    return {
        "comportement": "expliquer",
        "reponse": pastiller(texte, preuves, sources),
        "contributions": [{"jumeau": jumeau["nom"], "texte": "Connaissances et code de l'application consultés."}],
        "jumeaux_participants": [{"id": jumeau.get("id") or jumeau.get("nom") or "jumeau",
                                  "app_id": jumeau.get("id") or jumeau.get("nom") or "jumeau",
                                  "nom": jumeau.get("nom") or jumeau.get("id") or "Jumeau",
                                  "domaine": jumeau.get("domaine") or "SI", "participe": True}],
        "preuves": preuves,
    }


def validees(claims):
    return sum(c.get("statut") == "ACCEPTED" for c in claims)


async def relire_sans_risque(question, texte, sources, profil, modele, charte="", lecteurs=(), validees=None,
                             pieces_jointes=None):
    """Une panne du relecteur (délai, quota) ne doit jamais faire perdre une réponse déjà produite. Elle ne doit pas
    non plus se faire passer pour une relecture : l'état `indisponible` le dit (plan de remédiation L0.1)."""
    try:
        return await contradicteur.relire(
            question, texte, sources, profil, modele, charte, lecteurs, validees, pieces_jointes)
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


# Les libellés des outils et leur suivi vivent dans flux (partagés avec la mobilisation des jumeaux).
ETAPES = flux.LIBELLES_OUTILS
EXTRAIT_OUTIL = flux.EXTRAIT_OUTIL


async def executer(a, message, emit=None, chrono=None):
    """Le tour de l'agent ; avec `emit`, son brouillon et chacun de ses outils (début, arguments, issue, durée)
    partent au fil de l'eau. `chrono` reçoit l'instant du premier mot — la latence ressentie."""
    if emit is None:
        return str(await a.invoke_async(message)).strip()
    resultat, suivi = None, flux.SuiviOutils(emit)
    async for e in a.stream_async(message):
        if "data" in e and isinstance(e["data"], str):
            if chrono is not None:
                chrono.texte()
            await emit({"type": "texte", "delta": e["data"]})
        elif await suivi.suivre(e):
            pass
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
    jumeau : l'interlocuteur n'a pas à sélectionner ni à rattacher l'application. Un dépôt n'est pas un nom
    d'application : cette résolution passe par `identite.resoudre` côté serveur."""
    mots = _mots(question)
    phrase = f" {' '.join(mots)} "
    trouves = []
    for j in jumeaux:
        for nom in {" ".join(_mots(j.get("nom") or "")), " ".join(_mots(j["id"]))} - {""}:
            exact = f" {nom} " in phrase
            proche = (" " not in nom and len(nom) >= 5 and any(
                len(m) >= 5 and difflib.SequenceMatcher(None, nom, m).ratio() >= SEUIL_FAUTE for m in mots))
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
        return [ligne["texte"] for ligne in lu["lignes"]], lu["locator"], f"{m['chemin']}:{debut}"
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


async def repondre(jumeau_id, question, acteur, travail=None, profil=None, db=None, trace=None, emit=None,
                   autoriser_ecriture=False):
    """Réponse de Flore mobilisant un jumeau réel, ou None si `jumeau_id` n'est pas un jumeau réel ingéré.

    Dans un Travail (`travail` et `db`), Flore reçoit son état et les outils pour y écrire (plan, hypothèses,
    options, livrables, résumé) : elle travaille dans le Travail, elle ne fait pas que répondre. Avec des pièces
    jointes, les outils d'écriture ne sont ouverts que si l'humain les autorise pour ce tour.
    `trace` (dict facultatif) reçoit le texte brut, avec ses citations, et les citations invalides (évaluations).
    """
    chrono = mesure.Chrono()
    with chrono.phase("contexte"):
        ctx, dsn = await asyncio.to_thread(_contexte, jumeau_id, acteur, profil)
    if not ctx:
        return None
    if travail and db is not None:  # les pièces jointes du Travail, dans les droits déjà vérifiés par l'appelant
        from pieces import du_travail, sections_pour_prompt_detail
        ctx["pieces"] = await du_travail(db, travail)
        if pieces_non_transmises(ctx["pieces"]):
            ctx["pieces"] = []
            ctx["pieces_prompt"] = NOTE_PIECES_NON_TRANSMISES
        elif ctx["pieces"]:
            ctx["pieces_prompt"], ctx["pieces_selection"] = sections_pour_prompt_detail(ctx["pieces"], question)
    avertissement = SANS_ECRITURE_AVEC_PIECES if ctx.get("pieces") and not autoriser_ecriture else ""
    message = message_utilisateur(question, ctx.get("pieces_prompt") or "", avertissement)
    journal_pieces = []
    nom = ctx["jumeau"]["nom"]
    cle = cle_fil(acteur, travail)
    if not FILS.prendre(jumeau_id, cle):
        return _indisponible(nom, "une réponse est déjà en cours sur ce fil.")
    try:
        await _annoncer(emit, {"type": "etape", "libelle": f"Je regarde {nom}…"})
        modele = agent.modele()
        ecriture = (EcritureTravail(db, travail)
                    if travail and db is not None and (not ctx.get("pieces") or autoriser_ecriture) else None)
        if ecriture:
            ctx["travail"] = etat_texte(await ecriture.etat())
        ctx["dessin"] = dessin = dessin_pour(ctx) if ctx["sources"] else None
        supplement = ({"outils_pieces": lambda b: agent.outils_pieces(db, travail, b, journal_pieces)}
                      if ctx.get("pieces") else {})
        a = agent.construire(ctx, dsn, session=connaissance.id_session(jumeau_id, cle), modele=modele,
                             ecriture=ecriture, **supplement)
        with chrono.phase("agent"):
            texte = await executer(a, message, emit, chrono)
        await _annoncer(emit, {"type": "relecture"})
        # Relecture avant envoi ; une seule révision au plus.
        # ponytail: la consigne de révision reste dans le fil (brouillon, critique, correction) : historique cohérent,
        # mais plus long ; fil séparé si elle gêne la mémoire.
        with chrono.phase("relecture"):
            verdict = await relire_sans_risque(
                question, texte, ctx["sources"], ctx.get("profil"), modele,
                agent.CHARTE.read_text(encoding="utf-8"), ctx.get("lecteurs", []),
                validees(ctx["claims"]), ctx.get("pieces"))
        texte, corrige = await reviser(a, texte, verdict, chrono, emit, jumeau_id)
        texte, invalides_pieces = await asyncio.to_thread(retirer_citations_pieces, texte, ctx.get("pieces"))
        if trace is not None and invalides_pieces:
            trace["invalides"] = [*trace.get("invalides", []), *invalides_pieces]
        chrono.agent(a)
        with chrono.phase("controles"):
            invalides = await asyncio.to_thread(
                contradicteur.citations_invalides, texte, ctx["sources"], ctx.get("lecteurs", []))
            if trace is not None:
                trace.update(texte=texte, invalides=[*trace.get("invalides", []), *invalides])
            fraiches = await asyncio.to_thread(contradicteur.fraicheur, texte, ctx.get("lecteurs", []))
            texte = avec_schema(schemas.verifier(texte, {c["id"]: c for c in ctx["claims"] if c.get("id")},
                                                 deja_dessine=bool(dessin and dessin.mermaid)), dessin)
        reponse = vers_reponse_flore(ctx["jumeau"], ctx["sources"], texte, invalides, fraiches)
        if dessin and dessin.preuves:  # chaque flèche du schéma renvoie à sa ligne, dans le volet des preuves
            reponse["preuves"] = (reponse["preuves"] + dessin.preuves)[:MAX_PREUVES + len(dessin.preuves)]
        reponse["durees"] = chrono.bilan()
        usage = mesure.fusionner_usages(mesure.usage(a), (verdict or {}).get("usage"))
        usage["cout"] = mesure.cout(usage)
        usage["modele"] = modele.get_config().get("model_id", "inconnu") if modele else "inconnu"
        reponse["usage"] = usage
        reponse["relecture_etat"] = etat = etat_relecture(verdict, corrige)
        reponse["relu"], reponse["corrige"] = etat == "relue", corrige
        reponse["pieces_selection"] = ctx.get("pieces_selection") or []
        reponse["pieces_lectures"] = journal_pieces
        if dessin and dessin.structure:
            reponse["schemas"] = [dessin.structure]
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


async def mobiliser(jumeau_ids, question, acteur, travail=None, profil=None, db=None, emit=None,
                    autoriser_ecriture=False):
    """Réponse de Flore qui mobilise plusieurs jumeaux réels (étoile) ; None si aucun n'est un jumeau réel ingéré.

    Seuls `jumeau_ids` (déjà filtrés par le serveur selon les droits) sont mobilisables. Avec des pièces jointes,
    les outils d'écriture ne sont ouverts que si l'humain les autorise pour ce tour.
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
    pieces_travail, pieces_prompt, pieces_selection, journal_pieces = [], "", [], []
    if travail and db is not None:
        from pieces import du_travail, sections_pour_prompt_detail
        pieces_travail = await du_travail(db, travail)
        if pieces_non_transmises(pieces_travail):
            pieces_travail = []
            pieces_prompt = NOTE_PIECES_NON_TRANSMISES
        elif pieces_travail:
            pieces_prompt, pieces_selection = sections_pour_prompt_detail(pieces_travail, question)
        # Le texte des pièces reste à l'orchestratrice : les sous-agents ne reçoivent que les cartes de leur
        # application, et le contexte (donc le coût) ne se multiplie pas par le nombre de jumeaux mobilisés.
    cle = cle_fil(acteur, travail)
    noms = " et ".join(c["jumeau"]["nom"] for c in ctxs.values())
    if not FILS.prendre("mobilisation", cle):
        return _indisponible(noms, "une réponse est déjà en cours sur ce fil.")
    try:
        modele = agent.modele()
        ecriture = (EcritureTravail(db, travail)
                    if travail and db is not None and (not pieces_travail or autoriser_ecriture) else None)
        if pieces_travail and not autoriser_ecriture:
            pieces_prompt = bloc_donnees_pieces(pieces_prompt, SANS_ECRITURE_AVEC_PIECES)
        etat = etat_texte(await ecriture.etat()) if ecriture else None
        mob = mobilisation.Mobilisation(ctxs, dsn, modele, emit)
        scene, relations = mobilisation.Scene(ctxs), {}  # seuls les jumeaux autorisés (déjà filtrés par le serveur)
        # Un schéma peut se fonder sur le code ou les connaissances de chacun des jumeaux mobilisés.
        tous = {"sources": [s for c in ctxs.values() for s in c["sources"]],
                "claims": [c for x in ctxs.values() for c in x["claims"]]}
        dessin = dessin_pour(tous) if tous["sources"] else None
        lecteurs_tous = [lecteur for c in ctxs.values() for lecteur in c.get("lecteurs", [])]
        verifier = lambda t: contradicteur.citations_invalides(t, tous["sources"], lecteurs_tous)  # noqa: E731
        budget = agent.Budget()
        outils = [mob.outil(), scene.outil(), agent.consulter_methode]
        if pieces_travail:
            outils += agent.outils_pieces(db, travail, budget, journal_pieces)
        if dessin:
            outils.append(agent.outil_dessin(dessin, budget))
        if ecriture:
            outils += agent.outils_travail(ecriture, budget, verifier, pieces_travail)
        a = mobilisation.orchestrateur(modele, mobilisation.prompt(etat), outils)
        # Durée bornée : chaque outil a son plafond, mais pas le nombre de tours de l'orchestratrice.
        with chrono.phase("cartes"):
            cartes = await _cartes(ctxs, dsn, db, relations)
        with chrono.phase("agent"):
            texte = await asyncio.wait_for(
                executer(a, mobilisation.demande(cartes, question, pieces_prompt), emit, chrono),
                mobilisation.DUREE_MAX)
        await _annoncer(emit, {"type": "relecture"})
        sources = [s for ctx in ctxs.values() for s in ctx["sources"]]
        branches = [lecteur for ctx in ctxs.values() for lecteur in ctx.get("lecteurs", [])]
        with chrono.phase("relecture"):
            verdict = await relire_sans_risque(
                question, texte, sources, profil, modele, agent.CHARTE.read_text(encoding="utf-8"), branches,
                sum(validees(ctx["claims"]) for ctx in ctxs.values()), pieces_travail)
        texte, corrige = await reviser(a, texte, verdict, chrono, emit, "mobilisation")
        texte, _invalides_pieces = await asyncio.to_thread(retirer_citations_pieces, texte, pieces_travail)
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
        volet = preuves[:MAX_PREUVES] + (dessin.preuves if dessin else [])
        reponse = {
            "comportement": "expliquer",
            "reponse": pastiller(texte, volet, tous["sources"]),
            "contributions": [{"jumeau": ctxs[j]["jumeau"]["nom"], "texte": retirer_citations(c.constat)}
                              for j, c in mob.contributions.items()],
            "preuves": volet,
            **({"commande_carte": scene.commande} if scene.commande else {}),
            "durees": chrono.bilan(), "relecture_etat": etat_relecture(verdict, corrige),
            "relu": etat_relecture(verdict, corrige) == "relue", "corrige": corrige,
            "pieces_selection": pieces_selection, "pieces_lectures": journal_pieces,
            **({"schemas": [dessin.structure]} if dessin and dessin.structure else {}),
            "jumeaux_participants": [{"id": jid, "app_id": jid, "nom": ctx["jumeau"]["nom"],
                                      "domaine": ctx["jumeau"].get("domaine") or "SI", "participe": True}
                                     for jid, ctx in ctxs.items()],
        }
        usage = mesure.fusionner_usages(mesure.usage(a), *mob.usages, (verdict or {}).get("usage"))
        usage["cout"] = mesure.cout(usage)
        usage["modele"] = modele.get_config().get("model_id", "inconnu") if modele else "inconnu"
        reponse["usage"] = usage
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
