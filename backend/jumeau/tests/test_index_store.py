"""Magasin d'index : local content-addressed, S3 factice, zéro-rétention, validation et restauration."""
import hashlib
import io
import json
import subprocess
import tarfile

import pytest

from jumeau import cbm, depot, index_store, ingerer
from jumeau.index_store import IndexStoreError, LocalIndexStore, NullIndexStore, S3IndexStore, depuis_env
from jumeau.tests.conftest import JUMEAU, besoin_pg

SHA = "0123456789abcdef0123456789abcdef01234567"
SHA2 = "fedcba9876543210fedcba9876543210fedcba98"


def copie_source(tmp_path):
    copie = tmp_path / "copie"
    (copie / "src").mkdir(parents=True)
    (copie / "src" / "app.py").write_text("print('ok')\n")
    (copie / "requirements.txt").write_text("fastapi==1\n")
    (copie / ".git").write_text("gitdir: /hors/du/depot\n")
    return copie


def test_le_workspace_et_ses_derives_sont_configurables(monkeypatch, tmp_path):
    monkeypatch.setenv("JUMEAU_WORKSPACE", str(tmp_path / "espace"))
    monkeypatch.delenv("JUMEAU_COPIES", raising=False)
    monkeypatch.delenv("JUMEAU_DEPOTS", raising=False)
    monkeypatch.delenv("JUMEAU_INDEX_DIR", raising=False)
    assert index_store.workspace() == tmp_path / "espace"
    assert index_store.copies_dir() == tmp_path / "espace" / "copies"
    assert index_store.depots_dir() == tmp_path / "espace" / "depots"
    assert index_store.index_dir() == tmp_path / "espace" / "index"


def test_le_defaut_reste_le_workspace_historique(monkeypatch):
    for nom in ("JUMEAU_WORKSPACE", "JUMEAU_COPIES", "JUMEAU_DEPOTS", "JUMEAU_INDEX_DIR"):
        monkeypatch.delenv(nom, raising=False)
    assert index_store.workspace() == index_store.WORKSPACE_DEFAUT
    assert index_store.copies_dir() == index_store.WORKSPACE_DEFAUT / "copies"


def test_local_sauve_manifeste_hash_taille_et_date(tmp_path):
    copie = copie_source(tmp_path)
    store = LocalIndexStore(tmp_path / "index")
    manifeste = store.save("banque", "api", SHA, copie, index_code="jum-banque-api-0123456789ab")

    dossier = tmp_path / "index" / "banque" / "api" / SHA
    artefact = dossier / "copie.tar.gz"
    assert artefact.is_file() and (dossier / "manifest.json").is_file()
    assert manifeste["tenant"] == "banque" and manifeste["source"] == "api" and manifeste["sha"] == SHA
    assert manifeste["taille"] == artefact.stat().st_size
    assert manifeste["sha256"] == hashlib.sha256(artefact.read_bytes()).hexdigest()
    assert manifeste["date"].endswith("Z")
    assert manifeste["index_code"] == "jum-banque-api-0123456789ab"
    assert "/hors/du/depot" not in json.dumps(manifeste)  # aucun chemin local dans le manifeste


def test_local_restaure_la_copie_sans_git_ni_lien_symbolique(tmp_path):
    copie = copie_source(tmp_path)
    (copie / "lien").symlink_to("/etc/hostname")
    store = LocalIndexStore(tmp_path / "index")
    store.save("banque", "api", SHA, copie)

    destination = tmp_path / "restauree"
    assert store.restore("banque", "api", SHA, destination) == destination
    assert (destination / "src" / "app.py").read_text() == "print('ok')\n"
    assert not (destination / ".git").exists()
    assert not (destination / "lien").exists()


def test_local_est_idempotent_et_garde_l_artefact(tmp_path):
    copie = copie_source(tmp_path)
    store = LocalIndexStore(tmp_path / "index")
    premier = store.save("banque", "api", SHA, copie)
    artefact = tmp_path / "index" / "banque" / "api" / SHA / "copie.tar.gz"
    mtime = artefact.stat().st_mtime_ns

    second = store.save("banque", "api", SHA, copie)
    assert second == premier
    assert artefact.stat().st_mtime_ns == mtime
    assert not list(artefact.parent.glob(".copie-*.tmp"))


