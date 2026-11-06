"""Naissance relationnelle : manifeste, résolution déterministe et revue gouvernée."""
import os

import pytest

from meridian.adapters.outbound.postgres import depot
from meridian.adapters.outbound.postgres import relations_naissance as depot_relations
from meridian.application import relations_naissance as resolution
from meridian.domain import naissance_relationnelle as domaine


def _jumeau(identifiant="app-a", **extra):
    return {"id": identifiant, "tenant_id": "banque", "nom": identifiant.upper(),
            "type": "APPLICATION", "application_id": identifiant,
            "equipe": f"Équipe {identifiant}", "proprietaire": f"Équipe {identifiant}",
            "statut": "actif", "perimetre_id": "paiements", **extra}


def _commande(identifiant="cmd-1", **extra):
    return {"id": identifiant, "environnement": "prod", **extra}


def _claim(predicat, objet, identifiant=1, preuve="git://repo@app:src/a.py#L1-L1",
           portee=None, boundary_evidence=()):
    claim = {"id": identifiant, "predicat": predicat, "objet": objet,
             "statut": "PROPOSED", "confiance": 0.8, "preuve": preuve}
    if portee:
        claim["portee"] = portee
    if boundary_evidence:
        claim["boundary_evidence"] = list(boundary_evidence)
    return claim


def _manifeste(twin_id, *, exposes=(), consomme=(), statut="CONFIRMED"):
    return domaine.ManifesteNaissance(
        tenant_id="banque", twin_id=twin_id, birth_run_id=f"cmd-{twin_id}",
        application_id=twin_id, status=statut, owner=f"Équipe {twin_id}",
        exposures=tuple(domaine.Exposition(
            operation=objet, environment="prod", portee="SERVICE") for objet in exposes),
        consumptions=tuple(domaine.Consommation(
            logical_ref=objet, environment="prod", portee="EXTERNAL") for objet in consomme),
    )


def test_un_manifeste_porte_ses_expositions_ses_consommations_et_ses_preuves():
    manifeste = resolution.manifeste_depuis_claims(
        _commande(), _jumeau(), [
            _claim("EXPOSE", "GET /articles", 1),
            _claim("CONSOMME", "jms/OrderQueue", 2),
        ], birth_run_id="cmd-1")

    assert manifeste.twin_id == "app-a" and manifeste.tenant_id == "banque"
    assert [x.operation for x in manifeste.exposures] == ["GET /articles"]
    assert [x.logical_ref for x in manifeste.consumptions] == ["jms/OrderQueue"]
    assert manifeste.exposures[0].evidence_ids == ("claim:1", "preuve:git://repo@app:src/a.py#L1-L1")
    assert manifeste.status == "CONFIRMED" and manifeste.visibility == "TEAM"


def test_un_manifeste_sans_claim_dit_explicitement_ce_qui_manque():
    manifeste = resolution.manifeste_depuis_claims(
        _commande(), _jumeau(), [], birth_run_id="cmd-1", partial=True)
    assert manifeste.exposures == () and manifeste.consumptions == ()
    assert any("partielle" in x for x in manifeste.unknowns)
    assert any("exposition" in x for x in manifeste.unknowns)
    assert any("consommation" in x for x in manifeste.unknowns)


def test_une_url_avec_identifiants_est_refusee():
    with pytest.raises(ValueError):
        domaine.Exposition(operation="https://user:pw@example.test/api")


def test_la_naissance_ne_publie_pas_avant_l_etat_ne():
    with pytest.raises(resolution.NaissanceNonPrete):
        resolution.verifier_prealables_naissance(_commande(), _jumeau(), "en_cours")
    resolution.verifier_prealables_naissance(_commande(), _jumeau(), "ne")


def test_un_twin_sans_proprietaire_ou_sans_perimetre_ne_peut_pas_naitre():
    sans_owner = _jumeau()
    sans_owner["proprietaire"] = ""
    sans_owner["equipe"] = ""
    with pytest.raises(resolution.NaissanceNonPrete):
        resolution.verifier_prealables_naissance(_commande(), sans_owner, "ne")

    sans_perimetre = _jumeau()
    sans_perimetre["perimetre_id"] = ""
    with pytest.raises(resolution.NaissanceNonPrete):
        resolution.verifier_prealables_naissance(_commande(), sans_perimetre, "ne")


