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
            "INSERT INTO jumeau (id, tenant_id, nom, equipe, domaine, mission) "
            "VALUES (%s, %s, %s, %s, coalesce(%s, 'À confirmer'), %s) ON CONFLICT (id) DO UPDATE SET "
            "nom = EXCLUDED.nom, equipe = EXCLUDED.equipe, "
            "domaine = coalesce(%s, jumeau.domaine), mission = coalesce(%s, jumeau.mission)",
            (jumeau["id"], t, jumeau["nom"], jumeau["equipe"], jumeau.get("domaine"), jumeau.get("mission"),
             jumeau.get("domaine"), jumeau.get("mission")))
        source_id = conn.execute(
            "INSERT INTO source (tenant_id, jumeau_id, type, nom, emplacement, curseur, copie, index_code, branche, "
            "url, secret_ref) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (jumeau_id, nom) "
            "DO UPDATE SET emplacement = EXCLUDED.emplacement, curseur = EXCLUDED.curseur, copie = EXCLUDED.copie, "
            "index_code = EXCLUDED.index_code, branche = coalesce(EXCLUDED.branche, source.branche), "
            "url = coalesce(EXCLUDED.url, source.url), secret_ref = coalesce(EXCLUDED.secret_ref, source.secret_ref) "
            "RETURNING id",
            (t, jumeau["id"], source["type"], source["nom"], source["emplacement"], source["curseur"],
             source.get("copie"), source.get("index_code"), source.get("branche"), source.get("url"),
             source.get("secret_ref"))).fetchone()[0]
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
            conn.execute("INSERT INTO claim_source (claim_id, source_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                         (cid, source_id))
            for p in c["preuves"]:
                _lier_preuve(conn, t, source_id, cid, p, activite)
        # Cette source n'observe plus ce qu'elle n'a pas revu ; un Claim d'ingestion n'est clos que si plus aucune
        # source du jumeau ne l'observe (plusieurs dépôts par jumeau). Les propositions de conversation attendent
        # leur revue et ne sont jamais closes ici.
        conn.execute("DELETE FROM claim_source WHERE source_id = %s AND NOT (claim_id = ANY(%s))", (source_id, vus))
        conn.execute(
            "UPDATE claim SET valide_jusqua = now() WHERE jumeau_id = %s AND origine = 'INGESTION' "
            "AND valide_jusqua IS NULL AND NOT EXISTS (SELECT 1 FROM claim_source cs WHERE cs.claim_id = claim.id)",
            (jumeau["id"],))


def _lier_preuve(conn, tenant, source_id, claim_id, p, activite):
    conn.execute(
        "INSERT INTO preuve (tenant_id, source_id, locator, chemin, sha, ligne_debut, ligne_fin, hash, activite) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (source_id, locator) DO NOTHING",
        (tenant, source_id, p["locator"], p["chemin"], p["sha"], p["ligne_debut"], p["ligne_fin"],
         p["hash"], Jsonb(activite)))
    conn.execute(
        "INSERT INTO claim_preuve (claim_id, preuve_id) "
        "SELECT %s, id FROM preuve WHERE source_id = %s AND locator = %s ON CONFLICT DO NOTHING",
        (claim_id, source_id, p["locator"]))


def enregistrer_proposition(conn, jumeau, source_id, c, preuve, activite):
    """Claim proposé en conversation (M1, confiance basse) ; s'il existe déjà, la preuve s'y ajoute sans toucher au statut."""
    t = jumeau["tenant_id"]
    with conn.transaction():
        cid = conn.execute(
            "INSERT INTO claim (tenant_id, jumeau_id, sujet, predicat, objet, type, confiance, maturite, origine) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, 'M1', 'CONVERSATION') "
            "ON CONFLICT (jumeau_id, predicat, objet) DO UPDATE SET objet = EXCLUDED.objet, valide_jusqua = NULL "
            "WHERE claim.origine = 'CONVERSATION' RETURNING id",  # reproposée avec une preuve : de nouveau valable
            (t, jumeau["id"], c["sujet"], c["predicat"], c["objet"], c["type"], c["confiance"])).fetchone()
        if not cid:
            raise ValueError("cette connaissance est déjà établie par l'extraction du code")
        cid = cid[0]
        _lier_preuve(conn, t, source_id, cid, preuve, activite)
    return cid


def fusionner(conn, jumeau_id, garder, retirer):
    """Deux connaissances qui disent la même chose : `retirer` est close et ses preuves passent à `garder`.
    Seule une proposition non revue peut être retirée, et seulement au profit d'une connaissance de même prédicat."""
    with conn.transaction():
        lignes = {r[0]: r[1:] for r in conn.execute(
            "SELECT id, predicat, statut, origine FROM claim WHERE jumeau_id = %s AND id = ANY(%s) "
            "AND valide_jusqua IS NULL FOR UPDATE", (jumeau_id, [garder, retirer])).fetchall()}
        if garder == retirer or len(lignes) != 2:
            raise ValueError("deux connaissances valides et distinctes de ce jumeau sont attendues")
        if lignes[garder][0] != lignes[retirer][0]:
            raise ValueError("on ne fusionne que deux réponses à la même question (même prédicat)")
        if lignes[retirer][1:] != ("PROPOSED", "CONVERSATION"):
            raise ValueError("seule une proposition non revue par l'équipe peut être retirée")
        conn.execute("INSERT INTO claim_preuve (claim_id, preuve_id) SELECT %s, preuve_id FROM claim_preuve "
                     "WHERE claim_id = %s ON CONFLICT DO NOTHING", (garder, retirer))
        conn.execute("UPDATE claim SET valide_jusqua = now() WHERE id = %s", (retirer,))


def sources_du_jumeau(conn, jumeau_id):
    """Les dépôts du jumeau, chacun sur sa branche, au dernier commit ingéré."""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "SELECT id, nom, emplacement, curseur, copie, index_code, branche, url, secret_ref FROM source "
            "WHERE jumeau_id = %s AND type = 'GIT' ORDER BY nom", (jumeau_id,)).fetchall()


def source_du_jumeau(conn, jumeau_id, nom=None):
    """Un dépôt du jumeau : celui nommé, sinon le premier."""
    sources = sources_du_jumeau(conn, jumeau_id)
    return next((s for s in sources if nom is None or s["nom"] == nom), None)


def jumeau_par_id(conn, jumeau_id):
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute("SELECT id, tenant_id, nom, equipe, domaine, mission FROM jumeau WHERE id = %s",
                           (jumeau_id,)).fetchone()


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
