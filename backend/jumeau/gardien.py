"""Gardien du jumeau : il travaille sans humain, quand l'application change (Jumeau Harness §5.2).

À chaque nouveau commit : réingestion, comparaison des connaissances d'avant et d'après, signaux déterministes,
fiche vivante rédigée par Flore, situation publiée dans « Aujourd'hui ».

    python -m jumeau.gardien --jumeau tbt                      # une passe sur tous les dépôts du jumeau
    python -m jumeau.gardien --jumeau tbt --surveiller 300     # surveillance continue

ponytail: la surveillance interroge le dépôt à intervalle fixe ; un webhook Git (EventBridge) la remplacera.
"""
import argparse
import asyncio
import logging
import os
import hashlib
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
from pydantic import BaseModel, Field
from strands import Agent

from jumeau import (agent, comprendre, connaissance, contradicteur, decouverte_interfaces, depot, impacts_situations,
                    lecteurs, methodes, notifications_impacts, poignee, recoupement, registre, schemas, temps)
from jumeau.ingerer import ingerer
from jumeau.source_git import sha_courant

journal = logging.getLogger("meridian.gardien")

# (prédicat, apparition ?) → type, gravité, libellé ; l'ordre fixe l'ordre de présentation (le plus grave d'abord).
REGLES = [
    ("EXPOSE", False, "SERVICE_RETIRE", "haute", "service retiré", "services retirés"),
    ("EXPOSE", True, "SERVICE_AJOUTE", "normale", "nouveau service", "nouveaux services"),
    ("DEPEND_DE", False, "DEPENDANCE_RETIREE", "normale", "dépendance retirée", "dépendances retirées"),
    ("DEPEND_DE", True, "DEPENDANCE_AJOUTEE", "normale", "nouvelle dépendance", "nouvelles dépendances"),
    ("EXECUTE_IMAGE", True, "IMAGE_AJOUTEE", "normale", "nouveau composant déployé", "nouveaux composants déployés"),
    ("EXECUTE_IMAGE", False, "IMAGE_RETIREE", "normale", "composant retiré", "composants retirés"),
    ("LIT_VARIABLE", True, "REGLAGE_AJOUTE", "basse", "nouveau réglage", "nouveaux réglages"),
    ("LIT_VARIABLE", False, "REGLAGE_RETIRE", "basse", "réglage retiré", "réglages retirés"),
]
SCORES = {"haute": 82, "normale": 64, "basse": 48}

CONSIGNE_FICHE = """Rédige la fiche vivante de l'application en appliquant la méthode comprendre-application
(consulter_methode) : enquête, propose les connaissances prouvées, puis réponds uniquement par la fiche."""

MOTS_FICHE = 300                 # méthode comprendre-application, « Fiche vivante »
MAX_MOTS_FICHE = MOTS_FICHE + 30  # tolérance avant de demander une révision


def mots(fiche):
    """Mots lus par un employé : sans les citations, qui partent dans le volet des preuves."""
    return sum(1 for m in re.sub(r"`[^`]*#L\d+[^`]*`", "", fiche or "").split() if re.search(r"\w", m))


CONSIGNE_CONSOLIDER = """Applique la section « Consolider » de la méthode ci-dessus aux connaissances suivantes
(identifiant, statut, formulation). Rends une décision pour chaque question listée : les groupes à fusionner, ou
aucun groupe s'il n'y a pas de doublon.

{liste}"""


class Groupe(BaseModel):
    garder: int = Field(description="identifiant de la connaissance gardée")
    retirer: list[int] = Field(description="identifiants des connaissances qui disent la même chose")
    raison: str = Field(description="pourquoi elles disent la même chose")


class Decision(BaseModel):
    question: str = Field(description="clé de la question, entre crochets dans la liste")
    groupes: list[Groupe] = Field(description="vide s'il n'y a aucun doublon")


class Consolidation(BaseModel):
    decisions: list[Decision]


def _juge():
    """Agent sans outils, guidé par la méthode : il juge une liste fournie, il n'enquête pas."""
    return Agent(model=agent.modele(), system_prompt=methodes.lire("comprendre-application"), callback_handler=None)


