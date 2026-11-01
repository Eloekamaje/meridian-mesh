"""Adapters AWS optionnels derrière des ports étroits : Secrets Manager, SQS/EventBridge et Scheduler.

Aucun SDK AWS n'est importé à l'import du module : boto3 n'est chargé qu'au premier appel réel. Les tests
injectent un client factice, sans réseau ni credentials. Les erreurs ne recopient jamais une valeur de secret,
une URL de dépôt ni un emplacement de source.

Mapping ``source_schedule`` → EventBridge Scheduler :

- ``intervalle_s`` → ``rate(<n> minutes)`` avec ``n = ceil(secondes / 60)``, minimum 1 ;
- ``etat = active|paused`` → ``State = ENABLED|DISABLED`` ;
- ``tenant_id`` / ``source_id`` → nom de schedule déterministe et ``Target.Input`` JSON ;
- ``next_run_at`` reste tenu par Postgres : le schedule AWS ne fait que réveiller le worker, il n'est pas la
  source de vérité des runs.

Références de secret acceptées par l'adapter Secrets Manager : ``aws:<secret-id>#<champ>`` ou
``secretsmanager:<secret-id>#<champ>``. Sans ``#champ``, la valeur ``SecretString`` est rendue telle quelle ;
avec un champ, la valeur doit être un objet JSON et seul ce champ est rendu.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from typing import Any, Mapping, Protocol, runtime_checkable

PREFIXES_SECRET = ("aws:", "secretsmanager:")
_REFERENCE_SECRET = re.compile(
    r"(?:aws|secretsmanager):(?P<id>[A-Za-z0-9/_+=.@:-]{1,512})(?:#(?P<cle>[A-Za-z0-9._-]{1,128}))?\Z",
    re.IGNORECASE,
)
_ETATS_SCHEDULE = {"active": "ENABLED", "paused": "DISABLED"}


class ErreurAdapterAWS(RuntimeError):
    """Échec d'un adapter AWS, déjà traduit en erreur de port (aucun détail sensible)."""


class ConfigurationAWS(ErreurAdapterAWS, ValueError):
    """Configuration AWS absente ou SDK indisponible."""


class SecretIntrouvable(ErreurAdapterAWS, LookupError):
    """Secret AWS absent, refusé, mal formé ou sans le champ demandé."""


class PublicationRefusee(ErreurAdapterAWS):
    """Publication SQS/EventBridge refusée par le service."""


class PlanificationRefusee(ErreurAdapterAWS):
    """Création ou mise à jour d'un schedule EventBridge refusée."""


AwsAdapterError = ErreurAdapterAWS
AwsConfigurationError = ConfigurationAWS
SecretNotFoundError = SecretIntrouvable
PublishError = PublicationRefusee
ScheduleError = PlanificationRefusee


@runtime_checkable
class PortSecrets(Protocol):
    def resoudre(self, reference: str) -> str | None: ...


@runtime_checkable
class PortPublication(Protocol):
    def publier(self, evenement: Mapping[str, Any]) -> str | None: ...


@runtime_checkable
class PortPlanificateur(Protocol):
    def planifier(self, tenant_id: str, source_id: int, intervalle_s: int, *,
                  etat: str = "active") -> dict[str, Any]: ...


def _texte(valeur: Any) -> str:
    return str(valeur or "").strip()


def est_reference_secret_aws(reference: Any) -> bool:
    """Vrai pour une référence destinée à Secrets Manager, jamais pour ``env:``/``vault:``."""
    return _texte(reference).lower().startswith(PREFIXES_SECRET)


def _motif(exc: Exception) -> str:
    """Code d'erreur AWS s'il est sûr, sinon le type Python : jamais le message brut du service."""
    reponse = getattr(exc, "response", None)
    if isinstance(reponse, Mapping):
        code = (reponse.get("Error") or {}).get("Code")
        if isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", code):
            return code
    return type(exc).__name__


def _client(service: str, client: Any = None, *, region: str | None = None,
            endpoint: str | None = None) -> Any:
    """Client injecté, sinon boto3 chargé paresseusement ; aucun appel réseau ici."""
    if client is not None:
        return client
    try:
        import boto3
    except ImportError:
        raise ConfigurationAWS(f"boto3 requis pour l'adapter AWS {service}") from None
    try:
        return boto3.client(service, region_name=region or None, endpoint_url=endpoint or None)
    except Exception as exc:  # noqa: BLE001 - l'erreur de configuration ne doit pas fuiter de credentials
        raise ConfigurationAWS(f"client AWS {service} non configuré ({type(exc).__name__})") from None


