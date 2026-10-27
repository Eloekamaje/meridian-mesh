"""API GitHub pour l'atelier de commande : compte du jeton, dépôts lisibles, branches d'un dépôt.

Le jeton est lu dans Vault depuis la référence de la source ; il ne quitte jamais le serveur. Seule la forge
autorisée (JUMEAU_GIT_HOTE) est interrogée, sans suivre de redirection (l'en-tête d'autorisation suivrait).
"""
import json
import urllib.error
import urllib.request
from urllib.parse import quote, urlencode

from jumeau.naissance import NOM_VALIDE, _hote_autorise, resoudre_secret

MAX_PAGES = 3  # ponytail: 300 dépôts les plus récemment mis à jour ; recherche GitHub si un compte en voit plus
MAX_RESULTATS = 20
DELAI = 10


class JetonRefuse(Exception):
    """GitHub refuse le jeton (expiré, révoqué ou sans droit de lecture)."""


class _SansRedirection(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_ouvrir = urllib.request.build_opener(_SansRedirection).open


def _base():
    hote = _hote_autorise()
    return "https://api.github.com" if hote == "github.com" else f"https://{hote}/api/v3"


def _get(reference, chemin, **params):
    jeton = resoudre_secret(reference)
    if not jeton:
        raise RuntimeError("aucun jeton : l'autocomplétion des dépôts demande un jeton d'accès")
    url = f"{_base()}{chemin}" + (f"?{urlencode(params)}" if params else "")
    requete = urllib.request.Request(url, headers={"Authorization": f"Bearer {jeton}",
                                                   "Accept": "application/vnd.github+json"})
    try:
        with _ouvrir(requete, timeout=DELAI) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise JetonRefuse("GitHub refuse ce jeton") from e
        raise


def compte(reference):
    """Le compte que ce jeton ouvre."""
    return {"login": _get(reference, "/user")["login"]}


def depots(reference, recherche=""):
    """Dépôts lisibles avec ce jeton, les plus récemment mis à jour d'abord, filtrés par `recherche`."""
    trouves, motif = [], recherche.strip().lower()
    for page in range(1, MAX_PAGES + 1):
        lot = _get(reference, "/user/repos", per_page=100, page=page, sort="updated",
                   affiliation="owner,collaborator,organization_member")
        trouves += [{"nom": d["full_name"], "prive": d["private"], "defaut": d["default_branch"],
                     "maj": d["pushed_at"]} for d in lot if motif in d["full_name"].lower()]
        if len(lot) < 100 or len(trouves) >= MAX_RESULTATS:
            break
    return trouves[:MAX_RESULTATS]


def branches(reference, depot, recherche=""):
    """Branches d'un dépôt `propriétaire/nom`, filtrées par `recherche`."""
    proprietaire, _, nom = depot.partition("/")
    if not NOM_VALIDE.fullmatch(proprietaire or "") or not NOM_VALIDE.fullmatch(nom or ""):
        raise ValueError("dépôt attendu sous la forme propriétaire/nom")
    lot = _get(reference, f"/repos/{quote(proprietaire)}/{quote(nom)}/branches", per_page=100)
    motif = recherche.strip().lower()
    return [b["name"] for b in lot if motif in b["name"].lower()][:MAX_RESULTATS]
