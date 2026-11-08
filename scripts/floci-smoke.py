#!/usr/bin/env python3
"""Smoke AWS local contre Floci, avec les adapters réels de Méridian.

Le script ne teste pas Bedrock : Floci répond avec un stub (ou proxifie un backend
OpenAI-compatible), donc il ne prouve ni la qualité, ni le tool use, ni les citations.
Il valide la plomberie AWS : S3, SQS, EventBridge, Scheduler, Secrets Manager
(adaptateur optionnel), KMS, CloudWatch Logs et IAM. Vault reste le coffre principal.

Prérequis :

    docker compose -f docker-compose.floci.yml up -d
    terraform -chdir=infra/floci apply -auto-approve
    backend/.venv/bin/python scripts/floci-smoke.py

Le script est idempotent : il nettoie ses objets et supprime son schedule temporaire.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "backend"))

REGION_DEFAUT = "ca-central-1"
COMPTE_DEFAUT = "000000000000"
PREFIXE_DEFAUT = "meridian"


def _client(service: str, region: str, endpoint: str):
    import boto3

    return boto3.client(
        service,
        region_name=region,
        endpoint_url=endpoint,
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )


def _attendre_health(endpoint: str, tentatives: int = 30) -> dict:
    url = f"{endpoint.rstrip('/')}/_floci/health"
    derniere: Exception | None = None
    for _ in range(tentatives):
        try:
            with urllib.request.urlopen(url, timeout=3) as reponse:
                return json.loads(reponse.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            derniere = exc
            time.sleep(1)
    raise RuntimeError(f"Floci n'est pas prêt sur {url} ({derniere})")


def _sha(graine: str) -> str:
    import hashlib

    return hashlib.sha256(graine.encode("utf-8")).hexdigest()


def _vider_file(sqs, queue_url: str, maximum: int = 10) -> int:
    supprimes = 0
    for _ in range(maximum):
        messages = sqs.receive_message(
            QueueUrl=queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=1
        ).get("Messages", [])
        if not messages:
            break
        for message in messages:
            sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"])
            supprimes += 1
    return supprimes


def executer(args: argparse.Namespace) -> int:
    os.environ.update(
        AWS_ACCESS_KEY_ID="test",
        AWS_SECRET_ACCESS_KEY="test",
        AWS_DEFAULT_REGION=args.region,
        AWS_REGION=args.region,
        AWS_ENDPOINT_URL=args.endpoint,
    )

    from meridian.adapters.outbound.aws.adapters import (
        PlanificateurEventBridge,
        PublieurEventBridge,
        PublieurSQS,
        SecretsManager,
    )
    from meridian.adapters.outbound.connectors.index_store import S3IndexStore
    from meridian.adapters.outbound.stockage.s3 import S3Stockage

    health = _attendre_health(args.endpoint)
    print(f"[ok] Floci {health.get('version', '?')} prêt ({args.endpoint})")

    s3 = _client("s3", args.region, args.endpoint)
    sqs = _client("sqs", args.region, args.endpoint)
    events = _client("events", args.region, args.endpoint)
    scheduler = _client("scheduler", args.region, args.endpoint)
    secrets = _client("secretsmanager", args.region, args.endpoint)
    logs = _client("logs", args.region, args.endpoint)
    kms = _client("kms", args.region, args.endpoint)
    iam = _client("iam", args.region, args.endpoint)

    pieces = f"{args.prefix}-pieces"
    index = f"{args.prefix}-index"
    sessions = f"{args.prefix}-sessions"
    outbox_name = f"{args.prefix}-outbox"
    wakeup_name = f"{args.prefix}-source-wakeup"
    secret_name = f"{args.prefix}/local"

    for bucket in (pieces, index, sessions):
        s3.head_bucket(Bucket=bucket)
    print(f"[ok] S3 buckets : {pieces}, {index}, {sessions}")

    task_role = iam.get_role(RoleName=f"{args.prefix}-task")["Role"]["Arn"]
    scheduler_role = iam.get_role(RoleName=f"{args.prefix}-scheduler")["Role"]["Arn"]
    print(f"[ok] IAM roles : task={task_role.rsplit('/', 1)[-1]}, scheduler={scheduler_role.rsplit('/', 1)[-1]}")

    kms_key = kms.describe_key(KeyId=f"alias/{args.prefix}-local")["KeyMetadata"]["Arn"]
    chiffre = kms.encrypt(KeyId=kms_key, Plaintext=b"meridian-floci")["CiphertextBlob"]
    clair = kms.decrypt(CiphertextBlob=chiffre)["Plaintext"]
    assert clair == b"meridian-floci"
    print(f"[ok] KMS encrypt/decrypt : {kms_key.rsplit('/', 1)[-1]}")

    async def verifier_s3():
        stockage = S3Stockage(
            pieces,
            prefixe="smoke",
            endpoint_url=args.endpoint,
            region=args.region,
            force_path_style=True,
        )
        cle = await stockage.ecrire("hello.txt", b"hello-floci", {"type_mime": "text/plain"})
        try:
            assert await stockage.lire(cle) == b"hello-floci"
        finally:
            await stockage.supprimer(cle)
        return cle

    cle = asyncio.run(verifier_s3())
    print(f"[ok] S3Stockage write/read/delete : {cle}")

    with tempfile.TemporaryDirectory(prefix="meridian-floci-index-") as dossier:
        source = Path(dossier) / "source"
        source.mkdir()
        (source / "a.txt").write_text("hello-index", encoding="utf-8")
        destination = Path(dossier) / "destination"
        sha = _sha("meridian-floci-index")
        store = S3IndexStore(
            index,
            prefix=f"{args.prefix}/index",
            endpoint=args.endpoint,
            region=args.region,
            sse="aws:kms",
            kms_key=f"alias/{args.prefix}-local",
        )
        manifeste = store.save("local", "smoke", sha, source)
        assert store.has("local", "smoke", sha)
        store.restore("local", "smoke", sha, destination)
        assert (destination / "a.txt").read_text(encoding="utf-8") == "hello-index"
        store.delete("local", "smoke", sha)
        print(f"[ok] S3IndexStore save/restore/delete : {manifeste['sha256'][:12]}…")

    outbox_url = sqs.get_queue_url(QueueName=outbox_name)["QueueUrl"]
    wakeup_url = sqs.get_queue_url(QueueName=wakeup_name)["QueueUrl"]
    wakeup_arn = sqs.get_queue_attributes(
        QueueUrl=wakeup_url, AttributeNames=["QueueArn"]
    )["Attributes"]["QueueArn"]

    _vider_file(sqs, outbox_url)
    message_id = PublieurSQS(
        outbox_url, region=args.region, endpoint=args.endpoint
    ).publier({"type": "floci.smoke", "tenant_id": "local"})
    messages = sqs.receive_message(
        QueueUrl=outbox_url, MaxNumberOfMessages=1, WaitTimeSeconds=2
    ).get("Messages", [])
    assert messages and "floci.smoke" in messages[0]["Body"]
    sqs.delete_message(QueueUrl=outbox_url, ReceiptHandle=messages[0]["ReceiptHandle"])
    print(f"[ok] SQS publish/receive/delete : {message_id}")

    event_id = PublieurEventBridge(
        bus_name=args.prefix, region=args.region, endpoint=args.endpoint
    ).publier({"type": "floci.event", "tenant_id": "local"})
    recu = []
    for _ in range(5):
        recu = sqs.receive_message(
            QueueUrl=outbox_url, MaxNumberOfMessages=10, WaitTimeSeconds=1
        ).get("Messages", [])
        if recu:
            break
    assert recu, "EventBridge n'a pas livré l'événement dans la file outbox"
    for message in recu:
        sqs.delete_message(QueueUrl=outbox_url, ReceiptHandle=message["ReceiptHandle"])
    print(f"[ok] EventBridge bus + règle outbox → SQS : {event_id}")

    planificateur = PlanificateurEventBridge(
        scheduler_role,
        wakeup_arn,
        group_name=args.prefix,
        region=args.region,
        endpoint=args.endpoint,
    )
    nom = planificateur.nom("smoke", 1)
    try:
        scheduler.delete_schedule(Name=nom, GroupName=args.prefix)
    except scheduler.exceptions.ResourceNotFoundException:
        pass
    creation = planificateur.planifier("smoke", 1, 60)
    assert creation["etat"] == "active"
    planificateur.planifier("smoke", 1, 120, etat="paused", creer=False)
    scheduler.delete_schedule(Name=nom, GroupName=args.prefix)
    print(f"[ok] EventBridge Scheduler create/update/delete : {nom}")

    jeton = SecretsManager(
        region=args.region, endpoint=args.endpoint
    ).resoudre(f"aws:{secret_name}#jeton")
    assert jeton == "meridian-local"
    print(f"[ok] Secrets Manager (adaptateur) : {secret_name}#jeton")

    flux = f"smoke-{int(time.time())}"
    logs.create_log_stream(logGroupName="/meridian/api", logStreamName=flux)
    logs.put_log_events(
        logGroupName="/meridian/api",
        logStreamName=flux,
        logEvents=[{"timestamp": int(time.time() * 1000), "message": "floci smoke"}],
    )
    print("[ok] CloudWatch Logs write")

    print("Floci validé (11/11) — plomberie AWS locale, pas une validation Bedrock.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default=os.environ.get("AWS_ENDPOINT_URL", "http://127.0.0.1:4566"))
    parser.add_argument("--region", default=os.environ.get("JUMEAU_AWS_REGION", REGION_DEFAUT))
    parser.add_argument("--prefix", default=PREFIXE_DEFAUT)
    arguments = parser.parse_args()
    try:
        return executer(arguments)
    except Exception as exc:  # noqa: BLE001 - le smoke doit afficher la cause, pas une stack brute
        print(f"[erreur] {type(exc).__name__} : {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
