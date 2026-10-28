"""La carte d'un jumeau : sa porte extérieure dans le Mesh (docs/MERIDIAN_Jumeau_Mobilisation_v1.md §2).

Ce que Flore et les autres gardiens lisent sans réveiller le jumeau : qui il est, ce qu'il sait faire, ce qu'il offre,
avec qui il dit échanger, ses voisins dans le Mesh et son code. L'extraction technique (dépendances, réglages) reste à
la porte intérieure : on la demande au jumeau lui-même.
"""
from jumeau import connaissance, depot

MAX_PAR_RUBRIQUE = 8


def _objets(claims, predicat):
    """Formulations valables d'un prédicat (✓ si validées par l'équipe ; contestées exclues)."""
    return [c["objet"] + (" ✓" if c["statut"] == "ACCEPTED" else "")
            for c in claims if c["predicat"] == predicat and c["statut"] != "CONTESTED"][:MAX_PAR_RUBRIQUE]


def carte(jumeau, sources, claims, relations, noms):
    """`relations` : documents du Mesh (source, cible, etat) ; `noms` : id de jumeau → nom affichable."""
    voisins = []
    for r in relations:
        if jumeau["id"] not in (r.get("source"), r.get("cible")) or r.get("etat") == "obsolete":
            continue
        sortant = r.get("source") == jumeau["id"]
        autre = r["cible"] if sortant else r["source"]
        voisins.append({"jumeau": autre, "nom": noms.get(autre, autre), "sens": "vers" if sortant else "depuis",
                        "etat": r.get("etat")})
    return {
        "id": jumeau["id"], "nom": jumeau["nom"], "mission": jumeau.get("mission"), "domaine": jumeau.get("domaine"),
        "equipe": jumeau.get("equipe"),
        "capacites": _objets(claims, "REALISE_CAPACITE"),
        "offre": _objets(claims, "EXPOSE"),
        "echanges": _objets(claims, "ECHANGE_AVEC"),
        "voisins": voisins[:MAX_PAR_RUBRIQUE],
        "code": [f"{s['nom']} · {s.get('branche') or '?'} · {s['curseur'][:12]}" for s in sources],
    }


def texte(c):
    """La carte en quelques lignes, pour le prompt de Flore ou d'un autre gardien."""
    lignes = [f"### {c['nom']} [{c['id']}]", f"Mission : {c.get('mission') or 'non déclarée'}"
              + (f" · domaine {c['domaine']}" if c.get("domaine") else "")]
    for titre, cle in (("Sait faire", "capacites"), ("Offre", "offre"), ("Échange avec", "echanges")):
        if c[cle]:
            lignes.append(f"{titre} : " + " ; ".join(c[cle]))
    if c["voisins"]:
        lignes.append("Voisins : " + " ; ".join(f"{v['nom']} ({v['sens']}, {v['etat']})" for v in c["voisins"]))
    return "\n".join(lignes)


async def carte_du_jumeau(conn, db, jumeau_id):
    """Carte d'un jumeau réel : connaissances (Postgres), relations et noms (registre Mongo)."""
    jumeau = depot.jumeau_par_id(conn, jumeau_id)
    if not jumeau:
        return None
    relations = await db.relations.find({"$or": [{"source": jumeau_id}, {"cible": jumeau_id}]},
                                        {"_id": 0, "source": 1, "cible": 1, "etat": 1}).to_list(200)
    autres = {r["source"] for r in relations} | {r["cible"] for r in relations}
    noms = {j["id"]: j["nom"] async for j in db.jumeaux.find({"id": {"$in": sorted(autres)}}, {"_id": 0, "id": 1, "nom": 1})}
    return carte(jumeau, depot.sources_du_jumeau(conn, jumeau_id),
                 connaissance.connaissances(conn, jumeau_id, limite=1000), relations, noms)
