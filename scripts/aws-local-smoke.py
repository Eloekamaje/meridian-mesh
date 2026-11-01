#!/usr/bin/env python3
"""Smoke des adapters AWS contre moto en mémoire ou un endpoint local (moto_server/LocalStack)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "backend"))

REGION_DEFAUT = "ca-central-1"


def _preparer_credentials(endpoint: str | None) -> None:
    if endpoint:
        os.environ["AWS_ACCESS_KEY_ID"] = "local"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "local"
        os.environ["AWS_SESSION_TOKEN"] = "local"
    else:
        os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
        os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
        os.environ.setdefault("AWS_SESSION_TOKEN", "testing")


def _client(service: str, region: str, endpoint: str | None):
    import boto3

    return boto3.client(service, region_name=region, endpoint_url=endpoint or None)


def executer(region: str, endpoint: str | None) -> None:
    from meridian.adapters.outbound.aws import (
        PlanificateurEventBridge,
        PublieurEventBridge,
        PublieurSQS,
        SecretsManager,
    )

    secrets = _client("secretsmanager", region, endpoint)
    sqs = _client("sqs", region, endpoint)
    events = _client("events", region, endpoint)
    scheduler = _client("scheduler", region, endpoint)

    secrets.create_secret(
        Name="meridian/local", SecretString=json.dumps({"jeton": "jeton-local"}))
    jeton = SecretsManager(client=secrets).resoudre("aws:meridian/local#jeton")
    print(f"[ok] Secrets Manager get : {jeton}")

    queue_url = sqs.create_queue(QueueName="meridian-local-ingestion")["QueueUrl"]
    message_id = PublieurSQS(queue_url, client=sqs).publier(
        {"type": "graph.synchroniser", "tenant_id": "local"})
    print(f"[ok] SQS send : {message_id}")

    events.create_event_bus(Name="meridian-local")
    event_id = PublieurEventBridge(bus_name="meridian-local", client=events).publier(
        {"type": "graph.synchroniser", "tenant_id": "local"})
    print(f"[ok] EventBridge put_events : {event_id}")

    queue_arn = sqs.get_queue_attributes(
        QueueUrl=queue_url, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
    planificateur = PlanificateurEventBridge(
        "arn:aws:iam::123456789012:role/meridian-scheduler", queue_arn,
        client=scheduler, region=region)
    creation = planificateur.planifier("local", 1, 60)
    mise_a_jour = planificateur.planifier("local", 1, 120, etat="paused", creer=False)
    print(f"[ok] Scheduler create : {creation['nom']} ({creation['etat']})")
    print(f"[ok] Scheduler update : {mise_a_jour['nom']} ({mise_a_jour['etat']})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", help="endpoint local, ex. http://127.0.0.1:5000")
    parser.add_argument("--region", default=os.environ.get("JUMEAU_AWS_REGION", REGION_DEFAUT))
    arguments = parser.parse_args()

    _preparer_credentials(arguments.endpoint)
    if arguments.endpoint:
        executer(arguments.region, arguments.endpoint)
        print("Harness local validé (4/4) via", arguments.endpoint)
        return 0

    try:
        from moto import mock_aws
    except ImportError:
        print("moto absent : backend/.venv/bin/pip install 'moto[server]>=5,<6'", file=sys.stderr)
        return 2
    with mock_aws():
        executer(arguments.region, None)
    print("Harness local validé (4/4) via moto en mémoire")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
