"""Vérifier comme on teste (Jumeau Harness v3 §2) : chaque connaissance est vérifiée par une recette déterministe quand
elle existe, sinon par le juge d'appui (un agent sans outils, distinct de l'auteur) ; deux systèmes indépendants qui
l'appuient et concordent la disent « recoupée », seul chemin vers M3. L'humain ne garde que les vraies décisions.

États : verifie (recette), selon (une source l'appuie), recoupe (deux systèmes concordants), conteste (deux systèmes
discordants : une contradiction est ouverte pour l'équipe), en_partie (un détail n'est pas appuyé : comme pour le
Check Grounding de Google, une phrase appuyée en partie n'est pas appuyée), non_appuye (la preuve ne dit pas cela).
"""
import logging

from jumeau import depot, juge, recettes
from jumeau.source_git import lire_au_sha

journal = logging.getLogger("meridian.jumeau")
MAX_JUGEES = 2 * juge.MAX_LOT  # connaissances jugées par passe : coût borné, le reste à la passe suivante
MAX_RAISON = 300

LIBELLES = {"REALISE_CAPACITE": "réalise la capacité", "SERT_ACTEUR": "sert", "DETIENT": "détient",
            "APPLIQUE_REGLE": "applique la règle", "ECHANGE_AVEC": "échange avec", "DEPEND_DE": "dépend de",
            "EXPOSE": "expose", "LIT_VARIABLE": "lit la variable", "EXECUTE_IMAGE": "exécute l'image"}


DOCUMENTATION_DU_DEPOT = (".md", ".mdx", ".rst", ".adoc")  # pas .txt : requirements.txt est du code


def systeme_de_preuve(type_preuve, chemin, type_source):
    """Le système d'une preuve ; même règle que la fonction SQL du même nom (le trigger de maturité)."""
    if type_preuve == "CODE" and chemin.lower().endswith(DOCUMENTATION_DU_DEPOT):
        return "documentation"
    return type_source.lower()


def a_verifier(conn, jumeau_id):
    """Connaissances courantes dont les preuves ont changé depuis leur dernière vérification (ou jamais vérifiées),
    avec leurs preuves de soutien : [{id, sujet, predicat, objet, origine, empreinte, preuves: [...]}]."""
    lignes = conn.execute(
        """SELECT c.id, c.sujet, c.predicat, c.objet, c.origine,
                  p.id, p.type, p.locator, p.chemin, p.sha, p.ligne_debut, p.ligne_fin, p.source_id,
                  s.type, s.emplacement, s.copie,
                  (SELECT v.empreinte FROM verification v WHERE v.claim_id = c.id ORDER BY v.id DESC LIMIT 1)
           FROM claim c JOIN claim_preuve cp ON cp.claim_id = c.id AND cp.role = 'SUPPORT'
           JOIN preuve p ON p.id = cp.preuve_id JOIN source s ON s.id = p.source_id
           WHERE c.jumeau_id = %s AND c.valide_jusqua IS NULL ORDER BY c.id, p.id""", (jumeau_id,)).fetchall()
    claims = {}
    for (cid, sujet, predicat, objet, origine, pid, ptype, locator, chemin, sha, debut, fin, source_id, type_source,
         emplacement, copie, derniere) in lignes:
        c = claims.setdefault(cid, {"id": cid, "sujet": sujet, "predicat": predicat, "objet": objet,
                                    "origine": origine, "derniere": derniere, "preuves": []})
        c["preuves"].append({"id": pid, "type": ptype, "locator": locator, "chemin": chemin, "sha": sha,
                             "debut": debut, "fin": fin, "source_id": source_id,
                             "systeme": systeme_de_preuve(ptype, chemin, type_source),
                             "depot": copie or emplacement})
    resultat = []
    for c in claims.values():
        c["empreinte"] = ",".join(str(p["id"]) for p in c["preuves"])
        if c.pop("derniere") != c["empreinte"]:
            resultat.append(c)
    return resultat


def lignes_de(preuve, lecteurs):
    """Les lignes citées par une preuve, à sa version (commit ou version du document) ; None si illisibles."""
    try:
        if preuve["type"] == "CODE":
            contenu = lire_au_sha(preuve["depot"], preuve["sha"])(preuve["chemin"])
            return contenu[preuve["debut"] - 1:preuve["fin"]] if contenu is not None else None
        lecteur = next((l for l in lecteurs if getattr(l, "source_id", None) == preuve["source_id"]), None)
        if lecteur is None:
            return None
        return lecteur.lire(preuve["chemin"], preuve["debut"], preuve["fin"], version=preuve["sha"])["lignes"]
    except Exception:  # dépôt absent, source injoignable : la vérification se rejoue à la passe suivante
        journal.warning("vérification : preuve %s illisible", preuve["locator"], exc_info=True)
        return None


def enonce(c):
    return f"{c['sujet']} {LIBELLES.get(c['predicat'], c['predicat'])} : {c['objet']}"


