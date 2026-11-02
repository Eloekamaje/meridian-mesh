"""Synchronisation générique CSV -> faits canoniques, capacité et rôles."""
import asyncio
from datetime import date

import pytest

from meridian.adapters.outbound.postgres import planification as depot
from meridian.adapters.outbound.travail import source_travail
from meridian.application.planification import capacite, roles, sync
from meridian.tests.conftest import besoin_pg

pytestmark = besoin_pg
TENANT = "banque"


def _csv(tmp_path):
    fichier = tmp_path / "travail.csv"
    fichier.write_text(
        "external_id,titre,equipe_id,equipe_nom,type,statut,priorite,estimation,unite,"
        "cycle_id,cycle_nom,cycle_debut,cycle_fin,cycle_termine,release_id,release_nom,"
        "release_date,release_statut,maj_source\n"
        "A-1,Premier,A,Équipe A,story,a_faire,haute,3,points,S1,Sprint 1,2026-01-01,2026-01-14,true,R1,R1,2026-02-01,prevue,2026-01-10\n"
        "A-2,Deuxième,A,Équipe A,story,termine,basse,2,points,S1,Sprint 1,2026-01-01,2026-01-14,true,R1,R1,2026-02-01,prevue,2026-01-10\n",
        encoding="utf-8")
    return fichier


def _source(conn, chemin):
    return depot.creer_source(conn, TENANT, {
        "id": "csv-test", "provider": "csv", "usage": "travail", "nom": "CSV test",
        "configuration": {"chemin": str(chemin)},
    })


def test_sync_csv_est_idempotente_et_produit_les_faits(conn, tmp_path):
    source = _source(conn, _csv(tmp_path))
    premier = sync.synchroniser_travail(depot, conn, source, source_travail(source))
    second = sync.synchroniser_travail(depot, conn, source, source_travail(source))

    assert premier["ecrits"] == 2 and second["ecrits"] == 2
    elements = depot.elements(conn, TENANT)
    assert len(elements) == 2
    assert {e["external_id"] for e in elements} == {"A-1", "A-2"}
    assert all(e["source_id"] == "csv-test" for e in elements)
    assert depot.equipes(conn, TENANT)[0]["id"] == "A"


def test_capacite_distingue_charge_engagee_et_non_estimee(conn, tmp_path):
    sync.synchroniser_travail(depot, conn, _source(conn, _csv(tmp_path)), source_travail(_source(conn, _csv(tmp_path))))
    resume = capacite.resume(depot, conn, TENANT, equipe_id="A")
    assert resume["equipes"][0]["equipe_id"] == "A"
    charge = resume["equipes"][0]["charges"][0]
    assert charge["unite"] == "points" and charge["total"] == 3
    assert charge["capacite"] is None and charge["marge"] is None


def test_role_effectif_et_refus_d_action(conn):
    depot.affecter_role(conn, TENANT, {
        "acteur": "alice", "role": "scrum_master", "perimetre_type": "equipe",
        "perimetre_id": "A", "source": "test"})
    assert roles.role_effectif(depot, conn, TENANT, "alice") == "scrum_master"
    with pytest.raises(roles.AccesRefuse):
        roles.exiger("scrum_master", "lire_budget")
    assert roles.role_effectif(depot, conn, TENANT, "inconnu") == "observateur"


def test_sync_people_alimente_membres_competences_et_capacite(conn, tmp_path):
    fichier = tmp_path / "people.csv"
    fichier.write_text(
        "equipe_id,equipe_nom,acteur,fte,role,competence,niveau,debut,fin,unite,capacite,confiance\n"
        "A,Équipe A,alice,1,dev,python,4,2026-01-01,2026-01-31,jours,20,0.8\n",
        encoding="utf-8")
    source = depot.creer_source(conn, TENANT, {
        "id": "people-csv", "provider": "csv", "usage": "people", "nom": "People CSV",
        "configuration": {"chemin": str(fichier)}})
    assert sync.synchroniser_people(depot, conn, source, __import__("meridian.adapters.outbound.travail", fromlist=["source_people"]).source_people(source))["ok"] is True
    assert depot.membres(conn, TENANT, "A")[0]["acteur"] == "alice"
    assert depot.competences(conn, TENANT, "A")[0]["competence"] == "python"
    assert depot.capacites(conn, TENANT, "A")[0]["valeur"] == 20


