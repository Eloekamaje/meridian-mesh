"""L'enchaînement d'une fonctionnalité, lu dans le code : qui appelle qui, chaque appel prouvé par sa ligne.

L'index (codebase-memory, `trace_path`) donne les fonctions appelées mais ni l'appelant au-delà du premier niveau,
ni la ligne de l'appel. On trace donc un niveau à la fois (vraies paires appelant → appelé), puis on retrouve dans
le corps de l'appelant, au commit ingéré, la ligne qui nomme l'appelé : c'est la citation de la flèche. Déterministe,
sans modèle ; ce qui ne se prouve pas n'est pas rendu.
"""
import re

from jumeau.source_git import lire_au_sha

PROFONDEUR_MAX = 4
MAX_NOEUDS = 15
# Bruit d'une fonctionnalité métier : erreurs, journal, modèles de données, utilitaires de test.
BRUIT = re.compile(r"(?:^|\.)(?:errors?|exceptions?|logging|log|tests?|conftest)(?:\.|$)", re.IGNORECASE)
RE_LIGNE_FONCTION = re.compile(r"^\s*(\S+)\s+(?:Function|Method)\s+(\S+)\s+(\d+)-(\d+)\b")
RE_GROUPE = re.compile(r"^(\S.*):\s*$")
RE_APPELE = re.compile(r"^\s+(\S+)\s+(\d+)\s*$")


def _court(qn, projet):
    return qn[len(projet) + 1:] if qn.startswith(projet + ".") else qn


def localiser(appeler, projet, qn):
    """(chemin, début, fin) de la fonction `qn` dans l'index, ou None."""
    sortie = appeler("search_graph", project=projet, name_pattern=qn.rsplit(".", 1)[-1], limit=20)
    for ligne in str(sortie).splitlines():
        m = RE_LIGNE_FONCTION.match(ligne)
        if m and m.group(1) == qn:
            return m.group(2), int(m.group(3)), int(m.group(4))
    return None


def appeles(appeler, projet, qn):
    """Fonctions appelées directement par `qn` (premier niveau du graphe), noms qualifiés."""
    sortie = appeler("trace_path", project=projet, function_name=qn.rsplit(".", 1)[-1], direction="outbound", depth=1)
    groupe, resultat = "", []
    for ligne in str(sortie).splitlines():
        if (g := RE_GROUPE.match(ligne)) and not ligne.startswith(" "):
            groupe = g.group(1)
            continue
        if (a := RE_APPELE.match(ligne)) and a.group(2) == "1":
            nom = a.group(1)  # à plat (« qn hop ») à profondeur 1, sous un groupe (« prefixe: ») au-delà
            resultat.append(f"{groupe}.{nom}" if groupe and groupe != '""' else nom)
    return [r for r in dict.fromkeys(resultat) if r != qn]


def ligne_d_appel(lignes, debut, fin, nom):
    """Première ligne du corps (début–fin) qui nomme `nom` comme un appel ou une référence, ou None."""
    motif = re.compile(rf"(?<![\w]){re.escape(nom)}(?![\w])")
    for n in range(max(1, debut), min(fin, len(lignes)) + 1):
        if motif.search(lignes[n - 1]) and not lignes[n - 1].lstrip().startswith(("#", "//", '"""', "'''")):
            return n
    return None


def enchainement(source, fonction, appeler, profondeur=3, max_noeuds=MAX_NOEUDS):
    """Flèches prouvées depuis `fonction` (nom court ou qualifié) : [{de, vers, appel, chemin, ligne}], noms courts.
    Parcours en largeur, `profondeur` niveaux au plus, `max_noeuds` fonctions au plus."""
    projet = source["index_code"]
    lire = lire_au_sha(source.get("copie") or source["emplacement"], source["curseur"])
    depart = _depart(appeler, projet, fonction)
    if depart is None:
        return []
    vus, file, fleches = {depart}, [(depart, 0)], []
    while file and len(vus) <= max_noeuds:
        qn, niveau = file.pop(0)
        if niveau >= min(profondeur, PROFONDEUR_MAX):
            continue
        lieu = localiser(appeler, projet, qn)
        if not lieu:
            continue
        chemin, debut, fin = lieu
        try:
            contenu = lire(chemin)
        except ValueError:
            contenu = None
        if not contenu:
            continue
        trouves = []
        for appele in appeles(appeler, projet, qn):
            court = _court(appele, projet)
            if BRUIT.search(court):
                continue
            n = ligne_d_appel(contenu, debut, fin, appele.rsplit(".", 1)[-1])
            if n is not None:  # un appel non retrouvé dans le corps n'est pas prouvé : il n'est pas rendu
                trouves.append((n, appele, court))
        for n, appele, court in sorted(trouves):  # dans l'ordre du code : l'ordre d'une séquence
            fleches.append({"de": _court(qn, projet), "vers": court, "appel": appele.rsplit(".", 1)[-1],
                            "chemin": chemin, "ligne": n})
            if appele not in vus and len(vus) < max_noeuds:
                vus.add(appele)
                file.append((appele, niveau + 1))
    return fleches


def _depart(appeler, projet, fonction):
    nom = fonction.rsplit(".", 1)[-1]
    sortie = appeler("search_graph", project=projet, name_pattern=nom, limit=20)
    candidats = [m.group(1) for l in str(sortie).splitlines() if (m := RE_LIGNE_FONCTION.match(l))]
    exacts = [c for c in candidats if c.endswith("." + fonction) or c.rsplit(".", 1)[-1] == nom]
    return exacts[0] if exacts else None


def texte(fleches, source_nom=None):
    """Pour l'agent : une flèche par ligne, avec la citation à donner comme fondement à dessiner_schema."""
    if not fleches:
        return "Aucun enchaînement prouvé depuis cette fonction (introuvable dans l'index, ou appels non retrouvés)."
    prefixe = f"{source_nom}:" if source_nom else ""
    return "\n".join(f"{i}. {f['de']} → {f['vers']} (appel : {f['appel']}) · fondement : "
                     f"{prefixe}{f['chemin']}#L{f['ligne']}-L{f['ligne']}" for i, f in enumerate(fleches, 1))
