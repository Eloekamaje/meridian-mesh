#!/usr/bin/env python3
"""Enquêtes « comprendre l'application » sur les dépôts d'une racine, via le harness."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "backend"))

from meridian.application.exploration_agent import ExplorationHarness, RepoSnapshot  # noqa: E402
from meridian.adapters.outbound.llm.exploration_adapter import ExplorationAdapter  # noqa: E402

OBJECTIF = """Comprends cette application et présente-la en français, pour un employé qui ne connaît pas le code.
Structure attendue :
1. À quoi elle sert, en deux phrases.
2. Pour qui et dans quels parcours.
3. Ce qu'elle permet de faire.
4. Les règles métier et les refus qu'elle applique.
5. Les données qu'elle détient et les effets extérieurs.
6. Les applications, services et dépendances avec lesquels elle échange.
7. Ce que tu ignores et les limites de l'enquête.
Distingue OBSERVÉ et DÉDUIT. Cite le dépôt, le SHA, le fichier et les lignes pour chaque affirmation importante.
N'invente aucune preuve. N'enregistre pas de Claim si tu n'as pas de preuve localisée.
Réserve le prédicat EXPOSE aux routes définies par un serveur ; pour un appel sortant
(SDK, client HTTP, frontend), utilise le prédicat USES. Pour une route préfixée, cite aussi
la ligne qui déclare le préfixe (blueprint, namespace, @RequestMapping, app.use) : le harness
refuse un préfixe non prouvé. Si le préfixe n'est pas prouvé, enregistre la route locale
(ex. « GET /parameters ») et signale le préfixe comme INCONNU ; ne bloque pas la conclusion.
Avant de conclure, vérifie que chaque route citée dans ta synthèse a bien été enregistrée
via record_claim ou record_claims. N'écris jamais « Claims enregistrés » si le compteur de
Claims de l'état de l'enquête est resté à zéro."""


def _partiel(texte: str) -> bool:
    texte = str(texte or "").lower()
    return ("budget atteint" in texte or "enquête interrompue" in texte
            or "enquete interrompue" in texte or "je n'ai pas pu terminer" in texte
            or "synthèse partielle" in texte or "synthese partielle" in texte
            or "synthèse interrompue" in texte or "synthese interrompue" in texte
            or "synthèse impossible" in texte or "synthese impossible" in texte
            or "dernière requête a été tronquée" in texte
            or "derniere requete a ete tronquee" in texte)


_MOTS_SOURCE = ("src", "app", "api", "web", "backend", "frontend", "server", "client",
                "agent", "service", "package", "lib", "cli", "sdk", "core", "module",
                "apps", "extensions", "plugin", "plugins", "v2", "v3")


def _est_source(nom: str) -> bool:
    jetons = [jeton for jeton in re.split(r"[-_.]", str(nom or "").lower()) if jeton]
    return any(jeton == mot or jeton.startswith(mot) for jeton in jetons
               for mot in _MOTS_SOURCE)


_NON_SOURCE = {"node_modules", "dist", "build", "coverage", "__pycache__", ".next",
               "target", "tests", "test", "__tests__", "spec", "specs", "i18n",
               "public", "assets", "images", "static", "fonts"}


def _enfants(prefixe: str, liste) -> dict:
    """Découpe par sous-répertoire source ; ignore racine, tests, assets et dotfiles."""
    enfants = {}
    for fichier in liste:
        reste = fichier[len(prefixe) + 1:] if prefixe else fichier
        if "/" not in reste:
            continue
        morceau = reste.split("/", 1)[0]
        if not morceau or morceau.startswith(".") or morceau in _NON_SOURCE:
            continue
        cle = f"{prefixe}/{morceau}" if prefixe else morceau
        enfants.setdefault(cle, []).append(fichier)
    return enfants


def _groupes(fichiers, max_fichiers=500, max_groupes=8, max_parties=60):
    """Découpe par racines source, puis par sous-répertoires, sans noyer le code dans les dotfiles."""
    fichiers = list(fichiers)
    if len(fichiers) <= max_fichiers:
        return [("", fichiers)]
    sources = {}
    for fichier in fichiers:
        racine = fichier.split("/", 1)[0]
        if "/" in fichier and _est_source(racine):
            sources.setdefault(racine, []).append(fichier)
    if not sources:
        return [("", fichiers)]
    total_source = sum(len(liste) for liste in sources.values())
    if (total_source / max(1, len(fichiers)) < 0.2
            and len(fichiers) <= max_fichiers * 10):
        return [("", fichiers)]
    groupes = sorted(sources.items())
    while len(groupes) < max_parties:
        candidats = [index for index, (prefixe, _) in enumerate(groupes) if prefixe]
        if not candidats:
            break
        index = max(candidats, key=lambda i: len(groupes[i][1]))
        prefixe, liste = groupes[index]
        if len(liste) <= max_fichiers:
            break
        enfants = _enfants(prefixe, liste)
        if not enfants:
            break
        if len(enfants) == 1 and next(iter(enfants)) == prefixe:
            break
        if len(groupes) - 1 + len(enfants) > max_parties:
            break
        groupes[index:index + 1] = sorted(enfants.items())
    return groupes


_ORDRES_SOURCE = ("src", "app", "api", "web", "backend", "frontend", "packages",
                  "services", "lib", "cli", "sdks", "apps", "extensions", "dify-agent",
                  "v3", "v2", "agents", "bin", "plugin", "plugins")


def _priorite_partie(prefixe: str) -> tuple:
    """Les sous-systèmes de code passent avant les dotfiles, la docs et les configs."""
    if not prefixe:
        return (0, 0, "")
    premier = prefixe.split("/", 1)[0]
    if premier in _ORDRES_SOURCE:
        return (0, _ORDRES_SOURCE.index(premier), prefixe)
    if premier.startswith("."):
        return (3, 0, prefixe)
    if premier.lower() in {"docs", "doc", "documentation"}:
        return (2, 0, prefixe)
    return (1, 0, prefixe)


_PREFIXE_RE = re.compile(
    r"(url_prefix|Blueprint\s*\(|Namespace\s*\(|@RequestMapping|app\.use\s*\(|"
    r"router\.use\s*\(|include_router)"
)


def _indices_prefixes(snapshot, prefixe, limite=40):
    """Pré-scan déterministe des préfixes du sous-système et de ses paquets parents."""
    tous = snapshot.fichiers()
    ensemble = set(tous)
    candidats = []
    morceaux = [morceau for morceau in str(prefixe or "").split("/") if morceau]
    for index in range(len(morceaux), 0, -1):
        base = "/".join(morceaux[:index])
        for nom in ("__init__.py", "urls.py", "app.py", "server.py", "main.py"):
            candidat = f"{base}/{nom}"
            if candidat in ensemble and candidat not in candidats:
                candidats.append(candidat)
    for fichier in tous:
        if prefixe and not (fichier == prefixe or fichier.startswith(prefixe + "/")):
            continue
        if (fichier.endswith(("__init__.py", "urls.py", "app.py", "server.py", "main.py"))
                and fichier not in candidats):
            candidats.append(fichier)
    indices = []
    for fichier in candidats:
        try:
            contenu = snapshot.lire(fichier, 1, 400)
        except Exception:
            continue
        for ligne in contenu.get("lines", []):
            texte = str(ligne.get("text") or "")
            if _PREFIXE_RE.search(texte):
                indices.append(f"- {fichier}:{ligne.get('number')} `{texte.strip()[:200]}`")
                if len(indices) >= limite:
                    return indices
    return indices


def _prefixe_unique(snapshot, prefixe):
    """Rend le préfixe d'URL unique du groupe, ou une chaîne vide si ambigu."""
    indices = _indices_prefixes(snapshot, prefixe, 30)
    prefixes, chemins = [], []
    for ligne in indices:
        trouve = re.search(r'url_prefix\s*=\s*["\']([^"\']+)["\']', ligne)
        if trouve:
            prefixes.append(trouve.group(1))
        trouve = re.search(r'Namespace\([^\n]*?path\s*=\s*["\']([^"\']+)["\']', ligne)
        if trouve:
            chemins.append(trouve.group(1))
    prefixes = list(dict.fromkeys(prefixes))
    if len(prefixes) != 1:
        return ""
    base = prefixes[0]
    if chemins and chemins[0] not in {"", "/"}:
        base = base.rstrip("/") + "/" + chemins[0].strip("/")
    return base.rstrip("/") or "/"


