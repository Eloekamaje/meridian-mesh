#!/usr/bin/env python3
"""Série d'exploration via le harness : fichiers, stacks et indices de routes, sans sidecar."""
from __future__ import annotations

import json
import shutil
import sys
from collections import Counter
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "backend"))

from meridian.application.exploration_agent import ExplorationHarness, RepoSnapshot  # noqa: E402

MANIFESTES = {"pyproject.toml", "requirements.txt", "package.json", "pom.xml", "build.gradle",
              "go.mod", "Cargo.toml", "composer.json"}
MOTS_FRAMEWORKS = {
    "fastapi": ("fastapi",), "django": ("django",), "flask": ("flask",),
    "spring": ("spring-boot", "springframework"), "express": ("express",),
    "nestjs": ("@nestjs/",), "gin": ("gin-gonic",), "react": ("react",),
    "next": ("next",), "vue": ("vue",),
}
SONDES = {
    "python": (r"@(?:api_router|router|app)\.(?:get|post|put|patch|delete|head|options)\(",),
    "java": (r"@(?:Get|Post|Put|Patch|Delete)Mapping\b",),
    "javascript": (r"(?:app|router)\.(?:get|post|put|patch|delete)\(",),
    "go": (r"(?:r|router)\.(?:GET|POST|PUT|PATCH|DELETE)\(",),
}


def _langages(fichiers):
    return dict(Counter(Path(c).suffix.lower() or "(sans)" for c in fichiers).most_common(12))


def _manifestes(fichiers):
    return [c for c in fichiers if c.rsplit("/", 1)[-1] in MANIFESTES]


def _stacks(h, alias, fichiers):
    manifests = _manifestes(fichiers)[:20]
    textes = []
    for chemin in manifests:
        resultat = h.executer("read_file", {"repo": alias, "path": chemin, "start": 1, "end": 500})
        if resultat.get("ok") and isinstance(resultat.get("data"), dict):
            textes.append(str(resultat["data"].get("lines", "")))
    corpus = "\n".join(textes).lower()
    return manifests, sorted({nom for nom, motifs in MOTS_FRAMEWORKS.items()
                              if any(motif in corpus for motif in motifs)})


def _sonder_routes(h, alias, familles):
    total, tronque = {}, False
    for famille, motifs in SONDES.items():
        if famille not in familles:
            continue
        compte = 0
        for motif in motifs:
            resultat = h.executer("count_matches", {"repo": alias, "text": motif, "regex": True})
            if resultat.get("ok") and isinstance(resultat.get("data"), dict):
                compte += int(resultat["data"].get("total", 0))
            else:
                tronque = True
        total[famille] = compte
    return {"par_famille": total, "indices": sum(total.values()), "limite_atteinte": tronque}


def analyser(depot: Path) -> dict:
    snapshot = RepoSnapshot.depuis_git(depot.name, depot)
    etat = Path("/tmp/serie-exploration-harness") / depot.name
    shutil.rmtree(etat, ignore_errors=True)
    h = ExplorationHarness([snapshot], etat)
    fichiers = snapshot.fichiers()
    manifests, frameworks = _stacks(h, snapshot.alias, fichiers)
    extensions = _langages(fichiers)
    familles = set()
    if ".py" in extensions:
        familles.add("python")
    if ".java" in extensions:
        familles.add("java")
    if {".js", ".jsx", ".ts", ".tsx"} & set(extensions):
        familles.add("javascript")
    if ".go" in extensions:
        familles.add("go")
    return {
        "repo": depot.name, "sha": snapshot.sha, "branche": snapshot.branch,
        "fichiers": len(fichiers), "langages": extensions,
        "manifests": manifests, "frameworks": frameworks,
        "routes": _sonder_routes(h, snapshot.alias, familles),
        "couverture_routes": "non_evaluee" if familles else "non_supporte",
    }


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("racine", nargs="?", default="/home/majella/ProjetsPerso")
    p.add_argument("--sortie", default="/tmp/serie-exploration.json")
    args = p.parse_args(argv)
    racine = Path(args.racine)
    rapports = []
    for depot in sorted(racine.iterdir()):
        if not (depot / ".git").exists():
            continue
        try:
            rapports.append(analyser(depot))
        except Exception as erreur:
            rapports.append({"repo": depot.name, "erreur": str(erreur)[:500]})
    Path(args.sortie).write_text(json.dumps({"racine": str(racine), "repos": rapports},
                                            ensure_ascii=False, indent=2), encoding="utf-8")
    for r in rapports:
        if "erreur" in r:
            print(f"ERREUR  {r['repo']}: {r['erreur']}")
        else:
            print(f"{r['repo']:<40} {r['fichiers']:>6} fichiers  "
                  f"{r['routes']['indices']:>4} indices routes  "
                  f"{', '.join(r['frameworks']) or '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