def test_local_detecte_un_artefact_altere(tmp_path):
    copie = copie_source(tmp_path)
    store = LocalIndexStore(tmp_path / "index")
    store.save("banque", "api", SHA, copie)
    artefact = tmp_path / "index" / "banque" / "api" / SHA / "copie.tar.gz"
    artefact.write_bytes(artefact.read_bytes()[:-1])

    with pytest.raises(IndexStoreError):
        store.restore("banque", "api", SHA, tmp_path / "restauree")


def test_les_cles_invalides_sont_refusees(tmp_path):
    copie = copie_source(tmp_path)
    store = LocalIndexStore(tmp_path / "index")
    for tenant, source, sha in (("..", "api", SHA), ("banque", "../api", SHA), ("banque", "api", ".."),
                                ("banque", "api", "abc"), ("banque/api", "api", SHA), ("banque", "api\n", SHA)):
        with pytest.raises(ValueError):
            store.save(tenant, source, sha, copie)
        with pytest.raises(ValueError):
            store.has(tenant, source, sha)


def test_restauration_refuse_une_archive_qui_sort_de_la_destination(tmp_path):
    store = LocalIndexStore(tmp_path / "index")
    dossier = tmp_path / "index" / "banque" / "api" / SHA
    dossier.mkdir(parents=True)
    archive = dossier / "copie.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        info = tarfile.TarInfo("../evasion.txt")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
    manifeste = {"version": 1, "tenant": "banque", "source": "api", "sha": SHA,
                 "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                 "taille": archive.stat().st_size, "date": "2026-01-01T00:00:00Z"}
    (dossier / "manifest.json").write_text(json.dumps(manifeste))

    with pytest.raises(IndexStoreError):
        store.restore("banque", "api", SHA, tmp_path / "restauree")
    assert not (tmp_path / "evasion.txt").exists()


def test_la_taille_de_la_copie_est_bornee(tmp_path):
    copie = copie_source(tmp_path)
    store = LocalIndexStore(tmp_path / "index", maximum=10)
    with pytest.raises(IndexStoreError):
        store.save("banque", "api", SHA, copie)


def test_supprimer_les_anciens_artefacts_d_une_source(tmp_path):
    copie = copie_source(tmp_path)
    store = LocalIndexStore(tmp_path / "index")
    store.save("banque", "api", SHA, copie)
    store.save("banque", "api", SHA2, copie)
    assert store.delete_source("banque", "api", sauf=SHA2) == 1
    assert store.has("banque", "api", SHA2) and not store.has("banque", "api", SHA)


class FauxS3:
    """Client boto3 minimal : aucun réseau, objets en mémoire."""

    def __init__(self):
        self.objets = {}
        self.appels = []
        self._pagination = 2

    def put_object(self, **arguments):
        self.appels.append(("put", arguments))
        corps = arguments["Body"]
        donnees = corps.read() if hasattr(corps, "read") else corps
        self.objets[(arguments["Bucket"], arguments["Key"])] = donnees
        return {}

    def head_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objets:
            raise KeyError(Key)
        return {"ContentLength": len(self.objets[(Bucket, Key)])}

    def get_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objets:
            raise KeyError(Key)
        donnees = self.objets[(Bucket, Key)]
        return {"Body": io.BytesIO(donnees), "ContentLength": len(donnees)}

    def delete_object(self, Bucket, Key):
        self.appels.append(("delete", Key))
        self.objets.pop((Bucket, Key), None)
        return {}

    def list_objects_v2(self, Bucket, Prefix, ContinuationToken=None):
        cles = sorted(cle for (bucket, cle) in self.objets if bucket == Bucket and cle.startswith(Prefix))
        debut = int(ContinuationToken or 0)
        page = cles[debut:debut + self._pagination]
        suivant = debut + self._pagination
        reponse = {"Contents": [{"Key": cle} for cle in page], "IsTruncated": suivant < len(cles)}
        if reponse["IsTruncated"]:
            reponse["NextContinuationToken"] = str(suivant)
        return reponse


def test_s3_est_chiffre_prefixe_et_sans_url_publique(tmp_path):
    client = FauxS3()
    store = S3IndexStore("meridian-index", prefix="meridian/index", endpoint="http://minio:9000",
                         region="ca-central-1", client=client)
    copie = copie_source(tmp_path)
    manifeste = store.save("banque", "api", SHA, copie)

    prefixe = f"meridian/index/banque/api/{SHA}"
    assert set(client.objets) == {("meridian-index", f"{prefixe}/copie.tar.gz"),
                                  ("meridian-index", f"{prefixe}/manifest.json")}
    puts = [arguments for action, arguments in client.appels if action == "put"]
    assert all(a["ServerSideEncryption"] == "AES256" for a in puts)
    assert all("ACL" not in a for a in puts)
    assert not any(hasattr(store, nom) for nom in ("url_publique", "url", "presigned_url"))
    attendu = hashlib.sha256(client.objets[("meridian-index", f"{prefixe}/copie.tar.gz")]).hexdigest()
    assert manifeste["sha256"] == attendu


def test_s3_restaure_et_est_idempotent(tmp_path):
    client = FauxS3()
    store = S3IndexStore("bucket", client=client)
    copie = copie_source(tmp_path)
    premier = store.save("banque", "api", SHA, copie)
    assert ("bucket", f"banque/api/{SHA}/copie.tar.gz") in client.objets  # préfixe tenant/source/sha
    assert store.save("banque", "api", SHA, copie) == premier
    assert len([a for a in client.appels if a[0] == "put"]) == 2  # artefact + manifeste, pas de doublon

    destination = tmp_path / "restauree"
    assert store.restore("banque", "api", SHA, destination) == destination
    assert (destination / "src" / "app.py").read_text() == "print('ok')\n"


def test_s3_refuse_un_artefact_altere(tmp_path):
    client = FauxS3()
    store = S3IndexStore("bucket", client=client)
    store.save("banque", "api", SHA, copie_source(tmp_path))
    cle = f"banque/api/{SHA}/copie.tar.gz"
    client.objets[("bucket", cle)] = b"faux"

    with pytest.raises(IndexStoreError):
        store.restore("banque", "api", SHA, tmp_path / "restauree")


def test_s3_supprime_les_anciens_artefacts(tmp_path):
    client = FauxS3()
    store = S3IndexStore("bucket", client=client)
    copie = copie_source(tmp_path)
    store.save("banque", "api", SHA, copie)
    store.save("banque", "api", SHA2, copie)
    assert store.delete_source("banque", "api", sauf=SHA2) == 2
    assert store.has("banque", "api", SHA2) and not store.has("banque", "api", SHA)


def test_le_mode_none_ne_conserve_rien(tmp_path):
    store = NullIndexStore()
    assert store.save("banque", "api", SHA, copie_source(tmp_path)) is None
    assert store.has("banque", "api", SHA) is False
    assert store.restore("banque", "api", SHA, tmp_path / "restauree") is None
    assert store.delete_source("banque", "api") == 0
    assert not (tmp_path / "restauree").exists()
    with pytest.raises(ValueError):
        store.save("..", "api", SHA, tmp_path)


def test_depuis_env_construit_le_bon_magasin(tmp_path):
    assert isinstance(depuis_env({"JUMEAU_INDEX_STORE": "none"}), NullIndexStore)
    local = depuis_env({"JUMEAU_INDEX_STORE": "local", "JUMEAU_INDEX_DIR": str(tmp_path / "idx")})
    assert isinstance(local, LocalIndexStore) and local.racine == tmp_path / "idx"
    client = FauxS3()
    s3 = depuis_env({"JUMEAU_INDEX_STORE": "s3", "JUMEAU_INDEX_BUCKET": "bucket",
                     "JUMEAU_INDEX_ENDPOINT": "http://minio:9000", "JUMEAU_INDEX_SSE": "aws:kms",
                     "JUMEAU_INDEX_KMS_KEY": "cle"}, client=client)
    assert isinstance(s3, S3IndexStore) and s3.sse == "aws:kms" and s3.kms_key == "cle"
    with pytest.raises(ValueError):
        depuis_env({"JUMEAU_INDEX_STORE": "s3"})  # bucket absent
    with pytest.raises(ValueError):
        depuis_env({"JUMEAU_INDEX_STORE": "inconnu"})


def _ingerer_sans_binaire(monkeypatch, tmp_path):
    resultats = {**{famille: [] for famille in cbm.REQUETES},
                 "paquets": [{"chemin": "requirements.txt", "paquet": "fastapi"}]}

    def resultat_ingestion():
        return {famille: list(lignes) for famille, lignes in resultats.items()}

    monkeypatch.setattr(ingerer, "COPIES", tmp_path / "copies")
    monkeypatch.setattr(cbm, "indexer", lambda copie, nom: nom)
    monkeypatch.setattr(cbm, "interroger", lambda projet: (resultat_ingestion(), {}))
    monkeypatch.setattr(cbm, "retirer_ancien", lambda ancien, actuel: True)


@besoin_pg
def test_l_ingestion_sauve_l_artefact_et_nettoie_l_ancien(conn, depot_git, tmp_path, monkeypatch):
    _ingerer_sans_binaire(monkeypatch, tmp_path)
    monkeypatch.setenv("JUMEAU_INDEX_STORE", "local")
    monkeypatch.setenv("JUMEAU_INDEX_DIR", str(tmp_path / "index"))
    premier = ingerer.ingerer(conn, JUMEAU, depot_git)
    dossier = tmp_path / "index" / JUMEAU["tenant_id"] / depot_git.name / premier["sha"]
    assert (dossier / "copie.tar.gz").is_file() and (dossier / "manifest.json").is_file()

    (depot_git / "suite.txt").write_text("suite\n")
    subprocess.run(["git", "-C", str(depot_git), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(depot_git), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
                    "suite"], check=True, capture_output=True)
    second = ingerer.ingerer(conn, JUMEAU, depot_git)
    assert second["sha"] != premier["sha"]
    assert (tmp_path / "index" / JUMEAU["tenant_id"] / depot_git.name / second["sha"]).is_dir()
    assert not (tmp_path / "index" / JUMEAU["tenant_id"] / depot_git.name / premier["sha"]).exists()


@besoin_pg
def test_l_ingestion_restaure_l_artefact_au_meme_sha(conn, depot_git, tmp_path, monkeypatch):
    _ingerer_sans_binaire(monkeypatch, tmp_path)
    monkeypatch.setenv("JUMEAU_INDEX_STORE", "local")
    monkeypatch.setenv("JUMEAU_INDEX_DIR", str(tmp_path / "index"))
    premier = ingerer.ingerer(conn, JUMEAU, depot_git)
    source = depot.source_du_jumeau(conn, "tbt")
    assert source["copie"] is not None  # première ingestion : copie Git de travail

    vus = []
    monkeypatch.setattr(cbm, "indexe", lambda source: False)
    monkeypatch.setattr(cbm, "indexer", lambda copie, nom: vus.append(copie) or nom)
    monkeypatch.setattr(ingerer, "copie_au_sha", lambda *a, **k: (_ for _ in ()).throw(AssertionError("clone inutile")))
    ingerer.ingerer(conn, JUMEAU, depot_git)

    assert vus == [tmp_path / "copies" / "tbt" / depot_git.name]
    assert not (vus[0] / ".git").exists()  # copie restaurée = instantané source, pas un worktree
    assert depot.source_du_jumeau(conn, "tbt")["copie"] is None  # repli sur emplacement pour la lecture
    assert depot.source_du_jumeau(conn, "tbt")["curseur"] == premier["sha"]


@besoin_pg
def test_le_mode_none_supprime_la_copie_apres_ingestion(conn, depot_git, tmp_path, monkeypatch):
    _ingerer_sans_binaire(monkeypatch, tmp_path)
    monkeypatch.setenv("JUMEAU_INDEX_STORE", "none")
    ingerer.ingerer(conn, JUMEAU, depot_git)
    assert not (tmp_path / "copies" / "tbt" / depot_git.name).exists()
    assert depot.source_du_jumeau(conn, "tbt")["copie"] is None
