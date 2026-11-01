"""Pilotage local de codebase-memory-mcp (binaire compilé depuis les sources, sans LLM ni réseau)."""
import json
import logging
import re
import threading
import uuid
import os
import subprocess

REQUETES = {
    "routes": "MATCH (f)-[:HANDLES]->(r:Route) "
              "RETURN f.file_path AS chemin, f.start_line AS debut, f.end_line AS fin, r.method AS methode, r.name AS route",
    "paquets": "MATCH (a)-[:DEPENDS_ON]->(p:Package) RETURN DISTINCT a.file_path AS chemin, p.name AS paquet",
    "variables": "MATCH (a)-[:CONFIGURES]->(e:EnvVar) RETURN DISTINCT a.file_path AS chemin, e.name AS variable, "
                 "e.start_line AS ligne",
    "images": "MATCH (s)-[:USAGE]->(i:Image) RETURN DISTINCT s.file_path AS chemin, i.name AS image",
}
PLAFOND_DEFAUT, PLAFOND_MIN, PLAFOND_MAX = 10000, 100, 200000
journal = logging.getLogger(__name__)


def plafond():
    """Lignes gardées par famille (JUMEAU_PLAFOND), bornées ; valeur illisible : défaut."""
    try:
        return min(PLAFOND_MAX, max(PLAFOND_MIN, int(os.environ.get("JUMEAU_PLAFOND", PLAFOND_DEFAUT))))
    except ValueError:
        return PLAFOND_DEFAUT


def _cle(ligne):
    """Ordre stable : fichier, puis ligne, puis le reste ; deux passes au même commit gardent les mêmes lignes."""
    return (ligne.get("chemin") or "", ligne.get("debut") or ligne.get("ligne") or 0, json.dumps(ligne, sort_keys=True, default=str))


PREFIXE = "jum-"  # les index au format ancien (chemin absolu aplati) n'ont pas ce préfixe
LONGUEUR_SHA = 12


def nom_index(jumeau_id, depot, sha):
    """Nom de l'index : dérivé de (jumeau, dépôt, commit), identique sur toute machine, sans chemin absolu."""
    def sur(x):
        return re.sub(r"[^a-z0-9]+", "-", str(x).lower()).strip("-") or "x"
    return f"{PREFIXE}{sur(jumeau_id)}-{sur(depot)}-{sha[:LONGUEUR_SHA]}"


def perime(source):
    """Index d'un autre commit que celui ingéré ? Un index au format ancien (sans commit) n'est pas dit périmé :
    il reste lisible jusqu'à sa réindexation."""
    nom, sha = source.get("index_code") or "", source.get("curseur") or ""
    return nom.startswith(PREFIXE) and not nom.endswith("-" + sha[:LONGUEUR_SHA])


def _env():
    """Environnement du binaire. JUMEAU_CBM_CACHE range les bases ailleurs que dans le cache par défaut."""
    cache = os.environ.get("JUMEAU_CBM_CACHE")
    return {**os.environ, "CBM_CACHE_DIR": cache} if cache else None


CONFLIT_CACHE = "different cache directory"
MESSAGE_CONFLIT = "cache de l'index en conflit avec le démon déjà lancé"
_cause = None


def cause_panne():
    """Cause mémorisée au démarrage (None : rien d'anormal connu)."""
    return _cause


def verifier_cache():
    """Au démarrage : une action légère du CLI révèle si JUMEAU_CBM_CACHE diffère du cache du démon déjà lancé
    (unique par compte), cas où toute indexation échoue. Journalise l'erreur et son remède, mémorise la cause.
    Sans binaire, ou pour toute autre panne : ne fait rien. Ne lève jamais. Vrai si rien n'est en conflit."""
    global _cause
    binaire = os.environ.get("CBM_BIN", "codebase-memory-mcp")
    try:
        r = subprocess.run([binaire, "cli", "--quiet", "list_projects"], capture_output=True, text=True, timeout=30,
                           env=_env())
    except (OSError, subprocess.SubprocessError):
        return True
    detail = f"{r.stderr}\n{r.stdout}"
    if r.returncode != 0 and CONFLIT_CACHE in detail:
        _cause = MESSAGE_CONFLIT
        journal.error("%s : toute indexation échouera. Remède : ne pas définir JUMEAU_CBM_CACHE en développement, "
                      "ou arrêter le démon (`codebase-memory-mcp daemon stop`). Détail : %s", MESSAGE_CONFLIT,
                      detail.strip()[:200])
        return False
    _cause = None
    return True