async def _decider(juge, consigne):
    # Structure imposée par un appel d'outil (accepté par tous les fournisseurs, DeepSeek compris).
    return (await juge.invoke_async(consigne, structured_output_model=Consolidation)).structured_output


async def consolider(conn, jumeau_id):
    """Une seule réponse par idée. L'agent juge (décision structurée, obligatoire pour chaque question) ; le harness
    valide et exécute : identifiants de la liste, même question, rien de ce que l'équipe a validé n'est retiré."""
    claims = [c for c in connaissance.connaissances(conn, jumeau_id, limite=1000) if c["predicat"] in comprendre.PREDICATS]
    par_question = {cle: [c for c in claims if c["predicat"] == predicat]
                    for cle, _, predicat, _ in comprendre.QUESTIONS if predicat}
    a_juger = {cle: liste for cle, liste in par_question.items() if len(liste) > 1}
    if not a_juger:
        return {"fusions": 0, "refus": 0}
    titres = {cle: titre for cle, titre, *_ in comprendre.QUESTIONS}
    liste = "\n\n".join(f"## {titres[cle]} [{cle}]\n" + "\n".join(
        f"- {c['id']} ({'validée' if c['statut'] == 'ACCEPTED' else 'proposée'}) : {c['objet']}" for c in lignes)
        for cle, lignes in a_juger.items())
    juge = _juge()
    decision = await _decider(juge, CONSIGNE_CONSOLIDER.format(liste=liste))
    manquantes = set(a_juger) - {d.question for d in decision.decisions}
    if manquantes:  # une décision par question, sans exception : une omission n'est pas un « aucun doublon »
        decision = await _decider(juge, f"Il manque une décision pour : {', '.join(sorted(manquantes))}. Rends la "
                                        "décision complète, pour chaque question listée.")
    bilan = {"fusions": 0, "refus": 0}
    for d in decision.decisions:
        ids = {c["id"] for c in a_juger.get(d.question, [])}
        for g in d.groupes:
            for retirer in g.retirer:
                if g.garder not in ids or retirer not in ids or retirer == g.garder:
                    bilan["refus"] += 1
                    continue
                try:
                    depot.fusionner(conn, jumeau_id, g.garder, retirer)
                    bilan["fusions"] += 1
                    journal.info("fusion %s ← %s (%s) : %s", g.garder, retirer, d.question, g.raison[:200])
                except ValueError as e:
                    bilan["refus"] += 1
                    journal.info("fusion refusée %s ← %s : %s", g.garder, retirer, e)
    return bilan


# Une passe du gardien enquête sur toute l'application : plus d'outils et de propositions qu'une réponse de Flore.
BUDGET_PASSE = {"outils": 60, "propositions": 30}


CONSIGNE_RECIT = """L'application vient de changer. Signaux observés automatiquement :
{signaux}
Changements récents :
{commits}
En trois phrases au plus, en langage métier, dis ce que ce changement change pour l'entreprise et ce qu'il faut
vérifier. Pas de titre, pas de liste, pas de citation. Réponds uniquement par ces phrases."""


def connaissances_courantes(conn, jumeau_id):
    return {(c["predicat"], c["objet"]) for c in connaissance.connaissances(conn, jumeau_id, limite=10000)}


def signaux(avant, apres):
    """Changements de connaissances structurelles entre deux ingestions, du plus grave au moins grave."""
    sortie = []
    for predicat, apparition, type_, gravite, *_ in REGLES:
        ensemble = apres - avant if apparition else avant - apres
        sortie += [{"type": type_, "gravite": gravite, "predicat": predicat, "objet": objet}
                   for p, objet in sorted(ensemble) if p == predicat]
    return sortie


def _titre(nom, sigs):
    morceaux = []
    for _, _, type_, _, un, plusieurs in REGLES:
        n = sum(1 for s in sigs if s["type"] == type_)
        if n:
            morceaux.append(f"{n} {un if n == 1 else plusieurs}")
    return f"{nom} a changé : " + ", ".join(morceaux) if morceaux else f"{nom} a changé"


