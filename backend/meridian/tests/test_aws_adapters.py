"""Adapters AWS : secrets, publication outbox et scheduler, testés avec des clients factices, sans réseau."""
import json
import sys

import pytest

from meridian.adapters.outbound.connectors import auth_source
from meridian.adapters.outbound.aws import adapters as aws_adapters

SENTINELLE = "valeur-secrete-a-ne-jamais-fuiter"


class ErreurService(Exception):
    def __init__(self, code="AccessDeniedException", message=SENTINELLE):
        super().__init__(message)
        self.response = {"Error": {"Code": code, "Message": message}}


class FauxSecrets:
    def __init__(self, valeur=None, erreur=None):
        self.valeur = valeur if valeur is not None else json.dumps({"jeton": SENTINELLE})
        self.erreur = erreur
        self.appels = []

    def get_secret_value(self, SecretId):
        self.appels.append(SecretId)
        if self.erreur is not None:
            raise self.erreur
        return {"SecretString": self.valeur}


class FauxSQS:
    def __init__(self, erreur=None):
        self.erreur = erreur
        self.appels = []

    def send_message(self, **arguments):
        self.appels.append(arguments)
        if self.erreur is not None:
            raise self.erreur
        return {"MessageId": "msg-1"}


class FauxEvenements:
    def __init__(self, echecs=0):
        self.echecs = echecs
        self.appels = []

    def put_events(self, Entries):
        self.appels.append(Entries)
        return {"FailedEntryCount": self.echecs, "Entries": [{"EventId": "evt-1"}]}


class FauxScheduler:
    def __init__(self, erreur=None):
        self.erreur = erreur
        self.creations = []
        self.mises_a_jour = []

    def create_schedule(self, **arguments):
        self.creations.append(arguments)
        if self.erreur is not None:
            raise self.erreur
        return {"ScheduleArn": "arn:aws:scheduler:::schedule/meridian"}

    def update_schedule(self, **arguments):
        self.mises_a_jour.append(arguments)
        if self.erreur is not None:
            raise self.erreur
        return {"ScheduleArn": "arn:aws:scheduler:::schedule/meridian"}


def test_secrets_manager_resout_la_valeur_et_un_champ():
    client = FauxSecrets(json.dumps({"jeton": SENTINELLE, "autre": "x"}))
    adapter = aws_adapters.SecretsManager(client=client)

    assert adapter.resoudre("aws:meridian/git#jeton") == SENTINELLE
    assert adapter.resoudre("secretsmanager:meridian/git") == json.dumps(
        {"jeton": SENTINELLE, "autre": "x"})
    assert adapter.resoudre("") is None
    assert client.appels == ["meridian/git", "meridian/git"]
    assert adapter.mode == "aws-secrets-manager"


def test_secrets_manager_mappe_les_echecs_sans_fuite():
    adapter = aws_adapters.SecretsManager(client=FauxSecrets(erreur=ErreurService()))
    with pytest.raises(aws_adapters.SecretIntrouvable) as exc:
        adapter.resoudre("aws:meridian/git#jeton")
    assert "AccessDeniedException" in str(exc.value)
    assert SENTINELLE not in str(exc.value)

    for reference in ("vault:meridian/git#jeton", "aws:", "aws:meridian/git#"):
        with pytest.raises(aws_adapters.SecretIntrouvable):
            adapter.resoudre(reference)
    with pytest.raises(aws_adapters.SecretIntrouvable):
        aws_adapters.SecretsManager(client=FauxSecrets(json.dumps({"autre": "x"}))).resoudre(
            "aws:meridian/git#jeton")


def test_secrets_manager_sans_sdk_est_une_configuration_manquante(monkeypatch):
    monkeypatch.setitem(sys.modules, "boto3", None)
    with pytest.raises(aws_adapters.ConfigurationAWS):
        aws_adapters.SecretsManager().resoudre("aws:meridian/git#jeton")


def test_pat_source_resout_une_reference_aws(monkeypatch):
    monkeypatch.setattr(
        aws_adapters, "secrets_depuis_env",
        lambda env=None, client=None: aws_adapters.SecretsManager(client=FauxSecrets()),
    )
    source = auth_source.depuis_config({"auth_mode": "pat", "secret_ref": "aws:meridian/git#jeton"})
    assert source.token() == SENTINELLE


