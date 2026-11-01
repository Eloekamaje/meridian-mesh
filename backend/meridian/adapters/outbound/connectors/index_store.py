"""Stockage portable des artefacts d'index : copie source au SHA, adressée par (tenant, source, sha).

L'index de codebase-memory reste un cache binaire local, non portable tel quel. L'artefact conservé
est donc au minimum la copie source au SHA, compressée et accompagnée d'un manifeste : elle permet de
réindexer sur une autre machine sans dépendre du home de l'utilisateur.

Trois magasins :
- ``LocalIndexStore`` : racine configurable (``JUMEAU_INDEX_DIR``), manifeste JSON + ``copie.tar.gz`` ;
- ``S3IndexStore`` : S3/MinIO, préfixe ``tenant/source/sha``, chiffrement demandé, jamais d'URL publique ;
- ``NullIndexStore`` : zéro-rétention, aucune écriture.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shutil
import tarfile
import tempfile
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

WORKSPACE_DEFAUT = Path.home() / ".local/share/meridian"
TAILLE_MAX_DEFAUT = 1_073_741_824  # 1 Gio de contenu source, avant compression
TAILLE_MIN, TAILLE_MAX = 1024, 20 * 1024 * 1024 * 1024
MODES = ("local", "s3", "none")
ARTEFACT = "copie.tar.gz"
MANIFESTE = "manifest.json"
VERSION_MANIFESTE = 1

_NOM_VALIDE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]{0,127}\Z")
_SHA_VALIDE = re.compile(r"[0-9a-f]{7,64}\Z")
_PREFIXE_INTERDIT = re.compile(r"(^|/)\.\.(/|$)")


class IndexStoreError(RuntimeError):
    """Artefact absent, corrompu, ou archive refusée (chemin hors racine, taille dépassée)."""


class IndexStore(ABC):
    """Port commun : un artefact par ``(tenant, source, sha)``, jamais de secret dans le manifeste."""

    mode: str

    @abstractmethod
    def save(self, tenant: str, source: str, sha: str, copie: str | os.PathLike[str],
             index_code: str | None = None) -> dict[str, Any] | None: ...

    @abstractmethod
    def restore(self, tenant: str, source: str, sha: str, destination: str | os.PathLike[str],
                remplacer: bool = False) -> Path | None: ...

    @abstractmethod
    def has(self, tenant: str, source: str, sha: str) -> bool: ...

    @abstractmethod
    def delete(self, tenant: str, source: str, sha: str) -> bool: ...

    @abstractmethod
    def delete_source(self, tenant: str, source: str, sauf: str | None = None) -> int: ...


def workspace(env: Mapping[str, str] | None = None) -> Path:
    """Racine locale de Méridian (``JUMEAU_WORKSPACE``), compatible avec l'ancien défaut du home."""
    env = os.environ if env is None else env
    brut = (env.get("JUMEAU_WORKSPACE") or "").strip()
    return Path(brut).expanduser() if brut else WORKSPACE_DEFAUT


def copies_dir(env: Mapping[str, str] | None = None) -> Path:
    """Répertoire des copies de travail, dérivé du workspace (``JUMEAU_COPIES`` reste prioritaire)."""
    env = os.environ if env is None else env
    explicite = (env.get("JUMEAU_COPIES") or "").strip()
    return Path(explicite).expanduser() if explicite else workspace(env) / "copies"


def depots_dir(env: Mapping[str, str] | None = None) -> Path:
    """Répertoire des clones, dérivé du workspace (``JUMEAU_DEPOTS`` reste prioritaire)."""
    env = os.environ if env is None else env
    explicite = (env.get("JUMEAU_DEPOTS") or "").strip()
    return Path(explicite).expanduser() if explicite else workspace(env) / "depots"


def index_dir(env: Mapping[str, str] | None = None) -> Path:
    """Racine du magasin local (``JUMEAU_INDEX_DIR``), sinon ``workspace()/index``."""
    env = os.environ if env is None else env
    explicite = (env.get("JUMEAU_INDEX_DIR") or "").strip()
    return Path(explicite).expanduser() if explicite else workspace(env) / "index"


def taille_max(env: Mapping[str, str] | None = None) -> int:
    env = os.environ if env is None else env
    brut = env.get("JUMEAU_INDEX_MAX_OCTETS") or env.get("JUMEAU_INDEX_TAILLE_MAX")
    try:
        return min(TAILLE_MAX, max(TAILLE_MIN, int(brut)))
    except (TypeError, ValueError):
        return TAILLE_MAX_DEFAUT


