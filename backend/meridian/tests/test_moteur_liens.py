"""Découverte des liens entre composants : producteurs, consommateurs, soupçons.

Le jeu de tests porte sur un petit système contrôlé : un backend Comptes expose une API,
une gateway publie `/accounts`, Antifraude l'appelle, son frontend appelle son backend,
un appel tiers part vers Stripe, et une trace contredit la configuration.
"""
from __future__ import annotations

from meridian.adapters.outbound.connectors.decouverte_composants import extraire_depot
from meridian.application.moteur_liens import moteur_liens, revoir_lien
from meridian.domain.liens_composants import IdentiteDeclaree, Preuve, SourceDepot


def _comptes(*, avec_deploiement: bool = True) -> SourceDepot:
    fichiers = {
        "src/main/java/com/acme/comptes/AccountsController.java": """
package com.acme.comptes;
import org.springframework.web.bind.annotation.*;
@RestController
@RequestMapping("/accounts")
public class AccountsController {
    @GetMapping("/{id}")
    public String detail(@PathVariable("id") Long id) { return "ok"; }
    @GetMapping
    public String list() { return "ok"; }
}
""",
        "src/main/resources/application.yml": """
server:
  servlet:
    context-path: /api
""",
        "openapi.yaml": """
openapi: 3.0.0
info:
  title: Comptes
  version: "1.4"
paths:
  /accounts/{id}:
    get:
      operationId: getAccount
  /accounts:
    get:
      operationId: listAccounts
""",
    }
    if avec_deploiement:
        fichiers["src/main/resources/application.yml"] += """
spring:
  application:
    name: comptes-api
"""
        fichiers.update({
            "k8s/deployment.yaml": """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: comptes-api
  labels:
    app: comptes
spec:
  template:
    spec:
      containers:
        - name: comptes-api
          image: registry/comptes-api:1.4
""",
            "k8s/service.yaml": """
apiVersion: v1
kind: Service
metadata:
  name: comptes-api
spec:
  selector:
    app: comptes
  ports:
    - port: 8080
""",
            "k8s/ingress.yaml": """
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: comptes
spec:
  rules:
    - host: gateway.internal
      http:
        paths:
          - path: /accounts
            pathType: Prefix
            backend:
              service:
                name: comptes-api
                port:
                  number: 8080
""",
        })
    return SourceDepot(
        application_id="comptes", composant_id="comptes-api", environment="prod",
        owner="Équipe comptes", fichiers=fichiers)


def _antifraude_backend() -> SourceDepot:
    return SourceDepot(
        application_id="antifraude", composant_id="antifraude-backend", environment="prod",
        owner="Équipe antifraude", fichiers={
            "src/main/java/com/acme/antifraude/ComptesClient.java": """
package com.acme.antifraude;
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.*;
@FeignClient(name = "comptes-api", url = "${comptes.base-url}", path = "/accounts")
public interface ComptesClient {
    @GetMapping("/{id}")
    String get(@PathVariable("id") Long id);
}
""",
            "src/main/java/com/acme/antifraude/InternalAccountsController.java": """
package com.acme.antifraude;
import org.springframework.web.bind.annotation.*;
@RestController
@RequestMapping("/internal/accounts")
public class InternalAccountsController {
    @GetMapping("/{id}")
    public String detail(@PathVariable("id") Long id) { return "ok"; }
}
""",
            "src/main/resources/application.yml": """
spring:
  application:
    name: antifraude-backend
comptes:
  base-url: http://gateway.internal/accounts
""",
            "k8s/deployment.yaml": """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: antifraude-backend
  labels:
    app: antifraude
spec:
  template:
    spec:
      containers:
        - name: antifraude-backend
          image: registry/antifraude-backend:2.0
""",
            "k8s/service.yaml": """
apiVersion: v1
kind: Service
metadata:
  name: antifraude-backend
spec:
  selector:
    app: antifraude
""",
        })


def _antifraude_frontend() -> SourceDepot:
    return SourceDepot(
        application_id="antifraude", composant_id="antifraude-frontend", environment="prod",
        fichiers={
            "src/api.js": """
import axios from "axios";
export const getAccount = (id) =>
  axios.get(`http://antifraude-backend:8080/internal/accounts/${id}`);
""",
        })


