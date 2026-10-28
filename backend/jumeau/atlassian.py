"""Ce que partagent Confluence et Jira Cloud : identifiants e-mail:jeton, appel HTTPS borné, identité du compte."""
import base64
import json
import urllib.error
import urllib.request
from urllib.parse import urlencode

from jumeau.github import DELAI, Invalide, JetonRefuse, TropDeDemandes, _limiter

MAX_REPONSE = 5_000_000  # octets : une réponse démesurée ne sature pas la mémoire


def identifiants(email, jeton):
    email, jeton = email.strip(), jeton.strip()
    if ":" in email or "@" not in email:
        raise Invalide("adresse e-mail attendue")
    return f"{email}:{jeton}"


def appeler(ouvrir, service, hote, secret, chemin, params):
    """GET JSON sur l'hôte autorisé, avec « e-mail:jeton » ; erreurs typées, jamais le jeton dans un message."""
    if not secret:
        raise Invalide(f"aucun jeton : {service} demande une adresse e-mail et un jeton d'API")
    email, deux_points, jeton = secret.partition(":")
    if not (deux_points and email and jeton) or not secret.isascii() or not secret.isprintable() or " " in secret:
        raise Invalide("identifiants mal formés")
    _limiter(secret, service)
    url = f"https://{hote()}{chemin}" + (f"?{urlencode(params)}" if params else "")
    requete = urllib.request.Request(url, headers={
        "Authorization": "Basic " + base64.b64encode(secret.encode()).decode(), "Accept": "application/json"})
    try:
        with ouvrir(requete, timeout=DELAI) as r:
            corps = r.read(MAX_REPONSE + 1)
        if len(corps) > MAX_REPONSE:
            raise ValueError(f"réponse de {service} trop volumineuse")
        return json.loads(corps)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise TropDeDemandes(f"quota {service} atteint : réessayez dans une minute") from e
        if e.code in (401, 403):
            raise JetonRefuse(f"{service} refuse ces identifiants") from e
        if e.code == 404:
            raise LookupError("introuvable") from e
        raise


def compte(u, secret, cle_email):
    """Identité du jeton chez le service (accountId), jamais l'e-mail saisi : on ne peut pas se déclarer sous le
    nom d'un collègue."""
    declare = secret.partition(":")[0]
    if not u.get("accountId"):
        raise Invalide("le service n'a pas identifié le compte de ces identifiants")
    if u.get(cle_email) and u[cle_email].lower() != declare.lower():
        raise Invalide("l'adresse e-mail saisie n'est pas celle du compte de ce jeton")
    return {"login": declare, "compte": u["accountId"], "nom": u.get("displayName") or declare}