def _nom(valeur: Any, quoi: str) -> str:
    """Un segment de clé sûr : ni chemin, ni ``..``, ni caractère de contrôle."""
    if not isinstance(valeur, str) or not _NOM_VALIDE.fullmatch(valeur) or valeur in (".", ".."):
        raise ValueError(f"{quoi} invalide : {valeur!r}")
    return valeur


def _sha(valeur: Any) -> str:
    if not isinstance(valeur, str) or not _SHA_VALIDE.fullmatch(valeur):
        raise ValueError(f"sha invalide : {valeur!r}")
    return valeur


def _cle(tenant: Any, source: Any, sha: Any) -> str:
    return f"{_nom(tenant, 'tenant')}/{_nom(source, 'source')}/{_sha(sha)}"


def _prefixe(valeur: Any) -> str:
    if not valeur:
        return ""
    texte = str(valeur).strip("/")
    if not texte or _PREFIXE_INTERDIT.search(texte) or "\\" in texte:
        raise ValueError(f"préfixe invalide : {valeur!r}")
    for segment in texte.split("/"):
        _nom(segment, "préfixe")
    return texte


def _date() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _json(objet: Mapping[str, Any]) -> bytes:
    return json.dumps(objet, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _sha256_fichier(chemin: Path) -> str:
    h = hashlib.sha256()
    with chemin.open("rb") as f:
        for bloc in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloc)
    return h.hexdigest()


def _dans(racine: Path, cible: Path) -> bool:
    try:
        cible.resolve().relative_to(racine.resolve())
        return True
    except (ValueError, OSError):
        return False


def _exclu(relatif: PurePosixPath) -> bool:
    return any(part == ".git" for part in relatif.parts)


def _archiver(copie: Path, destination: Path, maximum: int) -> int:
    """Archive déterministe (tri, mtime nul, sans ``.git`` ni lien symbolique) ; rend la taille source."""
    copie = Path(copie)
    if not copie.is_dir():
        raise IndexStoreError(f"copie introuvable : {copie}")
    total = 0
    with destination.open("wb") as brut:
        with gzip.GzipFile(fileobj=brut, mode="wb", compresslevel=6, mtime=0) as gz:
            with tarfile.open(fileobj=gz, mode="w") as tar:
                for racine, dossiers, fichiers in os.walk(copie, followlinks=False):
                    base = Path(racine)
                    dossiers[:] = sorted(d for d in dossiers
                                         if d != ".git" and not (base / d).is_symlink())
                    for nom in dossiers:
                        relatif = (base / nom).relative_to(copie)
                        ti = tarfile.TarInfo(relatif.as_posix() + "/")
                        ti.type = tarfile.DIRTYPE
                        ti.mode, ti.mtime, ti.uid, ti.gid = 0o755, 0, 0, 0
                        ti.uname = ti.gname = ""
                        tar.addfile(ti)
                    for nom in sorted(fichiers):
                        chemin = base / nom
                        relatif = PurePosixPath(chemin.relative_to(copie).as_posix())
                        if _exclu(relatif) or chemin.is_symlink():
                            continue
                        info = chemin.lstat()
                        if not chemin.is_file():
                            continue  # socket, fifo, périphérique : jamais dans un artefact
                        if total + info.st_size > maximum:
                            raise IndexStoreError(
                                f"copie trop volumineuse : plus de {maximum} octets (JUMEAU_INDEX_MAX_OCTETS)")
                        total += info.st_size
                        ti = tarfile.TarInfo(relatif.as_posix())
                        ti.size = info.st_size
                        ti.mode = 0o755 if info.st_mode & 0o111 else 0o644
                        ti.mtime, ti.uid, ti.gid = 0, 0, 0
                        ti.uname = ti.gname = ""
                        with chemin.open("rb") as source:
                            tar.addfile(ti, source)
    return total


