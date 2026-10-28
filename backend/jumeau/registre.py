"""Projection des jumeaux réels (Postgres) dans le registre de l'application (collection Mongo `jumeaux`).

Le jumeau réel devient sélectionnable partout où l'application travaille déjà avec des jumeaux : Atlas, registre,
contexte de Flore, « Nouveau travail ». Rejouée au démarrage du serveur (le seed de démo vide le registre) et après
chaque ingestion. Postgres reste la source de vérité ; le registre n'en est qu'une vue.
"""
from psycopg.rows import dict_row

from jumeau import depot

SOURCES_POSSIBLES = ("code", "bdd", "observabilite", "incidents", "documentation")


def couverture(etablis, hypotheses):
    """Part de ce que le jumeau affirme **qui est établi** par une source, plutôt qu'écrit par un modèle.

    Avant, la couverture valait `min(20 + 12 * nb_sources, 88)` appliqué avec un `1` en dur : **tout jumeau réel
    affichait 32 %**, quel que soit son contenu — un chiffre qui ne mesurait rien et flattait d'autant plus que le
    jumeau savait peu (plan de remédiation L2.7). Ici, la valeur baisse quand le modèle écrit davantage sans preuve :
    c'est exactement ce qu'on veut voir.
    """
    total = (etablis or 0) + (hypotheses or 0)
    return round(100 * (etablis or 0) / total) if total else 0


def document(j):
    return {
        "id": j["id"],
        "nom": j["nom"],
        "domaine": j["domaine"],
        "mission": j["mission"] or f"Application {j['nom']}, comprise à partir de son code",
        "proprietaire": j["equipe"],
        "environnement": "production",
        "statut": "actif",
        "autonomie": "supervisé",
        "couverture": couverture(j.get("etablis"), j.get("hypotheses")),
        "fraicheur": (f"sans code · substance : {depot.substance(j.get('types') or []) or 'aucune'}" if j.get("depots", 1) == 0
                      else f"{j['depots']} dépôts de code · {j['claims']} claims" if j.get("depots", 1) > 1
                      else f"code au commit {j['curseur'][:12]} · {j['claims']} claims"),
        "sante": "inconnue",  # aucune source d'observabilité connectée
        "sources": {s: s == "code" and j.get("depots", 1) > 0 for s in SOURCES_POSSIBLES},
        "sources_detail": [{"cle": f"git-{d['nom']}", "statut": "prete",
                            "nom": f"Dépôt {d['nom']}" + (f" · {d['branche']}" if d.get("branche") else "")
                                   + f" · {d['curseur'][:12]}"} for d in j.get("liste_depots") or []],
        "reel": True,
        "ci": j.get("ci"),  # ancre d'identité (CMDB), quand la source ServiceNow est branchée
    }


def jumeaux_reels(conn):
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            """SELECT j.id, j.nom, j.equipe, j.domaine, j.mission, s.curseur,
                      (SELECT count(*) FROM claim c WHERE c.jumeau_id = j.id AND c.valide_jusqua IS NULL) AS claims,
                      (SELECT count(*) FROM claim c WHERE c.jumeau_id = j.id AND c.valide_jusqua IS NULL
                        AND predicat_prouvable(c.predicat)) AS etablis,
                      (SELECT count(*) FROM claim c WHERE c.jumeau_id = j.id AND c.valide_jusqua IS NULL
                        AND NOT predicat_prouvable(c.predicat)) AS hypotheses,
                      (SELECT count(*) FROM source WHERE jumeau_id = j.id AND type = 'GIT') AS depots,
                      (SELECT emplacement FROM source WHERE jumeau_id = j.id AND type = 'SERVICENOW'
                       ORDER BY id LIMIT 1) AS ci,
                      (SELECT array_agg(DISTINCT type) FROM source WHERE jumeau_id = j.id) AS types,
                      (SELECT json_agg(json_build_object('nom', nom, 'branche', branche, 'curseur', curseur)
                                       ORDER BY nom) FROM source WHERE jumeau_id = j.id AND type = 'GIT') AS liste_depots
               FROM jumeau j
               LEFT JOIN LATERAL (SELECT curseur FROM source WHERE jumeau_id = j.id AND type = 'GIT'
                             ORDER BY id DESC LIMIT 1) s ON true
               WHERE EXISTS (SELECT 1 FROM source WHERE jumeau_id = j.id)
               ORDER BY j.id""").fetchall()


ECART = 110  # distance minimale entre deux jumeaux sur l'Atlas (MIN_DIST du placement, plus une marge)
ANCRE_SANS_DOMAINE = (1260, 40)  # comme un jumeau né d'une commande (server.py)


def position_libre(ancre, occupees):
    """Première position à au moins ECART de toutes les autres, en spirale autour de `ancre` (déterministe)."""
    import math
    for n in range(400):
        angle, rayon = n * 2.39996, ECART * math.sqrt(n)  # spirale de Fibonacci : couvre le plan sans trou
        x, y = round(ancre[0] + rayon * math.cos(angle)), round(ancre[1] + rayon * math.sin(angle))
        if all(math.hypot(x - ox, y - oy) >= ECART for ox, oy in occupees):
            return {"x": x, "y": y}
    return {"x": ancre[0], "y": ancre[1]}  # ponytail: carte saturée autour de l'ancre ; le placement de l'Atlas écartera


async def _placer(db, jumeau_id, domaine):
    """Un jumeau réel sans position (l'Atlas ne peut pas le dessiner) en reçoit une près de son domaine. Une position
    posée à la main n'est jamais écrasée (mise à jour conditionnelle)."""
    autres = [d async for d in db.jumeaux.find({"position": {"$ne": None}}, {"_id": 0, "domaine": 1, "position": 1})]
    voisins = [d["position"] for d in autres if d.get("domaine") == domaine and d.get("position")]
    ancre = ((sum(p["x"] for p in voisins) / len(voisins), sum(p["y"] for p in voisins) / len(voisins))
             if voisins else ANCRE_SANS_DOMAINE)
    position = position_libre(ancre, [(d["position"]["x"], d["position"]["y"]) for d in autres if d.get("position")])
    await db.jumeaux.update_one({"id": jumeau_id, "position": None}, {"$set": {"position": position}})


async def projeter(db, conn):
    """Upsert des jumeaux réels dans le registre (motor) ; les jumeaux de démo ne sont pas touchés."""
    reels = jumeaux_reels(conn)
    for j in reels:
        doc = document(j)
        statut = doc.pop("statut")
        # Le statut n'est posé qu'à la création : un jumeau né d'une commande reste « en observation »
        # jusqu'à son admission par un humain.
        await db.jumeaux.update_one({"id": j["id"]}, {"$set": doc, "$setOnInsert": {"statut": statut}}, upsert=True)
        await _placer(db, j["id"], doc.get("domaine"))
    return len(reels)