def _gateway() -> SourceDepot:
    return SourceDepot(
        application_id="plateforme", composant_id="gateway", environment="prod",
        type_composant="GATEWAY", fichiers={
            "k8s/ingress.yaml": """
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: comptes
spec:
  rules:
    - host: gateway.internal
      http:
        paths:
          - path: /accounts
            backend:
              service:
                name: comptes-api
""",
        })


def _legacy() -> SourceDepot:
    return SourceDepot(
        application_id="legacy", composant_id="legacy-comptes", environment="prod",
        fichiers={
            "src/main/java/com/acme/legacy/LegacyAccountsController.java": """
package com.acme.legacy;
import org.springframework.web.bind.annotation.*;
@RestController
@RequestMapping("/accounts")
public class LegacyAccountsController {
    @GetMapping("/{id}")
    public String detail(@PathVariable("id") Long id) { return "ok"; }
}
""",
            "k8s/service.yaml": """
apiVersion: v1
kind: Service
metadata:
  name: legacy-comptes
spec:
  selector:
    app: legacy
""",
        })


def _lien(rapport, operation, consommateur="antifraude-backend"):
    return next(lien for lien in rapport.liens
                if lien.operation == operation and lien.consommateur_composant_id == consommateur)


def test_lien_inter_app_rest_avec_preuves():
    rapport = moteur_liens([
        extraire_depot(_comptes()),
        extraire_depot(_antifraude_backend()),
    ])

    lien = _lien(rapport, "GET /accounts/{id}")
    assert lien.nature == "mesh"
    assert lien.state == "suggere"
    assert lien.fournisseur_composant_id == "comptes-api"
    assert lien.fournisseur_application_id == "comptes"
    assert lien.portee == "SERVICE"
    assert lien.eligible is True
    assert lien.verifications == ("implemente", "configure")
    assert lien.confiance >= 0.8
    assert not lien.missing_evidence
    sources = {preuve.source for preuve in lien.preuves}
    assert {"CODE", "CONFIG", "CONTRAT", "DEPLOIEMENT"} <= sources
    assert rapport.questions == ()


def test_front_back_reste_un_lien_interne():
    rapport = moteur_liens([
        extraire_depot(_comptes()),
        extraire_depot(_antifraude_backend()),
        extraire_depot(_antifraude_frontend()),
    ])

    lien = _lien(rapport, "GET /internal/accounts/{id}",
                 consommateur="antifraude-frontend")
    assert lien.nature == "interne"
    assert lien.fournisseur_composant_id == "antifraude-backend"
    assert lien not in rapport.mesh
    assert lien in rapport.internes


def test_gateway_seule_ouvre_une_question_sur_le_producteur():
    reporting = SourceDepot(
        application_id="reporting", composant_id="reporting-api", environment="prod",
        fichiers={
            "src/main/resources/application.yml": """
reporting:
  comptes-url: http://gateway.internal/accounts/42
""",
        })

    rapport = moteur_liens([extraire_depot(_gateway()), extraire_depot(reporting)])

    assert rapport.mesh == ()
    question = next(question for question in rapport.questions
                    if question.type == "SERVICE_INCONNU")
    assert "comptes-api" in question.question
    assert question.candidats == ()
    assert "déclarer le service comptes-api" in question.next_check


def test_api_tierce_reste_externe():
    paiements = SourceDepot(
        application_id="paiements", composant_id="paiements-api", environment="prod",
        fichiers={
            "src/main.js": """
import axios from "axios";
export const payer = (jeton) => axios.post("https://api.stripe.com/v1/charges", jeton);
""",
        })

    rapport = moteur_liens([extraire_depot(paiements)])

    assert len(rapport.externes) == 1
    lien = rapport.externes[0]
    assert lien.nature == "externe"
    assert lien.fournisseur_service == "api.stripe.com"
    assert lien.fournisseur_composant_id == ""
    assert lien.eligible is False
    assert rapport.mesh == ()


