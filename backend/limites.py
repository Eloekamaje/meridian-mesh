"""Limites de plateforme : débit des tours Flore et garde-fous de configuration.

Le compteur est partagé quand Redis est actif (plusieurs workers) : un script Lua atomique incrémente la clé et
pose la fenêtre fixe à la création (aucun INCR orphelin sans TTL). Si Redis échoue, la limite est ignorée
(fail-open) et l'erreur est journalisée : une panne du limiteur ne doit pas bloquer les réponses. Sans Redis, un
compteur mémoire protégé par un verrou asyncio suffit (développement, tests, mono-worker). `maxi <= 0` désactive
la limite : les tours Flore ne sont plafonnés par défaut qu'en production.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time

from jumeau import partage

MAX_TOURS_PRODUCTION = 30
FENETRE_TOURS_DEFAUT = 60

TOURS_RATE_MAX = "TOURS_RATE_MAX"
TOURS_RATE_FENETRE = "TOURS_RATE_FENETRE"

SCRIPT_TOURS = """
local compte = redis.call('INCR', KEYS[1])
if compte == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return compte
"""

journal = logging.getLogger("meridian.limites")


def maximum(env: str, defaut: int) -> int:
    """Lit un entier dans l'environnement ; une valeur absente ou illisible garde le défaut."""
    brut = os.getenv(env)
    if brut is None or not str(brut).strip():
        return defaut
    try:
        return int(str(brut).strip())
    except ValueError:
        return defaut


def _production() -> bool:
    return os.getenv("APP_ENV", "").strip().lower() in {"prod", "production"}


def maxi_tours() -> int:
    """Plafond des tours Flore : valeurs par défaut en production, désactivé ailleurs sauf réglage explicite."""
    return maximum(TOURS_RATE_MAX, MAX_TOURS_PRODUCTION if _production() else 0)


def fenetre_tours() -> int:
    return maximum(TOURS_RATE_FENETRE, FENETRE_TOURS_DEFAUT)


def verifier_cors(origines, app_env=None):
    """Refuse le joker CORS en production : les origines autorisées doivent y être explicites.

    L'authentification de Méridian passe par des en-têtes (pas de cookie), donc `allow_credentials=False` ;
    le joker reste acceptable en développement, jamais en production.
    """
    propres = [str(o).strip() for o in (origines.split(",") if isinstance(origines, str) else origines)
               if str(o).strip()]
    env = (os.getenv("APP_ENV", "") if app_env is None else app_env).strip().lower()
    if env in {"prod", "production"} and "*" in propres:
        raise RuntimeError(
            "CORS_ORIGINS ne peut pas contenir « * » en production (APP_ENV=production) : "
            "indiquez explicitement les origines autorisées"
        )
    return propres


_compteurs = {}
_verrou = None
_boucle = None


def _verrou_courant():
    """Un verrou par boucle d'événements : les tests appellent `asyncio.run` plusieurs fois."""
    global _verrou, _boucle
    boucle = asyncio.get_running_loop()
    if _verrou is None or _boucle is not boucle:
        _verrou, _boucle = asyncio.Lock(), boucle
    return _verrou


def reinitialiser() -> None:
    """Vide les compteurs mémoire (tests, remise à zéro de la démo)."""
    _compteurs.clear()


async def autoriser(cle: str, maxi: int, fenetre: int) -> bool:
    """Un jeton de plus pour `cle` dans la fenêtre fixe de `fenetre` secondes ; faux au-delà de `maxi`."""
    if maxi <= 0:
        return True
    fenetre = max(1, int(fenetre))
    if partage.actif():
        cle_redis = f"{partage.prefixe()}limites:{cle}"
        try:
            client = await partage.client()
            compte = await client.eval(SCRIPT_TOURS, 1, cle_redis, fenetre)
        except Exception:  # Redis indisponible : ne pas bloquer les réponses (fail-open, documenté)
            journal.warning("limiteur Redis indisponible : limite ignorée pour %s", cle, exc_info=True)
            return True
        return int(compte) <= maxi
    maintenant = time.monotonic()
    async with _verrou_courant():
        compte, expiration = _compteurs.get(cle, (0, 0.0))
        if maintenant >= expiration:
            compte, expiration = 0, maintenant + fenetre
        compte += 1
        _compteurs[cle] = (compte, expiration)
        autorise = compte <= maxi
    return autorise
