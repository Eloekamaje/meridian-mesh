"""Détecteurs de besoins B7 : trois signatures déterministes, quota, dédup et fail-closed.

Deux modes : READ sans base (dépôts et conn injectés/mocks) et persistance réelle
(sautée sans ``JUMEAU_PG_DSN``, comme les autres tests Postgres).
"""
from datetime import datetime, timedelta, timezone

import pytest

from meridian.adapters.outbound.postgres import boucle, detecteurs_besoins, memoire_prospective
from meridian.tests.conftest import besoin_pg

TENANT = "banque"
MAINTENANT = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)


class DepotMemoire:
    """Dépôt minimal en mémoire : même contrat d'appel que ``enregistrer_boucle``."""

    def __init__(self):
        self.objets = {}

    def __call__(self, conn, tenant, objets):
        lot = objets if isinstance(objets, list) else [objets]
        lignes = []
        for payload in lot:
            brut = dict(payload)
            identifiant = brut["id"]
            donnees = {cle: valeur for cle, valeur in brut.items()
                       if cle not in ("id", "tenant_id", "famille", "type", "mode",
                                      "titre", "version", "cree_le", "observe_le",
                                      "valide_depuis", "valide_jusqua", "maj_le")}
            self.objets[identifiant] = {
                "id": identifiant, "tenant_id": tenant,
                "famille": brut.get("famille"), "type": brut.get("type"),
                "mode": brut.get("mode"), "titre": brut.get("titre", ""),
                "donnees": donnees, "version": self.objets.get(identifiant, {}).get("version", 0) + 1,
            }
            lignes.append(self.objets[identifiant])
        return lignes[0] if not isinstance(objets, list) else lignes

    def par_type(self, type_):
        return [ligne for ligne in self.objets.values() if ligne["type"] == type_]


def assertion(subject, predicate, object_, mode, identifiant=1, **champs):
    return {"id": identifiant, "subject": subject, "predicate": predicate,
            "object": object_, "mode": mode, "source": "test", "environment": "prod",
            "observed_at": MAINTENANT.isoformat(), **champs}


def situation(identifiant, twin_ids, observe_le=None):
    return {"id": identifiant, "tenant_id": TENANT, "famille": "emergence",
            "type": "SITUATION", "mode": "OBSERVED", "titre": identifiant,
            "observe_le": (observe_le or MAINTENANT).isoformat(),
            "donnees": {"twin_ids": list(twin_ids)}}


def reponse_flore(question="Qui consomme TBT la nuit ?", **champs):
    return {"role": "flore", "question": question,
            "texte": "Je n'ai pas trouvé.", **champs}


def detecter(depot, conn=None, **kwargs):
    kwargs.setdefault("maintenant", MAINTENANT)
    persister = kwargs.pop("persister", depot)
    return detecteurs_besoins.detecter(conn, TENANT, persister=persister, **kwargs)


# --- question_non_tranchee ---


def test_non_concluante_produit_unknown_et_intention():
    depot, intentions = DepotMemoire(), []
    rapport = detecter(
        depot, reponses=[reponse_flore(resolution={"absent": True, "statut": "absent"})],
        assertions=[], situations=[], needs=[], unknowns=[],
        creer_intention=lambda conn, intention: intentions.append(intention) or {"id": intention.id})

    assert rapport["totaux"] == {"crees": 1, "ignores": 0, "erreurs": 0}
    [unknown] = depot.par_type("UNKNOWN")
    assert unknown["donnees"]["question"] == "Qui consomme TBT la nuit ?"
    assert unknown["donnees"]["origine"] == "flore"
    assert unknown["donnees"]["statut"] == "OUVERT"
    assert unknown["donnees"]["intention_id"] == intentions[0].id
    assert unknown["id"] in intentions[0].evidence_ids
    assert intentions[0].donnees["unknown_id"] == unknown["id"]


@pytest.mark.parametrize("reponse", [
    reponse_flore(resolution={"absent": True, "statut": "absent"}),
    reponse_flore(resolution={"ambigu": True, "statut": "ambigu"}),
    reponse_flore(origine="repli"),
    reponse_flore(raisonnement_statut="clarification_requise"),
    reponse_flore(limite="périmètre trop large"),
    reponse_flore(texte="non observé dans le périmètre au 2026-11-02 ; ce n'est pas une preuve d'absence"),
])
def test_marqueurs_non_concluants(reponse):
    depot = DepotMemoire()
    rapport = detecter(depot, reponses=[reponse], assertions=[], situations=[],
                       needs=[], unknowns=[], creer_intention=None)
    assert rapport["totaux"]["crees"] == 1 and depot.par_type("UNKNOWN")


