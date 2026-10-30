"""Harness capacitaire de Flore (ADR-0004) : registre d'outils, adaptateurs et audit en mémoire.

Le harness ne connaît aucun outil codé en dur : il relie un `RegistreCapacites` à une table de callables déclarés.
Il expose uniquement les manifestes visibles pour la portée demandée, refuse tout nom hors manifeste, borne les
appels, applique un timeout aux callables asynchrones et journalise chaque tentative. Aucun code arbitraire n'est
chargé ou évalué, et aucune entrée/sortie réseau n'est effectuée ici.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable, Mapping
import copy
import inspect
import json
import re
import time
from typing import Any

from strands.tools.tools import AgentTool
from strands.types._events import ToolResultEvent

from jumeau.capacites import ManifesteOutil, RegistreCapacites

_JOUR = 500
_MAX_PROFONDEUR = 8
_CLE_SENSIBLE = (
    r"(?i)(?:api[_-]?key|apikey|access[_-]?token|auth[_-]?token|client[_-]?secret|"
    r"password|passwd|mot[_-]?de[_-]?passe|secret|token|authorization|bearer|credential|"
    r"private[_-]?key|signature|session[_-]?id|cookie)"
)
_JETON_SENSIBLE = (
    r"(?i)(?:\bbearer\s+[A-Za-z0-9_.~+/=-]{12,}|\bsk-[A-Za-z0-9_-]{8,}|"
    r"\bgh[pousr]_[A-Za-z0-9]{10,}|\bxox[baprs]-[A-Za-z0-9-]{10,})"
)
_AFFECTATION_SENSIBLE = (
    r"(?i)(?:api[_-]?key|apikey|access[_-]?token|auth[_-]?token|client[_-]?secret|"
    r"password|passwd|mot[\s_-]*de[\s_-]*passe|secret|token)\s*[:=]\s*['\"]?[A-Za-z0-9_./+~-]{6,}"
)


class ErreurHarness(Exception):
    """Erreur de politique ou d'exécution du harness."""


class OutilNonEnregistre(KeyError, ErreurHarness):
    """Le nom demandé ne correspond à aucun manifeste exécutable du registre."""


class OutilNonApprouve(PermissionError, ErreurHarness):
    """Le manifeste déclare une écriture qui n'a pas été approuvée pour ce harness."""


OutilInconnu = OutilNonEnregistre
EcritureNonApprouvee = OutilNonApprouve

_SCHEMA_RECHERCHER_ENTREE = {
    "type": "object",
    "properties": {
        "requete": {
            "type": "string",
            "description": "capacité, nom d'outil ou objet d'entreprise recherché",
        },
        "capacite": {
            "type": ["string", "null"],
            "description": "capacité d'entreprise pour restreindre la recherche",
        },
    },
    "required": ["requete"],
    "additionalProperties": False,
}
_SCHEMA_RECHERCHER_SORTIE = {
    "type": "object",
    "properties": {
        "statut": {"type": "string"},
        "requete": {"type": "string"},
        "capacites": {"type": "array", "items": {"type": "string"}},
        "outils": {"type": "array", "items": {"type": "object"}},
    },
    "required": ["statut", "requete", "capacites", "outils"],
    "additionalProperties": False,
}
_SCHEMA_DECRIRE_ENTREE = {
    "type": "object",
    "properties": {
        "nom": {"type": "string", "description": "nom stable de l'outil à décrire"},
    },
    "required": ["nom"],
    "additionalProperties": False,
}
_SCHEMA_DECRIRE_SORTIE = {
    "type": "object",
    "properties": {
        "statut": {"type": "string"},
        "nom": {"type": "string"},
        "version": {"type": "string"},
        "description": {"type": "string"},
        "capacite": {"type": "string"},
        "schema_entree": {"type": ["object", "boolean"]},
        "schema_sortie": {"type": ["object", "boolean"]},
        "portee": {"type": "object"},
    },
    "required": ["statut", "nom"],
    "additionalProperties": True,
}


