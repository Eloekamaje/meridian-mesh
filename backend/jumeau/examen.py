"""Revue d'un jumeau né du code : les sept questions de « comprendre une application » (POST /jumeaux/{jid}/examiner).

Les cinq premières viennent des connaissances prouvées (révisables par l'équipe), les deux dernières de la fiche
vivante du gardien. Les interfaces, dépendances et variables extraites du code n'y figurent pas : ce sont des
preuves, consultables sous la revue.
"""
from jumeau import comprendre, depot, gardien

SOURCES_NON_CONNECTEES = "Exploitation, incidents, base de données : sources non connectées"


def depuis_connaissances(jumeau, claims, fiche):
    lignes = comprendre.sections(fiche)
    blocs = []
    for cle, titre, predicat, _ in comprendre.QUESTIONS:
        if predicat:
            items = [{"texte": c["objet"], "statut": c["statut"]} for c in claims if c["predicat"] == predicat]
        else:
            items = [{"texte": texte} for texte, _ in lignes[cle]]
        if cle == "vie":
            items.append({"texte": f"Responsable : {jumeau.get('proprietaire') or 'non renseigné'}"})
        if cle == "inconnu":
            resumes = [c for c in claims if c["predicat"] in comprendre.PREDICATS]
            valides = sum(c["statut"] == "ACCEPTED" for c in resumes)
            items += [{"texte": f"{valides} connaissance(s) sur {len(resumes)} validée(s) par l'équipe"},
                      {"texte": SOURCES_NON_CONNECTEES}]
        blocs.append({"cle": cle, "titre": titre, "items": items})
    return {"identite": {k: jumeau.get(k) for k in ("nom", "mission", "domaine")}, "comprendre": blocs}


def examiner(conn, jumeau_id, doc):
    fiche = gardien.fiche_courante(conn, jumeau_id)
    return depuis_connaissances(doc, depot.lister_claims(conn, jumeau_id), fiche and fiche["contenu"])
