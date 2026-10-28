"""Projection des jumeaux réels (Postgres) dans le registre de l'application (collection Mongo `jumeaux`).

Le jumeau réel devient sélectionnable partout où l'application travaille déjà avec des jumeaux : Atlas, registre,
contexte de Flore, « Nouveau travail ». Rejouée au démarrage du serveur (le seed de démo vide le registre) et après
chaque ingestion. Postgres reste la source de vérité ; le registre n'en est qu'une vue.
"""
from psycopg.rows import dict_row

SOURCES_POSSIBLES = ("code", "bdd", "observabilite", "incidents", "documentation")


def couverture(nb_sources):
    # Même règle que la création d'un jumeau dans l'atelier (server.py) : chaque source connectée compte.
    return min(20 + 12 * nb_sources, 88)


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
        "couverture": couverture(1),
        "fraicheur": (f"{j['depots']} dépôts de code · {j['claims']} claims" if j.get("depots", 1) > 1
                      else f"code au commit {j['curseur'][:12]} · {j['claims']} claims"),
        "sante": "inconnue",  # aucune source d'observabilité connectée
        "sources": {s: s == "code" for s in SOURCES_POSSIBLES},
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
                      (SELECT count(*) FROM source WHERE jumeau_id = j.id AND type = 'GIT') AS depots,
                      (SELECT emplacement FROM source WHERE jumeau_id = j.id AND type = 'SERVICENOW'
                       ORDER BY id LIMIT 1) AS ci,
                      (SELECT json_agg(json_build_object('nom', nom, 'branche', branche, 'curseur', curseur)
                                       ORDER BY nom) FROM source WHERE jumeau_id = j.id AND type = 'GIT') AS liste_depots
               FROM jumeau j
               JOIN LATERAL (SELECT curseur FROM source WHERE jumeau_id = j.id AND type = 'GIT'
                             ORDER BY id DESC LIMIT 1) s ON true
               ORDER BY j.id""").fetchall()


async def projeter(db, conn):
    """Upsert des jumeaux réels dans le registre (motor) ; les jumeaux de démo ne sont pas touchés."""
    reels = jumeaux_reels(conn)
    for j in reels:
        doc = document(j)
        statut = doc.pop("statut")
        # Le statut n'est posé qu'à la création : un jumeau né d'une commande reste « en observation »
        # jusqu'à son admission par un humain.
        await db.jumeaux.update_one({"id": j["id"]}, {"$set": doc, "$setOnInsert": {"statut": statut}}, upsert=True)
    return len(reels)