def test_configuration_et_trace_contradictoires():
    antifraude = _antifraude_backend()
    fichiers = dict(antifraude.fichiers)
    fichiers["traces/traces.json"] = """
[
  {
    "component": "antifraude-backend",
    "application_id": "antifraude",
    "method": "GET",
    "url": "http://legacy-comptes/accounts/42",
    "operation": "GET /accounts/{id}"
  }
]
"""
    antifraude = SourceDepot(
        application_id=antifraude.application_id, composant_id=antifraude.composant_id,
        environment=antifraude.environment, owner=antifraude.owner, fichiers=fichiers)

    rapport = moteur_liens([
        extraire_depot(_comptes()),
        extraire_depot(antifraude),
        extraire_depot(_legacy()),
    ])

    contradictoires = [lien for lien in rapport.contradictions
                       if lien.operation == "GET /accounts/{id}"]
    assert len(contradictoires) == 2
    assert {lien.fournisseur_application_id for lien in contradictoires} == {"comptes", "legacy"}
    assert all(lien.state == "conteste" for lien in contradictoires)
    question = next(question for question in rapport.questions
                    if question.type == "CONTRADICTION")
    assert "GET /accounts/{id}" in question.question
    assert len(question.candidats) == 2


def test_revue_humaine_confirme_le_soupcon():
    rapport = moteur_liens([
        extraire_depot(_comptes()),
        extraire_depot(_antifraude_backend()),
    ])
    lien = _lien(rapport, "GET /accounts/{id}")

    confirme = revoir_lien(lien, "accepter", "Équipe comptes", motif="API publiée par la gateway")

    assert confirme.state == "confirme"
    assert confirme.eligible is True
    assert confirme.preuves[-1].source == "DECLARATION"
    assert confirme.preuves[-1].locator == "revue:Équipe comptes"
    assert "API publiée par la gateway" in confirme.preuves[-1].detail


def test_declaration_humaine_complete_l_identite_du_service():
    extractions = [
        extraire_depot(_comptes(avec_deploiement=False)),
        extraire_depot(_gateway()),
    ]
    reporting = SourceDepot(
        application_id="reporting", composant_id="reporting-api", environment="prod",
        fichiers={
            "src/main/resources/application.yml": """
reporting:
  comptes-url: http://gateway.internal/accounts/42
""",
        })
    extractions.append(extraire_depot(reporting))

    avant = moteur_liens(extractions)
    lien_avant = _lien(avant, "GET /accounts/{id}", consommateur="reporting-api")
    assert lien_avant.fournisseur_composant_id == "comptes-api"
    assert "comptes-api" in lien_avant.missing_evidence
    assert "configure" not in lien_avant.verifications

    declaration = IdentiteDeclaree(
        service_name="comptes-api", composant_id="comptes-api", application_id="comptes",
        environment="prod", acteur="Équipe plateforme",
        preuve=Preuve(source="DECLARATION", locator="revue:plateforme",
                      detail="le service comptes-api appartient à Comptes", mode="DECLARE",
                      confidence=1.0),
    )
    apres = moteur_liens(extractions, declarations=[declaration])
    lien_apres = _lien(apres, "GET /accounts/{id}", consommateur="reporting-api")

    assert lien_apres.portee == "SERVICE"
    assert "configure" in lien_apres.verifications
    assert not lien_apres.missing_evidence
    assert lien_apres.eligible is True
    assert any(preuve.source == "DECLARATION" for preuve in lien_apres.preuves)


def test_un_secret_de_configuration_n_est_jamais_repris():
    depot = SourceDepot(
        application_id="comptes", composant_id="comptes-api", environment="prod",
        fichiers={
            "src/main/resources/application.properties": """
db.password=super-secret
accounts.base-url=http://user:motdepasse@comptes.internal/accounts
""",
        })

    extraction = extraire_depot(depot)

    assert not any("password" in configuration.cle for configuration in extraction.configurations)
    assert not any("motdepasse" in configuration.valeur
                   for configuration in extraction.configurations)
    assert any("identifiants" in diagnostic for diagnostic in extraction.diagnostics)