def test_une_consommation_est_jointe_a_une_exposition_declaree():
    nouveau = resolution.manifeste_depuis_claims(
        _commande(), _jumeau("app-a"), [_claim("CONSOMME", "GET /articles", 11, portee="EXTERNAL")],
        birth_run_id="cmd-a")
    existant = resolution.manifeste_depuis_claims(
        _commande("cmd-b"), _jumeau("app-b"), [_claim("EXPOSE", "GET /articles", 22, portee="SERVICE")],
        birth_run_id="cmd-b")

    resultat = resolution.proposer_relations(nouveau, [existant])

    assert len(resultat.propositions) == 1
    proposition = resultat.propositions[0]
    assert (proposition.consumer_id, proposition.provider_id) == ("app-a", "app-b")
    assert proposition.mode == "DECLARED" and proposition.state == "supposee"
    assert proposition.object == "GET /articles"
    assert "claim:11" in proposition.evidence_ids and "claim:22" in proposition.evidence_ids


def test_la_resolution_est_symetrique():
    nouveau = resolution.manifeste_depuis_claims(
        _commande(), _jumeau("app-a"), [_claim("EXPOSE", "POST /orders", 11, portee="SERVICE")],
        birth_run_id="cmd-a")
    existant = resolution.manifeste_depuis_claims(
        _commande("cmd-b"), _jumeau("app-b"), [_claim("CONSOMME", "POST /orders", 22, portee="EXTERNAL")],
        birth_run_id="cmd-b")

    resultat = resolution.proposer_relations(nouveau, [existant])

    assert len(resultat.propositions) == 1
    proposition = resultat.propositions[0]
    assert (proposition.consumer_id, proposition.provider_id) == ("app-b", "app-a")


def test_un_environnement_incompatible_ne_produit_pas_de_relation():
    nouveau = resolution.manifeste_depuis_claims(
        _commande(environnement="prod"), _jumeau("app-a"),
        [_claim("CONSOMME", "GET /articles", 11, portee="EXTERNAL")], birth_run_id="cmd-a")
    existant = resolution.manifeste_depuis_claims(
        _commande("cmd-b", environnement="dev"), _jumeau("app-b"),
        [_claim("EXPOSE", "GET /articles", 22, portee="SERVICE")], birth_run_id="cmd-b")

    resultat = resolution.proposer_relations(nouveau, [existant])

    assert resultat.propositions == ()
    assert resultat.sans_candidat[0]["reference"] == "GET /articles"


def test_les_routes_techniques_sont_classees_et_non_eligibles():
    manifeste = resolution.manifeste_depuis_claims(
        _commande(), _jumeau("app-a"), [
            _claim("EXPOSE", "GET /health", 1),
            _claim("EXPOSE", "GET /api/admin/users", 2),
            _claim("EXPOSE", "POST /demo/reinitialiser", 3),
            _claim("EXPOSE", "GET /articles", 4),
        ], birth_run_id="cmd-a")
    portees = {x.operation: x.portee for x in manifeste.exposures}
    assert portees["GET /health"] == "HEALTH"
    assert portees["GET /api/admin/users"] == "ADMIN"
    assert portees["POST /demo/reinitialiser"] == "DEMO"
    assert portees["GET /articles"] == "UNKNOWN"
    assert all(not x.eligible for x in manifeste.exposures)


def test_une_exposition_interne_n_est_pas_matchee():
    nouveau = _manifeste("app-a", consomme=["GET /articles"])
    existant = domaine.ManifesteNaissance(
        tenant_id="banque", twin_id="app-b", birth_run_id="cmd-b",
        application_id="app-b", status="CONFIRMED", owner="Équipe app-b",
        exposures=(domaine.Exposition(operation="GET /articles", environment="prod",
                                      portee="INTERNAL"),))
    resultat = resolution.proposer_relations(nouveau, [existant])
    assert resultat.propositions == ()
    assert any("exposition INTERNAL" in x["raison"] for x in resultat.sans_candidat)


def test_une_consommation_inconnue_n_est_pas_matchee():
    existant = _manifeste("app-b", exposes=["GET /articles"])
    nouveau = domaine.ManifesteNaissance(
        tenant_id="banque", twin_id="app-a", birth_run_id="cmd-a",
        application_id="app-a", status="CONFIRMED", owner="Équipe app-a",
        consumptions=(domaine.Consommation(logical_ref="GET /articles", environment="prod",
                                           portee="UNKNOWN"),))
    resultat = resolution.proposer_relations(nouveau, [existant])
    assert resultat.propositions == ()
    assert any("consommation UNKNOWN" in x["raison"] for x in resultat.sans_candidat)


