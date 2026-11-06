"""La carte d'un jumeau : sa porte extérieure dans le Mesh (docs/MERIDIAN_Jumeau_Mobilisation_v1.md §2).

Ce que Flore et les autres gardiens lisent sans réveiller le jumeau : qui il est, ce qu'il sait faire, ce qu'il offre,
avec qui il dit échanger, ses voisins dans le Mesh et son code. L'extraction technique (dépendances, réglages) reste à
la porte intérieure : on la demande au jumeau lui-même.
"""
import asyncio
import re
import unicodedata

from meridian.adapters.outbound.postgres import comprendre, connaissance, depot, partage
from meridian.domain import schemas

MAX_PAR_RUBRIQUE = 8
AUDIENCES = ("business", "architecture", "audit")


NON_APPUYEES = schemas.NON_TENUES  # ce que sa preuve n'appuie pas ne se publie pas (Harness v3 §2)
# Le système d'une preuve est désormais le type de sa source (L1.3) : les libellés suivent.
SOURCES_LISIBLES = {"git": "le code", "confluence": "la documentation", "jira": "le suivi de projet",
                    "servicenow": "l'exploitation", "datadog": "l'observabilité"}


def _slug(valeur):
    """Comparaison de périmètres : accents et séparateurs ignorés, jamais le nom affiché."""
    texte = unicodedata.normalize("NFKD", str(valeur or ""))
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", texte.lower()).strip("-")


def perimetre_autorise(jumeau, consommateur):
    """Le périmètre du Twin, s'il est déclaré, doit correspondre au périmètre authentifié.

    `perimetre_id` (identifiant normalisé) prime sur `perimetre` (texte libre).
    """
    perimetre = _slug(jumeau.get("perimetre_id") or jumeau.get("perimetre"))
    if not perimetre:
        return True
    if consommateur is None or not consommateur.portfolio_id:
        return False
    return perimetre == _slug(consommateur.portfolio_id)


def _mention(c):
    """✓ si l'équipe l'a validée ; sinon son état de vérification, s'il est connu (rien = pas encore vérifiée)."""
    if c["statut"] == "ACCEPTED":
        return " ✓"
    v = c.get("verification") or {}
    if v.get("etat") == "selon":
        systeme = (v.get("systemes") or ["?"])[0]
        return f" (d'après {SOURCES_LISIBLES.get(systeme, systeme.capitalize())})"
    return {"verifie": " (vérifié)", "recoupe": " (recoupé)", "conteste": " (contesté)"}.get(v.get("etat"), "")


def _objets(claims, predicat):
    """Formulations valables d'un prédicat, avec leur mention ; contestées par l'équipe et non appuyées exclues."""
    return [c["objet"] + _mention(c) + (f" [c:{c['id']}]" if c.get("id") else "") for c in claims
            if c["predicat"] == predicat and c["statut"] != "CONTESTED"
            and (c.get("verification") or {}).get("etat") not in NON_APPUYEES][:MAX_PAR_RUBRIQUE]


def _valeurs(claims, predicat):
    """Objets bruts d'un prédicat, sans mention ni identifiant, pour une liste de noms."""
    return [c["objet"] for c in claims
            if c["predicat"] == predicat and c["statut"] != "CONTESTED"
            and (c.get("verification") or {}).get("etat") not in NON_APPUYEES]


def _criticite(fiche):
    """Criticité lue dans la fiche (« En 30 secondes »), jamais inventée."""
    if not fiche:
        return "inconnue"
    trente = comprendre.lire_fiche(fiche.get("contenu") or "").get("trente", {}).get("texte", [])
    for texte in trente:
        if texte.lower().startswith("criticité"):
            return texte.split(":", 1)[1].strip()
    return "inconnue"


def _fraicheur(sources, fiche):
    """Ce qui date la carte : commits des sources et version de la fiche."""
    cree = fiche.get("cree_le") if fiche else None
    return {
        "sources": [{"nom": s["nom"], "branche": s.get("branche"), "commit": s["curseur"][:12]}
                    for s in sources],
        "fiche": {
            "cree_le": cree.isoformat() if hasattr(cree, "isoformat") else cree,
            "stale": fiche.get("stale") if fiche else None,
        },
    }


def carte(jumeau, sources, claims, relations, noms, ci=None, fiche=None, *,
          audience="business", inclure_technique=False):
    """`relations` : documents du Mesh (source, cible, etat) ; `noms` : id de jumeau → nom affichable.

    `audience` choisit la lentille : `business` (défaut), `architecture` (ajoute les dépendances
    techniques) ou `audit` (ajoute les questions et les Claims de la fiche). `inclure_technique`
    ouvre la porte intérieure hors lentille architecture.
    """
    if audience not in AUDIENCES:
        raise ValueError(f"audience inconnue : {audience!r} (attendues : {', '.join(AUDIENCES)})")
    voisins = []
    for r in relations:
        if jumeau["id"] not in (r.get("source"), r.get("cible")) or r.get("etat") == "obsolete":
            continue
        sortant = r.get("source") == jumeau["id"]
        autre = r["cible"] if sortant else r["source"]
        voisins.append({"jumeau": autre, "nom": noms.get(autre, autre), "sens": "vers" if sortant else "depuis",
                        "etat": r.get("etat"), "relation": r.get("id")})
    echanges = _objets(claims, "ECHANGE_AVEC")
    dependances = sorted(set(_valeurs(claims, "ECHANGE_AVEC")) | {v["nom"] for v in voisins})
    resultat = {
        "id": jumeau["id"], "nom": jumeau["nom"], "mission": jumeau.get("mission"), "domaine": jumeau.get("domaine"),
        "type": jumeau.get("type") or "APPLICATION",
        "application_id": jumeau.get("application_id"),
        "perimetre": jumeau.get("perimetre"),
        "perimetre_id": jumeau.get("perimetre_id"),
        "equipe": jumeau.get("equipe"), "ci": ci,
        "capacites": _objets(claims, "REALISE_CAPACITE"),
        "offre": _objets(claims, "EXPOSE"),
        "echanges": echanges,
        "dependances": dependances,
        "voisins": voisins[:MAX_PAR_RUBRIQUE],
        "code": [f"{s['nom']} · {s.get('branche') or '?'} · {s['curseur'][:12]}" for s in sources],
        "criticite": _criticite(fiche),
        "couverture": (fiche or {}).get("couverture") or {},
        "fraicheur": _fraicheur(sources, fiche),
        "audience": audience,
    }
    if audience == "architecture" or inclure_technique:
        resultat["dependances_techniques"] = sorted(
            set(_valeurs(claims, "DEPEND_DE")) | set(_valeurs(claims, "DECLARE_DEPENDANCE")))
    if audience == "audit":
        resultat["questions"] = (fiche or {}).get("questions") or []
        resultat["claims"] = (fiche or {}).get("claims") or []
    return resultat


