"""Transforme les résultats de codebase-memory-mcp en Claims prouvés.

Fonctions pures : la lecture des fichiers (au SHA indexé) est injectée via `lire(chemin) -> list[str] | None`.
Un Claim n'est retenu que si sa preuve se vérifie dans le fichier : citation localisée, lignes existantes.
"""
import hashlib
import re

# Confiance initiale par règle (Architecture Jumeau §7.1, correction 4) ; la calibration l'ajustera.
CONFIANCE_INITIALE = {"API_USAGE": 0.9, "DEPENDENCY": 0.85}


def localiser(lignes, jeton):
    """Première ligne (1-based) contenant `jeton` comme mot entier, sinon None."""
    motif = re.compile(rf"(?<![\w.@/-]){re.escape(jeton)}(?![\w-])")
    return next((i for i, l in enumerate(lignes, 1) if motif.search(l)), None)


def preuve(depot, sha, chemin, lignes, debut, fin):
    citation = "\n".join(lignes[debut - 1:fin])
    return {
        "locator": f"git://{depot}@{sha}:{chemin}#L{debut}-L{fin}",
        "chemin": chemin,
        "sha": sha,
        "ligne_debut": debut,
        "ligne_fin": fin,
        "citation": citation,
        "hash": hashlib.sha256(citation.encode()).hexdigest(),
    }


def _motif_route(route):
    """cbm normalise les paramètres (`/jumeaux/{jid}` → `/jumeaux/{}`) : `{}` accepte tout nom de paramètre."""
    corps = r"\{[^}]*\}".join(re.escape(morceau) for morceau in route.split("{}"))
    return re.compile(rf"""["']{corps}["']""")  # chaîne complète : /items ne se prouve pas par /items/{id}


def _route(r, lignes):
    if r["debut"] is None or r["fin"] is None:
        return None
    debut, fin = int(r["debut"]) - 1, int(r["fin"])  # inclut le décorateur au-dessus du def
    if debut < 1 or fin > len(lignes) or not _motif_route(r["route"]).search("\n".join(lignes[debut - 1:fin])):
        return None
    return ("EXPOSE", f"{r['methode']} {r['route']}", "API_USAGE", debut, fin)


def _jeton(predicat, cle, transformer=lambda v: v, filtre=lambda l: True):
    def extraire(r, lignes):
        retenues = [l if filtre(l) else "" for l in lignes]  # garde la numérotation
        ligne = localiser(retenues, transformer(r[cle]))
        return (predicat, r[cle], "DEPENDENCY", ligne, ligne) if ligne else None
    return extraire


DECLARATION_IMAGE = re.compile(r"^\s*(image\s*:|FROM\s)", re.IGNORECASE)

EXTRACTEURS = {
    "routes": _route,
    "paquets": _jeton("DEPEND_DE", "paquet"),
    "variables": _jeton("LIT_VARIABLE", "variable"),
    # « docker.io/library/mongo » s'écrit « image: mongo:7.0 » (compose) ou « FROM mongo » (Dockerfile).
    "images": _jeton("EXECUTE_IMAGE", "image", lambda v: v.rsplit("/", 1)[-1], DECLARATION_IMAGE.match),
}


def adapter(resultats, lire, depot, sha, sujet):
    claims = {}
    for famille, extraire in EXTRACTEURS.items():
        for r in resultats.get(famille, []):
            lignes = lire(r["chemin"])
            trouve = extraire(r, lignes) if lignes else None
            if not trouve:
                continue
            predicat, objet, type_claim, debut, fin = trouve
            c = claims.setdefault((predicat, objet), {
                "sujet": sujet, "predicat": predicat, "objet": objet, "type": type_claim,
                "confiance": CONFIANCE_INITIALE[type_claim], "preuves": [],
            })
            p = preuve(depot, sha, r["chemin"], lignes, debut, fin)
            if p["locator"] not in {x["locator"] for x in c["preuves"]}:
                c["preuves"].append(p)
    return list(claims.values())
