"""Persistance des jumeaux, preuves et Claims (Postgres)."""
import re
from pathlib import Path

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

SCHEMA = Path(__file__).with_name("schema.sql")


VERROU_SCHEMA = 4242


def appliquer_schema(conn):
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (VERROU_SCHEMA,))
        conn.execute(SCHEMA.read_text())


def recalculer_maturites(conn):
    """Rejoue la maturité de toutes les connaissances. À appeler quand la **règle** change — par exemple quand un
    fichier Markdown du dépôt cesse d'être un système indépendant (plan de remédiation L1.3) : sans cela, les
    diplômes déjà acquis survivraient à la règle qui les a produits."""
    ids = [r[0] for r in conn.execute("SELECT id FROM claim").fetchall()]
    for cid in ids:
        conn.execute("SELECT recalculer_maturite(%s)", (cid,))
    return len(ids)


# Substance d'un jumeau, par ordre de préférence : le code, puis ce que la banque a d'un progiciel sans son code.
SUBSTANCES = (("GIT", "code"), ("DATADOG", "interfaces observées (Datadog)"), ("CONFLUENCE", "documentation (Confluence)"))


def substance(types):
    """Ce sur quoi repose la compréhension du jumeau, d'après les types de ses sources ; None s'il n'en a aucune."""
    types = {t.upper() for t in types}
    return next((libelle for type_, libelle in SUBSTANCES if type_ in types), None)


def types_de_sources(conn, jumeau_id):
    return [r[0] for r in conn.execute("SELECT DISTINCT type FROM source WHERE jumeau_id = %s", (jumeau_id,))]


def creer_jumeau(conn, jumeau):
    """Crée le jumeau d'un progiciel (sans code, donc sans ingestion qui le crée) ; idempotent."""
    conn.execute(
        "INSERT INTO jumeau (id, tenant_id, nom, equipe, domaine, mission) "
        "VALUES (%s, %s, %s, %s, coalesce(%s, 'À confirmer'), %s) ON CONFLICT (id) DO UPDATE SET "
        "nom = EXCLUDED.nom, equipe = EXCLUDED.equipe, domaine = coalesce(%s, jumeau.domaine), "
        "mission = coalesce(%s, jumeau.mission) WHERE jumeau.tenant_id = EXCLUDED.tenant_id",
        (jumeau["id"], jumeau["tenant_id"], jumeau["nom"], jumeau["equipe"], jumeau.get("domaine"),
         jumeau.get("mission"), jumeau.get("domaine"), jumeau.get("mission")))


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
            "url, secret_ref, troncature) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (jumeau_id, nom) "
            "DO UPDATE SET emplacement = EXCLUDED.emplacement, curseur = EXCLUDED.curseur, copie = EXCLUDED.copie, "
            "index_code = EXCLUDED.index_code, branche = coalesce(EXCLUDED.branche, source.branche), "
            "url = coalesce(EXCLUDED.url, source.url), secret_ref = coalesce(EXCLUDED.secret_ref, source.secret_ref), "
            "troncature = EXCLUDED.troncature "
            "RETURNING id",
            (t, jumeau["id"], source["type"], source["nom"], source["emplacement"], source["curseur"],
             source.get("copie"), source.get("index_code"), source.get("branche"), source.get("url"),
             source.get("secret_ref"), Jsonb(source["troncature"]) if source.get("troncature") else None)).fetchone()[0]
        tronque = bool(source.get("troncature"))
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
        # Extraction tronquée : ce qui manque peut être au-delà du plafond, pas disparu ; seules les propositions
        # non revues sont closes, ce que l'équipe a validé ou rejeté reste.
        revu = "AND claim_id IN (SELECT id FROM claim WHERE statut = 'PROPOSED')" if tronque else ""
        conn.execute(f"DELETE FROM claim_source WHERE source_id = %s AND NOT (claim_id = ANY(%s)) {revu}", (source_id, vus))
        conn.execute(
            "UPDATE claim SET valide_jusqua = now() WHERE jumeau_id = %s AND origine = 'INGESTION' "
            "AND valide_jusqua IS NULL AND NOT EXISTS (SELECT 1 FROM claim_source cs WHERE cs.claim_id = claim.id)"
            + (" AND statut = 'PROPOSED'" if tronque else ""), (jumeau["id"],))


