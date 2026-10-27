"""Persistance des jumeaux, preuves et Claims (Postgres)."""
from pathlib import Path

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

SCHEMA = Path(__file__).with_name("schema.sql")
MATURITE_APRES_ACCEPTATION = "M3"  # code + validation humaine = deux sources indépendantes (§7.2)


VERROU_SCHEMA = 4242


def appliquer_schema(conn):
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (VERROU_SCHEMA,))
        conn.execute(SCHEMA.read_text())


def enregistrer(conn, jumeau, source, claims, activite):
    """Upsert du jumeau, de la source, des Claims et de leurs preuves ; clôture les Claims non revus.

    Un Claim clos puis réobservé repart en PROPOSED/M2 : sa validation portait sur une période révolue.
    ponytail: clôture sur tout le jumeau, valable tant qu'il n'a qu'une source de code ; filtrer par source en phase 1.
    """
    if not claims:
        raise ValueError("aucun claim : ingestion refusée pour ne pas clôturer le jumeau")
    t = jumeau["tenant_id"]
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (jumeau["id"],))
        existant = conn.execute("SELECT tenant_id FROM jumeau WHERE id = %s", (jumeau["id"],)).fetchone()
        if existant and existant[0] != t:
            raise PermissionError(f"jumeau {jumeau['id']} appartient à un autre tenant")
        conn.execute(
            "INSERT INTO jumeau (id, tenant_id, nom, equipe) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (id) DO UPDATE SET nom = EXCLUDED.nom, equipe = EXCLUDED.equipe",
            (jumeau["id"], t, jumeau["nom"], jumeau["equipe"]))
        source_id = conn.execute(
            "INSERT INTO source (tenant_id, jumeau_id, type, nom, emplacement, curseur) "
            "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (jumeau_id, nom) "
            "DO UPDATE SET emplacement = EXCLUDED.emplacement, curseur = EXCLUDED.curseur RETURNING id",
            (t, jumeau["id"], source["type"], source["nom"], source["emplacement"], source["curseur"])).fetchone()[0]
        vus = []
        for c in claims:
            cid = conn.execute(
                "INSERT INTO claim (tenant_id, jumeau_id, sujet, predicat, objet, type, confiance) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (jumeau_id, predicat, objet) DO UPDATE SET "
                "confiance = EXCLUDED.confiance, "
                "statut = CASE WHEN claim.valide_jusqua IS NULL THEN claim.statut ELSE 'PROPOSED' END, "
                "maturite = CASE WHEN claim.valide_jusqua IS NULL THEN claim.maturite ELSE 'M2' END, "
                "valide_depuis = CASE WHEN claim.valide_jusqua IS NULL THEN claim.valide_depuis ELSE now() END, "
                "valide_jusqua = NULL RETURNING id",
                (t, jumeau["id"], c["sujet"], c["predicat"], c["objet"], c["type"], c["confiance"])).fetchone()[0]
            vus.append(cid)
            for p in c["preuves"]:
                conn.execute(
                    "INSERT INTO preuve (tenant_id, source_id, locator, chemin, sha, ligne_debut, ligne_fin, hash, activite) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (source_id, locator) DO NOTHING",
                    (t, source_id, p["locator"], p["chemin"], p["sha"], p["ligne_debut"], p["ligne_fin"],
                     p["hash"], Jsonb(activite)))
                conn.execute(
                    "INSERT INTO claim_preuve (claim_id, preuve_id) "
                    "SELECT %s, id FROM preuve WHERE source_id = %s AND locator = %s ON CONFLICT DO NOTHING",
                    (cid, source_id, p["locator"]))
        conn.execute(
            "UPDATE claim SET valide_jusqua = now() "
            "WHERE jumeau_id = %s AND valide_jusqua IS NULL AND NOT (id = ANY(%s))",
            (jumeau["id"], vus))


def reviser(conn, claim_id, acteur, decision, motif):
    """Revue humaine : la revue est écrite avant le statut (exigé par le trigger d'acceptation)."""
    with conn.transaction():
        tenant = conn.execute(
            "SELECT tenant_id FROM claim WHERE id = %s AND valide_jusqua IS NULL FOR UPDATE", (claim_id,)).fetchone()
        if not tenant:
            raise LookupError(claim_id)
        conn.execute(
            "INSERT INTO revue (tenant_id, claim_id, acteur, decision, motif) VALUES (%s, %s, %s, %s, %s)",
            (tenant[0], claim_id, acteur, decision, motif))
        maturite = "GREATEST(maturite, %s)" if decision == "ACCEPTED" else "maturite"
        params = (decision, MATURITE_APRES_ACCEPTATION, claim_id) if decision == "ACCEPTED" else (decision, claim_id)
        conn.execute(f"UPDATE claim SET statut = %s, maturite = {maturite} WHERE id = %s", params)


def lister_jumeaux(conn):
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "SELECT j.id, j.nom, j.equipe, count(c.id) FILTER (WHERE c.valide_jusqua IS NULL) AS claims "
            "FROM jumeau j LEFT JOIN claim c ON c.jumeau_id = j.id GROUP BY j.id ORDER BY j.nom").fetchall()


def lister_claims(conn, jumeau_id):
    """Claims valides du jumeau, avec preuves et revues."""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            """SELECT c.id, c.sujet, c.predicat, c.objet, c.type, c.statut, c.maturite,
                      c.confiance::float AS confiance, c.valide_depuis,
                      (SELECT coalesce(json_agg(json_build_object(
                          'id', p.id, 'locator', p.locator, 'chemin', p.chemin, 'sha', p.sha,
                          'ligne_debut', p.ligne_debut, 'ligne_fin', p.ligne_fin) ORDER BY p.id), '[]')
                       FROM claim_preuve cp JOIN preuve p ON p.id = cp.preuve_id WHERE cp.claim_id = c.id) AS preuves,
                      (SELECT coalesce(json_agg(json_build_object(
                          'acteur', r.acteur, 'decision', r.decision, 'motif', r.motif, 'le', r.le) ORDER BY r.le DESC), '[]')
                       FROM revue r WHERE r.claim_id = c.id) AS revues
               FROM claim c WHERE c.jumeau_id = %s AND c.valide_jusqua IS NULL
               ORDER BY c.type, c.predicat, c.objet""",
            (jumeau_id,)).fetchall()


def preuve_par_id(conn, preuve_id):
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "SELECT p.id, p.chemin, p.sha, p.ligne_debut, p.ligne_fin, p.hash, s.emplacement "
            "FROM preuve p JOIN source s ON s.id = p.source_id WHERE p.id = %s",
            (preuve_id,)).fetchone()