class SecretsManager:
    """Port de résolution des secrets : rend seulement la valeur au appelant, jamais dans un log."""

    mode = "aws-secrets-manager"

    def __init__(self, client: Any = None, region: str | None = None, endpoint: str | None = None):
        self.region = _texte(region) or None
        self.endpoint = _texte(endpoint) or None
        self._client = client

    def _secrets(self) -> Any:
        if self._client is None:
            self._client = _client("secretsmanager", None, region=self.region, endpoint=self.endpoint)
        return self._client

    def resoudre(self, reference: str | None) -> str | None:
        if not reference:
            return None
        correspondance = _REFERENCE_SECRET.fullmatch(_texte(reference))
        if correspondance is None:
            raise SecretIntrouvable("référence de secret AWS invalide")
        identifiant = correspondance.group("id")
        cle = correspondance.group("cle")
        try:
            reponse = self._secrets().get_secret_value(SecretId=identifiant)
        except ConfigurationAWS:
            raise
        except Exception as exc:  # noqa: BLE001 - traduit en erreur de port, sans message brut
            raise SecretIntrouvable(f"secret AWS introuvable ou refusé ({_motif(exc)})") from None
        valeur = reponse.get("SecretString") if isinstance(reponse, Mapping) else None
        if valeur is None:
            raise SecretIntrouvable("secret AWS sans SecretString")
        if cle:
            try:
                donnees = json.loads(valeur)
            except (TypeError, ValueError):
                raise SecretIntrouvable("secret AWS non JSON pour un champ demandé") from None
            if not isinstance(donnees, Mapping) or cle not in donnees:
                raise SecretIntrouvable("champ absent du secret AWS")
            valeur = donnees[cle]
        if valeur is None:
            raise SecretIntrouvable("valeur de secret AWS vide")
        return str(valeur)

    resoudre_secret = resoudre
    __call__ = resoudre


class PublieurSQS:
    """Port de publication durable : une ligne d'outbox devient un message SQS JSON."""

    mode = "aws-sqs"

    def __init__(self, queue_url: str | None, client: Any = None, region: str | None = None,
                 endpoint: str | None = None, message_group_id: str = "meridian"):
        self.queue_url = _texte(queue_url)
        if not self.queue_url:
            raise ConfigurationAWS("JUMEAU_SQS_QUEUE_URL requis")
        self.fifo = self.queue_url.endswith(".fifo")
        self.message_group_id = _texte(message_group_id) or "meridian"
        self.region = _texte(region) or None
        self.endpoint = _texte(endpoint) or None
        self._client = client

    def _sqs(self) -> Any:
        if self._client is None:
            self._client = _client("sqs", None, region=self.region, endpoint=self.endpoint)
        return self._client

    def publier(self, evenement: Mapping[str, Any]) -> str | None:
        if not isinstance(evenement, Mapping):
            raise ValueError("événement SQS : un mapping est requis")
        arguments: dict[str, Any] = {
            "QueueUrl": self.queue_url,
            "MessageBody": json.dumps(dict(evenement), ensure_ascii=False, sort_keys=True, default=str),
        }
        if self.fifo:
            arguments["MessageGroupId"] = self.message_group_id
        try:
            reponse = self._sqs().send_message(**arguments)
        except ConfigurationAWS:
            raise
        except Exception as exc:  # noqa: BLE001 - traduit en erreur de port
            raise PublicationRefusee(f"publication SQS refusée ({_motif(exc)})") from None
        return reponse.get("MessageId") if isinstance(reponse, Mapping) else None

    def publier_ligne(self, ligne: Mapping[str, Any]) -> str | None:
        """Adapte une ligne ``execution_outbox`` au message publié, sans bail ni secret."""
        if not isinstance(ligne, Mapping):
            raise ValueError("ligne d'outbox : un mapping est requis")
        evenement = {champ: ligne.get(champ)
                     for champ in ("id", "tenant_id", "run_id", "type", "payload", "cree_le")}
        return self.publier(evenement)

    def publieurs(self, types: Any) -> dict[str, Any]:
        """Mapping ``type -> publieur`` pour ``DispatcherOutbox``, limité aux types choisis."""
        return {str(type_): self.publier_ligne for type_ in types}

    __call__ = publier_ligne