def _echec(args, detail):
    return RuntimeError(f"codebase-memory-mcp {args[0]} : {_cause or detail}")


def _cli(*args):
    binaire = os.environ.get("CBM_BIN", "codebase-memory-mcp")
    r = subprocess.run([binaire, "cli", "--quiet", *args], capture_output=True, text=True, timeout=600, env=_env())
    if r.returncode != 0:
        raise _echec(args, r.stderr.strip() or r.stdout.strip())
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
            c = MCPClient(lambda: stdio_client(StdioServerParameters(command=binaire, args=[], env=_env())))
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
        raise RuntimeError(_cause or f"codebase-memory-mcp indisponible ({outil})")
    texte = "".join(b.get("text", "") for b in r["content"])
    if r["status"] != "success" or texte.lstrip().lower().startswith("error"):
        raise RuntimeError(texte[:300])
    return texte


def texte(outil, *args):
    """Sortie texte (format arborescent compact) d'un outil cbm, pour un LLM."""
    binaire = os.environ.get("CBM_BIN", "codebase-memory-mcp")
    r = subprocess.run([binaire, "cli", "--quiet", outil, *args], capture_output=True, text=True, timeout=60,
                       env=_env())
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or r.stdout.strip())
    return r.stdout


def indexe(source, appeler=None):
    """L'index de cette source répond-il pour CE commit ? Absent ou périmé : faux, l'ingestion (ou
    `python -m meridian.adapters.outbound.connectors.reindexer`) le reconstruit depuis la copie au SHA (plan de remédiation L0bis.3 et L0bis.4)."""
    projet = source.get("index_code")
    if not projet or perime(source):
        return False
    sonde = appeler or appeler_outil
    try:
        sonde("search_graph", project=projet, name_pattern="__meridian_sonde_absente__", limit=1, format="json")
        return True
    except Exception:
        return False


def appeler_outil(outil, **arguments):
    """Alias explicite de `appeler` (une sonde peut être injectée dans les tests)."""
    return appeler(outil, **arguments)


def retirer_ancien(ancien, actuel):
    """Après qu'un nouvel index a été enregistré : supprime l'index précédent de la même source, pour que chaque
    commit n'en laisse pas un de plus dans le cache. Seuls nos index (préfixe jum-) sont touchés ; un échec est
    journalisé, jamais fatal (l'ancien index ne sert plus, il prend seulement de la place)."""
    if not ancien or ancien == actuel or not ancien.startswith(PREFIXE):
        return False
    try:
        r = subprocess.run([os.environ.get("CBM_BIN", "codebase-memory-mcp"), "cli", "--quiet", "delete_project",
                            json.dumps({"project": ancien})], capture_output=True, text=True, timeout=120, env=_env())
    except (OSError, subprocess.TimeoutExpired):
        journal.warning("index %s non supprimé (binaire injoignable)", ancien, exc_info=True)
        return False
    if r.returncode != 0:
        journal.warning("index %s non supprimé : %s", ancien, (r.stderr or r.stdout).strip()[:200])
    return r.returncode == 0


def indexer(depot, nom):
    return _cli("index_repository", "--repo-path", str(depot), "--name", nom)["project"]


def interroger(projet):
    """(résultats par famille, troncature) : au-delà du plafond on garde le début de l'ordre stable et on le dit
    (`troncature` = {famille: {gardes, trouves}}) ; l'ingestion ne tombe pas."""
    resultats, troncature, limite = {}, {}, plafond()
    for famille, requete in REQUETES.items():
        r = _cli("query_graph", "--project", projet, "--query", f"{requete} LIMIT {PLAFOND_MAX}", "--format", "json")
        lignes = sorted((dict(zip(r["columns"], ligne)) for ligne in r["rows"]), key=_cle)
        coupe = bool(r.get("has_more") or r.get("truncated"))  # ponytail: au-delà de PLAFOND_MAX le binaire choisit les lignes
        if coupe or len(lignes) > limite:
            troncature[famille] = {"gardes": min(limite, len(lignes)), "trouves": len(lignes), **({"au_moins": True} if coupe else {})}
            journal.warning("extraction tronquée : %s, %d gardées sur %d%s (plafond JUMEAU_PLAFOND=%d)", famille,
                            troncature[famille]["gardes"], len(lignes), "+" if coupe else "", limite)
        resultats[famille] = lignes[:limite]
    return resultats, troncature