def test_deux_twins_de_la_meme_application_ne_produisent_pas_de_relation():
    nouveau = domaine.ManifesteNaissance(
        tenant_id="banque", twin_id="app-a", birth_run_id="cmd-a",
        application_id="meme-application", status="CONFIRMED", owner="Équipe app-a",
        consumptions=(domaine.Consommation(logical_ref="GET /articles", environment="prod",
                                           portee="EXTERNAL"),))
    existant = domaine.ManifesteNaissance(
        tenant_id="banque", twin_id="app-b", birth_run_id="cmd-b",
        application_id="meme-application", status="CONFIRMED", owner="Équipe app-b",
        exposures=(domaine.Exposition(operation="GET /articles", environment="prod",
                                      portee="SERVICE"),))
    resultat = resolution.proposer_relations(nouveau, [existant])
    assert resultat.propositions == ()
    assert any("même application" in x["raison"] for x in resultat.sans_candidat)


def test_une_ressource_intermediaire_produit_une_relation():
    nouveau = domaine.ManifesteNaissance(
        tenant_id="banque", twin_id="app-a", birth_run_id="cmd-a",
        application_id="app-a", status="CONFIRMED", owner="Équipe app-a",
        consumptions=(domaine.Consommation(
            logical_ref="ORDER.QUEUE", environment="prod", portee="EXTERNAL",
            ressource_id="mq:ORDER.QUEUE"),))
    existant = domaine.ManifesteNaissance(
        tenant_id="banque", twin_id="app-b", birth_run_id="cmd-b",
        application_id="app-b", status="CONFIRMED", owner="Équipe app-b",
        ressources=(domaine.Ressource(
            id="mq:ORDER.QUEUE", kind="QUEUE", nom="ORDER.QUEUE",
            owner_twin_id="app-b", portee="SERVICE", environment="prod"),))

    resultat = resolution.proposer_relations(nouveau, [existant])

    assert len(resultat.propositions) == 1
    proposition = resultat.propositions[0]
    assert proposition.via == "mq:ORDER.QUEUE"
    assert proposition.transport == "JMS"
    assert proposition.object == "ORDER.QUEUE"
    assert proposition.portee == "SERVICE"


def test_une_ressource_interne_ne_produit_pas_de_relation():
    nouveau = domaine.ManifesteNaissance(
        tenant_id="banque", twin_id="app-a", birth_run_id="cmd-a",
        application_id="app-a", status="CONFIRMED", owner="Équipe app-a",
        consumptions=(domaine.Consommation(
            logical_ref="ORDER.QUEUE", environment="prod", portee="EXTERNAL",
            ressource_id="mq:ORDER.QUEUE"),))
    existant = domaine.ManifesteNaissance(
        tenant_id="banque", twin_id="app-b", birth_run_id="cmd-b",
        application_id="app-b", status="CONFIRMED", owner="Équipe app-b",
        ressources=(domaine.Ressource(
            id="mq:ORDER.QUEUE", kind="QUEUE", nom="ORDER.QUEUE",
            owner_twin_id="app-b", portee="INTERNAL", environment="prod"),))

    resultat = resolution.proposer_relations(nouveau, [existant])

    assert resultat.propositions == ()


def test_un_proprietaire_confirme_et_un_autre_refuse():
    proposition = domaine.PropositionRelation(
        tenant_id="banque", consumer_id="app-a", provider_id="app-b", object="GET /articles",
        consumer_owner="alice", provider_owner="bob", confidence=0.8)

    confirmee = domaine.decider(proposition, "confirmer", "alice")
    assert confirmee.state == "confirmee"
    assert confirmee.confirmations == ("alice",)

    with pytest.raises(domaine.AutoriteInsuffisante):
        domaine.decider(proposition, "confirmer", "mallory")

    contestee = domaine.decider(proposition, "contester", "bob", motif="pas d'appel observé")
    assert contestee.state == "contestee" and contestee.review_note == "pas d'appel observé"


