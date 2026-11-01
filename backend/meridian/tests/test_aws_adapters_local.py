"""Adapters AWS exercés contre moto, le simulateur local, sans compte ni réseau réel."""
import json

import pytest

boto3 = pytest.importorskip("boto3")
pytest.importorskip("moto")

try:
    from moto import mock_aws  # noqa: F401
except ImportError:
    pytest.skip("moto>=5 requis", allow_module_level=True)

from meridian.adapters.outbound.aws import adapters as aws_adapters

REGION = "ca-central-1"
SENTINELLE = "jeton-local-moto"


@pytest.fixture
def aws(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    with mock_aws():
        yield


def _client(service):
    return boto3.client(service, region_name=REGION)


def test_secrets_manager_get_contre_moto(aws):
    secrets = _client("secretsmanager")
    secrets.create_secret(
        Name="meridian/local",
        SecretString=json.dumps({"jeton": SENTINELLE, "autre": "valeur"}),
    )
    adapter = aws_adapters.SecretsManager(client=secrets, region=REGION)

    assert adapter.resoudre("aws:meridian/local#jeton") == SENTINELLE
    assert json.loads(adapter.resoudre("secretsmanager:meridian/local")) == {
        "jeton": SENTINELLE, "autre": "valeur"}


def test_sqs_send_contre_moto(aws):
    sqs = _client("sqs")
    queue_url = sqs.create_queue(QueueName="meridian-local-ingestion")["QueueUrl"]
    publieur = aws_adapters.PublieurSQS(queue_url, client=sqs, region=REGION)

    message_id = publieur.publier_ligne({
        "id": 3, "tenant_id": "banque", "run_id": "run-local", "type": "graph.synchroniser",
        "payload": {"twins": ["tbt"]}, "cree_le": "2026-10-31T00:00:00Z", "secret": "ignore",
    })

    assert message_id
    messages = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=1)["Messages"]
    corps = json.loads(messages[0]["Body"])
    assert corps["tenant_id"] == "banque"
    assert corps["payload"] == {"twins": ["tbt"]}
    assert "secret" not in corps


def test_eventbridge_put_events_contre_moto(aws):
    events = _client("events")
    events.create_event_bus(Name="meridian-local")
    publieur = aws_adapters.PublieurEventBridge(bus_name="meridian-local", client=events, region=REGION)

    event_id = publieur.publier({"type": "graph.synchroniser", "tenant_id": "banque"})

    assert event_id


def test_scheduler_create_et_update_contre_moto(aws):
    sqs = _client("sqs")
    queue_url = sqs.create_queue(QueueName="meridian-local-scheduler")["QueueUrl"]
    queue_arn = sqs.get_queue_attributes(
        QueueUrl=queue_url, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
    scheduler = _client("scheduler")
    planificateur = aws_adapters.PlanificateurEventBridge(
        "arn:aws:iam::123456789012:role/meridian-scheduler", queue_arn,
        client=scheduler, region=REGION)

    creation = planificateur.planifier("banque", 7, 61)
    assert creation["arn"]
    schedule = scheduler.get_schedule(
        Name=creation["nom"], GroupName=planificateur.group_name)
    assert schedule["ScheduleExpression"] == "rate(2 minutes)"
    assert schedule["State"] == "ENABLED"
    assert json.loads(schedule["Target"]["Input"]) == {
        "tenant_id": "banque", "source_id": 7, "origine": "source_schedule"}

    mise_a_jour = planificateur.planifier("banque", 7, 120, etat="paused", creer=False)
    schedule = scheduler.get_schedule(
        Name=mise_a_jour["nom"], GroupName=planificateur.group_name)
    assert schedule["ScheduleExpression"] == "rate(2 minutes)"
    assert schedule["State"] == "DISABLED"
