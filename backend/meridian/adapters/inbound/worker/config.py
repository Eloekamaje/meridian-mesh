"""Configuration commune des workers : DSN dédié, tenants explicites, option de session.

Les workers multi-tenant ne doivent pas réutiliser le DSN de l'API. Un rôle dédié
``meridian_worker`` peut être ``BYPASSRLS`` pour balayer tous les tenants, ou rester
``NOBYPASSRLS`` avec une liste de tenants et un contexte posé par passe. Ce module ne
lit que l'environnement ; il ne se connecte jamais.
"""
from __future__ import annotations

import os

from psycopg.conninfo import conninfo_to_dict, make_conninfo

from jumeau.tenant import normaliser_slug

__all__ = [
    "DSN_ENV",
    "DSN_WORKER_ENV",
    "TENANTS_ENV",
    "TENANT_ENV",
    "dsn_avec_tenant",
    "dsn_worker",
    "normaliser_tenants",
    "option_connexion_tenant",
    "tenants_worker",
]

# DSN des workers : prioritaire sur le DSN applicatif, qui reste le repli.
DSN_WORKER_ENV = "JUMEAU_WORKER_PG_DSN"
DSN_ENV = "JUMEAU_PG_DSN"
# Liste explicite des tenants pour une passe par tenant (séparateur : virgule).
TENANTS_ENV = "JUMEAU_WORKER_TENANTS"
# Repli singulier pour les workers qui ne traitent qu'un tenant par processus.
TENANT_ENV = "JUMEAU_WORKER_TENANT"


def dsn_worker(env=None) -> str | None:
    """DSN des workers : ``JUMEAU_WORKER_PG_DSN`` puis ``JUMEAU_PG_DSN``.

    Une valeur vide ou composée d'espaces est ignorée, comme une variable absente.
    """
    source = os.environ if env is None else env
    for nom in (DSN_WORKER_ENV, DSN_ENV):
        valeur = str(source.get(nom) or "").strip()
        if valeur:
            return valeur
    return None


def normaliser_tenants(valeurs) -> tuple[str, ...]:
    """Valide une liste de tenants et la déduplique en conservant l'ordre.

    Accepte une chaîne séparée par des virgules ou un itérable. Chaque tenant passe
    par :func:`normaliser_slug` : aucun nom arbitraire n'atteint `set_config` ou les
    options de connexion.
    """
    if valeurs is None:
        return ()
    if isinstance(valeurs, str):
        valeurs = valeurs.split(",")
    resultat: list[str] = []
    for valeur in valeurs:
        texte = str(valeur or "").strip()
        if not texte:
            continue
        normalise = normaliser_slug(texte)
        if normalise not in resultat:
            resultat.append(normalise)
    return tuple(resultat)


def tenants_worker(env=None) -> tuple[str, ...]:
    """Tenants déclarés pour ce worker.

    ``JUMEAU_WORKER_TENANTS`` (liste) est prioritaire ; ``JUMEAU_WORKER_TENANT``
    (valeur unique) sert de repli pour un déploiement un-tenant-par-processus.
    """
    source = os.environ if env is None else env
    brut = source.get(TENANTS_ENV)
    if brut is None or not str(brut).strip():
        brut = source.get(TENANT_ENV)
    return normaliser_tenants(brut)


def option_connexion_tenant(tenant) -> str | None:
    """Option libpq qui fixe le tenant au niveau de la session.

    Utile aux workers qui ne peuvent pas envelopper chaque transaction dans
    :func:`jumeau.rls.contexte_tenant` (outbox, exécution) : chaque connexion ne voit
    alors qu'un seul tenant. Le slug est validé avant interpolation.
    """
    if tenant is None:
        return None
    identifiant = normaliser_slug(tenant)
    return f"-c meridian.tenant_id={identifiant}"


def dsn_avec_tenant(dsn: str, tenant) -> str:
    """DSN équivalent dont chaque nouvelle connexion porte le tenant de session.

    Les helpers historiques (rédaction, exécuteur cognitif) ouvrent leurs propres
    connexions depuis ``JUMEAU_PG_DSN`` : le worker leur transmet un DSN déjà scopé
    pour qu'un rôle ``NOBYPASSRLS`` ne perde pas le tenant.
    """
    option = option_connexion_tenant(tenant)
    if not option:
        return dsn
    parametres = conninfo_to_dict(dsn)
    existantes = str(parametres.get("options") or "").strip()
    parametres["options"] = f"{existantes} {option}".strip() if existantes else option
    return make_conninfo(**parametres)