def test_sync_finance_alimente_budget_et_couts(conn, tmp_path):
    budgets = tmp_path / "budgets.csv"
    couts = tmp_path / "couts.csv"
    budgets.write_text("id,initiative_id,libelle,devise,enveloppe,periode\n"
                       "B1,init-1,Paiements,EUR,100000,2026\n", encoding="utf-8")
    couts.write_text("id,budget_id,equipe_id,periode,prevu,engage,reel,forecast\n"
                     "C1,B1,A,2026,10000,5000,3000,90000\n", encoding="utf-8")
    source = depot.creer_source(conn, TENANT, {
        "id": "finance-csv", "provider": "csv", "usage": "finance", "nom": "Finance CSV",
        "configuration": {"budgets": str(budgets), "couts": str(couts)}})
    assert sync.synchroniser_finance(depot, conn, source, __import__("meridian.adapters.outbound.travail", fromlist=["source_finance"]).source_finance(source))["budgets"] == 1
    from meridian.application.planification import budget
    resume = budget.resume(depot, conn, TENANT, "init-1")
    assert resume["budgets"][0]["forecast"] == 90000
    assert resume["budgets"][0]["variance"] == 10000


def test_sync_incidents_alimente_la_charge_non_planifiee(conn, tmp_path):
    fichier = tmp_path / "incidents.csv"
    fichier.write_text("external_id,titre,equipe_id,statut,estimation,unite,maj_source\n"
                       "INC-1,Panne,A,en_cours,4,heures,2026-01-10\n", encoding="utf-8")
    source = depot.creer_source(conn, TENANT, {
        "id": "incidents-csv", "provider": "csv", "usage": "incidents", "nom": "Incidents CSV",
        "configuration": {"chemin": str(fichier)}})
    from meridian.adapters.outbound.travail import source_incidents
    assert sync.synchroniser(depot, conn, source, source_incidents(source))["incidents"] == 1
    elements = depot.elements(conn, TENANT, equipe_id="A")
    assert elements[0]["categorie_charge"] == "non_planifiee"
    resume = capacite.resume(depot, conn, TENANT, equipe_id="A")
    charge = resume["equipes"][0]["charges"][0]
    assert charge["unite"] == "heures" and charge["non_planifiee"] == 4


def test_prevision_equipe_utilise_les_cycles_termines(conn):
    depot.enregistrer_equipe(conn, TENANT, {"id": "A", "nom": "Équipe A"})
    for numero, fin in enumerate(("2026-01-14", "2026-01-28", "2026-02-11"), 1):
        depot.enregistrer_cycle(conn, TENANT, {
            "id": f"S{numero}", "equipe_id": "A", "nom": f"Sprint {numero}",
            "debut": f"2026-01-{1 + (numero - 1) * 14:02d}", "fin": fin, "termine": True})
        depot.enregistrer_element(conn, TENANT, {
            "id": f"done-{numero}", "source_id": "src", "external_id": f"D-{numero}",
            "equipe_id": "A", "titre": "Terminé", "statut": "termine",
            "cycle_id": f"S{numero}", "estimation": {"valeur": 5, "unite": "points"},
            "maj_source": fin})
    depot.enregistrer_element(conn, TENANT, {
        "id": "reste", "source_id": "src", "external_id": "R-1", "equipe_id": "A",
        "titre": "Reste", "statut": "a_faire", "estimation": {"valeur": 10, "unite": "points"}})
    from meridian.application.planification import previsions
    resultat = previsions.prevoir_equipe(depot, conn, TENANT, "A", seed=2, simulations=300)
    assert resultat["methode"] == "velocite_sprint"
    assert resultat["p50"] <= resultat["p85"] <= resultat["p95"]


def test_calibration_d_une_prevision(conn):
    from datetime import date
    identifiant = depot.enregistrer_prevision(conn, TENANT, {
        "perimetre_type": "equipe", "perimetre_id": "A", "equipe_id": "A",
        "methode": "debit_hebdomadaire", "entree_hash": "h", "p50": "2026-02-01",
        "p85": "2026-02-15", "p95": "2026-03-01", "confiance": 0.7})
    prevision = depot.prevision(conn, TENANT, identifiant)
    calibration = depot.enregistrer_calibration(conn, TENANT, prevision, date(2026, 2, 10))
    assert calibration["p85_couvert"] is True
    assert calibration["ecart_jours"] == 9


