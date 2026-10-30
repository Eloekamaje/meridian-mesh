"""Spécialiste de preuve : mapping déterministe des claims vers constats et risques, sans écriture."""
from datetime import datetime, timedelta, timezone

import pytest

from jumeau import depot
from jumeau.specialiste_preuve import (
    TITRE_CONTESTE,
    TITRE_CONTRADICTION,
    TITRE_PERIMEE,
    TITRE_SANS_PREUVE,
    TITRE_SUFFISANTES,
    SpecialistePreuve,
    construire_propositions,
)
from jumeau.specialistes import ContexteSpecialiste, Specialiste
from jumeau.tests.conftest import ACTIVITE, JUMEAU, SOURCE, besoin_pg, claim as claim_ingere

MAINTENANT = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)


def iso(jours=0):
    return (MAINTENANT - timedelta(days=jours)).isoformat()


class FauxCurseur:
    def __init__(self, lignes):
        self.lignes = lignes

    def fetchall(self):
        return self.lignes


class FauxConn:
    def __init__(self, lignes=(), erreur=None):
        self.lignes = list(lignes)
        self.erreur = erreur
        self.requetes = []

    def execute(self, requete, parametres=None):
        self.requetes.append((requete, parametres))
        if self.erreur:
            raise self.erreur
        return FauxCurseur(self.lignes)


def preuve(identifiant=10, role="SUPPORT", jours=1, locator=None):
    return {
        "id": identifiant,
        "role": role,
        "locator": locator or f"git://tbt@sha1:fichier.py#L{identifiant}-L{identifiant}",
        "observee_le": iso(jours),
    }


def claim(identifiant=1, objet=None, statut="PROPOSED", confiance=0.9, preuves=None, twin_id="tbt"):
    return {
        "id": identifiant,
        "tenant_id": "banque",
        "twin_id": twin_id,
        "sujet": "TBT",
        "predicat": "DEPEND_DE",
        "objet": objet or f"objet-{identifiant}",
        "type": "DEPENDENCY",
        "statut": statut,
        "maturite": "M2",
        "confiance": confiance,
        "valide_depuis": iso(0),
        "valide_jusqua": None,
        "enregistre_le": iso(0),
        "origine": "INGESTION",
        "preuves": list(preuves or []),
    }


def contexte(conn, **extra):
    return ContexteSpecialiste(tenant="banque", conn=conn, maintenant=MAINTENANT.isoformat(), **extra)


def par_titre(propositions, titre):
    return next(proposition for proposition in propositions if proposition.titre == titre)


def test_claim_sans_preuve_support_produit_un_risque_trace():
    lignes = [claim(1, preuves=[preuve(11, role="CONTRE")])]

    resultat = SpecialistePreuve().analyser(contexte(FauxConn(lignes)))

    assert resultat.statut == "ok"
    risque = par_titre(resultat.propositions, TITRE_SANS_PREUVE)
    assert risque.type == "RISQUE"
    assert "claim:1" in risque.preuves and "11" in risque.preuves
    assert any(ref.startswith("git://tbt@sha1:") for ref in risque.preuves)
    assert risque.actions == ("demander_preuve", "verifier_preuve")
    assert 0.0 <= risque.confiance <= 1.0
    assert TITRE_SUFFISANTES not in [p.titre for p in resultat.propositions]


def test_preuve_perimee_par_fraicheur_et_claim_faible_ou_conteste():
    lignes = [
        claim(1, preuves=[preuve(11, jours=90)]),
        claim(2, statut="CONTESTED", preuves=[preuve(12)]),
        claim(3, confiance=0.2, preuves=[preuve(13)]),
    ]

    propositions = construire_propositions(lignes, maintenant=MAINTENANT.isoformat())

    perimee = par_titre(propositions, TITRE_PERIMEE)
    assert perimee.type == "RISQUE" and "11" in perimee.preuves
    assert "90 j" in perimee.resume

    contestes = [p for p in propositions if p.titre == TITRE_CONTESTE]
    assert [p.type for p in contestes] == ["CONSTAT", "RISQUE"]
    assert {p.donnees["claim_id"] for p in contestes} == {2, 3}
    assert all("reouvrir_claim" in p.actions for p in contestes)