class PublieurEventBridge:
    """Port de publication durable via EventBridge, même contrat que :class:`PublieurSQS`."""

    mode = "aws-eventbridge"

    def __init__(self, bus_name: str = "default", source: str = "meridian", client: Any = None,
                 region: str | None = None, endpoint: str | None = None):
        self.bus_name = _texte(bus_name) or "default"
        self.source = _texte(source) or "meridian"
        self.region = _texte(region) or None
        self.endpoint = _texte(endpoint) or None
        self._client = client

    def _events(self) -> Any:
        if self._client is None:
            self._client = _client("events", None, region=self.region, endpoint=self.endpoint)
        return self._client

    def publier(self, evenement: Mapping[str, Any], detail_type: str | None = None) -> str | None:
        if not isinstance(evenement, Mapping):
            raise ValueError("événement EventBridge : un mapping est requis")
        entree = {
            "Source": self.source,
            "DetailType": _texte(detail_type) or _texte(evenement.get("type")) or "meridian.event",
            "Detail": json.dumps(dict(evenement), ensure_ascii=False, sort_keys=True, default=str),
            "EventBusName": self.bus_name,
        }
        try:
            reponse = self._events().put_events(Entries=[entree])
        except ConfigurationAWS:
            raise
        except Exception as exc:  # noqa: BLE001 - traduit en erreur de port
            raise PublicationRefusee(f"publication EventBridge refusée ({_motif(exc)})") from None
        if not isinstance(reponse, Mapping) or reponse.get("FailedEntryCount"):
            raise PublicationRefusee("publication EventBridge refusée (entrée refusée)")
        entrees = reponse.get("Entries") or []
        return entrees[0].get("EventId") if entrees and isinstance(entrees[0], Mapping) else None

    def publier_ligne(self, ligne: Mapping[str, Any]) -> str | None:
        if not isinstance(ligne, Mapping):
            raise ValueError("ligne d'outbox : un mapping est requis")
        evenement = {champ: ligne.get(champ)
                     for champ in ("id", "tenant_id", "run_id", "type", "payload", "cree_le")}
        return self.publier(evenement)

    def publieurs(self, types: Any) -> dict[str, Any]:
        return {str(type_): self.publier_ligne for type_ in types}

    __call__ = publier_ligne


class PlanificateurEventBridge:
    """Port scheduler : traduit ``source_schedule`` en schedule EventBridge, sans devenir la vérité."""

    mode = "aws-eventbridge-scheduler"

    def __init__(self, role_arn: str | None, target_arn: str | None, group_name: str = "default",
                 prefix: str = "meridian-source", client: Any = None, region: str | None = None,
                 endpoint: str | None = None):
        self.role_arn = _texte(role_arn)
        self.target_arn = _texte(target_arn)
        if not self.role_arn or not self.target_arn:
            raise ConfigurationAWS("JUMEAU_SCHEDULER_ROLE_ARN et JUMEAU_SCHEDULER_TARGET_ARN requis")
        self.group_name = _texte(group_name) or "default"
        self.prefix = _texte(prefix) or "meridian-source"
        self.region = _texte(region) or None
        self.endpoint = _texte(endpoint) or None
        self._client = client

    def _scheduler(self) -> Any:
        if self._client is None:
            self._client = _client("scheduler", None, region=self.region, endpoint=self.endpoint)
        return self._client

    @staticmethod
    def expression(intervalle_s: int) -> str:
        if isinstance(intervalle_s, bool):
            raise ValueError("intervalle_s doit être un entier positif")
        try:
            secondes = int(intervalle_s)
        except (TypeError, ValueError):
            raise ValueError("intervalle_s doit être un entier positif") from None
        if secondes <= 0:
            raise ValueError("intervalle_s doit être un entier positif")
        return f"rate({max(1, math.ceil(secondes / 60))} minutes)"

    def nom(self, tenant_id: str, source_id: int) -> str:
        tenant = _texte(tenant_id)
        identifiant = _texte(source_id)
        if not tenant or not identifiant:
            raise ValueError("tenant_id et source_id requis")
        base = re.sub(r"[^A-Za-z0-9_-]+", "-", f"{self.prefix}-{tenant}-{identifiant}").strip("-")
        digest = hashlib.sha256(f"{tenant}\0{identifiant}".encode("utf-8")).hexdigest()[:10]
        return f"{(base or self.prefix)[:48]}-{digest}"[:64]

    def requete(self, tenant_id: str, source_id: int, intervalle_s: int, *, etat: str = "active") -> dict:
        if etat not in _ETATS_SCHEDULE:
            raise ValueError(f"état de schedule inconnu : {etat!r}")
        entree = json.dumps({"tenant_id": _texte(tenant_id), "source_id": int(source_id),
                             "origine": "source_schedule"}, ensure_ascii=False, sort_keys=True)
        return {
            "Name": self.nom(tenant_id, source_id),
            "GroupName": self.group_name,
            "ScheduleExpression": self.expression(intervalle_s),
            "State": _ETATS_SCHEDULE[etat],
            "FlexibleTimeWindow": {"Mode": "OFF"},
            "Target": {"Arn": self.target_arn, "RoleArn": self.role_arn, "Input": entree},
        }

    def planifier(self, tenant_id: str, source_id: int, intervalle_s: int, *, etat: str = "active",
                  creer: bool = True) -> dict[str, Any]:
        requete = self.requete(tenant_id, source_id, intervalle_s, etat=etat)
        action = self._scheduler().create_schedule if creer else self._scheduler().update_schedule
        try:
            reponse = action(**requete)
        except ConfigurationAWS:
            raise
        except Exception as exc:  # noqa: BLE001 - traduit en erreur de port
            raise PlanificationRefusee(f"planification EventBridge refusée ({_motif(exc)})") from None
        return {"nom": requete["Name"], "arn": reponse.get("ScheduleArn")
                if isinstance(reponse, Mapping) else None, "etat": etat}

    def suspendre(self, tenant_id: str, source_id: int, *, intervalle_s: int = 3600) -> dict[str, Any]:
        return self.planifier(tenant_id, source_id, intervalle_s, etat="paused", creer=False)

    def reprendre(self, tenant_id: str, source_id: int, *, intervalle_s: int = 3600) -> dict[str, Any]:
        return self.planifier(tenant_id, source_id, intervalle_s, etat="active", creer=False)

    appliquer = planifier


