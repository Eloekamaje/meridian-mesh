"""API GitHub pour l'atelier de commande : compte du jeton, dépôts lisibles, branches d'un dépôt.

Le jeton est lu dans Vault depuis la référence de la source ; il ne quitte jamais le serveur. Seule la forge
autorisée (JUMEAU_GIT_HOTE) est interrogée, sans suivre de redirection (l'en-tête d'autorisation suivrait).
"""
import base64
import binascii
import hashlib
import json
import threading
import time
import urllib.error
from collections import deque
import urllib.request
from urllib.parse import quote, urlencode

from meridian.adapters.outbound.connectors.naissance import (
    NOM_VALIDE, _hote_autorise, resoudre_secret,
)

# ponytail: 300 dépôts les plus récemment mis à jour ; recherche GitHub si un compte en voit plus.
MAX_PAGES = 3
# Quota GitHub (5000 requêtes/h par jeton) : réponses gardées une minute, appels limités par jeton.
# ponytail: mémoire du processus ; un cache partagé (Redis) si le serveur tourne en plusieurs processus.
CACHE_SECONDES = 60
MAX_CACHE = 500
MAX_APPELS_MINUTE = 30
MAX_RESULTATS = 20
DELAI = 10


class Invalide(ValueError):
    """Demande mal formée ; son message peut être montré à l'utilisateur."""


class TropDeDemandes(Exception):
    """Limite d'appels à GitHub atteinte pour ce jeton."""


class JetonRefuse(Exception):
    """GitHub refuse le jeton (expiré, révoqué ou sans droit de lecture)."""