def situation(jumeau, version, sigs, commits, recit):
    """Situation de genre « changement » pour le fil « Aujourd'hui » (même forme que les situations de démo)."""
    nom = jumeau["nom"]
    gravites = {s["gravite"] for s in sigs}
    priorite = "haute" if "haute" in gravites else "normale" if "normale" in gravites else "basse"
    retires = [s["objet"] for s in sigs if s["type"] == "SERVICE_RETIRE"]
    reste = ([f"Qui utilisait encore le service retiré « {o} » ?" for o in retires[:3]]
             + ["Le changement est-il déjà en production ? L'exploitation peut le confirmer."])
    return {
        "id": f"sit-gardien-{jumeau['id']}-{version[:12]}",
        "verbe": "a_comprendre",
        "nature": "changement",
        "type": "changement",
        "titre": _titre(nom, sigs),
        "resume": recit or f"Le gardien de {nom} a observé {len(sigs)} changement(s) dans son code.",
        "priorite": priorite,
        "statut": "active",
        "score": SCORES[priorite],
        "detectee": datetime.now(timezone.utc).isoformat(),
        "question": f"Que change cette évolution de {nom} ?",
        "jumeaux": [jumeau["id"]],
        "decouverte_quoi": "; ".join(f"{s['type'].replace('_', ' ').lower()} : {s['objet']}" for s in sigs[:12]),
        "decouverte_pourquoi": [f"{c['message']} ({c['auteur']}, {c['date']})" for c in commits[:8]],
        "reste_a_comprendre": reste,
        "chronologie": [{"heure": c["date"], "texte": c["message"], "jumeau": jumeau["id"], "nature": "changement"}
                        for c in reversed(commits[:8])],
        # Plus de couverture forfaitaire : une situation n'affirme pas un chiffre qu'aucune mesure ne produit (L2.7).
        "indicateurs": {"confiance": 90, "fraicheur": "à l'instant", "contradictions": 0},
        "reel": True,
    }


def enregistrer_fiche(conn, jumeau_id, sha, contenu):
    conn.execute(
        "INSERT INTO fiche_vivante (jumeau_id, sha, contenu) VALUES (%s, %s, %s) "
        "ON CONFLICT (jumeau_id, sha) DO UPDATE SET contenu = EXCLUDED.contenu, cree_le = now()",
        (jumeau_id, sha, contenu))


DELAI_FICHE_SANS_CODE = timedelta(hours=12)


def fiche_recente(conn, jumeau_id, delai):
    """Date de la dernière fiche si elle a moins de `delai`, sinon None."""
    r = conn.execute("SELECT max(cree_le) FROM fiche_vivante WHERE jumeau_id = %s", (jumeau_id,)).fetchone()
    return r[0].isoformat() if r and r[0] and datetime.now(timezone.utc) - r[0] < delai else None


def fiche_courante(conn, jumeau_id):
    r = conn.execute("SELECT sha, contenu FROM fiche_vivante WHERE jumeau_id = %s ORDER BY cree_le DESC LIMIT 1",
                     (jumeau_id,)).fetchone()
    return {"sha": r[0], "contenu": r[1]} if r else None


