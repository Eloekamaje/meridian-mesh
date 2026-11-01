"""Le moteur de changement et d'impact du graphe d'interfaces.

Pur, déterministe et adossé à des preuves : deux lectures du même graphe rendent les mêmes changements, et chaque
changement cite la source qui l'a établi. Aucun consommateur n'est inventé : un impact n'existe que si le graphe
d'après porte une assertion `CONSOMME` qui désigne l'opération touchée.

Les identités de contenu (`Contract.id`, `Operation.id`) changent dès qu'un document change ; le diff apparie donc
d'abord les identifiants exacts, puis une identité stable (application, format, environnement pour un contrat ;
application, environnement, protocole, méthode et chemin pour une opération). Aucune fusion entre applications,
environnements ou contrats distincts n'est faite.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Iterable, Optional

from meridian.domain.interfaces import Assertion, Binding, Contract, InterfaceGraph, Operation

__all__ = ["Change", "Impact", "diff_graphs", "impacts", "resume"]

TYPES_CHANGE = frozenset({
    "contract_version", "contract_digest", "operation_added", "operation_removed", "operation_changed",
    "binding_added", "binding_removed", "assertion_added", "assertion_removed", "assertion_mode_changed",
})
SEVERITES = ("info", "warning", "breaking")
_RANG_SEVERITE = {"info": 0, "warning": 1, "breaking": 2}
_VERSION = re.compile(r"^\s*v?(\d+)(?:\.(\d+))?(?:\.(\d+))?")
_CHAMPS_OPERATION = ("contract_id", "protocol", "method", "path", "name", "version", "environment")
_CHAMPS_DERIVES = frozenset({"contract_id", "version"})
_SEVERITE_CHAMP = {
    "protocol": "breaking",
    "method": "breaking",
    "path": "breaking",
    "name": "warning",
    "version": "warning",
    "environment": "warning",
    "contract_id": "warning",
}


@dataclass(frozen=True)
class Change:
    """Un changement daté par sa provenance : `before`/`after` sont des valeurs ou des instantanés JSON."""

    type: str
    subject: str
    before: Any
    after: Any
    severity: str
    evidence: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)

    def to_dict(self) -> dict:
        return self.as_dict()


@dataclass(frozen=True)
class Impact:
    """Une application qui consomme une opération touchée, avec l'assertion qui le prouve."""

    application: str
    operation: str
    change_type: str
    severity: str
    evidence: list[dict] = field(default_factory=list)
    raison: str = ""

    def as_dict(self) -> dict:
        return asdict(self)

    def to_dict(self) -> dict:
        return self.as_dict()