def _normaliser_claims(etat, base, prefixe=""):
    """Préfixe les routes locales d'un groupe quand son préfixe est unique."""
    chemin = Path(etat) / "claims.json"
    if not base or not chemin.exists():
        return 0
    try:
        claims = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if not isinstance(claims, list):
        return 0
    normalises = 0
    for claim in claims:
        if str(claim.get("predicat") or "").upper() != "EXPOSE":
            continue
        objet = str(claim.get("objet") or "")
        if " " not in objet:
            continue
        methode, route = objet.split(" ", 1)
        if route == base or route.startswith(base + "/"):
            continue
        preuves = claim.get("preuves") or []
        if prefixe and not any(
                str(preuve.get("chemin") or "").startswith(prefixe + "/")
                for preuve in preuves):
            continue
        claim["objet"] = f"{methode} {base.rstrip('/')}{route}"
        normalises += 1
    if normalises:
        vus, uniques = set(), []
        for claim in claims:
            cle = (claim.get("predicat"), claim.get("objet"))
            if cle in vus:
                continue
            vus.add(cle)
            uniques.append(claim)
        chemin.write_text(json.dumps(uniques, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    return normalises


def _objectif(prefixe="", indices=None):
    base = OBJECTIF
    if prefixe:
        base += (f"\n\nLimite strictement l'enquête au préfixe `{prefixe}/` : ne lis pas "
                 "les autres sous-systèmes.")
    if indices:
        base += ("\n\nPréfixes déclarés dans ce sous-système (lignes déjà lues par le "
                 "harness ; utilise-les comme preuves pour composer les routes, et cite "
                 "la ligne correspondante) :\n" + "\n".join(indices))
    return base


def _semantique_graphify(depot: Path, construire: bool):
    graphe = depot / "graphify-out" / "graph.json"
    if not graphe.exists() and construire:
        try:
            subprocess.run(["graphify", "update", str(depot)], capture_output=True,
                           text=True, timeout=900, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return {}, {}
    if not graphe.exists():
        return {}, {}
    from meridian.adapters.outbound.connectors.graphify_semantics import GraphifySemanticTools
    outils = GraphifySemanticTools(graphe)
    return outils.outils(), outils.schemas()


def _mission(snapshot, cible, prefixe, max_steps, outils_semantiques=None,
             schemas_semantiques=None):
    etat = cible / "parties" / (prefixe.replace("/", "__") or "racine")
    rapport = etat / "report.md"
    if rapport.exists() and not _partiel(rapport.read_text(encoding="utf-8")):
        return {"prefixe": prefixe, "statut": "deja", "rapport": str(rapport)}
    indices = _indices_prefixes(snapshot, prefixe)
    try:
        harness = ExplorationHarness([snapshot], etat,
                                     outils_semantiques=outils_semantiques,
                                     schemas_semantiques=schemas_semantiques)
        texte = harness.run(_objectif(prefixe, indices), ExplorationAdapter(),
                            max_steps=max_steps,
                            resume=(etat / "checkpoint.json").exists())
    except Exception as erreur:
        return {"prefixe": prefixe, "statut": "echec", "rapport": str(rapport),
                "erreur": str(erreur)[:500]}
    base = _prefixe_unique(snapshot, prefixe)
    normalisations = _normaliser_claims(etat, base, prefixe) if base else 0
    return {"prefixe": prefixe, "statut": "partiel" if _partiel(texte) else "ok",
            "rapport": str(rapport), "resume": texte[:300],
            "prefixe_url": base, "normalisations": normalisations}


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("racine")
    p.add_argument("--sortie", default="/home/majella/.local/share/meridian/comprehension")
    p.add_argument("--max-steps", type=int, default=12)
    p.add_argument("--limite", type=int, default=0)
    p.add_argument("--decouper", action="store_true", help="découpe les gros dépôts en sous-systèmes")
    p.add_argument("--max-fichiers", type=int, default=500)
    p.add_argument("--max-groupes", type=int, default=8,
                   help="nombre cible de sous-systèmes (compatibilité)")
    p.add_argument("--max-parties", type=int, default=60,
                   help="plafond de sous-systèmes après découpage récursif")
    p.add_argument("--prefixe", default="",
                   help="ne traiter qu'un sous-arbre du dépôt (ex. api/controllers)")
    p.add_argument("--reset", action="store_true",
                   help="efface le dossier de sortie du dépôt avant de relancer")
    p.add_argument("--seulement", nargs="+", default=[], help="ne traiter que ces dépôts")
    p.add_argument("--graphify", action="store_true",
                   help="expose graphify_search/graphify_node si un graphe existe")
    p.add_argument("--graphify-construire", action="store_true",
                   help="construit graphify-out/graph.json si absent (peut être long)")
    args = p.parse_args(argv)
    racine = Path(args.racine)
    sortie = Path(args.sortie) / racine.name
    sortie.mkdir(parents=True, exist_ok=True)
    depots = [d for d in sorted(racine.iterdir()) if (d / ".git").exists()]
    if args.seulement:
        depots = [d for d in depots if d.name in set(args.seulement)]
    if args.limite:
        depots = depots[:args.limite]
    index = []
    for depot in depots:
        cible = sortie / depot.name
        if args.reset:
            shutil.rmtree(cible, ignore_errors=True)
        rapport = cible / "report.md"
        if rapport.exists() and not _partiel(rapport.read_text(encoding="utf-8")):
            index.append({"repo": depot.name, "statut": "deja", "rapport": str(rapport)})
            print(f"SKIP  {depot.name}")
            continue
        try:
            snapshot = RepoSnapshot.depuis_git(depot.name, depot)
            outils_sem, schemas_sem = ({}, {})
            if args.graphify or args.graphify_construire:
                outils_sem, schemas_sem = _semantique_graphify(
                    depot, args.graphify_construire)
                if outils_sem:
                    print(f"GRAPH {depot.name}  {depot / 'graphify-out' / 'graph.json'}")
            fichiers = snapshot.fichiers()
            prefixe = str(args.prefixe or "").strip("/")
            if prefixe:
                fichiers = [fichier for fichier in fichiers
                            if fichier == prefixe or fichier.startswith(prefixe + "/")]
                if not fichiers:
                    print(f"PREFIXE {depot.name} {prefixe} : aucun fichier")
                    continue
                if args.decouper and len(fichiers) > args.max_fichiers:
                    groupes = _groupes(fichiers, args.max_fichiers, args.max_groupes,
                                       args.max_parties)
                    groupes = [(p, liste) for p, liste in groupes
                               if p == prefixe or p.startswith(prefixe + "/")]
                    if not groupes:
                        groupes = [(prefixe, fichiers)]
                else:
                    groupes = [(prefixe, fichiers)]
            else:
                groupes = (_groupes(fichiers, args.max_fichiers, args.max_groupes,
                                    args.max_parties)
                           if args.decouper and len(fichiers) > args.max_fichiers
                           else [("", fichiers)])
            resultats = []
            for prefixe, _ in groupes:
                resultats.append(_mission(snapshot, cible, prefixe, args.max_steps,
                                          outils_sem, schemas_sem))
            resultats.sort(key=lambda r: _priorite_partie(r["prefixe"]))
            parties = [r for r in resultats if r["statut"] in ("ok", "deja", "partiel")]
            textes = []
            for partie in parties:
                contenu = Path(partie["rapport"]).read_text(encoding="utf-8")
                textes.append(f"## Sous-système `{partie['prefixe'] or 'racine'}`\n\n{contenu}")
            cible.mkdir(parents=True, exist_ok=True)
            texte = "\n\n".join(textes) if textes else "Aucune partie terminée."
            normalisations = sum(int(r.get("normalisations", 0)) for r in resultats)
            if normalisations:
                texte = (f"> Note : {normalisations} route(s) locale(s) ont été préfixées "
                         "automatiquement avec le préfixe du blueprint.\n\n" + texte)
            rapport.write_text(texte, encoding="utf-8")
            partiels = [r for r in resultats if r["statut"] in ("partiel", "echec")]
            statut = "echec" if not parties else ("partiel" if partiels else "ok")
            index.append({"repo": depot.name, "statut": statut,
                          "rapport": str(rapport), "sha": snapshot.sha,
                          "parties": resultats, "caracteres": len(texte),
                          "normalisations": normalisations, "resume": texte[:400]})
            print(f"{statut.upper():7} {depot.name}  {len(parties)}/{len(groupes)} parties, "
                  f"{len(partiels)} partielles  ({len(texte)} caractères)")
        except Exception as erreur:
            index.append({"repo": depot.name, "statut": "echec", "erreur": str(erreur)[:500]})
            print(f"ECHEC {depot.name}: {str(erreur)[:200]}")
    chemin_index = sortie / "index.json"
    if args.seulement and chemin_index.exists():
        try:
            ancien = json.loads(chemin_index.read_text(encoding="utf-8"))
            par_repo = {e["repo"]: e for e in ancien.get("repos", [])}
            for entree in index:
                par_repo[entree["repo"]] = entree
            index = [par_repo[n] for n in sorted(par_repo)]
        except (OSError, json.JSONDecodeError, KeyError):
            pass
    chemin_index.write_text(json.dumps({"racine": str(racine), "repos": index},
                                       ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
