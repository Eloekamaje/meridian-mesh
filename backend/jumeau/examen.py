"""Examen d'un jumeau né du code, dans la forme de l'examen de l'atelier (POST /jumeaux/{jid}/examiner).

La fiche des jumeaux (Revue) garde sa structure ; pour un jumeau né du code, chaque rubrique vient de ses
connaissances prouvées et de sa fiche vivante au lieu d'être simulée. Ce que le code ne révèle pas est dit.
"""
import re

from jumeau import depot, gardien

MAX_ITEMS = 12
RE_INCONNU = re.compile(r"^#{2,6}\s*ce qui reste inconnu", re.IGNORECASE)
RE_CITATION = re.compile(r"\s*`[^`]*#L\d+[^`]*`")


def _liste(objets):
    objets = list(objets)
    return ", ".join(objets[:MAX_ITEMS]) + (f" (+{len(objets) - MAX_ITEMS})" if len(objets) > MAX_ITEMS else "")


def _inconnus(fiche):
    """Puces de la rubrique « Ce qui reste inconnu » de la fiche vivante, sans les citations."""
    puces, dedans = [], False
    for ligne in (fiche or "").splitlines():
        if ligne.startswith("#"):
            dedans = bool(RE_INCONNU.match(ligne))
        elif dedans and re.match(r"\s*[-*]\s", ligne):
            puces.append(RE_CITATION.sub("", re.sub(r"^\s*[-*]\s+", "", ligne)).replace("**", "").strip())
    return puces


def depuis_connaissances(jumeau, claims, fiche):
    ouverts = [c for c in claims if c["statut"] != "CONTESTED"]
    par = lambda p: [c["objet"] for c in ouverts if c["predicat"] == p]  # noqa: E731
    capacites = [f"Expose {c['objet']}" + (" (confirmé par l'équipe)" if c["statut"] == "ACCEPTED" else "")
                 for c in ouverts if c["predicat"] == "EXPOSE"][:MAX_ITEMS]
    comportements = ["Lu dans le code : aucune source d'observabilité connectée, rien n'est observé en exécution"]
    for predicat, libelle in (("DEPEND_DE", "S'appuie sur"), ("LIT_VARIABLE", "Lit la configuration"),
                              ("EXECUTE_IMAGE", "Exécute les images")):
        if par(predicat):
            comportements.append(f"{libelle} : {_liste(par(predicat))}")
    contradictions = [f"{c['objet']} — contesté" + (f" : {c['revues'][0]['motif']}" if c["revues"] and
                                                    c["revues"][0].get("motif") else "")
                      for c in claims if c["statut"] == "CONTESTED"]
    return {
        "identite": {k: jumeau.get(k) for k in ("nom", "mission", "domaine")},
        "capacites": capacites or ["Aucune interface exposée trouvée dans le code"],
        "comportements": comportements,
        # ponytail: le code seul ne révèle pas les relations entre applications ; à tirer des appels HTTP (cbm).
        "relations_supposees": [],
        "contradictions": contradictions,
        "connaissances_manquantes": _inconnus(fiche) + ["Observabilité, incidents, base de données : non connectés"],
    }


def examiner(conn, jumeau_id, doc):
    fiche = gardien.fiche_courante(conn, jumeau_id)
    return depuis_connaissances(doc, depot.lister_claims(conn, jumeau_id), fiche and fiche["contenu"])
