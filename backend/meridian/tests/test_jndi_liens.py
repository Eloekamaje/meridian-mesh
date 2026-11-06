"""JNDI : injection Java, binding et listener JMS."""
from __future__ import annotations

from meridian.application import moteur_liens
from meridian.domain.decouverte_liens import Binding
from meridian.domain.liens_composants import Appel, Composant, ExtractionDepot
from meridian.domain.naissance_relationnelle import Exposition, ManifesteNaissance


def _manifeste(twin_id: str, application_id: str, exposures=()) -> ManifesteNaissance:
    return ManifesteNaissance(
        tenant_id="banque", twin_id=twin_id, birth_run_id=f"run-{twin_id}",
        application_id=application_id, status="CONFIRMED", exposures=tuple(exposures))


def test_jndi_binding_relie_une_injection_a_un_listener():
    fournisseur = _manifeste("payments", "payments", [
        Exposition(
            kind="JMS", operation="PAYMENT.EVENTS", environment="prod",
            portee="SERVICE", evidence_ids=("code:payments:listener",)),
    ])
    consommateur = _manifeste("front", "front")
    binding = Binding(
        kind="JNDI", nom="java:comp/env/jms/PaymentEvents", valeur="PAYMENT.EVENTS",
        environment="prod", source="web.xml")
    extractions = moteur_liens.extractions_depuis_manifests(
        [consommateur, fournisseur], [binding])
    code = ExtractionDepot(
        composant=Composant(application_id="front", nom="front"),
        appels=(Appel(
            composant_id="front", application_id="front", protocole="JNDI",
            cible="java:comp/env/jms/PaymentEvents", cible_type="JNDI",
            operation="java:comp/env/jms/PaymentEvents",
            chemin="java:comp/env/jms/PaymentEvents",
            environment="prod", source_kind="CODE"),),
    )

    rapport = moteur_liens.moteur_liens([*extractions, code])

    assert len(rapport.liens) == 1
    lien = rapport.liens[0]
    assert lien.consommateur_composant_id == "front"
    assert lien.fournisseur_composant_id == "payments"
    assert lien.operation == "PAYMENT.EVENTS"
    assert lien.portee == "SERVICE"