def _remplacer_preuves(conn, source_id, claim_id, chemin):
    """Une preuve nouvelle du même fichier de la même source **remplace** l'ancienne : elle ne s'empile pas.

    Sans cela, chaque commit ajoutait une preuve de plus (859 sur une seule connaissance) : l'ensemble des preuves
    devenait une archive de tous les états successifs du fichier, M3 pouvait s'obtenir en appariant une ligne d'un
    commit ancien avec un document d'un autre, et la revérification ne s'arrêtait plus (plan de remédiation L1.5).
    La preuve retirée reste dans `preuve` (immuable) ; seul son lien de soutien est défait."""
    conn.execute(
        "DELETE FROM claim_preuve WHERE claim_id = %s AND role = 'SUPPORT' AND preuve_id IN "
        "(SELECT id FROM preuve WHERE source_id = %s AND chemin = %s)", (claim_id, source_id, chemin))


def _lier_preuve(conn, tenant, source_id, claim_id, p, activite):
    _remplacer_preuves(conn, source_id, claim_id, p["chemin"])
    conn.execute(
        "INSERT INTO preuve (tenant_id, source_id, type, locator, chemin, sha, ligne_debut, ligne_fin, hash, activite) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (source_id, locator) DO NOTHING",
        (tenant, source_id, p.get("type", "CODE"), p["locator"], p["chemin"], p["sha"], p["ligne_debut"],
         p["ligne_fin"], p["hash"], Jsonb(activite)))
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


def ajouter_preuve(conn, jumeau, claim_id, source_id, p, activite, refuse_si):
    """Ajoute une preuve de soutien à une connaissance existante et courante de ce jumeau ; vrai si elle est nouvelle.
    `refuse_si(systemes_existants)` lève ValueError si la preuve n'apporte rien (même système)."""
    with conn.transaction():
        ligne = conn.execute("SELECT valide_jusqua IS NULL FROM claim WHERE id = %s AND jumeau_id = %s FOR UPDATE",
                             (claim_id, jumeau["id"])).fetchone()
        if not ligne:
            raise ValueError(f"connaissance {claim_id} : inconnue de ce jumeau")
        if not ligne[0]:
            raise ValueError(f"connaissance {claim_id} : close")
        if conn.execute("SELECT 1 FROM claim_preuve cp JOIN preuve x ON x.id = cp.preuve_id "
                        "WHERE cp.claim_id = %s AND cp.role = 'SUPPORT' AND x.source_id = %s AND x.locator = %s",
                        (claim_id, source_id, p["locator"])).fetchone():
            return False
        refuse_si([r[0] for r in conn.execute(
            "SELECT DISTINCT systeme_de_preuve(x.type, x.chemin, so.type) FROM claim_preuve cp "
            "JOIN preuve x ON x.id = cp.preuve_id JOIN source so ON so.id = x.source_id "
            "WHERE cp.claim_id = %s AND cp.role = 'SUPPORT'", (claim_id,))])
        _lier_preuve(conn, jumeau["tenant_id"], source_id, claim_id, p, activite)
    return True


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


def declarer_source(conn, jumeau, source):
    """Enregistre une source branchée (hors code) du jumeau : pas d'ingestion, ses lecteurs la lisent à la demande."""
    conn.execute(
        "INSERT INTO source (tenant_id, jumeau_id, type, nom, emplacement, curseur, url, secret_ref) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (jumeau_id, nom) DO UPDATE SET "
        "emplacement = EXCLUDED.emplacement, url = EXCLUDED.url, secret_ref = EXCLUDED.secret_ref",
        (jumeau["tenant_id"], jumeau["id"], source["type"], source["nom"], source["emplacement"],
         source.get("curseur"), source.get("url"), source.get("secret_ref")))


def sources_du_jumeau(conn, jumeau_id):
    """Les dépôts du jumeau, chacun sur sa branche, au dernier commit ingéré."""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "SELECT id, nom, emplacement, curseur, copie, index_code, branche, url, secret_ref FROM source "
            "WHERE jumeau_id = %s AND type = 'GIT' ORDER BY nom", (jumeau_id,)).fetchall()


def maj_index(conn, source_id, copie, index_code):
    """Range la copie et l'index reconstruits d'une source, sans toucher à ses connaissances."""
    conn.execute("UPDATE source SET copie = %s, index_code = %s WHERE id = %s", (str(copie), index_code, source_id))