def test_reponse_concluante_ne_produit_rien():
    depot = DepotMemoire()
    rapport = detecter(
        depot, reponses=[reponse_flore(texte="TBT est consommé par B2B et KYC.",
                                       origine="modele")],
        assertions=[], situations=[], needs=[], unknowns=[], creer_intention=None)
    assert rapport["totaux"]["crees"] == 0 and not depot.par_type("UNKNOWN")


def test_question_sans_texte_associe_est_ignoree():
    depot = DepotMemoire()
    rapport = detecter(
        depot, reponses=[reponse_flore(question="", origine="repli",
                                       resolution={"absent": True})],
        assertions=[], situations=[], needs=[], unknowns=[], creer_intention=None)
    assert rapport["totaux"]["crees"] == 0
    assert rapport["ignores"] and "question" in rapport["ignores"][0]["raison"]


def test_dedup_unknown_meme_question():
    depot = DepotMemoire()
    existant = {"id": "unk-ancien", "donnees": {
        "question": "qui consomme tbt la nuit ?", "statut": "OUVERT"}}
    rapport = detecter(
        depot, reponses=[reponse_flore(question="Qui consomme TBT la nuit ?",
                                       origine="repli")],
        assertions=[], situations=[], needs=[], unknowns=[existant],
        creer_intention=None)
    assert rapport["totaux"]["crees"] == 0
    assert rapport["ignores"][0]["signature"] == "question_non_tranchee"


# --- contournement ---


def test_contournement_produit_rivales_et_need():
    depot = DepotMemoire()
    assertions = [
        assertion("app-cartes", "CONSOMME", "GET /v1/payments", "declared", 1),
        assertion("app-cartes", "CONSOMME", "GET /v1/payments", "observed", 2),
        assertion("app-cartes", "CONSOMME", "POST /legacy/pay", "observed", 3),
    ]
    rapport = detecter(depot, reponses=[], assertions=assertions, situations=[],
                       needs=[], unknowns=[], creer_intention=None)

    assert rapport["totaux"] == {"crees": 1, "ignores": 0, "erreurs": 0}
    hypotheses = depot.par_type("CONJECTURE")
    [need] = depot.par_type("NEED")
    assert len(hypotheses) >= 2
    assert {h["donnees"]["statut"] for h in hypotheses} == {"EMISE"}
    assert all(len(h["donnees"]["rival_ids"]) >= 1 for h in hypotheses)
    assert need["donnees"]["signature"] == "contournement"
    assert need["donnees"]["refutable_par"].strip()
    assert set(need["donnees"]["conjecture_ids"]) == {h["id"] for h in hypotheses}
    assert need["donnees"]["sujet_detection"] == "app-cartes|CONSOMME"


def test_contournement_sans_excedent_ne_produit_rien():
    depot = DepotMemoire()
    assertions = [
        assertion("app-cartes", "CONSOMME", "GET /v1/payments", "declared", 1),
        assertion("app-cartes", "CONSOMME", "GET /v1/payments", "observed", 2),
    ]
    rapport = detecter(depot, reponses=[], assertions=assertions, situations=[],
                       needs=[], unknowns=[], creer_intention=None)
    assert rapport["totaux"]["crees"] == 0 and not depot.objets


def test_contournement_need_existant_est_ignore():
    depot = DepotMemoire()
    assertions = [
        assertion("app-cartes", "CONSOMME", "GET /v1/a", "declared", 1),
        assertion("app-cartes", "CONSOMME", "GET /v1/b", "observed", 2),
    ]
    existant = {"id": "need-x", "donnees": {
        "signature": "contournement", "statut": "OUVERT",
        "sujet_detection": "app-cartes|CONSOMME"}}
    rapport = detecter(depot, reponses=[], assertions=assertions, situations=[],
                       needs=[existant], unknowns=[], creer_intention=None)
    assert rapport["totaux"]["crees"] == 0
    assert rapport["ignores"][0]["signature"] == "contournement"


# --- recurrence ---