def _canon(valeur: Any) -> str:
    """Forme canonique pour trier et dédupliquer sans dépendre de l'ordre des clés ni de l'ordre d'entrée."""
    return json.dumps(valeur, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _preuves(*listes: Iterable[dict]) -> list[dict]:
    """Réunit des preuves, les trie et retire les doublons : la même source ne prouve pas deux fois."""
    vues, sortie = set(), []
    for preuve in sorted((p for liste in listes for p in liste), key=_canon):
        marque = _canon(preuve)
        if marque not in vues:
            vues.add(marque)
            sortie.append(preuve)
    return sortie


def _preuve_contrat(contrat: Contract) -> dict:
    return {
        "type": "contract", "id": contrat.id, "application": contrat.application_id, "format": contrat.format,
        "version": contrat.version, "digest": contrat.digest, "locator": contrat.locator,
        "environment": contrat.environment,
    }


def _preuve_operation(operation: Operation, application: str) -> dict:
    return {
        "type": "operation", "id": operation.id, "contract_id": operation.contract_id,
        "application": application, "protocol": operation.protocol, "method": operation.method,
        "path": operation.path, "name": operation.name, "version": operation.version,
        "environment": operation.environment,
    }


def _preuve_binding(binding: Binding) -> dict:
    return {"type": "binding", **asdict(binding)}


def _preuve_assertion(assertion: Assertion) -> dict:
    return {"type": "assertion", **asdict(assertion)}


def _application_operation(operation: Operation, contrats: dict[str, Contract]) -> str:
    contrat = contrats.get(operation.contract_id)
    return contrat.application_id if contrat is not None else operation.environment


def _references_operation(operation: Operation) -> set[str]:
    references = {operation.id, f"{operation.method} {operation.path}", operation.path}
    references.add(f"{operation.method.upper()} {operation.path}")
    return references


def _preuves_expose(operation: Operation, graph: InterfaceGraph, application: str,
                    contrats: dict[str, Contract]) -> list[dict]:
    contrat = contrats.get(operation.contract_id)
    references = _references_operation(operation)
    preuves = []
    for assertion in graph.assertions:
        if assertion.predicate != "EXPOSE" or assertion.object not in references:
            continue
        if contrat is not None and assertion.subject != application:
            continue
        preuves.append(_preuve_assertion(assertion))
    return preuves


def _preuves_operation(operation: Operation, graph: InterfaceGraph,
                       contrats: dict[str, Contract]) -> list[dict]:
    application = _application_operation(operation, contrats)
    preuves = [_preuve_operation(operation, application)]
    contrat = contrats.get(operation.contract_id)
    if contrat is not None:
        preuves.append(_preuve_contrat(contrat))
    preuves.extend(_preuves_expose(operation, graph, application, contrats))
    return preuves


def _composantes_version(version: Optional[str]) -> Optional[tuple[int, int, int]]:
    if not version:
        return None
    trouve = _VERSION.match(str(version))
    if trouve is None:
        return None
    return tuple(int(partie or 0) for partie in trouve.groups())  # type: ignore[return-value]


def _severite_version(avant: Optional[str], apres: Optional[str]) -> str:
    a, b = _composantes_version(avant), _composantes_version(apres)
    if a is None or b is None:
        return "warning"
    if a[0] != b[0]:
        return "breaking"
    if a[1] != b[1]:
        return "warning"
    if a[2] != b[2]:
        return "info"
    return "info"


def _severite_mode(avant: str, apres: str) -> str:
    """Un passage à l'observation confirme ; tout retour en arrière reste un avertissement, jamais une rupture."""
    if avant == "declared" and apres == "observed":
        return "info"
    return "warning"


def _severite_champs(champs: Iterable[str]) -> str:
    severite = "info"
    for champ in champs:
        candidate = _SEVERITE_CHAMP.get(champ, "warning")
        if _RANG_SEVERITE[candidate] > _RANG_SEVERITE[severite]:
            severite = candidate
    return severite


def _apparier(avant: list, apres: list, cle_exacte, cle_stable_avant, cle_stable_apres) -> tuple[list, list]:
    """Apparie d'abord les identifiants exacts, puis l'identité stable ; rend les paires et les ajouts restants."""
    restant = list(apres)
    paires = []
    for a in avant:
        trouve = next((b for b in restant if cle_exacte(a) == cle_exacte(b)), None)
        if trouve is not None:
            restant.remove(trouve)
        paires.append([a, trouve])
    for paire in paires:
        if paire[1] is not None:
            continue
        candidats = sorted((b for b in restant if cle_stable_avant(paire[0]) == cle_stable_apres(b)),
                           key=lambda b: (cle_exacte(b), _canon(asdict(b))))
        if candidats:
            choisi = candidats[0]
            restant.remove(choisi)
            paire[1] = choisi
    return [tuple(paire) for paire in paires], restant


def _cle_tri_contrat(contrat: Contract) -> tuple:
    return (contrat.application_id, contrat.format, contrat.environment, contrat.locator, contrat.digest, contrat.id)


def _cle_stable_contrat(contrat: Contract) -> tuple:
    return (contrat.application_id, contrat.format, contrat.environment)


def _cle_stable_operation(operation: Operation, contrats: dict[str, Contract]) -> tuple:
    return (_application_operation(operation, contrats), operation.environment, operation.protocol,
            operation.method, operation.path)


def _cle_tri_operation(operation: Operation, contrats: dict[str, Contract]) -> tuple:
    return (*_cle_stable_operation(operation, contrats), operation.name, operation.id)


def _diff_contrats(avant: InterfaceGraph, apres: InterfaceGraph) -> list[Change]:
    contrats_avant = {c.id: c for c in avant.contracts}
    contrats_apres = {c.id: c for c in apres.contracts}
    paires, ajoutes = _apparier(
        sorted(avant.contracts, key=_cle_tri_contrat), sorted(apres.contracts, key=_cle_tri_contrat),
        lambda c: c.id, _cle_stable_contrat, _cle_stable_contrat)
    changements: list[Change] = []
    for ancien, nouveau in paires:
        if nouveau is None:
            changements.append(Change(
                type="contract_digest", subject=ancien.application_id, before=ancien.digest, after=None,
                severity="warning", evidence=_preuves([_preuve_contrat(ancien)])))
            continue
        preuves = _preuves([_preuve_contrat(ancien)], [_preuve_contrat(nouveau)])
        if ancien.version != nouveau.version:
            changements.append(Change(
                type="contract_version", subject=ancien.application_id,
                before=ancien.version, after=nouveau.version,
                severity=_severite_version(ancien.version, nouveau.version), evidence=preuves))
        if ancien.digest != nouveau.digest:
            changements.append(Change(
                type="contract_digest", subject=ancien.application_id,
                before=ancien.digest, after=nouveau.digest, severity="warning", evidence=preuves))
        elif ancien.locator != nouveau.locator:
            changements.append(Change(
                type="contract_digest", subject=ancien.application_id,
                before=ancien.locator, after=nouveau.locator, severity="info", evidence=preuves))
    for contrat in ajoutes:
        changements.append(Change(
            type="contract_version", subject=contrat.application_id, before=None, after=contrat.version,
            severity="warning", evidence=_preuves([_preuve_contrat(contrat)])))
    return changements


def _diff_operations(avant: InterfaceGraph, apres: InterfaceGraph) -> list[Change]:
    contrats_avant = {c.id: c for c in avant.contracts}
    contrats_apres = {c.id: c for c in apres.contracts}
    paires, ajoutees = _apparier(
        sorted(avant.operations, key=lambda o: _cle_tri_operation(o, contrats_avant)),
        sorted(apres.operations, key=lambda o: _cle_tri_operation(o, contrats_apres)),
        lambda o: o.id,
        lambda o: _cle_stable_operation(o, contrats_avant),
        lambda o: _cle_stable_operation(o, contrats_apres))
    changements: list[Change] = []
    for ancienne, nouvelle in paires:
        if nouvelle is None:
            changements.append(Change(
                type="operation_removed", subject=ancienne.id, before=asdict(ancienne), after=None,
                severity="breaking", evidence=_preuves(_preuves_operation(ancienne, avant, contrats_avant))))
            continue
        identite_exacte = ancienne.id == nouvelle.id
        champs = [champ for champ in _CHAMPS_OPERATION
                  if getattr(ancienne, champ) != getattr(nouvelle, champ)
                  and (identite_exacte or champ not in _CHAMPS_DERIVES)]
        if not champs:
            continue
        preuves = _preuves(_preuves_operation(ancienne, avant, contrats_avant),
                           _preuves_operation(nouvelle, apres, contrats_apres))
        preuves.append({"type": "fields", "changed": list(champs)})
        changements.append(Change(
            type="operation_changed", subject=nouvelle.id,
            before=asdict(ancienne), after=asdict(nouvelle),
            severity=_severite_champs(champs), evidence=_preuves(preuves)))
    for operation in ajoutees:
        changements.append(Change(
            type="operation_added", subject=operation.id, before=None, after=asdict(operation),
            severity="info", evidence=_preuves(_preuves_operation(operation, apres, contrats_apres))))
    return changements


def _diff_bindings(avant: InterfaceGraph, apres: InterfaceGraph) -> list[Change]:
    paires, ajouts = _apparier(
        sorted(avant.bindings, key=lambda b: (b.protocol, b.url, b.environment, b.gateway or "", b.id)),
        sorted(apres.bindings, key=lambda b: (b.protocol, b.url, b.environment, b.gateway or "", b.id)),
        lambda b: b.id, lambda b: b.id, lambda b: b.id)
    changements: list[Change] = []
    for ancien, nouveau in paires:
        if nouveau is None or asdict(ancien) != asdict(nouveau):
            changements.append(Change(
                type="binding_removed", subject=ancien.id, before=asdict(ancien), after=None,
                severity="warning", evidence=_preuves([_preuve_binding(ancien)])))
            if nouveau is not None:
                changements.append(Change(
                    type="binding_added", subject=nouveau.id, before=None, after=asdict(nouveau),
                    severity="info", evidence=_preuves([_preuve_binding(nouveau)])))
    for binding in ajouts:
        changements.append(Change(
            type="binding_added", subject=binding.id, before=None, after=asdict(binding),
            severity="info", evidence=_preuves([_preuve_binding(binding)])))
    return changements


def _cle_assertion_complete(assertion: Assertion) -> tuple:
    return (assertion.subject, assertion.predicate, assertion.object, assertion.mode, assertion.source,
            assertion.locator, assertion.environment, assertion.confidence, assertion.evidence,
            assertion.observed_at, assertion.valid_from)


def _cle_assertion_sans_locator(assertion: Assertion) -> tuple:
    return (assertion.subject, assertion.predicate, assertion.object, assertion.mode, assertion.source,
            assertion.environment, assertion.confidence, assertion.evidence, assertion.observed_at,
            assertion.valid_from)


def _cle_assertion_sans_mode(assertion: Assertion) -> tuple:
    return (assertion.subject, assertion.predicate, assertion.object, assertion.source, assertion.environment)


def _cle_tri_assertion(assertion: Assertion) -> tuple:
    return _cle_assertion_complete(assertion)


def _diff_assertions(avant: InterfaceGraph, apres: InterfaceGraph) -> list[Change]:
    restant = sorted(apres.assertions, key=_cle_tri_assertion)
    paires: list[list[Optional[Assertion]]] = []
    for assertion in sorted(avant.assertions, key=_cle_tri_assertion):
        trouve = next((a for a in restant if _cle_assertion_complete(a) == _cle_assertion_complete(assertion)),
                      None)
        if trouve is not None:
            restant.remove(trouve)
        paires.append([assertion, trouve])
    for paire in paires:
        if paire[1] is not None:
            continue
        candidats = sorted(
            (a for a in restant if _cle_assertion_sans_locator(a) == _cle_assertion_sans_locator(paire[0])),
            key=_cle_tri_assertion)
        if candidats:
            choisi = candidats[0]
            restant.remove(choisi)
            paire[1] = choisi
    for paire in paires:
        if paire[1] is not None:
            continue
        candidats = sorted((a for a in restant if _cle_assertion_sans_mode(a) == _cle_assertion_sans_mode(paire[0])),
                           key=_cle_tri_assertion)
        if candidats:
            choisi = candidats[0]
            restant.remove(choisi)
            paire[1] = choisi

    changements: list[Change] = []
    for ancienne, nouvelle in paires:
        if nouvelle is None:
            changements.append(Change(
                type="assertion_removed", subject=ancienne.subject, before=asdict(ancienne), after=None,
                severity="warning", evidence=_preuves([_preuve_assertion(ancienne)])))
            continue
        if ancienne.mode != nouvelle.mode:
            changements.append(Change(
                type="assertion_mode_changed", subject=ancienne.subject, before=ancienne.mode, after=nouvelle.mode,
                severity=_severite_mode(ancienne.mode, nouvelle.mode),
                evidence=_preuves([_preuve_assertion(ancienne)], [_preuve_assertion(nouvelle)])))
        elif ancienne.locator != nouvelle.locator:
            # Un simple déplacement de provenance reste visible, mais il n'est jamais classé rupture.
            changements.append(Change(
                type="assertion_removed", subject=ancienne.subject, before=asdict(ancienne), after=None,
                severity="info", evidence=_preuves([_preuve_assertion(ancienne)])))
            changements.append(Change(
                type="assertion_added", subject=nouvelle.subject, before=None, after=asdict(nouvelle),
                severity="info", evidence=_preuves([_preuve_assertion(nouvelle)])))
    for assertion in restant:
        changements.append(Change(
            type="assertion_added", subject=assertion.subject, before=None, after=asdict(assertion),
            severity="info", evidence=_preuves([_preuve_assertion(assertion)])))
    return changements


def _cle_tri_change(change: Change) -> tuple:
    return (change.subject, change.type, _RANG_SEVERITE.get(change.severity, 9),
            _canon(change.before), _canon(change.after), _canon(change.evidence))


def diff_graphs(avant: InterfaceGraph, apres: InterfaceGraph) -> list[Change]:
    """Compare deux graphes et rend les changements triés, sans fusion d'identité entre applications."""
    changements = []
    changements.extend(_diff_contrats(avant, apres))
    changements.extend(_diff_operations(avant, apres))
    changements.extend(_diff_bindings(avant, apres))
    changements.extend(_diff_assertions(avant, apres))
    return sorted(changements, key=_cle_tri_change)


def _snapshots_operation(change: Change) -> list[dict]:
    snapshots = []
    for valeur in (change.before, change.after):
        snapshot = asdict(valeur) if is_dataclass(valeur) and not isinstance(valeur, type) else valeur
        if isinstance(snapshot, dict) and "method" in snapshot and "path" in snapshot:
            snapshots.append(snapshot)
    return snapshots


def _references_snapshot(snapshot: dict) -> set[str]:
    references: set[str] = set()
    identifiant = snapshot.get("id")
    if identifiant:
        references.add(str(identifiant))
    methode, chemin = snapshot.get("method"), snapshot.get("path")
    if methode and chemin:
        references.add(f"{methode} {chemin}")
        references.add(f"{str(methode).upper()} {chemin}")
    if chemin:
        references.add(str(chemin))
    return references


def _libelle_operation(snapshot: dict) -> str:
    if snapshot.get("id"):
        return str(snapshot["id"])
    return f"{snapshot.get('method', '')} {snapshot.get('path', '')}".strip()


def impacts(changements: Iterable[Change], graph_apres: InterfaceGraph) -> list[Impact]:
    """Liste les applications qui consomment une opération supprimée, changée ou touchée par une rupture.

    Seules les assertions `CONSOMME` présentes dans `graph_apres` font foi. Une application absente du graphe
    n'est jamais inventée : pas d'assertion, pas d'impact.
    """
    trouves: dict[tuple, dict] = {}
    for change in sorted(changements, key=_cle_tri_change):
        concerne_operation = change.type in ("operation_removed", "operation_changed")
        if not concerne_operation and change.severity != "breaking":
            continue
        snapshots = _snapshots_operation(change)
        if not snapshots:
            continue
        references: set[str] = set()
        for snapshot in snapshots:
            references.update(_references_snapshot(snapshot))
        operation = _libelle_operation(snapshots[-1])
        for assertion in graph_apres.assertions:
            if assertion.predicate != "CONSOMME" or assertion.object not in references:
                continue
            cle = (assertion.subject, operation, change.type, change.severity)
            preuve = _preuve_assertion(assertion)
            if cle not in trouves:
                trouves[cle] = {
                    "application": assertion.subject,
                    "operation": operation,
                    "change_type": change.type,
                    "severity": change.severity,
                    "evidence": [preuve],
                }
            else:
                trouves[cle]["evidence"].append(preuve)

    resultats: list[Impact] = []
    for (application, operation, type_change, severite), donnees in sorted(trouves.items(),
                                                                          key=lambda item: _canon(item[0])):
        preuves = _preuves(donnees["evidence"])
        modes = sorted({str(preuve.get("mode", "")) for preuve in preuves if preuve.get("mode")})
        detail = f" ({', '.join(modes)})" if modes else ""
        resultats.append(Impact(
            application=application, operation=operation, change_type=type_change, severity=severite,
            evidence=preuves,
            raison=f"{application} consomme {operation}{detail} ; changement {type_change} classé {severite}."))
    return resultats


def resume(changements: Iterable[Change], impacts: Iterable[Impact]) -> dict:
    """Compte par sévérité, liste les ruptures et rend un texte court, le tout sérialisable en JSON."""
    changements = list(changements)
    impacts = list(impacts)
    comptes = {severite: 0 for severite in SEVERITES}
    for change in changements:
        comptes[change.severity] = comptes.get(change.severity, 0) + 1
    ruptures = sorted((change for change in changements if change.severity == "breaking"), key=_cle_tri_change)
    applications = sorted({impact.application for impact in impacts})
    texte = (f"{len(changements)} changement(s) : {comptes['breaking']} breaking, {comptes['warning']} warning, "
             f"{comptes['info']} info ; {len(impacts)} impact(s) sur {len(applications)} application(s).")
    if ruptures:
        texte += " Ruptures : " + ", ".join(f"{change.type} ({change.subject})" for change in ruptures) + "."
    return {
        "total": len(changements),
        "par_severite": dict(comptes),
        "severites": dict(comptes),
        "breaking": [change.as_dict() for change in ruptures],
        "breaking_changes": [change.as_dict() for change in ruptures],
        "impacts": len(impacts),
        "applications_impactees": applications,
        "texte": texte,
    }
