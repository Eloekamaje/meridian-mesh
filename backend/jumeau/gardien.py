"""Gardien du jumeau : il travaille sans humain, quand l'application change (Jumeau Harness §5.2).

À chaque nouveau commit : réingestion, comparaison des connaissances d'avant et d'après, signaux déterministes,
fiche vivante rédigée par Flore, situation publiée dans « Aujourd'hui ».

    python -m jumeau.gardien --jumeau tbt --depot /chemin/vers/depot              # une passe
    python -m jumeau.gardien --jumeau tbt --depot /chemin/vers/depot --surveiller 300

ponytail: la surveillance interroge le dépôt à intervalle fixe ; un webhook Git (EventBridge) la remplacera.
"""
import argparse
import asyncio
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import psycopg

from jumeau import agent, connaissance, contradicteur, depot, registre, temps
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

CONSIGNE_FICHE = """Rédige la fiche vivante de l'application, que tu reliras au début de chaque conversation.
En Markdown, 350 mots au plus, sections : « Ce qu'elle fait pour l'entreprise », « Ses grands services »,
« Ce sur quoi elle s'appuie », « Ses évolutions récentes » (regarde son histoire), « Ce qui reste inconnu ».
Langage métier, chaque affirmation suivie de sa citation `chemin#Ldébut-Lfin`. Réponds uniquement par la fiche."""

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


def situation(jumeau, sha, sigs, commits, recit):
    """Situation de genre « changement » pour le fil « Aujourd'hui » (même forme que les situations de démo)."""
    nom = jumeau["nom"]
    gravites = {s["gravite"] for s in sigs}
    priorite = "haute" if "haute" in gravites else "normale" if "normale" in gravites else "basse"
    retires = [s["objet"] for s in sigs if s["type"] == "SERVICE_RETIRE"]
    reste = ([f"Qui utilisait encore le service retiré « {o} » ?" for o in retires[:3]]
             + ["Le changement est-il déjà en production ? L'exploitation peut le confirmer."])
    return {
        "id": f"sit-gardien-{jumeau['id']}-{sha[:12]}",
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
        "indicateurs": {"confiance": 90, "couverture": registre.couverture(1), "fraicheur": "à l'instant",
                        "contradictions": 0},
        "reel": True,
    }


def enregistrer_fiche(conn, jumeau_id, sha, contenu):
    conn.execute(
        "INSERT INTO fiche_vivante (jumeau_id, sha, contenu) VALUES (%s, %s, %s) "
        "ON CONFLICT (jumeau_id, sha) DO UPDATE SET contenu = EXCLUDED.contenu, cree_le = now()",
        (jumeau_id, sha, contenu))


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
    a = agent.construire(ctx, dsn, session=f"gardien-{ctx['jumeau']['id']}-{ctx['source']['curseur'][:12]}")
    fiche = str(await a.invoke_async(CONSIGNE_FICHE)).strip()
    invalides = contradicteur.citations_invalides(fiche, ctx["source"])
    if invalides:
        fiche = str(await a.invoke_async(contradicteur.consigne_revision(
            [f"Citations introuvables : {', '.join(invalides)}. Corrige-les avec lire_code ou retire l'affirmation."]
        ))).strip()
        fiche = contradicteur.retirer_citations_invalides(fiche, contradicteur.citations_invalides(fiche, ctx["source"]))
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


async def veiller(conn, db, jumeau_id, chemin_depot, rediger=_rediger):
    """Une passe du gardien. La partie déterministe (ingestion, signaux, situation) est publiée avant toute
    rédaction par le modèle : une panne du modèle ne fait jamais perdre un changement, et la passe suivante
    refait seulement la fiche qui manque.
    """
    jumeau = depot.jumeau_par_id(conn, jumeau_id)
    if not jumeau:
        raise ValueError(f"jumeau inconnu : {jumeau_id} (l'ingérer une première fois)")
    source_avant = depot.source_du_jumeau(conn, jumeau_id)
    sha_avant = source_avant["curseur"] if source_avant else None
    sigs, commits, bilan, sit = [], [], {}, None
    if sha_courant(chemin_depot) == sha_avant:
        if fiche_du_sha(conn, jumeau_id, sha_avant):
            return {"changement": False}
        source = source_avant  # passe précédente interrompue après l'ingestion : seule la fiche manque
    else:
        avant = connaissances_courantes(conn, jumeau_id)
        bilan = ingerer(conn, jumeau, Path(chemin_depot).resolve())
        sigs = signaux(avant, connaissances_courantes(conn, jumeau_id))
        source = depot.source_du_jumeau(conn, jumeau_id)
        commits = temps.commits_entre(source, sha_avant, source["curseur"])
        if sigs and sha_avant:  # première ingestion : pas de « changement » à annoncer
            sit = situation(jumeau, source["curseur"], sigs, commits, None)
            await publier(db, sit)
        await registre.projeter(db, conn)
    ctx = {"jumeau": jumeau, "source": source, "claims": connaissance.connaissances(conn, jumeau_id, limite=500),
           "acteur": "gardien", "profil": {"nom": "Gardien du jumeau", "role": "veille automatique"}}
    try:
        fiche, recit = await rediger(ctx, os.environ.get("JUMEAU_PG_DSN", ""), sigs, commits)
    except Exception:
        journal.warning("gardien %s : rédaction impossible, reprise à la passe suivante", jumeau_id, exc_info=True)
        return {"changement": True, "sha": source["curseur"], "signaux": len(sigs), "commits": len(commits),
                "fiche": False, **bilan}
    enregistrer_fiche(conn, jumeau_id, source["curseur"], fiche)
    if sit and recit:
        await db.situations.update_one({"id": sit["id"]}, {"$set": {"resume": recit}})
    journal.info("gardien %s : %s signal(aux), %s commit(s)", jumeau_id, len(sigs), len(commits))
    return {"changement": True, "sha": source["curseur"], "signaux": len(sigs), "commits": len(commits), **bilan}


async def surveiller(connecter, db, jumeau_id, chemin_depot, intervalle, passes=None):
    """Passes répétées ; une erreur passagère (modèle, base, git) est journalisée, la surveillance continue."""
    n = 0
    while passes is None or n < passes:
        n += 1
        try:
            with connecter() as conn:
                print(await veiller(conn, db, jumeau_id, chemin_depot), flush=True)
        except Exception:
            journal.exception("gardien %s : passe en échec, nouvel essai dans %s s", jumeau_id, intervalle)
        if passes is None or n < passes:
            await asyncio.sleep(intervalle)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--jumeau", required=True)
    p.add_argument("--depot", required=True, type=Path)
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