async def _rediger(ctx, dsn, sigs, commits):
    """Fiche vivante et récit du changement, rédigés par Flore avec les outils du jumeau (sans Travail).

    La fiche est relue dans le prompt de chaque conversation : ses citations sont vérifiées, révisées une fois,
    et celles qui restent fausses sont retirées. ponytail: pas de relecture par LLM (coût) ; à ajouter si la
    qualité des fiches dérive.
    """
    # Fil vierge à chaque passe : une passe précédente ne doit pas dicter la fiche (méthode à jour, code relu).
    a = agent.construire(ctx, dsn, session=None, budget=agent.Budget(**BUDGET_PASSE))
    fiche = str(await a.invoke_async(CONSIGNE_FICHE)).strip()
    invalides = contradicteur.citations_invalides(fiche, ctx["sources"], ctx.get("lecteurs", ()))
    if invalides:
        fiche = str(await a.invoke_async(contradicteur.consigne_revision(
            [f"Citations introuvables : {', '.join(invalides)}. Corrige-les avec lire_code ou retire l'affirmation."]
        ))).strip()
        fiche = contradicteur.retirer_citations_invalides(fiche, contradicteur.citations_invalides(fiche, ctx["sources"], ctx.get("lecteurs", ())))
    if mots(fiche) > MAX_MOTS_FICHE:  # une fiche trop longue perd le lecteur : une révision, comme pour les citations
        courte = str(await a.invoke_async(
            f"Ta fiche fait {mots(fiche)} mots ; la méthode en demande {MOTS_FICHE} au plus. Raccourcis-la sans changer "
            "ses sections ni ses citations ; réponds uniquement par la fiche.")).strip()
        if mots(courte) < mots(fiche) and not contradicteur.citations_invalides(courte, ctx["sources"], ctx.get("lecteurs", ())):
            fiche = courte
    recit = None
    if sigs:
        recit = str(await a.invoke_async(CONSIGNE_RECIT.format(
            signaux="\n".join(f"- {s['type']} : {s['objet']}" for s in sigs[:20]),
            commits="\n".join(f"- {c['date']} {c['message']}" for c in commits[:10])))).strip()
    return fiche, recit


def fiche_du_sha(conn, jumeau_id, sha):
    return conn.execute("SELECT 1 FROM fiche_vivante WHERE jumeau_id = %s AND sha = %s", (jumeau_id, sha)).fetchone()


async def publier(db, sit):
    """Publie la situation du changement et archive les précédentes du même jumeau (le fil ne s'encombre pas)."""
    prefixe = sit["id"].rsplit("-", 1)[0] + "-"
    await db.situations.update_many({"id": {"$regex": f"^{re.escape(prefixe)}", "$ne": sit["id"]}, "statut": "active"},
                                    {"$set": {"statut": "archivee"}})
    await db.situations.replace_one({"id": sit["id"]}, sit, upsert=True)


def empreinte(sources):
    """Version du jumeau : chaque dépôt avec son commit. La fiche vivante et la situation y sont rattachées."""
    return ",".join(f"{s['nom']}@{s['curseur'][:12]}" for s in sorted(sources, key=lambda s: s["nom"]))


class SourceInjoignable(Exception):
    """Une source branchée ne dit pas sa version : la passe ne rédige rien plutôt que de se tromper."""


def empreinte_lecteurs(branches):
    """Version d'un jumeau sans dépôt : l'état de chacune de ses sources (une source qui avance change la version)."""
    versions = []
    for l in sorted(branches, key=lambda l: l.nom):
        try:
            versions.append(f"{l.nom}:{l.version_courante()}")
        except Exception as e:  # réseau, secret absent, quota : on réessaiera à la passe suivante
            raise SourceInjoignable(f"source {l.nom} injoignable") from e
    brut = ",".join(versions)
    return "sources:" + hashlib.sha256(brut.encode()).hexdigest()[:16] if brut else ""


def _id_version(empreinte_):
    return hashlib.sha256(empreinte_.encode()).hexdigest()[:12]


def _rafraichir(source):
    """Un dépôt cloné par la naissance se relit depuis sa forge (même branche, même jeton de référence)."""
    if not source or not source.get("url"):
        return
    from jumeau import naissance  # import tardif : naissance utilise le gardien
    naissance.cloner({"url": source["url"], "branches": source.get("branche") or "main",
                      "secret": source.get("secret_ref")}, Path(source["emplacement"]))


