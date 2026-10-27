"""Pilotage local de codebase-memory-mcp (binaire compilé depuis les sources, sans LLM ni réseau)."""
import json
import threading
import uuid
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


_client = None
_verrou = threading.Lock()


def _mcp():
    """Un serveur MCP codebase-memory-mcp par processus, démarré à la première demande."""
    global _client
    with _verrou:
        if _client is None:
            from mcp import StdioServerParameters, stdio_client
            from strands.tools.mcp import MCPClient
            binaire = os.environ.get("CBM_BIN", "codebase-memory-mcp")
            c = MCPClient(lambda: stdio_client(StdioServerParameters(command=binaire, args=[])))
            c.start()
            _client = c
    return _client


def appeler(outil, **arguments):
    """Appelle une action de codebase-memory-mcp par le protocole MCP ; texte de la réponse."""
    global _client
    try:
        r = _mcp().call_tool_sync(f"meridian-{uuid.uuid4().hex[:8]}", outil, arguments)
    except Exception:
        _client = None  # serveur tombé : redémarré au prochain appel
        raise RuntimeError(f"codebase-memory-mcp indisponible ({outil})")
    texte = "".join(b.get("text", "") for b in r["content"])
    if r["status"] != "success" or texte.lstrip().lower().startswith("error"):
        raise RuntimeError(texte[:300])
    return texte


def texte(outil, *args):
    """Sortie texte (format arborescent compact) d'un outil cbm, pour un LLM."""
    binaire = os.environ.get("CBM_BIN", "codebase-memory-mcp")
    r = subprocess.run([binaire, "cli", "--quiet", outil, *args], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or r.stdout.strip())
    return r.stdout


def indexer(depot):
    return _cli("index_repository", "--repo-path", str(depot))["project"]


def interroger(projet):
    resultats = {}
    for famille, requete in REQUETES.items():
        r = _cli("query_graph", "--project", projet, "--query", f"{requete} LIMIT {LIMITE}", "--format", "json")
        if r.get("has_more") or r.get("truncated"):
            raise RuntimeError(f"{famille} : résultat tronqué, relever LIMITE")
        resultats[famille] = [dict(zip(r["columns"], ligne)) for ligne in r["rows"]]
    return resultats
