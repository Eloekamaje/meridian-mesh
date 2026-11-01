"""L'enchaînement d'une fonctionnalité, lu dans le code : qui appelle qui, chaque appel prouvé par sa ligne.

L'index (codebase-memory, `trace_path`) donne les fonctions appelées mais ni l'appelant au-delà du premier niveau,
ni la ligne de l'appel. On trace donc un niveau à la fois (vraies paires appelant → appelé), puis on retrouve dans
le corps de l'appelant, au commit ingéré, la ligne **qui appelle** l'appelé : c'est la citation de la flèche.
Déterministe, sans modèle ; ce qui ne se prouve pas n'est pas rendu.

Les deux outils sont interrogés en `format="json"` : la sortie texte était découpée par des expressions régulières,
et le résolveur (`strategy`, `confidence`) était jeté — donc une arête certaine (lsp) et une arête devinée
(heuristique) se présentaient de la même façon (plan de remédiation L0bis.2).
"""
import json
import re

from meridian.adapters.outbound.connectors.source_git import lire_au_sha
from meridian.domain.recettes import _masquer

PROFONDEUR_MAX = 4
MAX_NOEUDS = 15
# Bruit d'une fonctionnalité métier : erreurs, journal, modèles de données, utilitaires de test.
BRUIT = re.compile(r"(?:^|\.)(?:errors?|exceptions?|logging|log|tests?|conftest)(?:\.|$)", re.IGNORECASE)


def _json(sortie):
    """Charge le JSON rendu par un outil (format="json") ; une sortie illisible est une panne, pas une donnée."""
    try:
        return json.loads(sortie)
    except (TypeError, ValueError):
        raise RuntimeError("codebase-memory-mcp : réponse non JSON alors que format=json était demandé")


def _court(qn, projet):
    return qn[len(projet) + 1:] if qn.startswith(projet + ".") else qn


def _fonctions(appeler, projet, nom):
    """[(qn, chemin, début, fin)] des fonctions dont le nom court est `nom`."""
    donnees = _json(appeler("search_graph", project=projet, name_pattern=nom, limit=20, format="json"))
    trouves = []
    for groupe in donnees.get("groups") or []:
        prefixe = groupe.get("qn_prefix") or ""
        for ligne in groupe.get("rows") or []:
            qn = f"{prefixe}.{ligne[0]}" if prefixe else ligne[0]
            debut, _, fin = str(ligne[2]).partition("-")
            trouves.append((qn, groupe.get("file"), int(debut), int(fin or debut)))
    return trouves


def localiser(appeler, projet, qn):
    """(chemin, début, fin) de la fonction `qn` dans l'index, ou None."""
    for trouve_qn, chemin, debut, fin in _fonctions(appeler, projet, qn.rsplit(".", 1)[-1]):
        if trouve_qn == qn:
            return chemin, debut, fin
    return None


def appeles(appeler, projet, qn):
    """Ce que `qn` appelle à un niveau : [{qn, strategy, confidence}], sans doublon, sans elle-même.
    `strategy` dit comment le résolveur l'a établi (« lsp » certain, « heuristic » déduit) — on ne le jette plus."""
    donnees = _json(appeler("trace_path", project=projet, function_name=qn.rsplit(".", 1)[-1],
                            direction="outbound", depth=1, include_evidence=True, format="json"))
    sortie = {}
    for groupe in (donnees.get("callees") or {}).get("groups") or []:
        prefixe = groupe.get("qn_prefix") or ""
        for ligne in groupe.get("rows") or []:
            nom, hop = ligne[0], int(ligne[1])
            if hop != 1:
                continue
            cible = f"{prefixe}.{nom}" if prefixe else nom
            if cible != qn and cible not in sortie:
                sortie[cible] = {"qn": cible, "strategy": ligne[2] if len(ligne) > 2 else "",
                                 "confidence": float(ligne[3]) if len(ligne) > 3 else None}
    return list(sortie.values())


def ligne_d_appel(lignes, debut, fin, nom):
    """Première ligne du corps qui **appelle** `nom` (appel direct ou méthode), hors chaîne et hors commentaire.
    Une mention sans appel (`x = nom`, un texte qui nomme la fonction) ne fonde rien : None, et la flèche n'est pas
    rendue (plan de remédiation L0bis.1)."""
    masque = _masquer(lignes)
    mot = re.escape(nom)
    appel = re.compile(rf"(?<![\w])(?:[\w\]\)]+\s*(?:\.|::)\s*)?{mot}\s*\(")
    for n in range(max(1, debut), min(fin, len(lignes)) + 1):
        ligne = masque[n - 1]
        if appel.search(ligne):
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
            court = _court(appele["qn"], projet)
            if BRUIT.search(court):
                continue
            n = ligne_d_appel(contenu, debut, fin, appele["qn"].rsplit(".", 1)[-1])
            if n is not None:  # un appel non retrouvé dans le corps n'est pas prouvé : il n'est pas rendu
                trouves.append((n, appele, court))
        for n, appele, court in sorted(trouves, key=lambda t: t[0]):  # dans l'ordre du code : l'ordre d'une séquence
            fleches.append({"de": _court(qn, projet), "vers": court, "appel": appele["qn"].rsplit(".", 1)[-1],
                            "chemin": chemin, "ligne": n,
                            # comment le résolveur a établi l'arête : « lsp » (certain) ou « heuristic » (déduit)
                            "resolution": appele.get("strategy") or "", "confiance": appele.get("confidence")})
            if appele["qn"] not in vus and len(vus) < max_noeuds:
                vus.add(appele["qn"])
                file.append((appele["qn"], niveau + 1))
    return fleches


def _depart(appeler, projet, fonction):
    nom = fonction.rsplit(".", 1)[-1]
    for qn, _chemin, _debut, _fin in _fonctions(appeler, projet, nom):
        if qn.endswith("." + fonction) or qn.rsplit(".", 1)[-1] == nom:
            return qn
    return None


def _resolution(fleche):
    """Comment l'arête a été établie : une arête déduite ne se présente pas comme une arête certaine."""
    strategie, confiance = fleche.get("resolution") or "", fleche.get("confiance")
    if not strategie:
        return ""
    return f" · résolution : {strategie}" + (f" {confiance:.2f}".replace(".", ",") if isinstance(confiance, float) else "")


def texte(fleches, source_nom=None):
    """Pour l'agent : une flèche par ligne, avec la citation à donner comme fondement à dessiner_schema."""
    if not fleches:
        return "Aucun enchaînement prouvé depuis cette fonction (introuvable dans l'index, ou appels non retrouvés)."
    prefixe = f"{source_nom}:" if source_nom else ""
    return "\n".join(f"{i}. {f['de']} → {f['vers']} (appel : {f['appel']}){_resolution(f)} · fondement : "
                     f"{prefixe}{f['chemin']}#L{f['ligne']}-L{f['ligne']}" for i, f in enumerate(fleches, 1))
