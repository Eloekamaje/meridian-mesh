"""Extraction des contrats en interfaces de composant.

La détection réutilise `connecteur_interfaces` ; la lecture réutilise les parseurs
`domain.interfaces` et `interfaces_protocoles`. Ce module ne fait que mapper le
résultat vers le modèle de liens.
"""
from __future__ import annotations

from meridian.adapters.outbound.connectors import connecteur_interfaces
from meridian.adapters.outbound.connectors.extraction_commune import preuve
from meridian.application import interfaces_protocoles
from meridian.domain import interfaces
from meridian.domain.liens_composants import Interface

__all__ = ["est_contrat", "extraire_contrat", "interface_depuis_operation"]


def est_contrat(fichier: str, texte: str) -> str:
    suffixe = "." + fichier.rsplit(".", 1)[-1].lower() if "." in fichier else ""
    if suffixe in (".yaml", ".yml", ".json") and connecteur_interfaces.est_openapi(texte):
        return "openapi"
    if suffixe in (".yaml", ".yml") and connecteur_interfaces.est_asyncapi(texte):
        return "asyncapi"
    if suffixe in (".wsdl", ".xml") and connecteur_interfaces.est_wsdl(texte):
        return "wsdl"
    if suffixe in (".graphql", ".gql") or connecteur_interfaces.est_graphql(texte):
        return "graphql"
    if suffixe == ".proto" or connecteur_interfaces.est_proto(texte):
        return "proto"
    return ""


def interface_depuis_operation(application: str, composant: str, operation, contrat,
                              environment: str) -> Interface:
    protocole = str(getattr(operation, "protocol", "") or "").lower()
    protocole = {
        "rest": "HTTP", "soap": "SOAP", "graphql": "GRAPHQL", "grpc": "GRPC",
        "asyncapi": "ASYNCAPI",
    }.get(protocole, "AUTRE")
    methode = str(getattr(operation, "method", "") or "")
    chemin = str(getattr(operation, "path", "") or "")
    if protocole == "HTTP":
        libelle = f"{methode.upper()} {chemin}".strip()
    elif protocole == "SOAP":
        libelle = f"SOAP {chemin}".strip()
    else:
        libelle = f"{methode.upper()} {chemin}".strip() if methode else chemin
    return Interface(
        composant_id=composant, application_id=application, protocole=protocole,
        operation=libelle or chemin or methode, methode=methode, chemin=chemin,
        nom=str(getattr(operation, "name", "") or libelle), environment=environment,
        source_kind="CONTRAT", contrat_ref=str(getattr(contrat, "id", "") or ""),
        preuves=(preuve(
            "CONTRAT", f"{contrat.locator}:{getattr(operation, 'name', '') or chemin}",
            f"{contrat.format} {contrat.version or ''} {libelle}".strip(), confidence=0.9),),
    )


def extraire_contrat(fichier: str, texte: str, application: str, composant: str,
                     environment: str, genre: str) -> tuple[list[Interface], list[str]]:
    diagnostics: list[str] = []
    if genre == "openapi":
        graph = interfaces.parse_openapi(application, texte, fichier, environment)
    elif genre == "wsdl":
        graph = interfaces.parse_wsdl(application, texte, fichier, environment)
    elif genre == "graphql":
        graph = interfaces_protocoles.parse_graphql(application, texte, fichier, environment)
    elif genre == "proto":
        graph = interfaces_protocoles.parse_proto(application, texte, fichier, environment)
    elif genre == "asyncapi":
        graph = interfaces_protocoles.parse_asyncapi(application, texte, fichier, environment)
    else:
        return [], diagnostics
    diagnostics.extend(f"{fichier} : {diagnostic}" for diagnostic in graph.diagnostics)
    contrats = {contrat.id: contrat for contrat in graph.contracts}
    resultat = []
    for operation in graph.operations:
        contrat = contrats.get(operation.contract_id)
        if contrat is None:
            continue
        resultat.append(interface_depuis_operation(
            application, composant, operation, contrat, environment))
    return resultat, diagnostics
