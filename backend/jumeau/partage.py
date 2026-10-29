"""Connexion Redis partagée entre workers : bus d'événements et état des tours.

Sans `REDIS_URL`, l'application reste en mémoire (un seul worker, tests, développement).
Avec `REDIS_URL`, Redis devient obligatoire : on ne bascule jamais silencieusement en mémoire
avec plusieurs workers, sinon chaque worker croirait être seul.
"""
import asyncio
import json
import os
import re

from redis import asyncio as redis_asyncio

_clients = {}


def actif():
    return bool(os.getenv("REDIS_URL"))


def prefixe():
    return os.getenv("REDIS_PREFIX", "meridian:")


def canal(persona):
    return f"{prefixe()}evenements:{persona}"


def canal_arret():
    return f"{prefixe()}arret"


def canal_controle():
    return f"{prefixe()}controle"


async def client():
    boucle = asyncio.get_running_loop()
    if boucle not in _clients:
        _clients[boucle] = redis_asyncio.from_url(
            os.environ["REDIS_URL"], decode_responses=True, health_check_interval=30
        )
    return _clients[boucle]


def _url_affichee():
    return re.sub(r"(://[^:/@]+):[^@]+@", r"\1:***@", os.getenv("REDIS_URL", ""))


async def verifier():
    """Au démarrage : un Redis configuré mais injoignable doit échouer, pas diviser les workers."""
    if not actif():
        return
    try:
        await (await client()).ping()
    except Exception as exc:  # noqa: BLE001 - message de démarrage explicite
        raise RuntimeError(f"Redis est configuré mais injoignable ({_url_affichee()}): {exc}") from exc


async def fermer():
    for connexion in list(_clients.values()):
        try:
            await connexion.aclose()
        except Exception:
            pass
    _clients.clear()


async def publier(persona, evenement):
    if not actif():
        return
    await (await client()).publish(canal(persona), json.dumps(evenement, ensure_ascii=False, default=str))


async def publier_arret():
    """Réveille les flux SSE pour qu'ils se ferment avant que uvicorn n'attende leurs connexions."""
    if not actif():
        return
    await (await client()).publish(canal_arret(), "1")


async def abonner(persona):
    """Un abonnement par flux SSE : les événements de la persona et le signal d'arrêt du serveur."""
    pubsub = (await client()).pubsub()
    await pubsub.subscribe(canal(persona), canal_arret())
    return pubsub
