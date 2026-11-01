"""Fabrique du stockage des pièces : mongo (défaut), local, s3 ou minio."""
from __future__ import annotations

import os
from typing import Any, Callable

from meridian.adapters.outbound.stockage.grille import GridFSStockage
from meridian.adapters.outbound.stockage.local import LocalStockage
from meridian.adapters.outbound.stockage.s3 import S3Stockage

MODE_ENV = "JUMEAU_PIECES_STORAGE"
RACINE_ENV = "JUMEAU_PIECES_LOCAL_DIR"
BUCKET_ENV = "JUMEAU_PIECES_S3_BUCKET"
PREFIXE_ENV = "JUMEAU_PIECES_S3_PREFIX"
ENDPOINT_ENV = "JUMEAU_PIECES_S3_ENDPOINT"
REGION_ENV = "JUMEAU_PIECES_S3_REGION"
PATH_STYLE_ENV = "JUMEAU_PIECES_S3_FORCE_PATH_STYLE"
MODES = {"mongo", "gridfs", "local", "s3", "minio"}
VRAIS = {"1", "true", "yes", "on"}


def mode() -> str:
    valeur = str(os.environ.get(MODE_ENV) or "mongo").strip().lower()
    if valeur not in MODES:
        raise RuntimeError(f"{MODE_ENV} doit valoir {', '.join(sorted(MODES))} (reçu {valeur!r})")
    return valeur


def stockage_pieces(db, *, bucket_factory: Callable[[Any], Any] | None = None,
                     choix: str | None = None):
    choix = (choix or mode()).strip().lower()
    if choix not in MODES:
        raise RuntimeError(f"{MODE_ENV} doit valoir {', '.join(sorted(MODES))} (reçu {choix!r})")
    if choix in {"mongo", "gridfs"}:
        return GridFSStockage(db, bucket_factory=bucket_factory)
    if choix == "local":
        racine = os.environ.get(RACINE_ENV) or "var/pieces"
        return LocalStockage(racine)
    bucket = os.environ.get(BUCKET_ENV) or ""
    if not bucket:
        raise RuntimeError(f"{BUCKET_ENV} requis pour {MODE_ENV}={choix}")
    endpoint = os.environ.get(ENDPOINT_ENV) or os.environ.get("AWS_ENDPOINT_URL")
    if choix == "minio" and not endpoint:
        raise RuntimeError(f"{ENDPOINT_ENV} requis pour {MODE_ENV}=minio")
    return S3Stockage(
        bucket,
        prefixe=os.environ.get(PREFIXE_ENV) or "",
        endpoint_url=endpoint,
        region=os.environ.get(REGION_ENV) or os.environ.get("AWS_DEFAULT_REGION"),
        force_path_style=(choix == "minio"
                          or str(os.environ.get(PATH_STYLE_ENV) or "").strip().lower() in VRAIS),
        nom=choix,
    )


def verifier_stockage() -> None:
    """Valide la configuration au démarrage ; ne fait aucun appel réseau."""
    choix = mode()
    if choix in {"mongo", "gridfs", "local"}:
        return
    if not os.environ.get(BUCKET_ENV):
        raise RuntimeError(f"{BUCKET_ENV} requis pour {MODE_ENV}={choix}")
    if choix == "minio" and not (os.environ.get(ENDPOINT_ENV)
                                 or os.environ.get("AWS_ENDPOINT_URL")):
        raise RuntimeError(f"{ENDPOINT_ENV} requis pour {MODE_ENV}=minio")