async def veiller(conn, db, jumeau_id, chemins=None, rediger=_rediger):
    """Une passe du gardien sur tous les dépôts du jumeau (ou ceux de `chemins`).

    La partie déterministe (ingestion des dépôts qui ont avancé, signaux, situation) est publiée avant toute
    rédaction par le modèle : une panne du modèle ne fait jamais perdre un changement, et la passe suivante
    refait seulement la fiche qui manque.
    """
    jumeau = depot.jumeau_par_id(conn, jumeau_id)
    if not jumeau:
        raise ValueError(f"jumeau inconnu : {jumeau_id} (l'ingérer une première fois)")
    connues = depot.sources_du_jumeau(conn, jumeau_id)
    chemins = [Path(c).resolve() for c in (chemins or [s["emplacement"] for s in connues])]
    avant = connaissances_courantes(conn, jumeau_id)
    commits, ingeres, premiere = [], [], not connues
    for chemin in chemins:
        source_avant = next((s for s in connues if Path(s["emplacement"]).resolve() == chemin), None)
        try:
            await asyncio.to_thread(_rafraichir, source_avant)
        except (RuntimeError, ValueError, OSError):  # un dépôt injoignable ne bloque pas la veille des autres
            journal.warning("gardien %s : dépôt %s injoignable, ignoré à cette passe", jumeau_id, chemin.name,
                            exc_info=True)
            continue
        sha_avant = source_avant["curseur"] if source_avant else None
        if sha_courant(chemin) == sha_avant:
            continue
        origine = {k: source_avant[k] for k in ("branche", "url", "secret_ref")} if source_avant else None
        await asyncio.to_thread(ingerer, conn, jumeau, chemin, origine)
        source = depot.source_du_jumeau(conn, jumeau_id, chemin.name)
        nouveaux = temps.commits_entre(source, sha_avant, source["curseur"])
        commits += [{**c, "depot": source["nom"]} for c in nouveaux]
        ingeres.append(source["nom"])
    sources = depot.sources_du_jumeau(conn, jumeau_id)
    if ingeres:
        # La découverte d'interfaces fait partie de la passe : elle transforme les EXPOSE du code en graphe daté,
        # journalise un DiscoveryRun et calcule les changements/impacts. Une panne de ce journal ne bloque pas la veille.
        try:
            resultat = decouverte_interfaces.executer(
                conn, jumeau["tenant_id"], jumeau_id,
                claims=connaissance.connaissances(conn, jumeau_id, limite=1000), source="gardien")
            sit = impacts_situations.situation_depuis_run(resultat["run"], jumeau)
            if sit:
                await publier(db, sit)
                await notifications_impacts.publier_notification(db, jumeau, resultat["run"], sit)
        except Exception:
            journal.warning("gardien %s : découverte d'interfaces impossible", jumeau_id, exc_info=True)
    branches = lecteurs.lecteurs_de(depot.toutes_les_sources(conn, jumeau_id))
    # Sans dépôt (progiciel), pas d'ingestion de code : la version est celle des sources branchées.
    try:
        version = empreinte(sources) if sources else empreinte_lecteurs(branches)
    except SourceInjoignable as e:
        journal.warning("gardien %s : %s, passe sans rédaction", jumeau_id, e)
        return {"changement": False, "erreur": str(e)}
    if not ingeres and fiche_du_sha(conn, jumeau_id, version):
        return {"changement": False}
    # Sans code, une source qui bouge souvent (un ticket modifié) ne fait pas rédiger une fiche à chaque fois.
    if not sources and (recente := fiche_recente(conn, jumeau_id, DELAI_FICHE_SANS_CODE)):
        return {"changement": False, "fiche_recente": recente}
    sigs, sit = (signaux(avant, connaissances_courantes(conn, jumeau_id)) if ingeres else []), None
    if len(sources) > 1:
        commits = [{**c, "message": f"[{c['depot']}] {c['message']}"} for c in commits]
    if ingeres:
        comprendre.clore_sans_preuve(conn, jumeau_id)  # le code a changé : ce qui n'est plus prouvé est clos
        if sigs and not premiere:  # première ingestion : pas de « changement » à annoncer
            sit = situation(jumeau, _id_version(version), sigs, commits, None)
            await publier(db, sit)
        await registre.projeter(db, conn)
    bilan = {"changement": True, "version": version, "depots": ingeres, "signaux": len(sigs), "commits": len(commits)}
    ctx = {"jumeau": jumeau, "consignes": depot.consignes_du_jumeau(conn, jumeau),
           "sources": [s for s in sources if s["index_code"]],
           # Les sources branchées (documentation, trajectoire…) : la méthode y route les questions du « pourquoi ».
           "lecteurs": branches,
           # Ce que sa preuve n'appuie pas ne nourrit pas la fiche (Harness v3 §2) ; la méthode le dit aussi.
           "claims": [c for c in connaissance.connaissances(conn, jumeau_id, limite=500)
                      if (c.get("verification") or {}).get("etat") not in schemas.NON_TENUES],
           "acteur": "gardien", "profil": {"nom": "Gardien du jumeau", "role": "veille automatique"}}
    try:
        fiche, recit = await rediger(ctx, os.environ.get("JUMEAU_PG_DSN", ""), sigs, commits)
    except Exception:
        journal.warning("gardien %s : rédaction impossible, reprise à la passe suivante", jumeau_id, exc_info=True)
        return {**bilan, "fiche": False}
    enregistrer_fiche(conn, jumeau_id, version, fiche)
    try:
        journal.info("gardien %s : consolidation %s", jumeau_id, await consolider(conn, jumeau_id))
    except Exception:  # la consolidation se rattrape à la passe suivante ; la fiche est déjà enregistrée
        journal.warning("gardien %s : consolidation impossible", jumeau_id, exc_info=True)
    try:  # vérifier comme on teste (Harness v3 §2) : recettes sans modèle, juge d'appui borné
        journal.info("gardien %s : vérification %s", jumeau_id,
                     await recoupement.verifier(conn, jumeau, branches, agent.modele_juge()))
    except Exception:  # la vérification se rejoue à la passe suivante
        journal.warning("gardien %s : vérification impossible", jumeau_id, exc_info=True)
    try:
        journal.info("gardien %s : ancrage Jira, %s ancre(s)", jumeau_id, await asyncio.to_thread(
            connaissance.ancrer_jira, conn, jumeau, [s for s in sources if s["index_code"]]))
    except Exception:  # l'ancrage se rejoue à la passe suivante
        journal.warning("gardien %s : ancrage Jira impossible", jumeau_id, exc_info=True)
    try:
        journal.info("gardien %s : poignée de main %s", jumeau_id, await poignee.serrer(conn, db, jumeau_id))
    except Exception:  # les relations se reprennent à la passe suivante
        journal.warning("gardien %s : poignée de main impossible", jumeau_id, exc_info=True)
    if sit and recit:
        await db.situations.update_one({"id": sit["id"]}, {"$set": {"resume": recit}})
    journal.info("gardien %s : %s dépôt(s) ingéré(s), %s signal(aux)", jumeau_id, len(ingeres), len(sigs))
    return bilan