def test_un_twin_provisoire_ne_peut_pas_confirmer_une_relation():
    nouveau = resolution.manifeste_depuis_claims(
        _commande(), _jumeau("app-a", statut="observation"),
        [_claim("CONSOMME", "GET /articles", 11, portee="EXTERNAL")], birth_run_id="cmd-a")
    existant = resolution.manifeste_depuis_claims(
        _commande("cmd-b"), _jumeau("app-b"), [_claim("EXPOSE", "GET /articles", 22, portee="SERVICE")],
        birth_run_id="cmd-b")
    proposition = resolution.proposer_relations(nouveau, [existant]).propositions[0]
    assert proposition.mode == "PROPOSED"
    with pytest.raises(domaine.RelationInvalide):
        domaine.decider(proposition, "confirmer", "Équipe app-a")


def test_une_relation_critique_exige_les_deux_proprietaires():
    proposition = domaine.PropositionRelation(
        tenant_id="banque", consumer_id="app-a", provider_id="app-b", object="GET /articles",
        consumer_owner="alice", provider_owner="bob", confidence=0.9)

    première = domaine.decider(proposition, "confirmer", "alice", critique=True)
    assert première.state == "validation" and première.confirmations == ("alice",)

    seconde = domaine.decider(première, "confirmer", "bob", critique=True)
    assert seconde.state == "confirmee"
    assert set(seconde.confirmations) == {"alice", "bob"}


def test_l_observation_renforce_sans_confirmer():
    proposition = domaine.PropositionRelation(
        tenant_id="banque", consumer_id="app-a", provider_id="app-b", object="GET /articles")
    observee = domaine.marquer_observee(proposition, evidence_ids=["trace:1"])
    assert observee.state == "observee" and observee.mode == "OBSERVED"
    assert observee.last_observed_at
    assert "trace:1" in observee.evidence_ids


@pytest.mark.skipif(not os.environ.get("JUMEAU_PG_DSN"), reason="JUMEAU_PG_DSN non défini")
def test_celebrer_naissance_persiste_le_manifeste_et_emmet_twin_born(conn):
    jumeau = _jumeau("app-a")
    source = {"nom": "app-a-src", "type": "GIT", "emplacement": "/depot/app-a", "curseur": "sha1"}
    claims = [{
        "sujet": "APP-A", "predicat": "EXPOSE", "objet": "GET /articles", "type": "API_USAGE",
        "confiance": 0.9, "portee": "SERVICE",
        "preuves": [{"locator": "git://repo@sha1:src/a.py#L1-L1", "chemin": "src/a.py",
                    "sha": "sha1", "ligne_debut": 1, "ligne_fin": 1,
                    "citation": "GET /articles", "hash": "h"}],
    }]
    depot.enregistrer(conn, jumeau, source, claims, {"extracteur": "test", "version": "1"})

    resultat = depot_relations.celebrer_naissance(conn, _commande("cmd-a"), jumeau, acteur="test")

    assert resultat["evenement_emis"] is True
    assert resultat["manifeste"]["twin_id"] == "app-a"
    assert conn.execute("SELECT count(*) FROM execution_outbox WHERE type = 'twin.born'").fetchone()[0] == 1
    assert depot_relations.lire_manifestes(conn, "banque")[0].twin_id == "app-a"
    # Rejeu : le manifeste est stable, l'événement n'est pas dupliqué.
    encore = depot_relations.celebrer_naissance(conn, _commande("cmd-a"), jumeau, acteur="test")
    assert encore["evenement_emis"] is False
    assert conn.execute("SELECT count(*) FROM execution_outbox WHERE type = 'twin.born'").fetchone()[0] == 1


@pytest.mark.skipif(not os.environ.get("JUMEAU_PG_DSN"), reason="JUMEAU_PG_DSN non défini")
def test_rafraichir_les_manifestes_legacy_applique_la_portee(conn):
    jumeau = _jumeau("app-a")
    depot.enregistrer(conn, jumeau,
                      {"nom": "app-a-src", "type": "GIT", "emplacement": "/depot/app-a",
                       "curseur": "sha1"},
                      [{"sujet": "app-a", "predicat": "EXPOSE", "objet": "GET /health",
                        "type": "API_USAGE", "confiance": 0.9,
                        "preuves": [{"locator": "git://repo@sha1:app-a.py#L1-L1",
                                     "chemin": "app-a.py", "sha": "sha1", "ligne_debut": 1,
                                     "ligne_fin": 1, "citation": "GET /health", "hash": "h"}]}],
                      {"extracteur": "test", "version": "1"})
    depot_relations.backfill_manifestes(conn, "banque", appliquer=True)

    dry = depot_relations.rafraichir_manifestes_legacy(conn, "banque")
    assert dry["a_rafraichir"] == ["app-a"]
    applied = depot_relations.rafraichir_manifestes_legacy(conn, "banque", appliquer=True)
    assert applied["rafraichis"] == ["app-a"]
    manifeste = next(m for m in depot_relations.lire_manifestes(conn, "banque")
                     if m.twin_id == "app-a")
    assert manifeste.exposures[0].portee == "HEALTH"
    assert manifeste.exposures[0].boundary_evidence == ("heuristique:chemin:health",)