def manifestes_decouverte() -> list[ManifesteOutil]:
    """Les deux contrats read-only de découverte, ajoutés au catalogue par le harness."""
    return [
        ManifesteOutil(
            nom="rechercher_outil",
            version="1.0.0",
            description=(
                "Recherche dans le catalogue capacitaire les outils visibles pour la portée courante, sans en "
                "exécuter aucun."
            ),
            capacite="chercher_outil",
            types_objets_lus=("ManifesteOutil",),
            schema_entree=_SCHEMA_RECHERCHER_ENTREE,
            schema_sortie=_SCHEMA_RECHERCHER_SORTIE,
            lecture_seule=True,
            timeout_ms=2000,
            mode_preuve="DECLARED",
            source="builtin",
            allowlist=("meridian.builtin",),
        ),
        ManifesteOutil(
            nom="decrire_outil",
            version="1.0.0",
            description=(
                "Décrit le contrat d'un outil visible : capacité, schémas d'entrée et de sortie, portée et "
                "lecture seule, sans exécuter l'outil."
            ),
            capacite="chercher_outil",
            types_objets_lus=("ManifesteOutil",),
            schema_entree=_SCHEMA_DECRIRE_ENTREE,
            schema_sortie=_SCHEMA_DECRIRE_SORTIE,
            lecture_seule=True,
            timeout_ms=2000,
            mode_preuve="DECLARED",
            source="builtin",
            allowlist=("meridian.builtin",),
        ),
    ]


def _json(valeur: Any) -> str:
    return json.dumps(valeur, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _texte_expurge(valeur: str) -> str:
    texte = " ".join(str(valeur).split())
    if re.search(_JETON_SENSIBLE, texte) or re.search(_AFFECTATION_SENSIBLE, texte):
        return "***"
    return texte[:_JOUR]


def expurger(valeur: Any, cle: Any = None, profondeur: int = 0) -> Any:
    """Copie JSON-safe d'une valeur, clés et jetons sensibles remplacés par « *** »."""
    if profondeur > _MAX_PROFONDEUR:
        return "[…]"
    if cle is not None and re.search(_CLE_SENSIBLE, str(cle)):
        return "***"
    if valeur is None or isinstance(valeur, (bool, int)):
        return valeur
    if isinstance(valeur, float):
        return valeur if valeur == valeur and valeur not in (float("inf"), float("-inf")) else str(valeur)
    if isinstance(valeur, str):
        return _texte_expurge(valeur)
    if isinstance(valeur, Mapping):
        return {
            str(nom): expurger(contenu, nom, profondeur + 1)
            for nom, contenu in valeur.items()
        }
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return [expurger(contenu, None, profondeur + 1) for contenu in valeur]
    return _texte_expurge(str(valeur))


_expurger = expurger


def _secondes(timeout_ms: Any) -> float:
    if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, (int, float)) or timeout_ms <= 0:
        raise ValueError("timeout_ms : entier positif attendu")
    return max(1.0, float(timeout_ms)) / 1000.0


def _duree(debut: float) -> float:
    return round((time.perf_counter() - debut) * 1000.0, 3)


def _arguments(arguments: Any) -> dict:
    if arguments is None:
        return {}
    if not isinstance(arguments, Mapping):
        raise ValueError("arguments : objet attendu")
    return dict(arguments)