async def surveiller(connecter, db, jumeau_id, chemins, intervalle, passes=None):
    """Passes répétées ; une erreur passagère (modèle, base, git) est journalisée, la surveillance continue."""
    n = 0
    while passes is None or n < passes:
        n += 1
        try:
            with connecter() as conn:
                print(await veiller(conn, db, jumeau_id, chemins), flush=True)
        except Exception:
            journal.exception("gardien %s : passe en échec, nouvel essai dans %s s", jumeau_id, intervalle)
        if passes is None or n < passes:
            await asyncio.sleep(intervalle)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--jumeau", required=True)
    p.add_argument("--depot", action="append", type=Path,
                   help="dépôt à surveiller (répétable) ; par défaut, tous les dépôts connus du jumeau")
    p.add_argument("--surveiller", type=int, metavar="SECONDES", help="surveille le dépôt à cet intervalle")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    from motor.motor_asyncio import AsyncIOMotorClient

    def connecter():
        return psycopg.connect(os.environ["JUMEAU_PG_DSN"], autocommit=True)

    async def lancer():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        try:
            await surveiller(connecter, client[os.environ["DB_NAME"]], a.jumeau, a.depot,
                             a.surveiller or 0, passes=None if a.surveiller else 1)
        finally:
            client.close()
    asyncio.run(lancer())


if __name__ == "__main__":
    main()