@pytest.mark.skipif(not os.environ.get("JUMEAU_PG_DSN"), reason="JUMEAU_PG_DSN non défini")
def test_le_handler_twin_born_est_idempotent(conn):
    a = _manifeste("app-a", consomme=["GET /articles"])
    b = _manifeste("app-b", exposes=["GET /articles"])
    depot_relations.enregistrer_manifeste(conn, a)
    depot_relations.enregistrer_manifeste(conn, b)

    premier = depot_relations.traiter_twin_born(conn, b.as_dict())
    second = depot_relations.traiter_twin_born(conn, b.as_dict())

    assert premier["propositions"] == 1 and second["propositions"] == 1
    assert len(depot_relations.lister_propositions(conn, "banque")) == 1


@pytest.mark.skipif(not os.environ.get("JUMEAU_PG_DSN"), reason="JUMEAU_PG_DSN non défini")
def test_backfill_manifestes_dry_run_puis_apply(conn):
    for jumeau, predicat, objet in (
        (_jumeau("app-a"), "CONSOMME", "GET /articles"),
        (_jumeau("app-b"), "EXPOSE", "GET /articles"),
    ):
        depot.enregistrer(conn, jumeau,
                          {"nom": f"{jumeau['id']}-src", "type": "GIT",
                           "emplacement": f"/depot/{jumeau['id']}", "curseur": "sha1"},
                          [{"sujet": jumeau["id"], "predicat": predicat, "objet": objet,
                            "type": "API_USAGE", "confiance": 0.9,
                            "portee": "EXTERNAL" if predicat == "CONSOMME" else "SERVICE",
                            "preuves": [{"locator": f"git://repo@sha1:{jumeau['id']}.py#L1-L1",
                                         "chemin": f"{jumeau['id']}.py", "sha": "sha1",
                                         "ligne_debut": 1, "ligne_fin": 1,
                                         "citation": objet, "hash": "h"}]}],
                          {"extracteur": "test", "version": "1"})

    dry = depot_relations.backfill_manifestes(conn, "banque")
    assert dry["dry_run"] is True
    assert set(dry["a_creer"]) == {"app-a", "app-b"}
    assert depot_relations.lire_manifestes(conn, "banque") == []

    applied = depot_relations.backfill_manifestes(conn, "banque", appliquer=True)
    assert set(applied["crees"]) == {"app-a", "app-b"}
    assert {m.twin_id for m in depot_relations.lire_manifestes(conn, "banque")} == {"app-a", "app-b"}

    again = depot_relations.backfill_manifestes(conn, "banque", appliquer=True)
    assert again["a_creer"] == []
    assert set(again["ignores"]) == {"app-a", "app-b"}


@pytest.mark.skipif(not os.environ.get("JUMEAU_PG_DSN"), reason="JUMEAU_PG_DSN non défini")
def test_le_resolveur_persiste_et_revoit_une_proposition(conn):
    a = _manifeste("app-a", consomme=["GET /articles"])
    b = _manifeste("app-b", exposes=["GET /articles"])
    depot_relations.enregistrer_manifeste(conn, a)
    depot_relations.enregistrer_manifeste(conn, b)

    depot_relations.traiter_twin_born(conn, b.as_dict())
    propositions = depot_relations.lister_propositions(conn, "banque")
    assert len(propositions) == 1
    relation_id = propositions[0]["id"]
    assert propositions[0]["state"] == "supposee"
    assert propositions[0]["transport"] == "HTTP"
    assert propositions[0]["portee"] == "SERVICE"

    tranchee = depot_relations.review_proposition(
        conn, "banque", relation_id, decision="confirmer", acteur="Équipe app-a")
    assert tranchee.state == "confirmee"
    relue = depot_relations.lister_propositions(conn, "banque")[0]
    assert relue["state"] == "confirmee" and relue["reviewed_by"] == "Équipe app-a"