def test_helm_values_suffisent_a_identifier_le_producteur():
    stock = SourceDepot(
        application_id="stock", composant_id="stock-api", environment="prod",
        fichiers={
            "src/main/java/com/acme/stock/StockController.java": """
package com.acme.stock;
import org.springframework.web.bind.annotation.*;
@RestController
@RequestMapping("/stock")
public class StockController {
    @GetMapping("/{sku}")
    public String stock(@PathVariable("sku") String sku) { return "ok"; }
}
""",
            "helm/values.yaml": """
image:
  repository: registry/stock-api
  tag: "1.0"
service:
  name: stock-api
  port: 8080
ingress:
  hosts:
    - host: gateway.internal
      paths:
        - /stock
""",
        })
    commandes = SourceDepot(
        application_id="commandes", composant_id="commandes-api", environment="prod",
        fichiers={
            "src/main/resources/application.yml": """
stock:
  base-url: http://gateway.internal/stock/ABC-1
""",
        })

    rapport = moteur_liens([extraire_depot(stock), extraire_depot(commandes)])

    lien = _lien(rapport, "GET /stock/{sku}", consommateur="commandes-api")
    assert lien.nature == "mesh"
    assert lien.fournisseur_composant_id == "stock-api"
    assert lien.portee == "SERVICE"
    assert "HELM" in {preuve.source for preuve in lien.preuves}


def test_jms_relie_l_emetteur_au_listener():
    comptabilite = SourceDepot(
        application_id="comptabilite", composant_id="comptabilite-api", environment="prod",
        fichiers={
            "src/main/java/com/acme/compta/PaymentListener.java": """
package com.acme.compta;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;
@Component
public class PaymentListener {
    @JmsListener(destination = "PAYMENT.EVENTS")
    public void receive(String message) { }
}
""",
            "src/main/resources/application.yml": """
spring:
  application:
    name: comptabilite-api
""",
        })
    paiements = SourceDepot(
        application_id="paiements", composant_id="paiements-api", environment="prod",
        fichiers={
            "src/main/java/com/acme/paiements/PaymentSender.java": """
package com.acme.paiements;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;
@Component
public class PaymentSender {
    private final JmsTemplate jmsTemplate;
    public PaymentSender(JmsTemplate jmsTemplate) { this.jmsTemplate = jmsTemplate; }
    public void send(String message) { jmsTemplate.convertAndSend("PAYMENT.EVENTS", message); }
}
""",
            "src/main/resources/application.yml": """
spring:
  application:
    name: paiements-api
""",
        })

    rapport = moteur_liens([extraire_depot(comptabilite), extraire_depot(paiements)])

    lien = _lien(rapport, "PAYMENT.EVENTS", consommateur="paiements-api")
    assert lien.protocole == "JMS"
    assert lien.fournisseur_composant_id == "comptabilite-api"
    assert lien.nature == "mesh"
    assert "portée de l'interface non établie" in lien.missing_evidence
    assert lien.eligible is False


def test_wsdl_et_configuration_wsdl_relient_le_service_soap():
    comptes = SourceDepot(
        application_id="comptes", composant_id="comptes-api", environment="prod",
        fichiers={
            "contracts/comptes.wsdl": """
<definitions xmlns="http://schemas.xmlsoap.org/wsdl/"
             xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
             targetNamespace="urn:comptes">
  <portType name="ComptesPortType">
    <operation name="getAccount"/>
  </portType>
  <binding name="ComptesBinding" type="ComptesPortType">
    <soap:binding style="document" transport="http://schemas.xmlsoap.org/soap/http"/>
    <operation name="getAccount">
      <soap:operation soapAction="urn:getAccount"/>
    </operation>
  </binding>
  <service name="ComptesService">
    <port name="ComptesPort" binding="ComptesBinding">
      <soap:address location="http://comptes-api:8080/ws/Comptes"/>
    </port>
  </service>
</definitions>
""",
            "k8s/service.yaml": """
apiVersion: v1
kind: Service
metadata:
  name: comptes-api
spec:
  selector:
    app: comptes
""",
            "k8s/ingress.yaml": """
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: comptes-ws
spec:
  rules:
    - host: gateway.internal
      http:
        paths:
          - path: /ws
            backend:
              service:
                name: comptes-api
""",
        })
    antifraude = SourceDepot(
        application_id="antifraude", composant_id="antifraude-backend", environment="prod",
        fichiers={
            "src/main/resources/application.yml": """
comptes:
  wsdl-url: http://gateway.internal/ws/Comptes?wsdl
""",
        })

    rapport = moteur_liens([extraire_depot(comptes), extraire_depot(antifraude)])

    lien = _lien(rapport, "SOAP urn:getAccount", consommateur="antifraude-backend")
    assert lien.protocole == "SOAP"
    assert lien.fournisseur_composant_id == "comptes-api"
    assert lien.portee == "SERVICE"
    assert lien.eligible is True


