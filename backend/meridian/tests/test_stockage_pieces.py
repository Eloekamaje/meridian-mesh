"""Adaptateurs de stockage des pièces : local, S3/MinIO et fabrique."""
import asyncio

import boto3
import pytest
from moto import mock_aws

from meridian.adapters.outbound.stockage.fabrique import mode, stockage_pieces
from meridian.adapters.outbound.stockage.local import LocalStockage
from meridian.adapters.outbound.stockage.s3 import S3Stockage


def test_local_ecrit_lit_supprime_et_vide(tmp_path):
    stockage = LocalStockage(tmp_path)
    identifiant = asyncio.run(
        stockage.ecrire("case-1/p1", b"bonjour", {"type_mime": "text/plain"}))
    assert identifiant == "case-1/p1"
    assert (tmp_path / "case-1" / "p1").read_bytes() == b"bonjour"
    assert asyncio.run(stockage.lire(identifiant)) == b"bonjour"
    asyncio.run(stockage.supprimer(identifiant))
    assert not (tmp_path / "case-1" / "p1").exists()
    asyncio.run(stockage.ecrire("case-1/p2", b"x", {}))
    asyncio.run(stockage.vider())
    assert list(tmp_path.iterdir()) == []


def test_local_refuse_une_cle_hors_racine(tmp_path):
    stockage = LocalStockage(tmp_path)
    with pytest.raises(ValueError, match="invalide|hors racine"):
        asyncio.run(stockage.ecrire("../evasion", b"x", {}))


class _Corps:
    def __init__(self, data):
        self.data = data
        self.ferme = False

    def read(self):
        return self.data

    def close(self):
        self.ferme = True


class _ClientS3:
    def __init__(self):
        self.objets = {}
        self.supprimes = []

    def put_object(self, Bucket, Key, Body, ContentType, Metadata):
        self.objets[Key] = {"corps": Body, "type": ContentType, "meta": Metadata}

    def get_object(self, Bucket, Key):
        if Key not in self.objets:
            raise FileNotFoundError(Key)
        return {"Body": _Corps(self.objets[Key]["corps"])}

    def delete_object(self, Bucket, Key):
        self.supprimes.append(Key)
        self.objets.pop(Key, None)


def test_s3_ecrit_lit_et_supprime_avec_prefixe():
    client = _ClientS3()
    stockage = S3Stockage("bucket", prefixe="pieces", client=client)
    identifiant = asyncio.run(stockage.ecrire("case-1/p1", b"bonjour",
                                               {"type_mime": "text/plain", "case_id": "case-1"}))
    assert identifiant == "pieces/case-1/p1"
    assert client.objets[identifiant]["type"] == "text/plain"
    assert client.objets[identifiant]["meta"]["case_id"] == "case-1"
    assert asyncio.run(stockage.lire(identifiant)) == b"bonjour"
    asyncio.run(stockage.supprimer(identifiant))
    assert client.supprimes == [identifiant]


def test_fabrique_choisit_local_et_valide_minio(monkeypatch, tmp_path):
    monkeypatch.setenv("JUMEAU_PIECES_STORAGE", "local")
    monkeypatch.setenv("JUMEAU_PIECES_LOCAL_DIR", str(tmp_path))
    assert isinstance(stockage_pieces(None), LocalStockage)
    assert mode() == "local"


def test_fabrique_refuse_minio_sans_endpoint(monkeypatch):
    monkeypatch.setenv("JUMEAU_PIECES_STORAGE", "minio")
    monkeypatch.setenv("JUMEAU_PIECES_S3_BUCKET", "pieces")
    monkeypatch.delenv("JUMEAU_PIECES_S3_ENDPOINT", raising=False)
    monkeypatch.delenv("AWS_ENDPOINT_URL", raising=False)
    with pytest.raises(RuntimeError, match="ENDPOINT"):
        stockage_pieces(None)


@mock_aws
def test_s3_reel_avec_moto_et_suppression_du_prefixe():
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="pieces-test")
    stockage = S3Stockage("pieces-test", prefixe="pieces", client=client)
    identifiant = asyncio.run(stockage.ecrire("case-1/p1", b"bonjour", {"type_mime": "text/plain"}))
    assert identifiant == "pieces/case-1/p1"
    assert asyncio.run(stockage.lire(identifiant)) == b"bonjour"
    with pytest.raises(FileNotFoundError):
        asyncio.run(stockage.lire("pieces/absent"))
    asyncio.run(stockage.vider())
    assert client.list_objects_v2(Bucket="pieces-test").get("Contents", []) == []


def test_une_piece_est_lue_depuis_le_stockage_inscrit_dans_sa_metadonnee(monkeypatch, tmp_path):
    import pieces

    monkeypatch.setenv("JUMEAU_PIECES_STORAGE", "local")
    monkeypatch.setenv("JUMEAU_PIECES_LOCAL_DIR", str(tmp_path))
    (tmp_path / "case-1").mkdir()
    (tmp_path / "case-1" / "p1").write_bytes(b"contenu local")
    piece = {"id": "p1", "case_id": "case-1", "nom": "note.txt",
             "fichier_id": "case-1/p1", "stockage": "local"}

    class Collection:
        async def find_one(self, filtre, projection=None):
            return dict(piece) if filtre.get("id") == "p1" else None

    db = type("Db", (), {"pieces": Collection()})()
    doc, contenu = asyncio.run(pieces.contenu(db, "case-1", "p1"))
    assert contenu == b"contenu local"
    assert doc["nom"] == "note.txt"