def test_source_prioritaire_dedoublonne_un_meme_element(conn, tmp_path):
    def fichier(nom, titre):
        chemin = tmp_path / nom
        chemin.write_text("external_id,titre,equipe_id,statut,estimation,unite,maj_source\n"
                          f"X-1,{titre},A,a_faire,2,points,2026-01-10\n", encoding="utf-8")
        return chemin
    secondaire = depot.creer_source(conn, TENANT, {
        "id": "secondaire", "provider": "csv", "usage": "travail", "nom": "Secondaire",
        "prioritaire": False, "configuration": {"chemin": str(fichier("s.csv", "Secondaire"))}})
    primaire = depot.creer_source(conn, TENANT, {
        "id": "primaire", "provider": "csv", "usage": "travail", "nom": "Primaire",
        "prioritaire": True, "configuration": {"chemin": str(fichier("p.csv", "Primaire"))}})
    for source in (secondaire, primaire):
        sync.synchroniser_travail(depot, conn, source, source_travail(source))
    elements = depot.elements(conn, TENANT, equipe_id="A")
    assert len(elements) == 1
    assert elements[0]["titre"] == "Primaire"


def test_perimetre_equipe_filtre_les_lectures(conn):
    from types import SimpleNamespace
    from meridian.adapters.inbound.http import planification as http
    depot.affecter_role(conn, TENANT, {
        "acteur": "bob", "role": "scrum_master", "perimetre_type": "equipe",
        "perimetre_id": "A", "source": "test"})
    requete = SimpleNamespace(state=SimpleNamespace(tenant=TENANT, acteur="bob"), headers={})
    assert http._equipes_visibles(conn, requete, "scrum_master") == {"A"}
    admin = SimpleNamespace(state=SimpleNamespace(tenant=TENANT, acteur="bob"), headers={})
    assert http._equipes_visibles(conn, admin, "admin") is None


def test_temps_reel_absences_allocations_et_taux(conn, tmp_path):
    def ecrire(nom, contenu):
        chemin = tmp_path / nom
        chemin.write_text(contenu, encoding="utf-8")
        return str(chemin)
    travail = tmp_path / "travail.csv"
    travail.write_text("external_id,titre,equipe_id,statut,estimation,unite,maj_source\n"
                       "A-1,Travail,A,a_faire,2,points,2026-01-10\n", encoding="utf-8")
    temps = ecrire("temps.csv", "id,element_id,equipe_id,acteur,date_travail,valeur,unite\n"
                               "T1,A-1,A,alice,2026-01-10,3,heures\n")
    absences = ecrire("absences.csv", "id,equipe_id,acteur,debut,fin,valeur,unite\n"
                                     "AB1,A,alice,2026-01-10,2026-01-12,2,jours\n")
    allocations = ecrire("allocations.csv", "id,equipe_id,acteur,element_id,valeur,unite\n"
                                           "AL1,A,alice,A-1,50,pourcentage\n")
    taux = ecrire("taux.csv", "id,equipe_id,role,devise,cout_heure,debut,fin\n"
                             "TX1,A,dev,EUR,100,2026-01-01,2026-12-31\n")
    source_travail_csv = depot.creer_source(conn, TENANT, {
        "id": "travail-2", "provider": "csv", "usage": "travail", "nom": "Travail",
        "configuration": {"chemin": str(travail), "temps": temps}})
    sync.synchroniser_travail(depot, conn, source_travail_csv, source_travail(source_travail_csv))
    source_people = depot.creer_source(conn, TENANT, {
        "id": "people-2", "provider": "csv", "usage": "people", "nom": "People",
        "configuration": {"chemin": temps, "absences": absences, "allocations": allocations}})
    sync.synchroniser_people(depot, conn, source_people,
                             __import__("meridian.adapters.outbound.travail", fromlist=["source_people"]).source_people(source_people))
    source_finance = depot.creer_source(conn, TENANT, {
        "id": "finance-2", "provider": "csv", "usage": "finance", "nom": "Finance",
        "configuration": {"chemin": taux, "taux": taux}})
    sync.synchroniser_finance(depot, conn, source_finance,
                              __import__("meridian.adapters.outbound.travail", fromlist=["source_finance"]).source_finance(source_finance))
    assert depot.temps(conn, TENANT, "A")[0]["valeur"] == 3
    assert depot.absences(conn, TENANT, "A")[0]["valeur"] == 2
    assert depot.allocations(conn, TENANT, "A")[0]["valeur"] == 50
    assert depot.taux(conn, TENANT, "A")[0]["cout_heure"] == 100
    resume = capacite.resume(depot, conn, TENANT, equipe_id="A")
    assert resume["equipes"][0]["temps_reel"][0]["valeur"] == 3
    assert resume["equipes"][0]["absences"][0]["valeur"] == 2
