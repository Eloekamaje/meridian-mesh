"""Exécuteur gouverné des manifestes capacitaires (ADR-0004).

L'exécuteur relie un registre de manifestes à des adaptateurs locaux, synchrones ou asynchrones. Il vérifie la
portée, l'allowlist, le plafond de coût et l'approbation des écritures avant tout appel, borne le délai, capture
les erreurs sans divulguer les arguments et produit une ligne d'audit minimale. Aucun réseau, aucune base et
aucune commande externe ne sont utilisés ici : les adaptateurs restent des callables fournis par l'appelant.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
import copy
from dataclasses import dataclass
import inspect
import math
import time
from typing import Any

STATUT_MANIFESTE_ABSENT = "manifeste_absent"
STATUT_HORS_PORTEE = "hors_portee"
STATUT_ECRITURE_NON_APPROUVEE = "ecriture_non_approuvee"
STATUT_COUT = "cout"
STATUT_ADAPTATEUR_ABSENT = "adaptateur_absent"

STATUTS_REFUS = (
    STATUT_MANIFESTE_ABSENT,
    STATUT_HORS_PORTEE,
    STATUT_ECRITURE_NON_APPROUVEE,
    STATUT_COUT,
    STATUT_ADAPTATEUR_ABSENT,
)

_AXES = ("tenant", "acteur", "perimetre")


class ExecutionRefusee(Exception):
    """Un appel est refusé par la politique avant toute exécution de l'adaptateur."""

    def __init__(self, statut: str, nom: str | None = None, detail: str | None = None) -> None:
        self.statut = statut
        self.nom = nom
        self.detail = detail
        message = statut if detail is None else f"{statut} : {detail}"
        if nom:
            message = f"{message} ({nom})"
        super().__init__(message)

    @property
    def categorie(self) -> str:
        """Alias lisible de la catégorie de refus."""
        return self.statut

    @property
    def status(self) -> str:
        """Alias anglais de la catégorie de refus."""
        return self.statut


class ExecutionInvalide(ValueError):
    """La politique, les arguments ou un adaptateur ne respectent pas le contrat d'appel."""


@dataclass(frozen=True)
class PolitiqueExecution:
    """Bornes d'exécution demandées par un appelant : portée, écritures, coût, délai et allowlist."""

    tenant: str | None = None
    acteur: str | None = None
    perimetre: str | None = None
    autoriser_ecritures: bool = False
    max_cout: float = 0.0
    timeout_s: float = 5.0
    allowlist: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        allowlist = self.allowlist
        if allowlist is None:
            allowlist = ()
        elif isinstance(allowlist, str):
            allowlist = (allowlist,)
        else:
            try:
                allowlist = tuple(allowlist)
            except TypeError as erreur:
                raise ExecutionInvalide("allowlist : séquence attendue") from erreur
        object.__setattr__(self, "allowlist", allowlist)


@dataclass(frozen=True)
class Approbation:
    """Approbation explicite d'une écriture ; aucune approbation n'est déduite automatiquement."""

    acteur: str
    motif: str
    preuve: str | None = None


@dataclass(frozen=True)
class ResultatExecution:
    """Résultat d'un appel : valeur ou type d'erreur, durée et ligne d'audit expurgée."""

    nom: str
    ok: bool
    valeur: Any = None
    erreur: str | None = None
    duree_ms: float = 0.0
    audit: dict[str, Any] | None = None


