"""Authentification des sources Git : PAT uniquement pour l'instant.

Le port ne rend jamais un secret persistant : il rend le jeton lu dans Vault/env et utilisable par `env_git`.
Les références (`vault:`/`env:`) restent la seule chose stockée.
"""
from __future__ import annotations

import os
from typing import Any, Mapping

AUTH_PAT = "pat"
AUTH_AUCUNE = "aucune"


class AuthSourceInvalide(ValueError):
    """Configuration d'authentification invalide ou jeton refusé."""


def _texte(valeur: Any) -> str:
    return str(valeur or "").strip()


def _mode(config: Mapping[str, Any]) -> str:
    mode = _texte(config.get("auth_mode") or config.get("auth") or AUTH_PAT).lower()
    if mode in {"pat", "token", "github_token"}:
        return AUTH_PAT
    if mode in {"aucune", "none", "public"}:
        return AUTH_AUCUNE
    raise AuthSourceInvalide(f"mode d'authentification inconnu : {mode!r}")


def champs_source(config: Mapping[str, Any]) -> dict:
    """Champs sûrs à persister sur la source : aucune valeur de secret."""
    mode = _mode(config)
    if mode == AUTH_PAT:
        reference = _texte(config.get("secret_ref") or config.get("secret"))
        return {"auth_mode": AUTH_PAT, **({"secret_ref": reference} if reference else {})}
    return {"auth_mode": AUTH_AUCUNE}


class AuthSource:
    """Un jeton pour Git, éventuellement None pour un dépôt public."""
    mode = AUTH_AUCUNE

    def token(self) -> str | None:
        return None

    def env(self) -> dict:
        return {}


class SansAuth(AuthSource):
    mode = AUTH_AUCUNE


class PATSource(AuthSource):
    mode = AUTH_PAT

    def __init__(self, reference: str | None):
        self.reference = _texte(reference)

    def token(self) -> str | None:
        if not self.reference:
            return None
        try:
            if self.reference.lower().startswith(("aws:", "secretsmanager:")):
                from jumeau.aws_adapters import secrets_depuis_env
                return secrets_depuis_env().resoudre(self.reference)
            from jumeau.naissance import resoudre_secret
            return resoudre_secret(self.reference)
        except Exception as exc:  # noqa: BLE001 - jamais le secret dans l'erreur
            raise AuthSourceInvalide("PAT introuvable ou refusé") from exc


def depuis_config(config: Mapping[str, Any] | None) -> AuthSource:
    """Fabrique le seul point d'entrée utilisé par le clone/test Git."""
    config = dict(config or {})
    mode = _mode(config)
    if mode == AUTH_AUCUNE:
        return SansAuth()
    return PATSource(_texte(config.get("secret_ref") or config.get("secret")))


def configuration_pour_source(base: Mapping[str, Any] | None) -> dict:
    """Configuration normalisée à persister sur `source.configuration`, sans secret brut."""
    config = dict(base or {})
    securise = champs_source(config)
    for cle in ("url", "branche", "depots", "organisation", "selection"):
        if config.get(cle) is not None:
            securise[cle] = config[cle]
    return securise
