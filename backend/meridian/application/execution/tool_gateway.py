"""Passerelle d'outils gouvernée : allowlist, politique lecture/écriture et idempotence.

Une opération de lecture s'exécute directement ; une opération d'écriture crée un effet
`PROPOSE` et une demande d'approbation, puis lève `ApprobationRequise`. Une fois approuvée,
le même appel reprend l'effet et l'exécute au plus une fois grâce à la clé
`(run_id, étape, cible, opération)`.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import quote

from meridian.application.execution.modele import (
    ApprobationRequise,
    EchecEffet,
    EffetRejete,
    ErreurTransitoire,
    OutilRefuse,
    TransitionInvalide,
)

journal = logging.getLogger("meridian.execution.gateway")

LECTURE = "lecture"
ECRITURE = "ecriture"
_METHODES_LECTURE = frozenset({"GET", "HEAD", "OPTIONS"})
ENV_ALLOWLIST = "EXECUTION_ALLOWLIST"


def _valider_allowlist(valeur: Any) -> dict:
    """Valide la forme tenant -> acteur -> outil -> {lecture/ecriture: [opérations]}."""
    if not isinstance(valeur, Mapping):
        raise ValueError(f"{ENV_ALLOWLIST} doit être un objet JSON")
    valide: dict = {}
    for tenant, acteurs in valeur.items():
        if not isinstance(tenant, str) or not tenant.strip() or not isinstance(acteurs, Mapping):
            raise ValueError(f"{ENV_ALLOWLIST} : tenant et acteurs attendus")
        valide[tenant] = {}
        for acteur, outils in acteurs.items():
            if (not isinstance(acteur, str) or not acteur.strip()
                    or not isinstance(outils, Mapping)):
                raise ValueError(f"{ENV_ALLOWLIST} : acteur et outils attendus")
            valide[tenant][acteur] = {}
            for outil, politiques in outils.items():
                if (not isinstance(outil, str) or not outil.strip()
                        or not isinstance(politiques, Mapping)):
                    raise ValueError(f"{ENV_ALLOWLIST} : outil et politiques attendus")
                valide[tenant][acteur][outil] = {}
                for politique in (LECTURE, ECRITURE):
                    operations = politiques.get(politique, ())
                    if isinstance(operations, str) or not isinstance(operations, Sequence):
                        raise ValueError(
                            f"{ENV_ALLOWLIST} : {politique} doit être une liste d'opérations")
                    if any(not isinstance(o, str) or not o.strip() for o in operations):
                        raise ValueError(f"{ENV_ALLOWLIST} : opérations non vides attendues")
                    valide[tenant][acteur][outil][politique] = tuple(operations)
                inconnues = set(politiques) - {LECTURE, ECRITURE}
                if inconnues:
                    raise ValueError(
                        f"{ENV_ALLOWLIST} : politique inconnue {sorted(inconnues)[0]!r}")
    return valide


def allowlist_depuis_env(valeur: str | None = None) -> dict:
    """Lit `EXECUTION_ALLOWLIST` (JSON) ; vide signifie « aucun outil autorisé ».

    Aucune URL n'est fournie par cette variable : les `OutilHTTP` restent définis par
    l'appelant, et un outil d'écriture n'est exécutable que si son opération figure
    explicitement dans la liste `ecriture`.
    """
    brut = os.environ.get(ENV_ALLOWLIST) if valeur is None else valeur
    if brut is None or not str(brut).strip():
        return {}
    try:
        donnees = json.loads(brut)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{ENV_ALLOWLIST} n'est pas un JSON valide") from exc
    return _valider_allowlist(donnees)


@dataclass(frozen=True)
class OutilHTTP:
    """Un outil HTTP : chaque opération associe une méthode à un chemin avec `{cible}`."""

    base_url: str
    operations: Mapping[str, tuple[str, str]]
    allowlist_hosts: Sequence[str] = ()
    timeout_s: float = 5.0


class ToolGateway:
    """Exécute les effets autorisés d'un run, avec approbation humaine pour les écritures.

    `allowlist` a la forme `tenant -> acteur -> outil -> {"lecture": (...), "ecriture": (...)}`.
    Quand elle n'est pas fournie, elle est lue depuis `EXECUTION_ALLOWLIST` ; absente ou
    vide, la passerelle refuse tout outil. Un outil d'écriture doit donc être explicitement
    autorisé dans la liste `ecriture` avant toute proposition d'effet.
    Le transport et l'adaptateur HTTP sont injectables : les tests n'ouvrent aucune connexion.
    """

    def __init__(
        self,
        connect: Callable[[], Any],
        *,
        allowlist: Mapping[str, Mapping[str, Mapping[str, Mapping[str, Sequence[str]]]]] | None = None,
        outils: Mapping[str, OutilHTTP],
        transport: Callable[..., Any] | None = None,
        timeout_s: float = 5.0,
        depot: Any = None,
        http: Any = None,
    ):
        if depot is None:
            raise ValueError("dépôt d'exécution requis")
        if http is None:
            raise ValueError("adaptateur HTTP requis")
        self.connect = connect
        self.depot = depot
        self.http = http
        self.allowlist = dict(allowlist) if allowlist is not None else allowlist_depuis_env()
        self.outils: dict[str, tuple[OutilHTTP, Callable[..., dict[str, Any]]]] = {}
        for nom, definition in outils.items():
            methodes = tuple(dict.fromkeys(
                methode for methode, _ in definition.operations.values()))
            adaptateur = self.http.creer_adaptateur_http(
                definition.base_url,
                allowlist_hosts=definition.allowlist_hosts,
                allow_methods=methodes,
                timeout_s=definition.timeout_s or timeout_s,
                transport=transport,
            )
            self.outils[nom] = (definition, adaptateur)

    @staticmethod
    def allowlist_depuis_env(valeur: str | None = None) -> dict:
        """Alias de :func:`allowlist_depuis_env` pour les appelants orientés classe."""
        return allowlist_depuis_env(valeur)

    def _avec(self, action):
        conn = self.connect()
        try:
            return action(conn)
        finally:
            close = getattr(conn, "close", None)
            if close:
                close()

    def _politique(self, tenant: str, acteur: str, outil: str, operation: str) -> str:
        acteurs = self.allowlist.get(tenant)
        if acteurs is None:
            raise OutilRefuse(f"tenant {tenant!r} non autorisé")
        outils = acteurs.get(acteur)
        if outils is None:
            raise OutilRefuse(f"acteur {acteur!r} non autorisé pour le tenant {tenant!r}")
        politiques = outils.get(outil)
        if politiques is None:
            raise OutilRefuse(f"outil {outil!r} non autorisé pour cet acteur")
        for politique in (LECTURE, ECRITURE):
            if operation in politiques.get(politique, ()):
                return politique
        raise OutilRefuse(f"opération {operation!r} non autorisée pour l'outil {outil!r}")

    def proposer(self, run: Mapping[str, Any], *, etape: str, outil: str, operation: str,
                 cible: str, payload: Mapping[str, Any] | None = None) -> dict:
        """Exécute une lecture ou propose une écriture pour le run donné."""
        if not isinstance(run, Mapping):
            raise ValueError("run doit être un mapping")
        tenant = str(run.get("tenant_id") or "")
        acteur = str(run.get("acteur") or "")
        run_id = str(run.get("run_id") or "")
        if not tenant or not acteur or not run_id:
            raise ValueError("run sans tenant_id, acteur ou run_id")
        etape, outil, operation, cible = (
            str(etape).strip(), str(outil).strip(), str(operation).strip(), str(cible).strip())
        if not etape or not outil or not operation or not cible:
            raise ValueError("étape, outil, opération et cible sont requis")
        if payload is not None and not isinstance(payload, Mapping):
            raise ValueError("payload doit être un mapping ou None")

        politique = self._politique(tenant, acteur, outil, operation)
        definition, adaptateur = self.outils.get(outil, (None, None))
        if definition is None:
            raise OutilRefuse(f"outil {outil!r} sans adaptateur configuré")
        if operation not in definition.operations:
            raise OutilRefuse(f"opération {operation!r} sans adaptateur configuré")

        commun = {
            "tenant": tenant, "acteur": acteur, "run_id": run_id, "etape": etape,
            "outil": outil, "operation": operation, "cible": cible, "payload": payload,
            "definition": definition, "adaptateur": adaptateur, "run": run,
        }
        if politique == LECTURE:
            return self._executer_lecture(**commun)
        return self._proposer_ecriture(**commun)

    def _executer_lecture(self, *, tenant: str, run_id: str, etape: str, outil: str,
                          operation: str, cible: str,
                          payload: Mapping[str, Any] | None, definition: OutilHTTP,
                          adaptateur: Callable[..., dict[str, Any]], **_: Any) -> dict:
        existant = self._avec(lambda conn: self.depot.obtenir_effet(
            conn, tenant, run_id, etape, cible, operation))
        if existant is not None:
            if existant["statut"] == "EXECUTE":
                return self.depot.effet_public(existant)
            if existant["statut"] == "REJETE":
                raise EffetRejete(f"effet rejeté : {etape}/{cible}/{operation}")
            if existant["statut"] == "PROPOSE":
                raise ApprobationRequise(run_id, etape, outil, cible, operation)
            resultat = self._appeler(definition, adaptateur, outil, operation, cible, payload)
            effet, _ = self._avec(lambda conn: self.depot.marquer_effet_execute(
                conn, tenant, run_id, etape=etape, cible=cible, operation=operation,
                resultat=resultat))
            return self.depot.effet_public(effet)

        resultat = self._appeler(definition, adaptateur, outil, operation, cible, payload)
        effet, _ = self._avec(lambda conn: self.depot.enregistrer_effet_lecture(
            conn, tenant, run_id, etape=etape, cible=cible, operation=operation,
            outil=outil, payload=payload, resultat=resultat))
        return self.depot.effet_public(effet)

    def _proposer_ecriture(self, *, tenant: str, acteur: str, run_id: str, etape: str,
                           outil: str, operation: str, cible: str,
                           payload: Mapping[str, Any] | None, definition: OutilHTTP,
                           adaptateur: Callable[..., dict[str, Any]],
                           run: Mapping[str, Any], **_: Any) -> dict:
        worker_id = run.get("bail_proprietaire")
        token = run.get("fencing_token")
        effet, _ = self._avec(lambda conn: self.depot.proposer_effet(
            conn, tenant, run_id, etape=etape, cible=cible, operation=operation,
            outil=outil, acteur=acteur, payload=payload,
            worker_id=str(worker_id) if worker_id else None,
            fencing_token=int(token) if token is not None else None,
        ))
        statut = effet["statut"]
        if statut == "PROPOSE":
            raise ApprobationRequise(run_id, etape, outil, cible, operation)
        if statut == "REJETE":
            raise EffetRejete(f"effet rejeté : {etape}/{cible}/{operation}")
        if statut == "EXECUTE":
            return self.depot.effet_public(effet)
        if statut != "APPROUVE":
            raise TransitionInvalide(f"statut d'effet inattendu : {statut}")
        try:
            resultat = self._appeler(definition, adaptateur, outil, operation, cible, payload)
        except Exception as exc:
            self._tracer_echec(tenant, run_id, etape, cible, operation, str(exc))
            raise
        effet, _ = self._avec(lambda conn: self.depot.marquer_effet_execute(
            conn, tenant, run_id, etape=etape, cible=cible, operation=operation,
            resultat=resultat))
        return self.depot.effet_public(effet)

    def _appeler(self, definition: OutilHTTP, adaptateur: Callable[..., dict[str, Any]],
                 outil: str, operation: str, cible: str,
                 payload: Mapping[str, Any] | None) -> dict[str, Any]:
        methode, modele = definition.operations[operation]
        chemin = modele.replace("{cible}", quote(cible, safe=""))
        try:
            if methode.upper() in _METHODES_LECTURE:
                options = {"params": dict(payload)} if payload else {}
                return adaptateur(methode, chemin, **options)
            return adaptateur(methode, chemin, json=dict(payload or {}))
        except self.http.HTTPRefuse as exc:
            if exc.statut in (self.http.STATUT_TIMEOUT, self.http.STATUT_TRANSPORT):
                raise ErreurTransitoire(f"{outil}.{operation} : {exc.statut}") from None
            raise EchecEffet(f"{outil}.{operation} : {exc.statut}") from None

    def _tracer_echec(self, tenant: str, run_id: str, etape: str, cible: str,
                      operation: str, erreur: str) -> None:
        try:
            self._avec(lambda conn: self.depot.marquer_effet_echec(
                conn, tenant, run_id, etape=etape, cible=cible, operation=operation,
                erreur=erreur))
        except Exception:  # noqa: BLE001 - l'échec initial reste prioritaire
            journal.exception("run %s : trace de l'échec d'effet impossible", run_id)


__all__ = ["ECRITURE", "LECTURE", "ENV_ALLOWLIST", "allowlist_depuis_env", "OutilHTTP", "ToolGateway"]