class Executeur:
    """Exécute des adaptateurs déclarés après vérification de la politique et journalisation minimale."""

    def __init__(
        self,
        registre: Any,
        adaptateurs: Mapping[str, Callable[..., Any]] | None = None,
        audit: Any = None,
        horloge: Callable[[], float] | None = None,
    ) -> None:
        self._registre = registre
        self._adaptateurs: dict[str, Callable[..., Any]] = {}
        try:
            adaptateurs = dict(adaptateurs or {})
        except (TypeError, ValueError) as erreur:
            raise ExecutionInvalide("adaptateurs : table nom → fonction attendue") from erreur
        for nom, fonction in adaptateurs.items():
            self.enregistrer_adaptateur(nom, fonction)
        if horloge is not None and not callable(horloge):
            raise ExecutionInvalide("horloge : fonction attendue")
        self._audit = audit
        self._horloge = horloge or time.perf_counter

    def enregistrer_adaptateur(self, nom: Any, fonction: Any) -> None:
        """Déclare un adaptateur local ; la fonction reçoit uniquement les arguments nommés demandés."""
        if not isinstance(nom, str) or not nom.strip():
            raise ExecutionInvalide("nom d'adaptateur invalide")
        if not callable(fonction):
            raise ExecutionInvalide("adaptateur : fonction attendue")
        self._adaptateurs[nom.strip()] = fonction

    @staticmethod
    def _verifier_politique(politique: Any) -> PolitiqueExecution:
        if not isinstance(politique, PolitiqueExecution):
            raise ExecutionInvalide("politique : PolitiqueExecution attendue")
        for axe in _AXES:
            valeur = getattr(politique, axe)
            if valeur is not None and (not isinstance(valeur, str) or not valeur.strip()):
                raise ExecutionInvalide(f"politique.{axe} : chaîne non vide attendue")
        if not isinstance(politique.autoriser_ecritures, bool):
            raise ExecutionInvalide("politique.autoriser_ecritures : booléen attendu")
        if isinstance(politique.max_cout, bool) or not isinstance(politique.max_cout, (int, float)):
            raise ExecutionInvalide("politique.max_cout : nombre attendu")
        if not math.isfinite(float(politique.max_cout)) or politique.max_cout < 0:
            raise ExecutionInvalide("politique.max_cout : valeur positive ou nulle attendue")
        if isinstance(politique.timeout_s, bool) or not isinstance(politique.timeout_s, (int, float)):
            raise ExecutionInvalide("politique.timeout_s : nombre attendu")
        if not math.isfinite(float(politique.timeout_s)) or politique.timeout_s <= 0:
            raise ExecutionInvalide("politique.timeout_s : valeur strictement positive attendue")
        for entree in politique.allowlist:
            if not isinstance(entree, str) or not entree.strip():
                raise ExecutionInvalide("politique.allowlist : chaînes non vides attendues")
        return politique

    @staticmethod
    def _arguments(arguments: Any) -> dict[str, Any]:
        if arguments is None:
            return {}
        if not isinstance(arguments, Mapping):
            raise ExecutionInvalide("arguments : objet attendu")
        return dict(arguments)

    @staticmethod
    def _portee_autorisee(manifeste: Any, politique: PolitiqueExecution) -> bool:
        for axe in _AXES:
            attendu = getattr(manifeste, axe, None)
            if attendu in (None, "*"):
                continue
            if getattr(politique, axe) != attendu:
                return False
        return True

    @staticmethod
    def _allowlist_autorisee(manifeste: Any, politique: PolitiqueExecution, nom: str) -> bool:
        entrees = {entree.strip() for entree in politique.allowlist}
        if not entrees:
            return True
        if nom in entrees:
            return True
        manifeste_allowlist = {
            str(entree).strip() for entree in (getattr(manifeste, "allowlist", ()) or ())
        }
        return bool(entrees & manifeste_allowlist)

    @staticmethod
    def _approbation_valide(approbation: Any) -> bool:
        if not isinstance(approbation, Approbation):
            return False
        if not isinstance(approbation.acteur, str) or not approbation.acteur.strip():
            return False
        if not isinstance(approbation.motif, str) or not approbation.motif.strip():
            return False
        return approbation.preuve is None or isinstance(approbation.preuve, str)

    @classmethod
    def _ecriture_autorisee(cls, manifeste: Any, politique: PolitiqueExecution,
                            approbation: Any) -> bool:
        if manifeste.lecture_seule:
            return True
        return politique.autoriser_ecritures is True and cls._approbation_valide(approbation)

    @staticmethod
    def _ligne_audit(politique: PolitiqueExecution, manifeste: Any, nom: str, statut: str,
                     duree_ms: float, erreur: str | None = None, motif: str | None = None,
                     approbation: Any = None) -> dict[str, Any]:
        ecriture = manifeste is not None and not getattr(manifeste, "lecture_seule", True)
        acteur = approbation.acteur if ecriture and isinstance(approbation, Approbation) else None
        ligne: dict[str, Any] = {
            "tenant": politique.tenant,
            "acteur": politique.acteur,
            "perimetre": politique.perimetre,
            "outil": nom,
            "nom": nom,
            "capacite": getattr(manifeste, "capacite", None) if manifeste is not None else None,
            "statut": statut,
            "approbation": acteur,
            "duree_ms": duree_ms,
            "erreur": erreur,
        }
        if motif is not None:
            ligne["motif"] = motif
        return ligne

    async def _auditer(self, ligne: Mapping[str, Any]) -> None:
        sink = self._audit
        if sink is None:
            return
        if isinstance(sink, list):
            try:
                sink.append(copy.deepcopy(dict(ligne)))
            except Exception:
                return
            return
        try:
            ecrire = getattr(sink, "enregistrer", None)
            if ecrire is None and callable(sink):
                ecrire = sink
            if ecrire is None:
                return
            resultat = ecrire(copy.deepcopy(dict(ligne)))
            if inspect.isawaitable(resultat):
                await resultat
        except Exception:
            return

    async def _refuser(self, statut: str, nom: str, manifeste: Any, politique: PolitiqueExecution,
                       approbation: Any, motif: str) -> None:
        ligne = self._ligne_audit(politique, manifeste, nom, "refuse", 0.0, motif=motif,
                                  approbation=approbation)
        await self._auditer(ligne)
        raise ExecutionRefusee(statut, nom=nom, detail=motif)

    def _duree(self, debut: float | None) -> float:
        if debut is None:
            return 0.0
        try:
            valeur = (float(self._horloge()) - debut) * 1000.0
        except Exception:
            return 0.0
        if not math.isfinite(valeur) or valeur < 0:
            return 0.0
        return round(valeur, 3)

    @staticmethod
    def _asynchrone(fonction: Callable[..., Any]) -> bool:
        return inspect.iscoroutinefunction(fonction) or inspect.iscoroutinefunction(
            getattr(fonction, "__call__", None)
        )

    async def _appeler_adapte(self, fonction: Callable[..., Any],
                              arguments: Mapping[str, Any]) -> Any:
        if self._asynchrone(fonction):
            return await fonction(**arguments)
        resultat = await asyncio.to_thread(fonction, **arguments)
        if inspect.isawaitable(resultat):
            return await resultat
        return resultat

    async def executer(
        self,
        nom: str,
        arguments: Mapping[str, Any] | None = None,
        *,
        politique: PolitiqueExecution,
        approbation: Approbation | None = None,
    ) -> ResultatExecution:
        """Vérifie le manifeste et la politique, exécute l'adaptateur, puis rend un résultat audité."""
        politique = self._verifier_politique(politique)
        essaies = self._arguments(arguments)
        nom_demande = nom.strip() if isinstance(nom, str) else str(nom)
        manifeste = self._registre.decrire(nom_demande)
        if manifeste is None:
            await self._refuser(STATUT_MANIFESTE_ABSENT, nom_demande, None, politique,
                                approbation, "manifeste absent")
        nom_canonique = manifeste.nom
        if not self._portee_autorisee(manifeste, politique):
            await self._refuser(STATUT_HORS_PORTEE, nom_canonique, manifeste, politique,
                                approbation, "hors portée")
        if not self._allowlist_autorisee(manifeste, politique, nom_canonique):
            await self._refuser(STATUT_HORS_PORTEE, nom_canonique, manifeste, politique,
                                approbation, "allowlist")
        if not self._ecriture_autorisee(manifeste, politique, approbation):
            await self._refuser(STATUT_ECRITURE_NON_APPROUVEE, nom_canonique, manifeste, politique,
                                approbation, "écriture non approuvée")
        if politique.max_cout > 0 and manifeste.cout > politique.max_cout:
            await self._refuser(STATUT_COUT, nom_canonique, manifeste, politique,
                                approbation, "coût au-dessus du plafond")
        fonction = self._adaptateurs.get(nom_canonique)
        if fonction is None:
            await self._refuser(STATUT_ADAPTATEUR_ABSENT, nom_canonique, manifeste, politique,
                                approbation, "adaptateur absent")

        timeout = min(float(politique.timeout_s), manifeste.timeout_ms / 1000.0)
        try:
            debut: float | None = float(self._horloge())
        except Exception:
            debut = None
        valeur: Any = None
        erreur: str | None = None
        statut = "ok"
        try:
            valeur = await asyncio.wait_for(
                self._appeler_adapte(fonction, essaies), timeout=timeout)
        except asyncio.TimeoutError:
            statut = "timeout"
            erreur = "TimeoutError"
        except Exception as incident:
            statut = "erreur"
            erreur = type(incident).__name__

        duree_ms = self._duree(debut)
        ligne = self._ligne_audit(politique, manifeste, nom_canonique, statut, duree_ms,
                                  erreur=erreur, approbation=approbation)
        await self._auditer(ligne)
        return ResultatExecution(
            nom=nom_canonique,
            ok=statut == "ok",
            valeur=valeur if statut == "ok" else None,
            erreur=erreur,
            duree_ms=duree_ms,
            audit=ligne,
        )

    def lister(self, politique: PolitiqueExecution) -> list[Any]:
        """Les manifestes visibles pour la politique, filtrés par portée, allowlist, écriture et coût."""
        politique = self._verifier_politique(politique)
        sortie: list[Any] = []
        for manifeste in self._registre.lister():
            if not self._portee_autorisee(manifeste, politique):
                continue
            if not self._allowlist_autorisee(manifeste, politique, manifeste.nom):
                continue
            if not manifeste.lecture_seule and politique.autoriser_ecritures is not True:
                continue
            if politique.max_cout > 0 and manifeste.cout > politique.max_cout:
                continue
            sortie.append(manifeste)
        return sortie

    def as_dict(self) -> dict[str, Any]:
        """Catalogue des manifestes et noms d'adaptateurs enregistrés, sans contenu d'appel."""
        return {
            "outils": [manifeste.as_dict() for manifeste in self._registre.lister()],
            "adaptateurs": sorted(self._adaptateurs),
        }


__all__ = [
    "STATUTS_REFUS",
    "STATUT_MANIFESTE_ABSENT",
    "STATUT_HORS_PORTEE",
    "STATUT_ECRITURE_NON_APPROUVEE",
    "STATUT_COUT",
    "STATUT_ADAPTATEUR_ABSENT",
    "ExecutionRefusee",
    "ExecutionInvalide",
    "PolitiqueExecution",
    "Approbation",
    "ResultatExecution",
    "Executeur",
]
