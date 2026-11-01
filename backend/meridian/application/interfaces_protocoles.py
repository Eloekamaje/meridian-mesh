"""Graphe d'interfaces pour GraphQL, gRPC et AsyncAPI.

Ces parseurs ramènent les protocoles à la même unité que REST/SOAP : un contrat, une opération et une
assertion `EXPOSE`. Ils réutilisent les extracteurs déclaratifs de `protocoles_outils` et ne font ni réseau,
ni compilation, ni exécution. Un document illisible reste un graphe partiel avec un diagnostic court.
"""
from __future__ import annotations

from meridian.domain import interfaces
from meridian.application import protocoles_outils

__all__ = ["parse_asyncapi", "parse_graphql", "parse_proto"]


def _contrat(application_id, format_, locator, environment, digest):
    return interfaces.Contract(
        id=interfaces._id("ctr", format_, application_id, environment, locator, digest),
        format=format_, version=None, digest=digest, locator=locator,
        application_id=application_id, environment=environment,
    )


def _assertion(contrat, operation, objet):
    return interfaces.Assertion(
        subject=contrat.application_id, predicate="EXPOSE", object=objet, mode="declared",
        source=contrat.format, locator=contrat.locator, environment=contrat.environment,
        confidence=interfaces.CONFIANCE_HAUTE, evidence=f"{contrat.locator}#{contrat.digest}",
    )


def parse_graphql(application_id: str, sdl: str, locator: str,
                  environment: str = "inconnu") -> interfaces.InterfaceGraph:
    """Chaque champ Query/Mutation/Subscription devient une opération `graphql` déclarée."""
    texte = sdl if isinstance(sdl, str) else ""
    digest = interfaces._digest(texte)
    contrat = _contrat(application_id, "graphql", locator, environment, digest)
    graph = interfaces.InterfaceGraph(contracts=[contrat])
    operations = protocoles_outils.operations_graphql(texte)
    if not operations:
        graph.partial = True
        graph.diagnostics.append("aucun champ Query/Mutation/Subscription lisible")
        return graph
    for info in operations:
        genre, nom = info["genre"], info["nom"]
        operation = interfaces.Operation(
            id=interfaces._id("op", contrat.id, "graphql", genre, nom),
            contract_id=contrat.id, protocol="graphql", method=genre.upper(), path=nom,
            name=nom, version=None, environment=environment)
        graph.operations.append(operation)
        graph.assertions.append(_assertion(contrat, operation, f"GRAPHQL {genre} {nom}"))
    return interfaces._dedupliquer(graph)


def parse_proto(application_id: str, proto_text: str, locator: str,
                environment: str = "inconnu") -> interfaces.InterfaceGraph:
    """Chaque `rpc` devient une opération `grpc` déclarée, avec `service.methode` comme action."""
    texte = proto_text if isinstance(proto_text, str) else ""
    digest = interfaces._digest(texte)
    contrat = _contrat(application_id, "grpc", locator, environment, digest)
    graph = interfaces.InterfaceGraph(contracts=[contrat])
    operations = protocoles_outils.operations_grpc(texte)
    if not operations:
        graph.partial = True
        graph.diagnostics.append("aucun service/rpc lisible")
        return graph
    for info in operations:
        service, methode = info["service"], info["methode"]
        action = f"{service}.{methode}"
        operation = interfaces.Operation(
            id=interfaces._id("op", contrat.id, "grpc", service, methode),
            contract_id=contrat.id, protocol="grpc", method="RPC", path=action,
            name=methode, version=None, environment=environment)
        graph.operations.append(operation)
        graph.assertions.append(_assertion(contrat, operation, f"GRPC {action}"))
    return interfaces._dedupliquer(graph)


def parse_asyncapi(application_id: str, document, locator: str,
                   environment: str = "inconnu") -> interfaces.InterfaceGraph:
    """Chaque opération de canal devient une opération `asyncapi` (publish/subscribe)."""
    digest = interfaces._digest(str(document))
    contrat = _contrat(application_id, "asyncapi", locator, environment, digest)
    graph = interfaces.InterfaceGraph(contracts=[contrat])
    try:
        operations = protocoles_outils.operations_asyncapi(document)
    except Exception as exc:  # noqa: BLE001 - un document hostile reste un diagnostic
        graph.partial = True
        graph.diagnostics.append(f"document AsyncAPI illisible ({type(exc).__name__})")
        return graph
    if not operations:
        graph.partial = True
        graph.diagnostics.append("aucune opération de canal lisible")
        return graph
    for info in operations:
        canal, identifiant, sens = info["canal"], info["identifiant"], info["sens"]
        operation = interfaces.Operation(
            id=interfaces._id("op", contrat.id, "asyncapi", canal, identifiant, sens),
            contract_id=contrat.id, protocol="asyncapi", method=sens.upper(), path=canal,
            name=identifiant, version=None, environment=environment)
        graph.operations.append(operation)
        graph.assertions.append(_assertion(contrat, operation, f"ASYNCAPI {sens} {canal}"))
    return interfaces._dedupliquer(graph)