class _SansRedirection(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_ouvrir = urllib.request.build_opener(_SansRedirection).open


_cache, _appels, _verrou = {}, {}, threading.Lock()


def _limiter(jeton, service="GitHub"):
    """Au plus MAX_APPELS_MINUTE appels à GitHub (ou autre `service`) par jeton sur une minute glissante."""
    cle, maintenant = hashlib.sha256(jeton.encode()).hexdigest(), time.monotonic()
    with _verrou:
        file = _appels.setdefault(cle, deque())
        while file and file[0] < maintenant - 60:
            file.popleft()
        if len(file) >= MAX_APPELS_MINUTE:
            raise TropDeDemandes(f"trop de demandes à {service} : réessayez dans une minute")
        file.append(maintenant)


def _memo(reference, cle, calcul):
    """Réponse gardée CACHE_SECONDES par référence de jeton (jamais le jeton lui-même comme clé)."""
    maintenant = time.monotonic()
    with _verrou:
        trouve = _cache.get((reference, cle))
        if trouve and trouve[0] > maintenant:
            return trouve[1]
    valeur = calcul()
    with _verrou:
        if len(_cache) >= MAX_CACHE:
            _cache.clear()
        _cache[(reference, cle)] = (maintenant + CACHE_SECONDES, valeur)
    return valeur


def oublier(reference):
    """Un nouveau jeton remplace l'ancien sous la même référence : ses réponses gardées ne valent plus."""
    with _verrou:
        for cle in [c for c in _cache if c[0] == reference]:
            del _cache[cle]


def _base():
    hote = _hote_autorise()
    return "https://api.github.com" if hote == "github.com" else f"https://{hote}/api/v3"


def _get(reference, chemin, **params):
    return _get_avec(resoudre_secret(reference), chemin, **params)


def _get_avec(jeton, chemin, **params):
    if not jeton:
        raise Invalide("aucun jeton : l'autocomplétion des dépôts demande un jeton d'accès")
    if not jeton.isascii() or not jeton.isprintable() or " " in jeton:
        raise Invalide("jeton mal formé")
    _limiter(jeton)
    url = f"{_base()}{chemin}" + (f"?{urlencode(params)}" if params else "")
    requete = urllib.request.Request(url, headers={"Authorization": f"Bearer {jeton}",
                                                   "Accept": "application/vnd.github+json"})
    try:
        with _ouvrir(requete, timeout=DELAI) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code in (403, 429) and e.headers and e.headers.get("X-RateLimit-Remaining") == "0":
            attente = max(int(e.headers.get("X-RateLimit-Reset", "0")) - int(time.time()), 60)
            raise TropDeDemandes(f"quota GitHub épuisé pour ce compte : réessayez dans {-(-attente // 60)} min") from e
        if e.code in (401, 403):
            raise JetonRefuse("GitHub refuse ce jeton") from e
        if e.code == 404:
            raise Invalide("ressource GitHub introuvable") from e
        raise


def compte(reference):
    """Le compte que ce jeton ouvre."""
    return _memo(reference, "compte", lambda: compte_du_jeton(resoudre_secret(reference)))


def compte_du_jeton(jeton):
    """Vérifie un jeton auprès de GitHub avant de le conserver (un jeton refusé n'écrase rien)."""
    u = _get_avec(jeton, "/user")
    return {"login": u["login"], "nom": u.get("name") or u["login"], "avatar": u.get("avatar_url")}


def _tous_les_depots(reference):
    tous = []
    for page in range(1, MAX_PAGES + 1):
        lot = _get(reference, "/user/repos", per_page=100, page=page, sort="updated",
                   affiliation="owner,collaborator,organization_member")
        tous += [{"nom": d["full_name"], "prive": d["private"], "defaut": d["default_branch"], "maj": d["pushed_at"],
                  "description": (d.get("description") or "")[:140], "langage": d.get("language")} for d in lot]
        if len(lot) < 100:
            break
    return tous


def depots(reference, recherche=""):
    """Dépôts lisibles avec ce jeton, les plus récemment mis à jour d'abord, filtrés par `recherche` (la liste est
    lue une fois puis filtrée ici : la frappe ne rappelle pas GitHub)."""
    motif = recherche.strip().lower()
    return [d for d in _memo(reference, "depots", lambda: _tous_les_depots(reference))
            if motif in d["nom"].lower()][:MAX_RESULTATS]


def branches(reference, depot, recherche=""):
    """Branches d'un dépôt `propriétaire/nom`, filtrées par `recherche`."""
    proprietaire, _, nom = depot.partition("/")
    if not NOM_VALIDE.fullmatch(proprietaire or "") or not NOM_VALIDE.fullmatch(nom or ""):
        raise Invalide("dépôt attendu sous la forme propriétaire/nom")
    noms = _memo(reference, ("branches", depot), lambda: [
        b["name"] for b in _get(reference, f"/repos/{quote(proprietaire)}/{quote(nom)}/branches", per_page=100)])
    motif = recherche.strip().lower()
    return [b for b in noms if motif in b.lower()][:MAX_RESULTATS]


def lire_fichier(reference, depot, chemin, ref="", max_octets: int = 2_000_000):
    """Lit un fichier texte d'un dépôt GitHub, à une référence donnée, sans clone.

    Le contenu est borné, décodé depuis base64 et jamais écrit sur disque. Le chemin
    refuse les traversées (`..`) ; un fichier binaire ou trop gros est refusé.
    """
    proprietaire, _, nom = str(depot or "").partition("/")
    if not NOM_VALIDE.fullmatch(proprietaire or "") or not NOM_VALIDE.fullmatch(nom or ""):
        raise Invalide("dépôt attendu sous la forme propriétaire/nom")
    chemin = str(chemin or "").strip()
    if (not chemin or chemin.startswith(("/", "-"))
            or any(partie in ("", ".", "..") for partie in chemin.split("/"))
            or any(ord(caractere) < 32 for caractere in chemin)):
        raise Invalide("chemin de fichier invalide")
    params = {"ref": ref} if ref else {}
    donnees = _get(
        reference,
        f"/repos/{quote(proprietaire)}/{quote(nom)}/contents/{quote(chemin, safe='/')}",
        **params)
    if (not isinstance(donnees, dict) or donnees.get("type") != "file"
            or donnees.get("encoding") != "base64"):
        raise Invalide("fichier GitHub illisible")
    try:
        contenu = base64.b64decode(donnees.get("content") or "", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise Invalide("contenu GitHub invalide") from exc
    if len(contenu) > max_octets:
        raise Invalide("fichier GitHub trop volumineux")
    try:
        return contenu.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Invalide("fichier GitHub non textuel") from exc