def _extraire(archive: Path, destination: Path, maximum: int) -> None:
    """Extraction sûre : refuse absolu, ``..``, liens, périphériques et toute taille hors borne."""
    total = 0
    with tarfile.open(archive, "r:gz") as tar:
        for membre in tar:
            nom = PurePosixPath(membre.name)
            if nom.is_absolute() or not nom.parts or any(p in ("", ".", "..") for p in nom.parts):
                raise IndexStoreError(f"chemin d'archive refusé : {membre.name!r}")
            if membre.issym() or membre.islnk() or membre.isdev() or not (membre.isfile() or membre.isdir()):
                raise IndexStoreError(f"entrée d'archive refusée : {membre.name!r}")
            cible = destination.joinpath(*nom.parts)
            if not _dans(destination, cible):
                raise IndexStoreError(f"chemin hors destination : {membre.name!r}")
            if membre.isdir():
                cible.mkdir(parents=True, exist_ok=True)
                continue
            total += membre.size
            if membre.size < 0 or total > maximum:
                raise IndexStoreError(
                    f"archive trop volumineuse : plus de {maximum} octets (JUMEAU_INDEX_MAX_OCTETS)")
            cible.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(membre)
            if source is None:
                raise IndexStoreError(f"entrée illisible : {membre.name!r}")
            with source, cible.open("wb") as sortie:
                reste = membre.size
                for bloc in iter(lambda: source.read(min(1024 * 1024, reste)), b""):
                    sortie.write(bloc)
                    reste -= len(bloc)
                    if reste <= 0:
                        break
                if reste != 0:
                    raise IndexStoreError(f"entrée tronquée : {membre.name!r}")
            os.chmod(cible, membre.mode & 0o777)


def _preparer_destination(destination: Path, remplacer: bool) -> None:
    if destination.is_symlink():
        if not remplacer:
            raise FileExistsError(f"destination symbolique refusée : {destination}")
        destination.unlink()
    elif destination.exists():
        if destination.is_dir() and not any(destination.iterdir()):
            return
        if not remplacer:
            raise FileExistsError(f"destination déjà présente : {destination}")
        if destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()
    destination.mkdir(parents=True, exist_ok=True)


def _manifeste(tenant: str, source: str, sha: str, digest: str, taille: int, octets: int,
               index_code: str | None) -> dict[str, Any]:
    manifeste = {
        "version": VERSION_MANIFESTE,
        "tenant": tenant,
        "source": source,
        "sha": sha,
        "format": "tar.gz",
        "artefact": ARTEFACT,
        "sha256": digest,
        "taille": taille,
        "octets_source": octets,
        "date": _date(),
    }
    if index_code:
        manifeste["index_code"] = index_code
    return manifeste


def _verifier(manifeste: Mapping[str, Any], tenant: str, source: str, sha: str) -> None:
    if not isinstance(manifeste, Mapping) or manifeste.get("version") != VERSION_MANIFESTE:
        raise IndexStoreError("manifeste d'index illisible ou version inconnue")
    for quoi, attendu in (("tenant", tenant), ("source", source), ("sha", sha)):
        if manifeste.get(quoi) != attendu:
            raise IndexStoreError(f"manifeste incohérent : {quoi}")
    if not isinstance(manifeste.get("sha256"), str) or len(manifeste["sha256"]) != 64:
        raise IndexStoreError("manifeste sans hash SHA-256")
    if not isinstance(manifeste.get("taille"), int) or manifeste["taille"] < 0:
        raise IndexStoreError("manifeste sans taille valide")


def _verifier_artefact(chemin: Path, manifeste: Mapping[str, Any], tenant: str | None = None,
                       source: str | None = None, sha: str | None = None) -> None:
    _verifier(manifeste, tenant or manifeste.get("tenant"), source or manifeste.get("source"),
              sha or manifeste.get("sha"))
    if not chemin.is_file():
        raise IndexStoreError("artefact absent")
    if chemin.stat().st_size != manifeste["taille"]:
        raise IndexStoreError("taille d'artefact incohérente")
    if _sha256_fichier(chemin) != manifeste["sha256"]:
        raise IndexStoreError("hash SHA-256 de l'artefact incohérent")