def texte(c):
    """La carte en quelques lignes, pour le prompt de Flore ou d'un autre gardien."""
    lignes = [f"### {c['nom']} [{c['id']}]", f"Mission : {c.get('mission') or 'non déclarée'}"
              + (f" · domaine {c['domaine']}" if c.get("domaine") else "")
              + (f" · CMDB {c['ci']}" if c.get("ci") else "")]
    lignes.append(f"Responsable : {c.get('equipe') or 'à confirmer'}"
                  + (f" · criticité {c['criticite']}" if c.get("criticite") and c["criticite"] != "inconnue" else ""))
    if c.get("code"):
        lignes.append("Code : " + " ; ".join(c["code"]))
    for titre, cle in (("Sait faire", "capacites"), ("Offre", "offre"), ("Échange avec", "echanges")):
        if c[cle]:
            lignes.append(f"{titre} : " + " ; ".join(c[cle]))
    if c.get("dependances"):
        lignes.append("Dépend de / échange avec : " + " ; ".join(c["dependances"]))
    if c["voisins"]:
        lignes.append("Voisins : " + " ; ".join(f"{v['nom']} ({v['sens']}, {v['etat']})"
                                                + (f" [r:{v['relation']}]" if v.get("relation") else "") for v in c["voisins"]))
    if c.get("fraicheur"):
        f = c["fraicheur"]
        mention = f"{len(f.get('sources') or [])} source(s)"
        fiche = f.get("fiche") or {}
        if fiche.get("cree_le"):
            mention += f" · fiche {str(fiche['cree_le'])[:10]}"
        if fiche.get("stale"):
            mention += " · à revérifier"
        lignes.append("Fraîcheur : " + mention)
    if c.get("couverture"):
        lignes.append(f"Compréhension : {c['couverture'].get('answered', 0)}/"
                      f"{c['couverture'].get('total', 0)} questions répondues")
    return "\n".join(lignes)


async def carte_du_jumeau(conn, db, jumeau_id, visibles=None, consommateur=None, tenant_id=None,
                          audience="business", inclure_technique=False):
    """Carte d'un jumeau réel : connaissances (Postgres), relations et noms (registre Mongo).

    Avec `visibles`, seuls les voisins de cet ensemble apparaissent : une carte ne révèle pas un jumeau
    que le lecteur ne voit pas. Avec `consommateur`, les Claims sont projetés par `claim_share` ; sans
    lui, la carte est celle du propriétaire. `tenant_id` est la frontière dure : un jumeau d'un autre
    tenant n'est jamais rendu. Le périmètre déclaré du Twin, s'il existe, doit correspondre au
    périmètre authentifié.
    """
    from meridian.adapters.outbound.llm import gardien  # import tardif : gardien -> poignee -> carte

    jumeau = await asyncio.to_thread(depot.jumeau_carte, conn, jumeau_id)  # Postgres hors de la boucle asynchrone
    if not jumeau:
        return None
    if tenant_id and jumeau.get("tenant_id") != tenant_id:
        return None
    if consommateur is not None and not perimetre_autorise(jumeau, consommateur):
        return None
    relations = await db.relations.find({"$or": [{"source": jumeau_id}, {"cible": jumeau_id}]},
                                        {"_id": 0, "id": 1, "source": 1, "cible": 1, "etat": 1}).to_list(200)
    if visibles is not None:
        relations = [r for r in relations if ({r["source"], r["cible"]} - {jumeau_id}) <= visibles]
    autres = {r["source"] for r in relations} | {r["cible"] for r in relations}
    noms = {j["id"]: j["nom"] async for j in db.jumeaux.find({"id": {"$in": sorted(autres)}}, {"_id": 0, "id": 1, "nom": 1})}

    def charger():
        sources = depot.sources_du_jumeau(conn, jumeau_id)
        claims = (partage.claims_visibles(conn, consommateur.tenant_id, consommateur,
                                          jumeau_id=jumeau_id, limite=1000)
                  if consommateur is not None
                  else connaissance.connaissances(conn, jumeau_id, limite=1000))
        return sources, claims, depot.ci_du_jumeau(conn, jumeau_id)

    sources, claims, ci = await asyncio.to_thread(charger)
    fiche = await asyncio.to_thread(gardien.fiche_courante, conn, jumeau_id)
    return carte(jumeau, sources, claims, relations, noms, ci, fiche,
                 audience=audience, inclure_technique=inclure_technique)