def _lier(callback: Callable, arguments: Mapping) -> dict:
    """Valide les arguments contre la signature du callable, sans appeler l'outil."""
    signature = inspect.signature(callback)
    valeurs: dict[str, Any] = {}
    for nom, parametre in signature.parameters.items():
        if parametre.kind is inspect.Parameter.VAR_KEYWORD:
            contenu = arguments.get(nom)
            if contenu is None:
                for cle, valeur in arguments.items():
                    valeurs.setdefault(cle, valeur)
            elif isinstance(contenu, Mapping):
                valeurs.update(contenu)
            continue
        if parametre.kind is inspect.Parameter.VAR_POSITIONAL:
            continue
        if nom in arguments:
            valeurs[nom] = arguments[nom]
        elif parametre.default is not inspect.Parameter.empty:
            continue
        else:
            raise ValueError(f"argument manquant : {nom}")
    inconnus = set(arguments) - set(signature.parameters)
    if inconnus and not any(
        parametre.kind is inspect.Parameter.VAR_KEYWORD
        for parametre in signature.parameters.values()
    ):
        raise ValueError("argument inconnu")
    return valeurs


def _consommer(tache: Any) -> None:
    """Consomme l'exception éventuelle d'une écriture d'audit asynchrone, sans bruit ni blocage."""
    if tache.cancelled():
        return
    try:
        tache.exception()
    except Exception:
        return