def test_sqs_publie_une_ligne_outbox_et_le_groupe_fifo():
    client = FauxSQS()
    publieur = aws_adapters.PublieurSQS("https://sqs.local/queue.fifo", client=client)
    ligne = {"id": 3, "tenant_id": "banque", "run_id": "run-1", "type": "graph.synchroniser",
             "payload": {"twins": ["tbt"]}, "cree_le": "2026-10-31T00:00:00Z", "secret": "ignore"}

    assert publieur.publier_ligne(ligne) == "msg-1"
    arguments = client.appels[0]
    assert arguments["QueueUrl"] == "https://sqs.local/queue.fifo"
    assert arguments["MessageGroupId"] == "meridian"
    corps = json.loads(arguments["MessageBody"])
    assert corps["tenant_id"] == "banque" and corps["payload"] == {"twins": ["tbt"]}
    assert "secret" not in corps
    assert list(publieur.publieurs(["graph.synchroniser"])) == ["graph.synchroniser"]


def test_sqs_refuse_une_configuration_absente():
    with pytest.raises(aws_adapters.ConfigurationAWS):
        aws_adapters.PublieurSQS("")
    with pytest.raises(aws_adapters.ConfigurationAWS):
        aws_adapters.publieur_depuis_env({})


def test_sqs_mappe_un_refus_de_publication_sans_fuite():
    publieur = aws_adapters.PublieurSQS(
        "https://sqs.local/queue", client=FauxSQS(erreur=ErreurService("ThrottlingException")))
    with pytest.raises(aws_adapters.PublicationRefusee) as exc:
        publieur.publier({"type": "graph.synchroniser", "tenant_id": "banque"})
    assert "ThrottlingException" in str(exc.value)
    assert SENTINELLE not in str(exc.value)


def test_eventbridge_publie_et_mappe_les_entrees_refusees():
    client = FauxEvenements()
    publieur = aws_adapters.PublieurEventBridge(bus_name="meridian", client=client)
    assert publieur.publier({"type": "graph.synchroniser", "tenant_id": "banque"}) == "evt-1"
    entree = client.appels[0][0]
    assert entree["EventBusName"] == "meridian" and entree["DetailType"] == "graph.synchroniser"
    assert json.loads(entree["Detail"])["tenant_id"] == "banque"

    with pytest.raises(aws_adapters.PublicationRefusee):
        aws_adapters.PublieurEventBridge(client=FauxEvenements(echecs=1)).publier({"type": "x"})


def test_scheduler_traduit_source_schedule_sans_secret():
    client = FauxScheduler()
    planificateur = aws_adapters.PlanificateurEventBridge(
        "arn:aws:iam::123:role/scheduler", "arn:aws:sqs:ca-central-1:123:ingestion", client=client)

    resultat = planificateur.planifier("banque", 7, 61)
    requete = client.creations[0]
    assert resultat["nom"] == requete["Name"] and resultat["etat"] == "active"
    assert requete["ScheduleExpression"] == "rate(2 minutes)"
    assert requete["State"] == "ENABLED"
    assert requete["FlexibleTimeWindow"] == {"Mode": "OFF"}
    assert json.loads(requete["Target"]["Input"]) == {
        "tenant_id": "banque", "source_id": 7, "origine": "source_schedule"}
    assert planificateur.requete("banque", 7, 60, etat="paused")["State"] == "DISABLED"
    assert "secret" not in json.dumps(requete).lower()


def test_scheduler_refuse_une_configuration_ou_un_intervalle_invalide():
    with pytest.raises(aws_adapters.ConfigurationAWS):
        aws_adapters.PlanificateurEventBridge(None, "arn:target")
    with pytest.raises(aws_adapters.ConfigurationAWS):
        aws_adapters.planificateur_depuis_env({})
    with pytest.raises(ValueError):
        aws_adapters.PlanificateurEventBridge("role", "target").expression(0)


def test_scheduler_mappe_un_refus_sans_fuite():
    planificateur = aws_adapters.PlanificateurEventBridge(
        "role", "target", client=FauxScheduler(erreur=ErreurService("ConflictException")))
    with pytest.raises(aws_adapters.PlanificationRefusee) as exc:
        planificateur.planifier("banque", 7, 60)
    assert "ConflictException" in str(exc.value)
    assert SENTINELLE not in str(exc.value)
