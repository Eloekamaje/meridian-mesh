"""Transforme les résultats de codebase-memory-mcp en Claims prouvés.

Fonctions pures : la lecture des fichiers (au SHA indexé) est injectée via `lire(chemin) -> list[str] | None`.
Un Claim n'est retenu que si sa preuve se vérifie dans le fichier : citation localisée, lignes existantes.
"""
import hashlib
import re

from jumeau import recettes

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


MAX_DECORATEURS = 15  # lignes au-dessus du def où chercher le début des décorateurs


def _debut_decorateurs(lignes, ligne_def):
    """Première ligne du bloc de décorateurs juste au-dessus du def (un décorateur peut tenir sur plusieurs lignes)."""
    haut = ligne_def - 1
    while (haut >= 1 and ligne_def - haut <= MAX_DECORATEURS and lignes[haut - 1].strip()
           and not lignes[haut - 1].lstrip().startswith(("def ", "async def ", "class "))):
        haut -= 1
    return next((n for n in range(haut + 1, ligne_def) if lignes[n - 1].lstrip().startswith("@")), ligne_def - 1)


def _route(r, lignes):
    if r["debut"] is None or r["fin"] is None or r.get("methode") == "ANY":
        return None
    ligne_def, fin = int(r["debut"]), int(r["fin"])
    if ligne_def < 2 or fin > len(lignes):
        return None
    debut = _debut_decorateurs(lignes, ligne_def)
    if not _motif_route(r["route"]).search("\n".join(lignes[debut - 1:fin])):
        return None
    return ("EXPOSE", f"{r['methode']} {_chemin_complet(r.get('prefixe'), r['route'])}", "API_USAGE", debut, fin)


def _chemin_complet(prefixe, route):
    """Le décorateur porte le chemin local ; le préfixe du routeur (entrée ANY de cbm) donne le chemin exposé."""
    if not prefixe or route.startswith(prefixe):
        return route or "/"
    return prefixe.rstrip("/") + route if route else prefixe


def _avec_prefixes(routes):
    """cbm signale le préfixe de routeur d'un gestionnaire par une entrée « ANY » sur le même fichier et la même ligne."""
    prefixes = {(r["chemin"], r["debut"]): r["route"] for r in routes if r.get("methode") == "ANY"}
    return [{**r, "prefixe": prefixes.get((r["chemin"], r["debut"]))} for r in routes]


def _jeton(predicat, cle, transformer=lambda v: v, filtre=lambda l, v: True):
    def extraire(r, lignes):
        retenues = [l if filtre(l, r[cle]) else "" for l in lignes]  # garde la numérotation
        ligne = localiser(retenues, transformer(r[cle]))
        return (predicat, r[cle], "DEPENDENCY", ligne, ligne) if ligne else None
    return extraire


DECLARATION_IMAGE = re.compile(r"^\s*(image\s*:|FROM\s)", re.IGNORECASE)

EXTRACTEURS = {
    "routes": _route,
    "paquets": _jeton("DEPEND_DE", "paquet"),
    # Une variable est prouvée par une ligne qui la lit (os.environ, getenv, process.env, compose…), jamais par un
    # commentaire ou une docstring qui la nomme : la même recette que la vérification (Harness v3 §2).
    "variables": _jeton("LIT_VARIABLE", "variable",
                        filtre=lambda l, v: recettes.recette("LIT_VARIABLE", v, [l]) == "verifie"),
    # « docker.io/library/mongo » s'écrit « image: mongo:7.0 » (compose) ou « FROM mongo » (Dockerfile).
    "images": _jeton("EXECUTE_IMAGE", "image", lambda v: v.rsplit("/", 1)[-1], lambda l, v: DECLARATION_IMAGE.match(l)),
}


def adapter(resultats, lire, depot, sha, sujet):
    claims = {}
    for famille, extraire in EXTRACTEURS.items():
        lignes_resultat = resultats.get(famille, [])
        for r in (_avec_prefixes(lignes_resultat) if famille == "routes" else lignes_resultat):
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