class LocalIndexStore(IndexStore):
    """Artefacts sur disque : ``<racine>/<tenant>/<source>/<sha>/{copie.tar.gz,manifest.json}``."""

    mode = "local"

    def __init__(self, racine: str | os.PathLike[str], maximum: int | None = None):
        self.racine = Path(racine).expanduser()
        self.maximum = maximum or TAILLE_MAX_DEFAUT

    def _dossier(self, tenant: str, source: str, sha: str) -> Path:
        return self.racine.joinpath(*_cle(tenant, source, sha).split("/"))

    def _manifeste(self, dossier: Path) -> dict[str, Any] | None:
        try:
            manifeste = json.loads((dossier / MANIFESTE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return manifeste if isinstance(manifeste, dict) else None

    def has(self, tenant: str, source: str, sha: str) -> bool:
        dossier = self._dossier(tenant, source, sha)
        if not (dossier / ARTEFACT).is_file():
            return False
        manifeste = self._manifeste(dossier)
        return bool(manifeste and manifeste.get("version") == VERSION_MANIFESTE)

    def save(self, tenant: str, source: str, sha: str, copie: str | os.PathLike[str],
             index_code: str | None = None) -> dict[str, Any]:
        dossier = self._dossier(tenant, source, sha)
        manifeste = self._manifeste(dossier)
        try:
            if manifeste and self.has(tenant, source, sha):
                _verifier_artefact(dossier / ARTEFACT, manifeste, tenant, source, sha)
                return manifeste
        except IndexStoreError:
            pass  # artefact corrompu : il sera réécrit
        dossier.mkdir(parents=True, exist_ok=True)
        fd, temporaire = tempfile.mkstemp(dir=dossier, prefix=".copie-", suffix=".tmp")
        os.close(fd)
        temporaire = Path(temporaire)
        try:
            octets = _archiver(Path(copie), temporaire, self.maximum)
            taille = temporaire.stat().st_size
            manifeste = _manifeste(tenant, source, sha, _sha256_fichier(temporaire), taille, octets, index_code)
            os.replace(temporaire, dossier / ARTEFACT)
            _ecrire_atomique(dossier / MANIFESTE, _json(manifeste))
            return manifeste
        finally:
            temporaire.unlink(missing_ok=True)

    def restore(self, tenant: str, source: str, sha: str, destination: str | os.PathLike[str],
                remplacer: bool = False) -> Path | None:
        dossier = self._dossier(tenant, source, sha)
        manifeste = self._manifeste(dossier)
        if manifeste is None or not (dossier / ARTEFACT).is_file():
            return None
        _verifier_artefact(dossier / ARTEFACT, manifeste, tenant, source, sha)
        destination = Path(destination).expanduser()
        _preparer_destination(destination, remplacer)
        try:
            _extraire(dossier / ARTEFACT, destination, self.maximum)
        except Exception:
            shutil.rmtree(destination, ignore_errors=True)
            raise
        return destination

    def delete(self, tenant: str, source: str, sha: str) -> bool:
        dossier = self._dossier(tenant, source, sha)
        if not dossier.exists():
            return False
        shutil.rmtree(dossier)
        return True

    def delete_source(self, tenant: str, source: str, sauf: str | None = None) -> int:
        racine = self.racine / _nom(tenant, "tenant") / _nom(source, "source")
        if sauf:
            _sha(sauf)
        if not racine.is_dir():
            return 0
        retires = 0
        for dossier in racine.iterdir():
            if dossier.is_dir() and dossier.name != sauf:
                shutil.rmtree(dossier, ignore_errors=True)
                retires += 1
        return retires

    # Alias français, pour rester lisible dans le reste du code.
    sauver = save
    restaurer = restore
    existe = has
    supprimer = delete


def _ecrire_atomique(chemin: Path, contenu: bytes) -> None:
    fd, temporaire = tempfile.mkstemp(dir=chemin.parent, prefix=f".{chemin.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(contenu)
        os.replace(temporaire, chemin)
    finally:
        Path(temporaire).unlink(missing_ok=True)


class S3IndexStore(IndexStore):
    """S3/MinIO : clé ``<préfixe>/<tenant>/<source>/<sha>/``, chiffrement demandé, aucune URL publique."""

    mode = "s3"

    def __init__(self, bucket: str, prefix: str = "", endpoint: str | None = None,
                 region: str | None = None, client: Any = None, sse: str = "AES256",
                 kms_key: str | None = None, maximum: int | None = None):
        self.bucket = _nom(bucket, "bucket")
        self.prefix = _prefixe(prefix)
        self.endpoint = endpoint or None
        self.region = region or None
        if sse not in ("AES256", "aws:kms"):
            raise ValueError(f"chiffrement S3 non autorisé : {sse!r}")
        self.sse, self.kms_key = sse, kms_key
        self.maximum = maximum or TAILLE_MAX_DEFAUT
        self._client = client

    def _s3(self) -> Any:
        if self._client is None:
            import boto3  # import paresseux : le mode local ne dépend pas de boto3

            self._client = boto3.client("s3", endpoint_url=self.endpoint, region_name=self.region)
        return self._client

    def _base(self, tenant: str, source: str) -> str:
        base = f"{_nom(tenant, 'tenant')}/{_nom(source, 'source')}"
        return f"{self.prefix}/{base}".strip("/")

    def _cle_objet(self, tenant: str, source: str, sha: str, nom: str = "") -> str:
        base = f"{self._base(tenant, source)}/{_sha(sha)}"
        return f"{base}/{nom}" if nom else base

    def _chiffrement(self) -> dict[str, str]:
        reglage = {"ServerSideEncryption": self.sse}
        if self.sse == "aws:kms" and self.kms_key:
            reglage["SSEKMSKeyId"] = self.kms_key
        return reglage

    def _manifeste(self, tenant: str, source: str, sha: str) -> dict[str, Any] | None:
        try:
            reponse = self._s3().get_object(Bucket=self.bucket, Key=self._cle_objet(tenant, source, sha, MANIFESTE))
        except Exception:
            return None
        corps = reponse["Body"]
        donnees = corps.read() if hasattr(corps, "read") else corps
        try:
            manifeste = json.loads(donnees)
        except (TypeError, ValueError):
            return None
        return manifeste if isinstance(manifeste, dict) else None

    def has(self, tenant: str, source: str, sha: str) -> bool:
        try:
            self._s3().head_object(Bucket=self.bucket, Key=self._cle_objet(tenant, source, sha, ARTEFACT))
            self._s3().head_object(Bucket=self.bucket, Key=self._cle_objet(tenant, source, sha, MANIFESTE))
        except Exception:
            return False
        return True

    def save(self, tenant: str, source: str, sha: str, copie: str | os.PathLike[str],
             index_code: str | None = None) -> dict[str, Any]:
        if self.has(tenant, source, sha):
            manifeste = self._manifeste(tenant, source, sha)
            try:
                if manifeste is not None:
                    _verifier(manifeste, tenant, source, sha)
                    return manifeste
            except IndexStoreError:
                pass  # manifeste corrompu : il sera réécrit
        with tempfile.TemporaryDirectory(prefix="meridian-index-") as dossier:
            archive = Path(dossier) / ARTEFACT
            octets = _archiver(Path(copie), archive, self.maximum)
            taille = archive.stat().st_size
            manifeste = _manifeste(tenant, source, sha, _sha256_fichier(archive), taille, octets, index_code)
            with archive.open("rb") as corps:
                self._s3().put_object(
                    Bucket=self.bucket, Key=self._cle_objet(tenant, source, sha, ARTEFACT), Body=corps,
                    ContentType="application/gzip", **self._chiffrement())
            self._s3().put_object(
                Bucket=self.bucket, Key=self._cle_objet(tenant, source, sha, MANIFESTE), Body=_json(manifeste),
                ContentType="application/json", **self._chiffrement())
            return manifeste

    def restore(self, tenant: str, source: str, sha: str, destination: str | os.PathLike[str],
                remplacer: bool = False) -> Path | None:
        manifeste = self._manifeste(tenant, source, sha)
        if manifeste is None:
            return None
        _verifier(manifeste, tenant, source, sha)
        try:
            reponse = self._s3().get_object(Bucket=self.bucket, Key=self._cle_objet(tenant, source, sha, ARTEFACT))
        except Exception:
            return None
        corps = reponse["Body"]
        if hasattr(corps, "read"):
            try:
                donnees = corps.read(self.maximum + 1_048_577)
            except TypeError:  # certains clients factices n'acceptent pas de borne
                donnees = corps.read()
        else:
            donnees = corps
        if len(donnees) > self.maximum + 1_048_576:
            raise IndexStoreError("artefact S3 trop volumineux")
        if hashlib.sha256(donnees).hexdigest() != manifeste["sha256"] or len(donnees) != manifeste["taille"]:
            raise IndexStoreError("artefact S3 incohérent (hash ou taille)")
        with tempfile.TemporaryDirectory(prefix="meridian-index-") as dossier:
            archive = Path(dossier) / ARTEFACT
            archive.write_bytes(donnees)
            destination = Path(destination).expanduser()
            _preparer_destination(destination, remplacer)
            try:
                _extraire(archive, destination, self.maximum)
            except Exception:
                shutil.rmtree(destination, ignore_errors=True)
                raise
        return destination

    def delete(self, tenant: str, source: str, sha: str) -> bool:
        supprime = False
        for nom in (ARTEFACT, MANIFESTE):
            try:
                self._s3().delete_object(Bucket=self.bucket, Key=self._cle_objet(tenant, source, sha, nom))
                supprime = True
            except Exception:
                pass
        return supprime

    def delete_source(self, tenant: str, source: str, sauf: str | None = None) -> int:
        prefixe = self._base(tenant, source)
        if sauf:
            _sha(sauf)
        cles, jeton = [], None
        while True:
            try:
                arguments = {"Bucket": self.bucket, "Prefix": f"{prefixe}/"}
                if jeton:
                    arguments["ContinuationToken"] = jeton
                reponse = self._s3().list_objects_v2(**arguments)
            except Exception:
                break
            cles += [objet.get("Key", "") for objet in (reponse.get("Contents") or [])]
            if not reponse.get("IsTruncated"):
                break
            jeton = reponse.get("NextContinuationToken")
            if not jeton:
                break
        retires = 0
        for cle in cles:
            if not cle or (sauf and cle.startswith(f"{prefixe}/{sauf}/")):
                continue
            try:
                self._s3().delete_object(Bucket=self.bucket, Key=cle)
                retires += 1
            except Exception:
                pass
        return retires

    # Alias français, pour rester lisible dans le reste du code.
    sauver = save
    restaurer = restore
    existe = has
    supprimer = delete


class NullIndexStore(IndexStore):
    """Zéro-rétention : l'ingestion ne conserve aucun artefact."""

    mode = "none"
    maximum = TAILLE_MAX_DEFAUT

    def save(self, tenant: str, source: str, sha: str, copie: str | os.PathLike[str],
             index_code: str | None = None) -> None:
        _cle(tenant, source, sha)
        return None

    def restore(self, tenant: str, source: str, sha: str, destination: str | os.PathLike[str],
                remplacer: bool = False) -> None:
        _cle(tenant, source, sha)
        return None

    def has(self, tenant: str, source: str, sha: str) -> bool:
        _cle(tenant, source, sha)
        return False

    def delete(self, tenant: str, source: str, sha: str) -> bool:
        _cle(tenant, source, sha)
        return False

    def delete_source(self, tenant: str, source: str, sauf: str | None = None) -> int:
        _nom(tenant, "tenant")
        _nom(source, "source")
        if sauf:
            _sha(sauf)
        return 0

    # Alias français, pour rester lisible dans le reste du code.
    sauver = save
    restaurer = restore
    existe = has
    supprimer = delete


def depuis_env(env: Mapping[str, str] | None = None,
               client: Any = None) -> LocalIndexStore | S3IndexStore | NullIndexStore:
    """Construit le magasin demandé ; aucun secret n'est lu ici (boto3 utilise sa chaîne d'identifiants)."""
    env = os.environ if env is None else env
    mode = (env.get("JUMEAU_INDEX_STORE") or "local").strip().lower()
    if mode not in MODES:
        raise ValueError(f"JUMEAU_INDEX_STORE invalide : {mode!r} (local, s3 ou none)")
    if mode == "none":
        return NullIndexStore()
    if mode == "local":
        return LocalIndexStore(index_dir(env), maximum=taille_max(env))
    bucket = (env.get("JUMEAU_INDEX_BUCKET") or env.get("JUMEAU_S3_BUCKET") or "").strip()
    if not bucket:
        raise ValueError("JUMEAU_INDEX_STORE=s3 exige JUMEAU_INDEX_BUCKET")
    endpoint = (env.get("JUMEAU_INDEX_ENDPOINT") or env.get("JUMEAU_INDEX_S3_ENDPOINT")
                or env.get("AWS_ENDPOINT_URL_S3") or env.get("AWS_ENDPOINT_URL") or None)
    region = (env.get("JUMEAU_INDEX_REGION") or env.get("JUMEAU_INDEX_S3_REGION")
              or env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION") or None)
    return S3IndexStore(
        bucket, prefix=env.get("JUMEAU_INDEX_PREFIX") or "", endpoint=endpoint, region=region,
        client=client, sse=env.get("JUMEAU_INDEX_SSE") or "AES256", kms_key=env.get("JUMEAU_INDEX_KMS_KEY") or None,
        maximum=taille_max(env))


# Noms explicites pour les appelants qui préfèrent l'anglais.
store_from_env = depuis_env