def test_meme_triplet_est_signale_comme_contradiction_ou_doublon():
    lignes = [
        claim(1, objet="motor", preuves=[preuve(11)]),
        claim(2, objet="motor", preuves=[preuve(12)], twin_id="autre"),
    ]

    propositions = construire_propositions(lignes, maintenant=MAINTENANT.isoformat())

    contradiction = par_titre(propositions, TITRE_CONTRADICTION)
    assert contradiction.type == "CONSTAT"
    assert contradiction.donnees["claim_ids"] == [1, 2]
    assert {"claim:1", "claim:2", "11", "12"} <= set(contradiction.preuves)


def test_objets_differents_ne_sont_pas_un_doublon():
    lignes = [claim(1, objet="motor", preuves=[preuve(11)]),
              claim(2, objet="redis", preuves=[preuve(12)])]

    propositions = construire_propositions(lignes, maintenant=MAINTENANT.isoformat())

    assert TITRE_CONTRADICTION not in [p.titre for p in propositions]
    assert TITRE_SUFFISANTES in [p.titre for p in propositions]


def test_tous_les_claims_appuyes_produisent_preuves_suffisantes_avec_confiance():
    lignes = [
        claim(1, confiance=0.8, preuves=[preuve(11)]),
        claim(2, confiance=0.6, preuves=[preuve(12), preuve(13)]),
    ]

    propositions = construire_propositions(lignes, maintenant=MAINTENANT.isoformat())

    suffisantes = par_titre(propositions, TITRE_SUFFISANTES)
    assert suffisantes.type == "CONSTAT"
    assert suffisantes.confiance == pytest.approx(0.7)
    assert suffisantes.donnees["nb_claims"] == 2
    assert suffisantes.donnees["nb_preuves_support"] == 3
    assert {"claim:1", "claim:2", "11", "12", "13"} <= set(suffisantes.preuves)


def test_sans_connexion_ou_sans_claim_est_partiel_sans_invention():
    sans_conn = SpecialistePreuve().analyser(contexte(None))
    sans_claim = SpecialistePreuve().analyser(contexte(FauxConn([])))

    for resultat in (sans_conn, sans_claim):
        assert resultat.statut == "partiel"
        assert resultat.propositions == []
        assert resultat.limites and "aucune proposition inventée" in resultat.limites[0]


def test_erreur_ne_livre_que_le_type_et_ne_fuite_aucun_secret():
    resultat = SpecialistePreuve().analyser(
        contexte(FauxConn(erreur=RuntimeError("token=secret-de-test"))))

    assert resultat.statut == "erreur"
    assert resultat.erreur == "RuntimeError"
    assert resultat.propositions == []
    assert "secret-de-test" not in str(resultat.as_dict())


def test_lecture_tenant_scopee_filtree_et_en_select_seulement():
    conn = FauxConn([claim(1, preuves=[preuve(11)])])

    SpecialistePreuve().analyser(contexte(conn, claim_ids=("1",), twin_ids=("tbt",)))

    requete, parametres = conn.requetes[0]
    assert requete.lstrip().upper().startswith("SELECT")
    assert "c.tenant_id = %s" in requete
    assert "INSERT" not in requete.upper() and "UPDATE" not in requete.upper()
    assert "DELETE" not in requete.upper()
    assert parametres[0] == "banque"
    assert parametres[1] == ["1"] and parametres[2] == ["tbt"]


def test_le_specialiste_respecte_le_protocole():
    assert isinstance(SpecialistePreuve(), Specialiste)
    assert SpecialistePreuve().nom == "preuve"
    assert SpecialistePreuve().autorite == "proposition"


@besoin_pg
def test_pg_claim_ingere_appuye_produit_preuves_suffisantes_sans_ecriture(conn):
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim_ingere("motor")], ACTIVITE)
    claim_id = depot.lister_claims(conn, "tbt")[0]["id"]
    avant = conn.execute("SELECT count(*) FROM claim").fetchone()[0]

    resultat = SpecialistePreuve().analyser(contexte(
        conn, claim_ids=(str(claim_id),), twin_ids=("tbt",)))

    assert resultat.statut == "ok"
    suffisantes = par_titre(resultat.propositions, TITRE_SUFFISANTES)
    assert suffisantes.donnees["claim_ids"] == [claim_id]
    assert conn.execute("SELECT count(*) FROM claim").fetchone()[0] == avant
