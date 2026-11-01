"""Stockage S3 et compatible S3 (MinIO, Garage, etc.)."""
from __future__ import annotations

import asyncio
from typing import Any


class S3Stockage:
    def __init__(self, bucket: str, *, prefixe: str = "", client=None,
                 endpoint_url: str | None = None, region: str | None = None,
                 force_path_style: bool = False, nom: str = "s3"):
        if not bucket:
            raise ValueError("bucket S3 requis")
        if client is None:
            import boto3
            from botocore.config import Config

            config = Config(s3={"addressing_style": "path"}) if force_path_style else None
            client = boto3.client(
                "s3", region_name=region or None, endpoint_url=endpoint_url or None,
                config=config,
            )
        self.bucket = bucket
        self.nom = nom
        self.prefixe = prefixe.strip("/")
        self.client = client

    def _cle(self, cle: str) -> str:
        morceaux = [morceau for morceau in str(cle).replace("\\", "/").split("/") if morceau]
        if not morceaux or any(morceau in {".", ".."} for morceau in morceaux):
            raise ValueError(f"clé de stockage invalide : {cle!r}")
        return "/".join([self.prefixe, *morceaux] if self.prefixe else morceaux)

    async def ecrire(self, cle: str, data: bytes, metadata: dict[str, Any]) -> str:
        key = self._cle(cle)
        entetes = {str(k): str(v) for k, v in (metadata or {}).items() if v is not None}
        await asyncio.to_thread(
            self.client.put_object,
            Bucket=self.bucket, Key=key, Body=data,
            ContentType=str(metadata.get("type_mime") or "application/octet-stream"),
            Metadata=entetes,
        )
        return key

    async def lire(self, identifiant: str) -> bytes:
        try:
            reponse = await asyncio.to_thread(
                self.client.get_object, Bucket=self.bucket, Key=identifiant)
        except Exception as exc:
            code = str(getattr(exc, "response", {}).get("Error", {}).get("Code") or "")
            if code in {"NoSuchKey", "NoSuchBucket", "404", "NotFound"}:
                raise FileNotFoundError("contenu de la pièce introuvable") from exc
            raise
        corps = reponse["Body"]
        try:
            return await asyncio.to_thread(corps.read)
        finally:
            fermer = getattr(corps, "close", None)
            if fermer:
                await asyncio.to_thread(fermer)

    async def supprimer(self, identifiant: str) -> None:
        await asyncio.to_thread(
            self.client.delete_object, Bucket=self.bucket, Key=identifiant)

    async def deplacer(self, identifiants: list[str], case_id: str) -> None:
        return None

    async def vider(self) -> None:
        paginateur = self.client.get_paginator("list_objects_v2")
        prefixe = f"{self.prefixe}/" if self.prefixe else ""
        for page in paginateur.paginate(Bucket=self.bucket, Prefix=prefixe):
            objets = [{"Key": objet["Key"]} for objet in page.get("Contents", [])]
            if objets:
                await asyncio.to_thread(
                    self.client.delete_objects,
                    Bucket=self.bucket,
                    Delete={"Objects": objets, "Quiet": True},
                )
