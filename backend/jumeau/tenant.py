"""Contexte tenant et règle d'absence.

Le tenant est la frontière supérieure du Mesh : aucune lecture ni écriture ne
doit se faire hors tenant. Ce module ne consulte ni base ni réseau ; il décide
uniquement, à partir de l'en-tête ``X-Tenant`` et du mode d'authentification,
quel tenant s'applique à la requête.

En mode ``demo`` seulement, l'absence d'en-tête vaut explicitement ``local`` :
c'est un confort de démonstration, jamais un défaut de production. Dès que le
mode n'est plus ``demo`` (ou que ``APP_ENV`` vaut ``production``), le tenant est
obligatoire : aucun repli silencieux n'est effectué.

Une absence n'est jamais une preuve d'inexistence. :func:`absence` produit la
formulation bornée « non observé dans [scope] au [date] », avec les sources et
le cas de résolution éventuel.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
import os
import re
import unicodedata

__all__ = [
    "TenantContext",
    "TenantError",
    "TenantInvalide",
    "TenantRequis",
    "absence",
    "exiger_tenant",
    "normaliser_slug",
    "resoudre_tenant",
]

MODE_DEMO = "demo"
TENANT_DEFAUT_DEMO = "local"
SOURCE_DEFAUT = "defaut"
SOURCE_ENTETE = "entete"
SOURCE_IDENTITE = "identite"

TAILLE_MAX_SLUG = 64
_SLUG = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_ENV_PRODUCTION = frozenset({"prod", "production"})


class TenantError(ValueError):
    """Erreur de contexte tenant, portant le statut HTTP attendu par l'API."""

    status = 400
    status_code = 400


class TenantInvalide(TenantError):
    """Le tenant fourni n'est pas un slug exploitable."""


class TenantRequis(TenantError):
    """Aucun tenant n'est disponible alors qu'il est obligatoire."""

    status = 401
    status_code = 401


@dataclass(frozen=True)
class TenantContext:
    """Tenant retenu pour une requête, avec sa provenance et le mode courant."""

    id: str
    demo: bool
    source: str

    @property
    def tenant(self) -> str:
        """Alias de ``id`` pour les appelants qui nomment le tenant ``tenant``."""
        return self.id

    def as_dict(self) -> dict:
        return asdict(self)

    def __str__(self) -> str:
        return self.id


def _mode(auth_mode: str | None) -> str:
    valeur = os.getenv("AUTH_MODE", MODE_DEMO) if auth_mode is None else auth_mode
    return str(valeur).strip().lower()


def _est_demo(mode: str) -> bool:
    if os.getenv("APP_ENV", "").strip().lower() in _ENV_PRODUCTION:
        return False
    return mode == MODE_DEMO


def normaliser_slug(valeur) -> str:
    """Valide et canonise un identifiant tenant.

    Un slug est une suite de minuscules, chiffres et séparateurs simples
    (``.``, ``_``, ``-``), sans séparateur en tête, en queue ni doublé. Les
    accents sont retirés et la casse est abaissée ; tout le reste est refusé.
    """
    if not isinstance(valeur, str):
        raise TenantInvalide("tenant : chaîne attendue")
    texte = unicodedata.normalize("NFKD", valeur.strip())
    texte = "".join(c for c in texte if not unicodedata.combining(c)).lower()
    if not texte:
        raise TenantInvalide("X-Tenant ne peut pas être vide")
    if len(texte) > TAILLE_MAX_SLUG:
        raise TenantInvalide(f"tenant : {TAILLE_MAX_SLUG} caractères au maximum")
    if _SLUG.fullmatch(texte) is None:
        raise TenantInvalide(
            "tenant : slug attendu (minuscules, chiffres, séparateurs . _ -, sans séparateur aux extrémités)"
        )
    return texte


def resoudre_tenant(x_tenant: str | None, auth_mode: str | None = None) -> TenantContext:
    """Résout le tenant de la requête.

    En mode ``demo``, ``X-Tenant`` absent donne explicitement ``local``. Un
    en-tête vide ou invalide est refusé dans tous les modes. Hors demo (proxy,
    OIDC, production, mode inconnu), l'en-tête est obligatoire : l'absence
    lève :class:`TenantRequis` au lieu de retomber sur ``local``.
    """
    mode = _mode(auth_mode)
    demo = _est_demo(mode)
    if x_tenant is None:
        if demo:
            return TenantContext(id=TENANT_DEFAUT_DEMO, demo=True, source=SOURCE_DEFAUT)
        raise TenantRequis("X-Tenant est requis hors du mode demo")
    tenant = normaliser_slug(x_tenant)
    return TenantContext(id=tenant, demo=demo, source=SOURCE_ENTETE)


def exiger_tenant(tenant: TenantContext | str | None, auth_mode: str | None = None) -> TenantContext:
    """Exige un tenant déjà établi (ou un slug) et rend son contexte.

    Contrairement à :func:`resoudre_tenant`, cette fonction ne fabrique jamais
    de tenant par défaut : ``None`` est toujours une erreur.
    """
    if isinstance(tenant, TenantContext):
        if not tenant.id:
            raise TenantRequis("tenant requis")
        normalise = normaliser_slug(tenant.id)
        if normalise == tenant.id:
            return tenant
        return TenantContext(id=normalise, demo=tenant.demo, source=tenant.source or SOURCE_IDENTITE)
    if tenant is None:
        raise TenantRequis("tenant requis")
    return resoudre_tenant(tenant, auth_mode=auth_mode)


def _texte_date(valeur) -> str:
    if isinstance(valeur, (datetime, date)):
        return valeur.isoformat()
    texte = str(valeur or "").strip()
    if not texte:
        raise TenantInvalide("date : valeur obligatoire pour borner une absence")
    return texte


def _liste_sources(sources) -> list:
    if sources is None:
        return []
    if isinstance(sources, str):
        return [sources]
    if isinstance(sources, dict):
        return [dict(sources)]
    try:
        return list(sources)
    except TypeError as exc:
        raise TenantInvalide("sources : liste attendue") from exc


def absence(scope, sources, date, case_id=None) -> dict:
    """Formule une absence bornée, jamais une preuve d'inexistence.

    Le résultat est sérialisable en JSON et porte le périmètre, la date, les
    sources interrogées, le cas de résolution éventuel et ``observed=False``.
    """
    scope_texte = str(scope or "").strip()
    if not scope_texte:
        raise TenantInvalide("scope : valeur obligatoire pour borner une absence")
    date_texte = _texte_date(date)
    phrase = (
        f"non observé dans {scope_texte} au {date_texte} ; "
        "ce n'est pas une preuve d'absence"
    )
    return {
        "scope": scope_texte,
        "sources": _liste_sources(sources),
        "date": date_texte,
        "case_id": case_id,
        "observed": False,
        "phrase": phrase,
        "wording": phrase,
    }