def _region(env: Mapping[str, str]) -> str | None:
    return (_texte(env.get("JUMEAU_AWS_REGION") or env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION"))
            or None)


def secrets_depuis_env(env: Mapping[str, str] | None = None, client: Any = None) -> SecretsManager:
    env = os.environ if env is None else env
    return SecretsManager(
        client=client,
        region=_region(env),
        endpoint=(_texte(env.get("AWS_ENDPOINT_URL_SECRETS_MANAGER") or env.get("AWS_ENDPOINT_URL")) or None),
    )


def publieur_depuis_env(env: Mapping[str, str] | None = None, client: Any = None) -> PublieurSQS | PublieurEventBridge:
    """SQS si une file est configurée, sinon EventBridge si un bus l'est."""
    env = os.environ if env is None else env
    queue = _texte(env.get("JUMEAU_SQS_QUEUE_URL") or env.get("AWS_SQS_QUEUE_URL"))
    if queue:
        return PublieurSQS(
            queue, client=client, region=_region(env),
            endpoint=(_texte(env.get("AWS_ENDPOINT_URL_SQS") or env.get("AWS_ENDPOINT_URL")) or None),
        )
    bus = _texte(env.get("JUMEAU_EVENTBRIDGE_BUS") or env.get("JUMEAU_EVENTBRIDGE_BUS_NAME"))
    if bus:
        return PublieurEventBridge(
            bus, client=client, region=_region(env),
            endpoint=(_texte(env.get("AWS_ENDPOINT_URL_EVENTS") or env.get("AWS_ENDPOINT_URL")) or None),
        )
    raise ConfigurationAWS("JUMEAU_SQS_QUEUE_URL ou JUMEAU_EVENTBRIDGE_BUS requis")


def planificateur_depuis_env(env: Mapping[str, str] | None = None,
                             client: Any = None) -> PlanificateurEventBridge:
    env = os.environ if env is None else env
    return PlanificateurEventBridge(
        role_arn=env.get("JUMEAU_SCHEDULER_ROLE_ARN") or env.get("AWS_SCHEDULER_ROLE_ARN"),
        target_arn=env.get("JUMEAU_SCHEDULER_TARGET_ARN") or env.get("AWS_SCHEDULER_TARGET_ARN"),
        group_name=env.get("JUMEAU_SCHEDULER_GROUP") or "default",
        prefix=env.get("JUMEAU_SCHEDULER_PREFIX") or "meridian-source",
        client=client,
        region=_region(env),
        endpoint=(_texte(env.get("AWS_ENDPOINT_URL_SCHEDULER") or env.get("AWS_ENDPOINT_URL")) or None),
    )


SecretsManagerAdapter = SecretsManager
SqsPublisher = PublieurSQS
EventBridgePublisher = PublieurEventBridge
EventBridgeScheduler = PlanificateurEventBridge
secrets_from_env = secrets_depuis_env
publisher_from_env = publieur_depuis_env
scheduler_from_env = planificateur_depuis_env
