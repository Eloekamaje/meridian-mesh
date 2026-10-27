"""Pilotage local de codebase-memory-mcp (binaire compilé depuis les sources, sans LLM ni réseau)."""
import json
import os
import subprocess

REQUETES = {
    "routes": "MATCH (f)-[:HANDLES]->(r:Route) "
              "RETURN f.file_path AS chemin, f.start_line AS debut, f.end_line AS fin, r.method AS methode, r.name AS route",
    "paquets": "MATCH (a)-[:DEPENDS_ON]->(p:Package) RETURN DISTINCT a.file_path AS chemin, p.name AS paquet",
    "variables": "MATCH (a)-[:CONFIGURES]->(e:EnvVar) RETURN DISTINCT a.file_path AS chemin, e.name AS variable",
    "images": "MATCH (s)-[:USAGE]->(i:Image) RETURN DISTINCT s.file_path AS chemin, i.name AS image",
}
LIMITE = 10000


def _cli(*args):
    binaire = os.environ.get("CBM_BIN", "codebase-memory-mcp")
    r = subprocess.run([binaire, "cli", "--quiet", *args], capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"codebase-memory-mcp {args[0]} : {r.stderr.strip() or r.stdout.strip()}")
    return json.loads(r.stdout)


def indexer(depot):
    return _cli("index_repository", "--repo-path", str(depot))["project"]


def oublier(projet):
    _cli("delete_project", "--project", projet)


def interroger(projet):
    resultats = {}
    for famille, requete in REQUETES.items():
        r = _cli("query_graph", "--project", projet, "--query", f"{requete} LIMIT {LIMITE}", "--format", "json")
        if r.get("has_more") or r.get("truncated"):
            raise RuntimeError(f"{famille} : résultat tronqué, relever LIMITE")
        resultats[famille] = [dict(zip(r["columns"], ligne)) for ligne in r["rows"]]
    return resultats