def test_un_lien_mesh_devient_une_proposition_gouvernee():
    from meridian.application.moteur_liens import vers_proposition

    rapport = moteur_liens([
        extraire_depot(_comptes()),
        extraire_depot(_antifraude_backend()),
    ])
    lien = _lien(rapport, "GET /accounts/{id}")

    proposition = vers_proposition(
        lien, "banque", owners={"antifraude": "Équipe antifraude",
                                "comptes": "Équipe comptes"})

    assert proposition.consumer_id == "antifraude-backend"
    assert proposition.provider_id == "comptes-api"
    assert proposition.consumer_application_id == "antifraude"
    assert proposition.provider_application_id == "comptes"
    assert proposition.object == "GET /accounts/{id}"
    assert proposition.state == "supposee"
    assert proposition.mode == "INFERRED"
    assert proposition.portee == "SERVICE"
    assert proposition.transport == "HTTP"
    assert proposition.consumer_owner == "Équipe antifraude"
    assert proposition.provider_owner == "Équipe comptes"
    assert proposition.evidence_ids


def test_une_question_ouverte_devient_un_cas_de_resolution():
    from meridian.application.moteur_liens import vers_resolution_case

    reporting = SourceDepot(
        application_id="reporting", composant_id="reporting-api", environment="prod",
        fichiers={
            "src/main/resources/application.yml": """
reporting:
  comptes-url: http://gateway.internal/accounts/42
""",
        })
    rapport = moteur_liens([extraire_depot(_gateway()), extraire_depot(reporting)])
    question = next(question for question in rapport.questions
                    if question.type == "SERVICE_INCONNU")

    case = vers_resolution_case(question, "banque", "reporting-api",
                                owner="Équipe plateforme")

    assert case.twin_id == "reporting-api"
    assert case.reference == "ANY /accounts/42"
    assert "comptes-api" in case.missing_evidence
    assert "comptes-api" in case.next_check
    assert case.owner == "Équipe plateforme"
    assert case.status == "open"


def test_les_manifestes_et_bindings_existants_alimentent_le_moteur():
    from meridian.application.moteur_liens import extractions_depuis_manifests
    from meridian.domain.decouverte_liens import Binding
    from meridian.domain.naissance_relationnelle import Consommation, Exposition, ManifesteNaissance

    manifests = [
        ManifesteNaissance(
            tenant_id="banque", twin_id="comptes", birth_run_id="run-comptes",
            application_id="comptes", status="CONFIRMED", owner="Équipe comptes",
            exposures=(Exposition(
                kind="HTTP", operation="GET /accounts/{id}", environment="prod",
                portee="SERVICE", evidence_ids=("code:AccountsController#detail",)),)),
        ManifesteNaissance(
            tenant_id="banque", twin_id="antifraude", birth_run_id="run-antifraude",
            application_id="antifraude", status="CONFIRMED", owner="Équipe antifraude",
            consumptions=(Consommation(
                kind="HTTP", logical_ref="${comptes.base-url}",
                target_hint="GET /accounts/{id}", environment="prod",
                evidence_ids=("code:ComptesClient#get",)),)),
    ]
    bindings = [
        Binding(kind="PROPERTY", nom="comptes.base-url",
                valeur="http://gateway.internal/accounts", environment="prod",
                source="application.yml"),
        Binding(kind="GATEWAY_ROUTE", nom="/accounts", valeur="comptes-api",
                environment="prod", source="ingress.yaml"),
        Binding(kind="SERVICE", nom="comptes-api", valeur="comptes",
                environment="prod", source="service.yaml"),
    ]

    rapport = moteur_liens(extractions_depuis_manifests(manifests, bindings))

    lien = _lien(rapport, "GET /accounts/{id}", consommateur="antifraude")
    assert lien.nature == "mesh"
    assert lien.fournisseur_application_id == "comptes"
    assert lien.portee == "SERVICE"
    assert lien.verifications == ("implemente", "configure")
    assert any(preuve.source == "CODE" for preuve in lien.preuves)
    assert any(preuve.source == "CONFIG" for preuve in lien.preuves)
    assert any(preuve.source == "DEPLOIEMENT" for preuve in lien.preuves)