def ci_du_jumeau(conn, jumeau_id):
    """Ancre d'identité : l'élément de configuration de la CMDB (périmètre de sa source ServiceNow), ou None."""
    r = conn.execute("SELECT emplacement FROM source WHERE jumeau_id = %s AND type = 'SERVICENOW' ORDER BY id LIMIT 1",
                     (jumeau_id,)).fetchone()
    return r[0] if r else None


def toutes_les_sources(conn, jumeau_id):
    """Toutes les sources du jumeau, de tout type (code et sources branchées), pour en faire des lecteurs."""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute("SELECT * FROM source WHERE jumeau_id = %s ORDER BY nom", (jumeau_id,)).fetchall()


def source_du_jumeau(conn, jumeau_id, nom=None):
    """Un dépôt du jumeau : celui nommé, sinon le premier."""
    sources = sources_du_jumeau(conn, jumeau_id)
    return next((s for s in sources if nom is None or s["nom"] == nom), None)


def jumeau_par_id(conn, jumeau_id):
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute("SELECT id, tenant_id, nom, equipe, domaine, mission FROM jumeau WHERE id = %s",
                           (jumeau_id,)).fetchone()


def reviser(conn, claim_id, acteur, decision, motif):
    """Revue humaine : la revue est écrite avant le statut (exigé par le trigger d'acceptation). Rend l'énoncé revu."""
    with conn.transaction():
        tenant = conn.execute(
            "SELECT tenant_id, sujet, predicat, objet FROM claim WHERE id = %s AND valide_jusqua IS NULL FOR UPDATE",
            (claim_id,)).fetchone()
        if not tenant:
            raise LookupError(claim_id)
        conn.execute(
            "INSERT INTO revue (tenant_id, claim_id, acteur, decision, motif) VALUES (%s, %s, %s, %s, %s)",
            (tenant[0], claim_id, acteur, decision, motif))
        conn.execute("UPDATE claim SET statut = %s WHERE id = %s", (decision, claim_id))  # maturité : trigger
    return {"sujet": tenant[1], "predicat": tenant[2], "objet": tenant[3]}


PORTEES = ("domaine", "equipe", "jumeau")
MAX_TEXTE, MAX_POURQUOI = 500, 1000
MAX_CONSIGNES, MAX_CARACTERES = 40, 6000
# Chaque portée a sa part : des consignes de jumeau ne font pas sauter celles du domaine ou de l'équipe.
QUOTA_CONSIGNES, QUOTA_CARACTERES = MAX_CONSIGNES // len(PORTEES), MAX_CARACTERES // len(PORTEES)
_CONTROLES = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u200b-\u200f\u2028-\u202e\u2060-\u2069\ufeff\U000e0000-\U000e007f]")


def nettoyer_consigne(texte):
    """Sans caractères de contrôle (retours à la ligne compris : une consigne tient sur une ligne) ni blancs en trop."""
    return " ".join(_CONTROLES.sub(" ", texte or "").split())


def _cible(jumeau, portee):
    return jumeau[{"domaine": "domaine", "equipe": "equipe", "jumeau": "id"}[portee]]