def test_recurrence_trois_situations_produit_need():
    depot = DepotMemoire()
    situations = [situation(f"sit-{n}", ["app-cartes"]) for n in range(3)]
    rapport = detecter(depot, reponses=[], assertions=[], situations=situations,
                       needs=[], unknowns=[], creer_intention=None)

    assert rapport["totaux"]["crees"] == 1
    [need] = depot.par_type("NEED")
    assert need["donnees"]["signature"] == "recurrence"
    assert need["donnees"]["refutable_par"].strip()
    assert "app-cartes" in need["donnees"]["ecart"]
    assert need["donnees"]["twin_ids"] == ["app-cartes"]
    assert sorted(need["donnees"]["situation_ids"]) == ["sit-0", "sit-1", "sit-2"]


def test_recurrence_deux_situations_ne_produit_rien():
    depot = DepotMemoire()
    situations = [situation(f"sit-{n}", ["app-cartes"]) for n in range(2)]
    rapport = detecter(depot, reponses=[], assertions=[], situations=situations,
                       needs=[], unknowns=[], creer_intention=None)
    assert rapport["totaux"]["crees"] == 0 and not depot.par_type("NEED")


def test_recurrence_situations_sur_twins_distincts_ne_produit_rien():
    depot = DepotMemoire()
    situations = [situation("sit-a", ["app-a"]), situation("sit-b", ["app-b"]),
                  situation("sit-c", ["app-c"])]
    rapport = detecter(depot, reponses=[], assertions=[], situations=situations,
                       needs=[], unknowns=[], creer_intention=None)
    assert rapport["totaux"]["crees"] == 0


# --- dédup, quota, fail-closed ---


def test_second_run_ne_cree_rien():
    depot, intentions = DepotMemoire(), []
    kwargs = dict(
        reponses=[reponse_flore(origine="repli")],
        assertions=[
            assertion("app-cartes", "CONSOMME", "GET /v1/a", "declared", 1),
            assertion("app-cartes", "CONSOMME", "GET /v1/b", "observed", 2)],
        situations=[situation(f"sit-{n}", ["app-cartes"]) for n in range(3)],
        needs=[], unknowns=[],
        creer_intention=lambda conn, i: intentions.append(i) or {"id": i.id})
    premier = detecter(depot, **kwargs)
    assert premier["totaux"]["crees"] == 3 and len(intentions) == 1

    # le run suivant voit le contenu du dépôt — même signature, mêmes sujets
    kwargs["needs"] = depot.par_type("NEED")
    kwargs["unknowns"] = depot.par_type("UNKNOWN")
    second = detecter(depot, **kwargs)
    assert second["totaux"]["crees"] == 0
    assert second["totaux"]["ignores"] >= 2


def test_quota_borne_le_nombre_de_besoins():
    depot = DepotMemoire()
    assertions = []
    for rang in range(5):
        assertions += [
            assertion(f"app-{rang}", "CONSOMME", f"GET /decl/{rang}", "declared", rang * 2),
            assertion(f"app-{rang}", "CONSOMME", f"GET /obs/{rang}", "observed", rang * 2 + 1)]
    rapport = detecter(depot, reponses=[], assertions=assertions, situations=[],
                       needs=[], unknowns=[], creer_intention=None, quota=2)
    assert rapport["totaux"]["crees"] == 2


def test_signature_filtre_les_detecteurs():
    depot = DepotMemoire()
    rapport = detecter(
        depot, signature="recurrence",
        reponses=[reponse_flore(origine="repli")],
        assertions=[assertion("a", "P", "d", "declared", 1),
                    assertion("a", "P", "o", "observed", 2)],
        situations=[situation(f"sit-{n}", ["app-cartes"]) for n in range(3)],
        needs=[], unknowns=[], creer_intention=None)
    assert {c["signature"] for c in rapport["crees"]} == {"recurrence"}


def test_signature_inconnue_refusee():
    with pytest.raises(detecteurs_besoins.DetectionInvalide):
        detecter(DepotMemoire(), signature="nimportequoi", needs=[], unknowns=[])