def _invoquer(callback: Callable, arguments: Mapping) -> Any:
    """Appelle l'adaptateur avec les arguments nommés, ou avec le dictionnaire si son unique paramètre l'attend."""
    parametres = list(inspect.signature(callback).parameters.values())
    positionnels = [
        parametre
        for parametre in parametres
        if parametre.kind in (inspect.Parameter.POSITIONAL_ONLY,
                              inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    accepte_nommes = any(
        parametre.kind is inspect.Parameter.VAR_KEYWORD for parametre in parametres
    )
    if (not accepte_nommes and len(positionnels) == 1
            and positionnels[0].name in ("arguments", "args", "payload", "parametres", "params")
            and positionnels[0].name not in arguments):
        return callback(dict(arguments))
    return callback(**arguments)


class _OutilHarness(AgentTool):
    """Adaptateur Strands d'un manifeste : la seule voie d'exécution est `Harness.appeler`."""

    _harness: "Harness"
    _nom: str
    _callback: Callable
    _asynchrone: bool
    _approuves: frozenset[str]

    def __init__(self, harness: "Harness", manifeste: ManifesteOutil, callback: Callable,
                 approuves: Iterable[str] = ()) -> None:
        super().__init__()
        self._harness = harness
        self._nom = manifeste.nom
        self._callback = callback
        self._asynchrone = inspect.iscoroutinefunction(callback)
        self._approuves = frozenset(approuves)
        self._spec = {
            "name": manifeste.nom,
            "description": manifeste.description,
            "inputSchema": copy.deepcopy(manifeste.as_dict()["schema_entree"]),
        }

    @property
    def tool_name(self) -> str:
        return self._nom

    @property
    def tool_spec(self) -> dict:
        return self._spec

    @property
    def tool_type(self) -> str:
        return "python"

    def __call__(self, *args, **kwargs):
        arguments = _lier(self._callback, dict(inspect.signature(self._callback).bind(*args, **kwargs).arguments))
        if self._asynchrone:
            return self._harness._appeler_avec(self._callback, self._nom, arguments,
                                               approuves=self._approuves)
        return self._harness._appeler_sync_avec(self._callback, self._nom, arguments,
                                                approuves=self._approuves)

    async def stream(self, tool_use, invocation_state, **kwargs):
        identifiant = tool_use.get("toolUseId", "unknown")
        arguments = tool_use.get("input", {}) or {}
        try:
            resultat = await self._harness._appeler_avec(
                self._callback, self._nom, arguments, approuves=self._approuves)
        except Exception as erreur:
            yield ToolResultEvent(
                {
                    "toolUseId": identifiant,
                    "status": "error",
                    "content": [{"text": f"Error: {type(erreur).__name__} - outil indisponible"}],
                },
                exception=erreur,
            )
            return
        texte = resultat if isinstance(resultat, str) else _json(resultat)
        yield ToolResultEvent(
            {
                "toolUseId": identifiant,
                "status": "success",
                "content": [{"text": texte}],
            }
        )


class Harness:
    """Relie manifestes et adaptateurs ; filtre, exécute, borne et audite les appels."""

    def __init__(
        self,
        registre: RegistreCapacites | None = None,
        adaptateurs: Mapping[str, Callable] | None = None,
        *,
        approuves: Iterable[str] = (),
        tenant: str | None = None,
        persona: str | None = None,
        perimetre: str | None = None,
        audit: list[dict] | None = None,
        audit_sink: Any = None,
    ) -> None:
        self.registre = registre if registre is not None else RegistreCapacites()
        self.adaptateurs = dict(adaptateurs or {})
        self.approuves = {str(nom) for nom in (approuves or ())}
        self.tenant = tenant
        self.persona = persona
        self.perimetre = perimetre
        self.audit_sink = audit_sink
        self._audit: list[dict] = audit if isinstance(audit, list) else []
        self._decouverte: dict[str, Callable] = {
            "rechercher_outil": self._rechercher,
            "decrire_outil": self._decrire,
        }
        for manifeste in manifestes_decouverte():
            if manifeste.nom not in self.registre:
                self.registre.enregistrer(manifeste)

    def _callable(self, nom: str) -> Callable | None:
        return self._decouverte.get(nom) or self.adaptateurs.get(nom)

    def _approuves(self, approuves: Iterable[str] | None = None) -> set[str]:
        return self.approuves | {str(nom) for nom in (approuves or ())}

    def _visible(self, manifeste: ManifesteOutil, lecture_seule: bool | None,
                 approuves: set[str]) -> bool:
        if manifeste.lecture_seule:
            return lecture_seule is not False
        if lecture_seule is True:
            return False
        return manifeste.nom in approuves

    def _manifests(
        self,
        tenant: Any = None,
        persona: Any = None,
        perimetre: Any = None,
        lecture_seule: bool | None = None,
        approuves: Iterable[str] | None = None,
    ) -> list[ManifesteOutil]:
        approuves = self._approuves(approuves)
        candidats = self.registre.lister(
            tenant=self.tenant if tenant is None else tenant,
            persona=self.persona if persona is None else persona,
            perimetre=self.perimetre if perimetre is None else perimetre,
        )
        return [
            manifeste
            for manifeste in candidats
            if self._visible(manifeste, lecture_seule, approuves)
        ]

    def _auditer(self, nom: str, manifeste: ManifesteOutil | None, arguments: Any,
                 debut: float | None, statut: str, **details: Any) -> None:
        ligne = {
            "nom": nom,
            "capacite": manifeste.capacite if manifeste is not None else None,
            "arguments": _expurger(arguments),
            "duree_ms": _duree(debut) if debut is not None else 0.0,
            "statut": statut,
        }
        ligne.update(details)
        self._audit.append(ligne)
        self._persister(ligne)

    def _persister(self, ligne: Mapping) -> None:
        """Écrit la ligne au sink sans jamais modifier ni retenir le résultat de l'appel d'outil."""
        sink = self.audit_sink
        if sink is None:
            return
        charge = dict(ligne)
        charge.setdefault("outil", charge.get("nom"))
        charge["quand"] = time.time()
        try:
            ecrire = getattr(sink, "enregistrer", None)
            if ecrire is None and callable(sink):
                ecrire = sink
            if ecrire is None:
                return
            resultat = ecrire(copy.deepcopy(charge))
        except Exception:
            return
        if inspect.isawaitable(resultat):
            try:
                boucle = asyncio.get_running_loop()
            except RuntimeError:
                if inspect.iscoroutine(resultat):
                    resultat.close()
                return
            boucle.create_task(resultat).add_done_callback(_consommer)

    def _verifier(self, nom: Any, approuves: Iterable[str] | None = None,
                  executeur: Callable | None = None) -> ManifesteOutil:
        if not isinstance(nom, str):
            nom = str(nom)
        manifeste = self.registre.decrire(nom)
        executeur = executeur if executeur is not None else self._callable(nom)
        if manifeste is None or executeur is None:
            self._auditer(nom, manifeste, None, None, "refuse", motif="outil non enregistré")
            raise OutilNonEnregistre(f"outil non enregistré : {nom}")
        if not manifeste.lecture_seule and nom not in self._approuves(approuves):
            self._auditer(nom, manifeste, None, None, "refuse", motif="écriture non approuvée")
            raise OutilNonApprouve(f"écriture non approuvée : {nom}")
        return manifeste

    async def _attendre(self, nom: str, manifeste: ManifesteOutil, arguments: dict,
                        valeur: Any, debut: float, timeout_ms: int) -> Any:
        try:
            if inspect.isawaitable(valeur):
                resultat = await asyncio.wait_for(valeur, timeout=_secondes(timeout_ms))
            else:
                resultat = valeur
        except asyncio.TimeoutError:
            self._auditer(nom, manifeste, arguments, debut, "timeout", erreur="TimeoutError")
            raise
        except Exception as erreur:
            self._auditer(nom, manifeste, arguments, debut, "erreur", erreur=type(erreur).__name__)
            raise
        self._auditer(nom, manifeste, arguments, debut, "ok")
        return resultat

    async def appeler(self, nom: str, arguments: Mapping | None = None, timeout_ms: Any = None,
                      *, approuves: Iterable[str] | None = None) -> Any:
        """Vérifie le manifeste, exécute l'adaptateur, l'audite et rend son résultat brut."""
        return await self._appeler_avec(self._callable(nom), nom, arguments, timeout_ms,
                                        approuves=approuves)

    async def _appeler_avec(self, callback: Callable | None, nom: str,
                            arguments: Mapping | None = None, timeout_ms: Any = None,
                            *, approuves: Iterable[str] | None = None) -> Any:
        arguments_expurges = arguments
        manifeste = self._verifier(nom, approuves, callback)
        essaies = _arguments(arguments)
        timeout = manifeste.timeout_ms if timeout_ms is None else timeout_ms
        _secondes(timeout)
        debut = time.perf_counter()
        try:
            valeur = _invoquer(callback, essaies)
        except Exception as erreur:
            self._auditer(manifeste.nom, manifeste, arguments_expurges, debut, "erreur",
                          erreur=type(erreur).__name__)
            raise
        return await self._attendre(manifeste.nom, manifeste, essaies, valeur, debut, timeout)

    def _appeler_sync(self, nom: str, arguments: Mapping | None = None, *,
                      approuves: Iterable[str] | None = None) -> Any:
        return self._appeler_sync_avec(self._callable(nom), nom, arguments,
                                       approuves=approuves)

    def _appeler_sync_avec(self, callback: Callable | None, nom: str,
                           arguments: Mapping | None = None, *,
                           approuves: Iterable[str] | None = None) -> Any:
        arguments_expurges = arguments
        manifeste = self._verifier(nom, approuves, callback)
        essaies = _arguments(arguments)
        debut = time.perf_counter()
        try:
            valeur = _invoquer(callback, essaies)
        except Exception as erreur:
            self._auditer(manifeste.nom, manifeste, arguments_expurges, debut, "erreur",
                          erreur=type(erreur).__name__)
            raise
        if inspect.isawaitable(valeur):
            return self._attendre(manifeste.nom, manifeste, essaies, valeur, debut,
                                  manifeste.timeout_ms)
        self._auditer(manifeste.nom, manifeste, essaies, debut, "ok")
        return valeur

    def outils(
        self,
        contexte: Any = None,
        budget: Any = None,
        selection: Any = None,
        *,
        tenant: Any = None,
        persona: Any = None,
        perimetre: Any = None,
        lecture_seule: bool | None = None,
        approuves: Iterable[str] | None = None,
    ) -> list[AgentTool]:
        """Les adaptateurs visibles pour la portée, plus les deux outils de découverte."""
        approuves_effectifs = self._approuves(approuves)
        sortie: list[AgentTool] = []
        for manifeste in self._manifests(tenant, persona, perimetre, lecture_seule, approuves):
            callback = self._callable(manifeste.nom)
            if callback is None:
                continue
            if manifeste.nom == "rechercher_outil":
                callback = self._decouverte_recherche(tenant, persona, perimetre,
                                                      approuves_effectifs)
            elif manifeste.nom == "decrire_outil":
                callback = self._decouverte_description(tenant, persona, perimetre,
                                                        approuves_effectifs)
            sortie.append(_OutilHarness(self, manifeste, callback, approuves_effectifs))
        return sortie

    def _decouverte_recherche(self, tenant: Any, persona: Any, perimetre: Any,
                              approuves: Iterable[str]) -> Callable:
        def rechercher(requete: str, capacite: str | None = None) -> str:
            return self._rechercher(requete, capacite, tenant=tenant, persona=persona,
                                    perimetre=perimetre, approuves=approuves)
        return rechercher

    def _decouverte_description(self, tenant: Any, persona: Any, perimetre: Any,
                                approuves: Iterable[str]) -> Callable:
        def decrire(nom: str) -> str:
            return self._decrire(nom, tenant=tenant, persona=persona, perimetre=perimetre,
                                 approuves=approuves)
        return decrire

    def approuver(self, nom: str) -> "Harness":
        self.approuves.add(str(nom))
        return self

    def revoquer(self, nom: str) -> "Harness":
        self.approuves.discard(str(nom))
        return self

    def rechercher_outil(self, requete: str, capacite: str | None = None) -> str:
        return self._rechercher(requete, capacite)

    def decrire_outil(self, nom: str) -> str:
        return self._decrire(nom)

    def auditer(self) -> list[dict]:
        """Trace append-only des appels, arguments expurgés, durée et statut."""
        return copy.deepcopy(self._audit)

    def as_dict(self) -> dict:
        return {"audit": self.auditer()}

    def _rechercher(self, requete: str, capacite: str | None = None, *,
                    tenant: Any = None, persona: Any = None, perimetre: Any = None,
                    approuves: Iterable[str] | None = None) -> str:
        tenant_effectif = self.tenant if tenant is None else tenant
        persona_effectif = self.persona if persona is None else persona
        perimetre_effectif = self.perimetre if perimetre is None else perimetre
        visibles = {
            manifeste.nom
            for manifeste in self._manifests(tenant_effectif, persona_effectif,
                                             perimetre_effectif, approuves=approuves)
        }
        resultats = [
            manifeste
            for manifeste in self.registre.chercher(
                requete,
                tenant=tenant_effectif,
                persona=persona_effectif,
                perimetre=perimetre_effectif,
                capacite=capacite,
            )
            if manifeste.nom in visibles
        ]
        return _json({
            "statut": "ok",
            "requete": str(requete or ""),
            "capacites": self.registre.capacites(),
            "outils": [manifeste.as_dict() for manifeste in resultats],
        })

    def _decrire(self, nom: str, *, tenant: Any = None, persona: Any = None,
                 perimetre: Any = None, approuves: Iterable[str] | None = None) -> str:
        manifeste = self.registre.decrire(nom)
        if manifeste is None:
            return _json({"statut": "introuvable", "nom": str(nom or "")})
        visibles = {
            candidat.nom
            for candidat in self._manifests(tenant, persona, perimetre, approuves=approuves)
        }
        if manifeste.nom not in visibles:
            return _json({"statut": "indisponible", "nom": manifeste.nom})
        charge = manifeste.as_dict()
        charge["statut"] = "ok"
        return _json(charge)


__all__ = [
    "Harness",
    "ErreurHarness",
    "OutilNonEnregistre",
    "OutilNonApprouve",
    "OutilInconnu",
    "EcritureNonApprouvee",
    "manifestes_decouverte",
    "expurger",
]
