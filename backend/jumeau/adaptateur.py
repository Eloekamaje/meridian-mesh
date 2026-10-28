"""Transforme les résultats de codebase-memory-mcp en Claims prouvés.

Fonctions pures : la lecture des fichiers (au SHA indexé) est injectée via `lire(chemin) -> list[str] | None`.
Un Claim n'est retenu que si sa preuve se vérifie dans le fichier : citation localisée, lignes existantes.

**La preuve n'est plus choisie par la règle qui la vérifie.** L'extracteur prend la ligne que l'index désigne
(`start_line`) ou, à défaut, la première ligne du fichier qui déclare l'objet ; il n'appelle jamais `recettes`. La
recette (`recettes.py`), elle, juge ensuite si cette ligne appuie l'énoncé — et peut donc échouer : c'était le défaut
L1.1 du plan de remédiation, où l'extraction était filtrée par la recette elle-même, si bien que « vérifié » ne
pouvait jamais être faux.
"""
import hashlib
import re

# Confiance initiale par règle (Architecture Jumeau §7.1, correction 4) ; la calibration l'ajustera.
CONFIANCE_INITIALE = {"API_USAGE": 0.9, "DEPENDENCY": 0.85}

# Formes de **déclaration** propres à l'extraction (le vérificateur a les siennes, plus larges) : le but ici est de
# situer la preuve, pas de la juger. Chaînes, pas de motifs compilés : `{nom}` est substitué à l'usage.
DECLARATIONS = {
    "LIT_VARIABLE": (
        r"^\s*(?:-\s*)?[\"']?{nom}[\"']?\s*[:=]",                                # compose, .env, YAML
        r"^\s*(?:ENV|ARG)\s+{nom}\b",                                            # Dockerfile
        r"(?:environ(?:\.get)?\s*[\[(]|getenv\s*\(|process\.env\.|process\.env\[\s*[\"'])\s*[\"']?{nom}",  # code
    ),
}


def localiser(lignes, jeton):
    """Première ligne (1-based) contenant `jeton` comme mot entier, sinon None."""
    motif = re.compile(rf"(?<![\w.@/-]){re.escape(jeton)}(?![\w-])")
    return next((i for i, l in enumerate(lignes, 1) if motif.search(l)), None)


def declarer(predicat, objet, lignes):
    """Première ligne où `objet` est **déclaré ou lu** pour ce prédicat, sinon None (règle de l'extracteur)."""
    motifs = DECLARATIONS.get(predicat)
    if not motifs:
        return localiser(lignes, objet)
    nom = re.escape(objet)
    for i, ligne in enumerate(lignes, 1):
        if any(re.compile(m.format(nom=nom)).search(ligne) for m in motifs):
            return i
    return None


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


def _jeton(predicat, cle, transformer=lambda v: v, filtre=lambda l, v: True, ligne_index=False):
    def extraire(r, lignes):
        if ligne_index and r.get("ligne"):
            n = int(r["ligne"])
            return (predicat, r[cle], "DEPENDENCY", n, n) if 1 <= n <= len(lignes) else None
        retenues = [l if filtre(l, r[cle]) else "" for l in lignes]  # garde la numérotation
        ligne = localiser(retenues, transformer(r[cle]))
        return (predicat, r[cle], "DEPENDENCY", ligne, ligne) if ligne else None
    return extraire


def _variable(r, lignes):
    """La ligne que l'index désigne (`start_line` du nœud EnvVar) ; à défaut, la première déclaration reconnue.
    Jamais la recette : la vérification doit pouvoir contredire l'extraction (plan de remédiation L1.1)."""
    n = int(r.get("ligne") or 0)
    if 1 <= n <= len(lignes):
        return ("LIT_VARIABLE", r["variable"], "DEPENDENCY", n, n)
    ligne = declarer("LIT_VARIABLE", r["variable"], lignes)
    return ("LIT_VARIABLE", r["variable"], "DEPENDENCY", ligne, ligne) if ligne else None


DECLARATION_IMAGE = re.compile(r"^\s*(image\s*:|FROM\s)", re.IGNORECASE)

EXTRACTEURS = {
    "routes": _route,
    "paquets": _jeton("DEPEND_DE", "paquet"),
    # Une variable est située par l'index (ou sa déclaration), jamais par la règle qui la vérifie.
    "variables": _variable,
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