def test_echec_persistance_remonte_en_erreurs():
    def persister_en_echec(conn, tenant, objets):
        raise RuntimeError("trigger need_exige_refutation : refutable_par manquant")
    rapport = detecter(
        DepotMemoire(), persister=persister_en_echec, signature="recurrence",
        situations=[situation(f"sit-{n}", ["app-cartes"]) for n in range(3)],
        needs=[], unknowns=[], creer_intention=None)
    # le persister injecté échoue : l'erreur est visible, jamais avalée
    assert rapport["totaux"]["crees"] == 0
    assert rapport["totaux"]["erreurs"] == 1
    assert "refutable_par" in rapport["erreurs"][0]["erreur"]


# --- Persistance Postgres réelle ---


def _donnees_travail(conversation):
    return {"id": "case-1", "conversation": conversation}


@besoin_pg
def test_persistance_reelle_contournement_et_recurrence(conn):
    from meridian.domain.interfaces import Assertion, InterfaceGraph
    from meridian.adapters.outbound.postgres import interfaces_depot

    graphe = InterfaceGraph(assertions=[
        Assertion(subject="app-cartes", predicate="CONSOMME", object="GET /v1/payments",
                  mode="declared", source="code", locator="spec", environment="prod",
                  confidence=0.9, evidence="contrat"),
        Assertion(subject="app-cartes", predicate="CONSOMME", object="POST /legacy/pay",
                  mode="observed", source="runtime", locator="otlp", environment="prod",
                  confidence=0.8, evidence="trace"),
    ])
    interfaces_depot.enregistrer(conn, TENANT, graphe)
    for n in range(3):
        sit = boucle.Situation(id=f"sit-rec-{n}", tenant_id=TENANT,
                               description="récurrent", twin_ids=["app-cartes"])
        boucle.enregistrer_boucle(conn, TENANT, sit)

    rapport = detecteurs_besoins.detecter(conn, TENANT, maintenant=MAINTENANT)
    assert rapport["erreurs"] == []
    signatures = {c["signature"] for c in rapport["crees"]}
    assert {"contournement", "recurrence"} <= signatures

    relu = boucle.lire_boucle(conn, TENANT, rapport["crees"][0]["id"])
    assert relu["type"] in {"NEED", "UNKNOWN", "CONJECTURE"}

    second = detecteurs_besoins.detecter(conn, TENANT, maintenant=MAINTENANT)
    assert second["crees"] == []
    assert second["erreurs"] == []


@besoin_pg
def test_persistance_reelle_question_non_tranchee_avec_intention(conn):
    conn.execute(
        "INSERT INTO travail (id, tenant_id, donnees) VALUES (%s, %s, %s::jsonb)",
        ("case-qnt", TENANT, __import__("json").dumps(_donnees_travail([
            {"role": "utilisateur", "texte": "Qui appelle l'interface de nuit ?"},
            {"role": "flore", "texte": "Réponse de secours.", "origine": "repli"},
        ]))))

    rapport = detecteurs_besoins.detecter(conn, TENANT, signature="question_non_tranchee")
    assert rapport["erreurs"] == []
    [cree] = rapport["crees"]
    relu = boucle.lire_boucle(conn, TENANT, cree["id"])
    assert relu["type"] == "UNKNOWN"
    assert relu["donnees"]["origine"] == "flore"
    intention_id = relu["donnees"]["intention_id"]
    assert intention_id
    intention = memoire_prospective.lire(conn, TENANT, intention_id)
    assert intention is not None and intention["statut"] == "a_faire"
    assert cree["id"] in intention["evidence_ids"]

    second = detecteurs_besoins.detecter(conn, TENANT, signature="question_non_tranchee")
    assert second["crees"] == [] and second["erreurs"] == []


@besoin_pg
def test_fail_closed_need_sans_refutable_remonte(conn):
    """Un NEED refusé par le trigger apparaît dans erreurs, jamais silencieusement."""
    def persister_casse(conn_, tenant, objets):
        lot = objets if isinstance(objets, list) else [objets]
        depouilles = []
        for payload in lot:
            brut = dict(payload)
            brut.pop("refutable_par", None)
            depouilles.append(brut)
        return boucle.enregistrer_boucle(conn_, tenant, depouilles)

    rapport = detecteurs_besoins.detecter(
        conn, TENANT, signature="recurrence", persister=persister_casse,
        situations=[situation(f"sit-fc-{n}", ["app-fc"]) for n in range(3)],
        needs=[], unknowns=[], creer_intention=None)
    assert rapport["crees"] == []
    assert rapport["erreurs"]
