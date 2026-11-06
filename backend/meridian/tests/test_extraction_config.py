"""Extraction de configuration : namespace, ingress et réécritures."""
from __future__ import annotations

from meridian.adapters.outbound.connectors.decouverte_composants import extraire_depot
from meridian.application import moteur_liens
from meridian.domain.liens_composants import (
    Appel,
    Composant,
    Deploiement,
    ExtractionDepot,
    Interface,
    RoutePasserelle,
    SourceDepot,
)


def _depot(fichiers):
    return SourceDepot(application_id="comptes", composant_id="comptes-api",
                       environment="prod", fichiers=fichiers)


def test_namespace_est_extrait_du_deploiement():
    extraction = extraire_depot(_depot({
        "k8s/deployment.yaml": """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: comptes-api
  namespace: paiements
spec:
  template:
    spec:
      containers:
      - name: comptes-api
        image: registry/comptes:1
""",
    }))

    assert extraction.deploiements[0].namespace == "paiements"


def test_ingress_reecrit_le_chemin_backend():
    extraction = extraire_depot(_depot({
        "k8s/ingress.yaml": """
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: comptes
  namespace: paiements
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /accounts
spec:
  rules:
  - host: api.example.test
    http:
      paths:
      - path: /api/comptes
        pathType: Prefix
        backend:
          service:
            name: comptes-api
            port:
              number: 80
""",
    }))

    deploiement = extraction.deploiements[0]
    route = deploiement.routes[0]
    assert deploiement.namespace == "paiements"
    assert route.chemin == "/api/comptes"
    assert route.chemin_backend == "/accounts"


def test_rewrite_d_ingress_permet_la_portee_service():
    fournisseur = ExtractionDepot(
        composant=Composant(application_id="comptes", nom="comptes-api"),
        interfaces=(Interface(
            composant_id="comptes-api", application_id="comptes", protocole="HTTP",
            operation="GET /accounts/{id}", methode="GET", chemin="/accounts/{id}",
            environment="prod", source_kind="CODE"),),
        deploiements=(Deploiement(
            composant_id="comptes-api", application_id="comptes", environment="prod",
            service_name="comptes-api",
            routes=(RoutePasserelle(
                chemin="/api/comptes", service="comptes-api", host="api.example.test",
                environment="prod", chemin_backend="/accounts"),),
        ),),
    )
    consommateur = ExtractionDepot(
        composant=Composant(application_id="front", nom="front"),
        appels=(Appel(
            composant_id="front", application_id="front", protocole="HTTP",
            cible="http://api.example.test/api/comptes/42", cible_type="URL",
            methode="GET", chemin="/api/comptes/42", operation="GET /api/comptes/42",
            environment="prod", source_kind="CODE"),),
    )

    rapport = moteur_liens.moteur_liens([fournisseur, consommateur])

    assert len(rapport.liens) == 1
    assert rapport.liens[0].operation == "GET /accounts/{id}"
    assert rapport.liens[0].portee == "SERVICE"