def etat_du_jugement(appui, systemes):
    """Décision du juge → état. Deux systèmes indépendants qui l'appuient et concordent : recoupé ; une recopie ne
    compte qu'une fois."""
    if appui.appui == "non":
        return "non_appuye"
    if appui.appui == "partiel":
        return "en_partie"
    if len(systemes) >= 2 and appui.concordance == "contradictoires":
        return "conteste"
    if len(systemes) >= 2 and appui.concordance == "concordantes" and appui.appui == "oui" and not appui.copie:
        return "recoupe"
    return "selon"


def _enregistrer(conn, c, etat, methode, systemes, raison=None):
    conn.execute("INSERT INTO verification (claim_id, etat, methode, systemes, empreinte, raison) "
                 "VALUES (%s, %s, %s, %s, %s, %s)",
                 (c["id"], etat, methode, sorted(systemes), c["empreinte"], (raison or "")[:MAX_RAISON] or None))


def _ouvrir_contradiction(conn, jumeau, c, raison):
    """Deux systèmes discordants : la contradiction va à l'équipe (une seule par connaissance tant qu'elle est ouverte)."""
    if conn.execute("SELECT 1 FROM contradiction WHERE claim_id = %s AND statut = 'OUVERTE'", (c["id"],)).fetchone():
        return
    par_systeme = {}
    for p in c["preuves"]:
        par_systeme.setdefault(p["systeme"], p["locator"])
    (sa, la), (sb, lb) = list(par_systeme.items())[:2]
    depot.enregistrer_contradiction(conn, jumeau, f"{enonce(c)} — {raison}"[:1000], (la, sa), (lb, sb),
                                    "juge-recoupement", c["id"])


async def verifier(conn, jumeau, lecteurs=(), modele=None, juger=juge.juger, limite=MAX_JUGEES):
    """Une passe de vérification. Les recettes s'exécutent toutes (sans modèle) ; le juge prend au plus `limite`
    connaissances, d'abord celles qui ont plusieurs systèmes (le recoupement), puis celles proposées en conversation."""
    bilan = {"verifie": 0, "selon": 0, "recoupe": 0, "conteste": 0, "en_partie": 0, "non_appuye": 0, "en_attente": 0}
    a_juger = []
    for c in a_verifier(conn, jumeau["id"]):
        systemes = {p["systeme"] for p in c["preuves"]}
        if c["predicat"] in recettes.PREDICATS and systemes == {"git"}:
            extraits = [lignes_de(p, lecteurs) for p in c["preuves"]]
            if all(e is None for e in extraits):
                bilan["en_attente"] += 1
                continue
            etat = ("verifie" if any(e and recettes.recette(c["predicat"], c["objet"], e) == "verifie" for e in extraits)
                    else "non_appuye")
            _enregistrer(conn, c, etat, "recette", systemes)
            bilan[etat] += 1
        else:
            a_juger.append((c, systemes))
    a_juger.sort(key=lambda cs: (len(cs[1]) < 2, cs[0]["origine"] != "CONVERSATION", cs[0]["id"]))
    bilan["en_attente"] += max(0, len(a_juger) - limite)
    a_juger = a_juger[:limite]
    if not a_juger:
        return bilan
    dossiers, par_id = [], {}
    for c, systemes in a_juger:
        extraits = [{"systeme": p["systeme"], "citation": p["locator"], "lignes": l}
                    for p in c["preuves"] if (l := lignes_de(p, lecteurs))]
        if not extraits:
            bilan["en_attente"] += 1
            continue
        dossiers.append({"id": c["id"], "enonce": enonce(c), "extraits": extraits})
        par_id[c["id"]] = (c, {e["systeme"] for e in extraits})
    decisions = await juger(modele, dossiers) if dossiers else {}
    for cid, (c, systemes) in par_id.items():
        appui = decisions.get(cid)
        if appui is None:  # lot en panne ou décision manquante : rejoué à la passe suivante
            bilan["en_attente"] += 1
            continue
        etat = etat_du_jugement(appui, systemes)
        _enregistrer(conn, c, etat, "juge", systemes, appui.raison)
        if etat == "conteste":
            _ouvrir_contradiction(conn, jumeau, c, appui.raison)
        bilan[etat] += 1
    return bilan


def etats(conn, jumeau_id):
    """{claim_id: {etat, methode, systemes, raison}} : la dernière vérification de chaque connaissance courante."""
    return {cid: {"etat": e, "methode": m, "systemes": s, "raison": r} for cid, e, m, s, r in conn.execute(
        """SELECT DISTINCT ON (v.claim_id) v.claim_id, v.etat, v.methode, v.systemes, v.raison
           FROM verification v JOIN claim c ON c.id = v.claim_id
           WHERE c.jumeau_id = %s AND c.valide_jusqua IS NULL ORDER BY v.claim_id, v.id DESC""", (jumeau_id,))}