def ajouter_consigne(conn, jumeau, portee, texte, pourquoi, auteur, origine="HUMAIN"):
    """La cible est déduite du jumeau : on ne choisit pas une portée arbitraire. Rend l'id."""
    if portee not in PORTEES:
        raise ValueError(f"portée inconnue : {portee}")
    texte, pourquoi = nettoyer_consigne(texte), nettoyer_consigne(pourquoi)
    if not texte or not pourquoi:
        raise ValueError("texte et pourquoi sont obligatoires")
    if len(texte) > MAX_TEXTE or len(pourquoi) > MAX_POURQUOI:
        raise ValueError("texte ou pourquoi trop long")
    nombre, caracteres = conn.execute(
        "SELECT count(*), coalesce(sum(length(texte) + length(pourquoi)), 0) FROM consigne "
        "WHERE tenant_id = %s AND portee = %s AND cible = %s AND retiree_le IS NULL",
        (jumeau["tenant_id"], portee, _cible(jumeau, portee))).fetchone()
    if nombre >= QUOTA_CONSIGNES or caracteres + len(texte) + len(pourquoi) > QUOTA_CARACTERES:
        raise ValueError(f"trop de consignes pour cette portée ({QUOTA_CONSIGNES} ou {QUOTA_CARACTERES} caractères "
                         "au plus) : retirez-en une d'abord")
    return conn.execute(
        "INSERT INTO consigne (tenant_id, portee, cible, texte, pourquoi, auteur, origine) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (jumeau["tenant_id"], portee, _cible(jumeau, portee), texte, pourquoi, auteur, origine)).fetchone()[0]


def retirer_consigne(conn, jumeau, consigne_id):
    """Seule une consigne active qui s'applique à `jumeau` (même tenant, portée et cible résolues) peut être retirée."""
    if not conn.execute(
            "UPDATE consigne SET retiree_le = now() WHERE id = %s AND tenant_id = %s AND retiree_le IS NULL AND "
            "((portee = 'domaine' AND cible = %s) OR (portee = 'equipe' AND cible = %s) OR (portee = 'jumeau' AND cible = %s)) "
            "RETURNING id", (consigne_id, jumeau["tenant_id"], jumeau["domaine"], jumeau["equipe"], jumeau["id"])).fetchone():
        raise LookupError(consigne_id)


def borner_consignes(consignes):
    """Au plus QUOTA_CONSIGNES et QUOTA_CARACTERES par portée (donc MAX_* en tout) ; si l'on coupe une portée, on garde
    ses consignes les plus récentes. L'ordre reçu (domaine → équipe → jumeau, puis date) est conservé."""
    gardees, par_portee = set(), {}
    for i in range(len(consignes) - 1, -1, -1):
        c = consignes[i]
        nombre, total = par_portee.get(c["portee"], (0, 0))
        total += len(c["texte"]) + len(c["pourquoi"])
        if nombre < QUOTA_CONSIGNES and total <= QUOTA_CARACTERES:
            gardees.add(i)
            par_portee[c["portee"]] = (nombre + 1, total)
        else:
            par_portee[c["portee"]] = (QUOTA_CONSIGNES, total)  # une fois coupée, la portée ne reprend pas plus ancien
    return [c for i, c in enumerate(consignes) if i in gardees]


def consignes_du_jumeau(conn, jumeau):
    """Consignes actives qui s'appliquent au jumeau : domaine, puis équipe, puis jumeau, puis date."""
    with conn.cursor(row_factory=dict_row) as cur:
        lignes = cur.execute(
            "SELECT id, portee, cible, texte, pourquoi, auteur, origine, cree_le FROM consigne "
            "WHERE tenant_id = %s AND retiree_le IS NULL AND "
            "((portee = 'domaine' AND cible = %s) OR (portee = 'equipe' AND cible = %s) OR (portee = 'jumeau' AND cible = %s)) "
            "ORDER BY array_position(ARRAY['domaine', 'equipe', 'jumeau'], portee), cree_le, id",
            (jumeau["tenant_id"], jumeau["domaine"], jumeau["equipe"], jumeau["id"])).fetchall()
    return borner_consignes(lignes)


def consigne_proposee(enonce, motif):
    """Proposition issue d'une contestation motivée ; jamais créée seule, un humain la confirme."""
    texte = nettoyer_consigne(f"Ne pas affirmer sans nouvelle preuve : {enonce['sujet']} {enonce['predicat']} {enonce['objet']}")
    return {"portee": "jumeau", "texte": texte[:MAX_TEXTE], "pourquoi": nettoyer_consigne(motif)[:MAX_POURQUOI]}


def enregistrer_contradiction(conn, jumeau, enonce, a, b, acteur, claim_id=None):
    """a, b : (locator, système). Le harness a déjà vérifié les deux citations."""
    return conn.execute(
        "INSERT INTO contradiction (tenant_id, jumeau_id, claim_id, enonce, preuve_a, systeme_a, preuve_b, systeme_b, "
        "signalee_par) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (jumeau["tenant_id"], jumeau["id"], claim_id, enonce, *a, *b, acteur)).fetchone()[0]


VERDICTS = ("a", "b", "aucune")


def trancher_contradiction(conn, jumeau_id, contradiction_id, acteur, verdict, motif=None):
    """Décision humaine, définitive : `a` ou `b` a raison, ou `aucune` (les deux sont à corriger)."""
    if verdict not in VERDICTS:
        raise ValueError(f"verdict inconnu : {verdict}")
    if not conn.execute(
            "UPDATE contradiction SET statut = 'TRANCHEE', tranchee_par = %s, tranchee_le = now(), verdict = %s, "
            "motif = %s WHERE id = %s AND jumeau_id = %s AND statut = 'OUVERTE' RETURNING id",
            (acteur, verdict, motif, contradiction_id, jumeau_id)).fetchone():
        raise LookupError(contradiction_id)


def contradiction_par_id(conn, contradiction_id):
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "SELECT id, jumeau_id, statut, preuve_a, preuve_b, systeme_a, systeme_b FROM contradiction WHERE id = %s",
            (contradiction_id,)).fetchone()


def contradictions_ouvertes(conn, jumeau_id):
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "SELECT id, claim_id, enonce, preuve_a, preuve_b, systeme_a, systeme_b FROM contradiction "
            "WHERE jumeau_id = %s AND statut = 'OUVERTE' ORDER BY id", (jumeau_id,)).fetchall()


def ancrer(conn, jumeau, claim_id, source_id, chemin, debut, fin, locator, raison, origine):
    """Rattache une connaissance de source (non-code) à des lignes de code ; vrai si l'ancre est nouvelle."""
    with conn.transaction():
        if not conn.execute(
                "SELECT 1 FROM claim c WHERE c.id = %s AND c.jumeau_id = %s AND c.valide_jusqua IS NULL AND EXISTS ("
                "SELECT 1 FROM claim_preuve cp JOIN preuve p ON p.id = cp.preuve_id JOIN source so ON so.id = p.source_id "
                "WHERE cp.claim_id = c.id AND cp.role = 'SUPPORT' AND so.type <> 'GIT')",
                (claim_id, jumeau["id"])).fetchone():
            raise ValueError(f"connaissance {claim_id} : inconnue, close, ou prouvée par le code seul (rien à ancrer)")
        return conn.execute(
            "INSERT INTO ancre (tenant_id, claim_id, source_id, chemin, ligne_debut, ligne_fin, locator, raison, origine) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (claim_id, locator) DO NOTHING RETURNING id",
            (jumeau["tenant_id"], claim_id, source_id, chemin, debut, fin, locator, raison[:500], origine)
        ).fetchone() is not None


def lister_jumeaux(conn):
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "SELECT j.id, j.nom, j.equipe, count(c.id) FILTER (WHERE c.valide_jusqua IS NULL) AS claims "
            "FROM jumeau j LEFT JOIN claim c ON c.jumeau_id = j.id GROUP BY j.id ORDER BY j.nom").fetchall()


def troncature(conn, jumeau_id):
    """Familles dont la dernière extraction a été tronquée par le plafond : {famille: {gardes, trouves}}."""
    fusion = {}
    for (t,) in conn.execute("SELECT troncature FROM source WHERE jumeau_id = %s AND troncature IS NOT NULL", (jumeau_id,)):
        fusion.update(t)
    return fusion


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
                       FROM revue r WHERE r.claim_id = c.id) AS revues,
                      (SELECT coalesce(json_agg(json_build_object(
                          'chemin', a.chemin, 'ligne_debut', a.ligne_debut, 'ligne_fin', a.ligne_fin,
                          'raison', a.raison, 'origine', a.origine) ORDER BY a.id), '[]')
                       FROM ancre a WHERE a.claim_id = c.id) AS ancres,
                      (SELECT json_build_object('etat', v.etat, 'methode', v.methode, 'systemes', v.systemes,
                                                'raison', v.raison)
                       FROM verification v WHERE v.claim_id = c.id ORDER BY v.id DESC LIMIT 1) AS verification
               FROM claim c WHERE c.jumeau_id = %s AND c.valide_jusqua IS NULL
               ORDER BY c.type, c.predicat, c.objet""",
            (jumeau_id,)).fetchall()


def preuve_par_id(conn, preuve_id):
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "SELECT p.id, p.chemin, p.sha, p.ligne_debut, p.ligne_fin, p.hash, s.emplacement "
            "FROM preuve p JOIN source s ON s.id = p.source_id WHERE p.id = %s",
            (preuve_id,)).fetchone()
