"""Paris datés des besoins C6 : intentions dues jugées par le signal d'origine.

Deux modes : READ sans base (dépôts, intentions et lectures injectés/mocks) et
persistance réelle (sautée sans ``JUMEAU_PG_DSN``, comme les autres tests Postgres).
"""
from datetime import datetime, timedelta, timezone

from meridian.adapters.outbound.postgres import (
    boucle, memoire_prospective, resolution_besoins,
)
from meridian.domain import memoire_prospective as domaine_prospectif
from meridian.tests.conftest import besoin_pg

TENANT = "banque"
MAINTENANT = datetime(2026, 11, 16, 9, 0, tzinfo=timezone.utc)
DUE = (MAINTENANT - timedelta(days=1)).isoformat(timespec="seconds")
PAS_DUE = (MAINTENANT + timedelta(days=7)).isoformat(timespec="seconds")


class DepotMemoire:
    """Dépôt minimal en mémoire : même contrat d'appel que ``enregistrer_boucle``,
    sur des lignes à ``donnees`` imbriquées comme ``objet_entreprise``."""

    def __init__(self):
        self.objets = {}

    def __call__(self, conn, tenant, objets):
        lot = objets if isinstance(objets, list) else [objets]
        lignes = []
        for brut in lot:
            charge = dict(brut.get("donnees") or {})
            charge.update({cle: valeur for cle, valeur in brut.items() if cle not in (
                "id", "tenant_id", "famille", "type", "mode", "titre", "version",
                "cree_le", "observe_le", "valide_depuis", "valide_jusqua", "maj_le",
                "donnees")})
            ligne = {"id": brut["id"], "tenant_id": tenant,
                     "famille": brut.get("famille"), "type": brut.get("type"),
                     "mode": brut.get("mode"), "titre": brut.get("titre", ""),
                     "donnees": charge,
                     "version": self.objets.get(brut["id"], {}).get("version", 0) + 1}
            self.objets[brut["id"]] = ligne
            lignes.append(ligne)
        return lignes[0] if not isinstance(objets, list) else lignes

    def par_type(self, type_):
        return [ligne for ligne in self.objets.values() if ligne["type"] == type_]


class Clotures:
    """Mock de ``memoire_prospective.clore`` : même signature, appels mémorisés."""

    def __init__(self):
        self.appels = []

    def __call__(self, conn, tenant, intention_id, *, statut="fait", acteur="", motif=""):
        self.appels.append({"intention_id": intention_id, "statut": statut,
                            "acteur": acteur, "motif": motif})
        return {"id": intention_id, "statut": statut}


def need(identifiant="need-1", statut="QUALIFIE", signature="contournement",
         sujet="app-cartes|CONSOMME", intention_id="int-1", **donnees):
    charge = {"statut": statut, "signature": signature,
              "sujet_detection": sujet, "intention_id": intention_id,
              "porteur": "equipe-cartes", "exigence": "observé et déclaré coïncident",
              "ecart": "observé hors déclaré", "refutable_par": "réconcilié 30 jours",
              "claim_ids": ["claim-1"], "twin_ids": ["app-cartes"]}
    charge.update(donnees)
    return {"id": identifiant, "tenant_id": TENANT, "famille": "emergence",
            "type": "NEED", "mode": "PROPOSED", "titre": identifiant,
            "donnees": charge}


def unknown(identifiant="unk-1", statut="OUVERT",
            question="Qui consomme TBT la nuit ?", intention_id="int-u", **donnees):
    charge = {"statut": statut, "question": question, "origine": "flore",
              "intention_id": intention_id}
    charge.update(donnees)
    return {"id": identifiant, "tenant_id": TENANT, "famille": "connaissance",
            "type": "UNKNOWN", "mode": "PROPOSED", "titre": question,
            "donnees": charge}


def intention(identifiant="int-1", echeance=DUE, statut="a_faire", **donnees):
    return {"id": identifiant, "tenant_id": TENANT,
            "objet": "Vérifier le besoin", "echeance": echeance,
            "scope": "tenant", "scope_id": "", "source": "detecteur",
            "owner": "gardien", "statut": statut, "priorite": "normale",
            "evidence_ids": [], "donnees": dict(donnees)}


def assertion(subject, predicate, object_, mode, identifiant=1):
    return {"id": identifiant, "subject": subject, "predicate": predicate,
            "object": object_, "mode": mode, "source": "test",
            "environment": "prod", "observed_at": MAINTENANT.isoformat()}


def situation(identifiant, twin_ids, observe_le=None):
    return {"id": identifiant, "tenant_id": TENANT, "famille": "emergence",
            "type": "SITUATION", "mode": "OBSERVED", "titre": identifiant,
            "observe_le": (observe_le or MAINTENANT).isoformat(),
            "donnees": {"twin_ids": list(twin_ids)}}


def verifier(depot=None, clotures=None, conn=None, **kwargs):
    kwargs.setdefault("maintenant", MAINTENANT)
    kwargs.setdefault("persister", depot or DepotMemoire())
    kwargs.setdefault("clore_intention", clotures)
    return resolution_besoins.verifier_paris(conn, TENANT, **kwargs)


# --- contournement ---


def test_need_qualifie_signal_disparu_corrobore():
    depot, clotures = DepotMemoire(), Clotures()
    rapport = verifier(
        depot, clotures,
        needs=[need()], unknowns=[], intentions=[intention()],
        assertions=[assertion("app-cartes", "CONSOMME", "GET /v1/payments", "declared", 1),
                    assertion("app-cartes", "CONSOMME", "GET /v1/payments", "observed", 2)],
        situations=[], creer_intention=None)

    assert rapport["totaux"]["evalues"] == 1
    assert rapport["totaux"]["corroborés"] == 1
    assert rapport["erreurs"] == []
    assert depot.objets["need-1"]["donnees"]["statut"] == "CORROBORE"
    assert depot.objets["need-1"]["donnees"]["verification"]["verdict"] == "signal_disparu"
    assert [a["statut"] for a in clotures.appels] == ["fait"]


def test_need_ouvert_signal_disparu_qualifie_si_applicable():
    depot, clotures = DepotMemoire(), Clotures()
    rapport = verifier(
        depot, clotures,
        needs=[need(statut="OUVERT")], unknowns=[], intentions=[intention()],
        assertions=[], situations=[], creer_intention=None)

    assert rapport["totaux"]["corroborés"] == 1
    assert depot.objets["need-1"]["donnees"]["statut"] == "QUALIFIE"


def test_signal_persistant_intention_expiree_et_attention():
    depot, clotures = DepotMemoire(), Clotures()
    rapport = verifier(
        depot, clotures,
        needs=[need()], unknowns=[], intentions=[intention()],
        assertions=[assertion("app-cartes", "CONSOMME", "GET /decl", "declared", 1),
                    assertion("app-cartes", "CONSOMME", "GET /obs", "observed", 2)],
        situations=[], creer_intention=None)

    assert rapport["totaux"]["evalues"] == 1
    assert rapport["totaux"]["persistants"] == 1
    assert rapport["totaux"]["expires"] == 1
    assert rapport["totaux"]["corroborés"] == 0
    attention = depot.objets["need-1"]["donnees"]["attention"]
    assert attention["raison"] == "intention_expiree"
    assert attention["depuis"] == MAINTENANT.isoformat(timespec="seconds")
    assert [a["statut"] for a in clotures.appels] == ["expire"]
    assert depot.objets["need-1"]["donnees"]["statut"] == "QUALIFIE"


def test_transition_invalide_remonte_en_erreurs_sans_crash():
    depot, clotures = DepotMemoire(), Clotures()
    # OUVERT sans porteur ni claim lié : QUALIFIE est refusée par le modèle.
    rapport = verifier(
        depot, clotures,
        needs=[need(statut="OUVERT", porteur="", claim_ids=[])],
        unknowns=[], intentions=[intention()],
        assertions=[], situations=[], creer_intention=None)

    assert rapport["totaux"]["evalues"] == 1
    assert rapport["totaux"]["erreurs"] == 1
    assert "claim" in rapport["erreurs"][0]["erreur"] or "porteur" in rapport["erreurs"][0]["erreur"]
    assert clotures.appels == []  # l'intention reste ouverte : le pari est rejoué


def test_sans_intention_due_rien_ne_se_passe():
    depot, clotures = DepotMemoire(), Clotures()
    rapport = verifier(
        depot, clotures,
        needs=[need()], unknowns=[], intentions=[intention(echeance=PAS_DUE)],
        assertions=[], situations=[], creer_intention=None)

    assert rapport["totaux"]["evalues"] == 0
    assert rapport["totaux"]["erreurs"] == 0
    assert depot.objets == {} and clotures.appels == []


# --- recurrence ---


def test_recurrence_signal_disparu_corrobore():
    depot, clotures = DepotMemoire(), Clotures()
    rapport = verifier(
        depot, clotures,
        needs=[need(signature="recurrence", sujet="twin:app-cartes")],
        unknowns=[], intentions=[intention(signature="recurrence")],
        assertions=[], situations=[], creer_intention=None)

    assert rapport["totaux"]["corroborés"] == 1
    assert depot.objets["need-1"]["donnees"]["statut"] == "CORROBORE"


def test_recurrence_signal_persistant_expire():
    depot, clotures = DepotMemoire(), Clotures()
    situations = [situation(f"sit-{n}", ["app-cartes"]) for n in range(3)]
    rapport = verifier(
        depot, clotures,
        needs=[need(signature="recurrence", sujet="twin:app-cartes")],
        unknowns=[], intentions=[intention(signature="recurrence")],
        assertions=[], situations=situations, creer_intention=None)

    assert rapport["totaux"]["persistants"] == 1
    assert depot.objets["need-1"]["donnees"]["attention"]["raison"] == "intention_expiree"
    assert [a["statut"] for a in clotures.appels] == ["expire"]


def test_recurrence_ancienne_fenetre_suffit_a_maintenir():
    """Le refutable_par exige < seuil sur deux fenêtres consécutives : une fenêtre
    ancienne au-dessus du seuil maintient le signal."""
    depot, clotures = DepotMemoire(), Clotures()
    ancienne = MAINTENANT - timedelta(days=40)  # fenêtre précédente (30 j +)
    situations = [situation(f"sit-a-{n}", ["app-cartes"], ancienne) for n in range(3)]
    rapport = verifier(
        depot, clotures,
        needs=[need(signature="recurrence", sujet="twin:app-cartes")],
        unknowns=[], intentions=[intention(signature="recurrence")],
        assertions=[], situations=situations, creer_intention=None)

    assert rapport["totaux"]["persistants"] == 1


# --- question_non_tranchee ---


def test_question_repondue_unknown_resolu_et_intention_faite():
    depot, clotures = DepotMemoire(), Clotures()
    claims = [{"sujet": "TBT", "predicat": "CONSOMME_PAR", "objet": "B2B nocturne"}]
    rapport = verifier(
        depot, clotures,
        needs=[], unknowns=[unknown()], intentions=[intention("int-u")],
        assertions=[], situations=[], claims=claims, creer_intention=None)

    assert rapport["totaux"]["resolus"] == 1
    assert depot.objets["unk-1"]["donnees"]["statut"] == "RESOLU"
    assert [a["statut"] for a in clotures.appels] == ["fait"]


def test_question_resolue_manuellement_clot_le_pari():
    depot, clotures = DepotMemoire(), Clotures()
    rapport = verifier(
        depot, clotures,
        needs=[], unknowns=[unknown(statut="RESOLU", resolution_claim_id="claim-9")],
        intentions=[intention("int-u")], assertions=[], situations=[], claims=[],
        creer_intention=None)

    assert rapport["totaux"]["resolus"] == 1
    assert [a["statut"] for a in clotures.appels] == ["fait"]


def test_question_sans_reponse_expire_et_attention():
    depot, clotures = DepotMemoire(), Clotures()
    rapport = verifier(
        depot, clotures,
        needs=[], unknowns=[unknown()], intentions=[intention("int-u")],
        assertions=[], situations=[], claims=[], creer_intention=None)

    assert rapport["totaux"]["persistants"] == 1
    assert depot.objets["unk-1"]["donnees"]["attention"]["raison"] == "intention_expiree"
    assert depot.objets["unk-1"]["donnees"]["statut"] == "OUVERT"
    assert [a["statut"] for a in clotures.appels] == ["expire"]


def test_unknown_liee_cote_intention_est_evaluee():
    """Le lien fonctionne dans les deux sens : ``donnees.unknown_id`` côté intention."""
    depot, clotures = DepotMemoire(), Clotures()
    rapport = verifier(
        depot, clotures,
        needs=[], unknowns=[unknown(intention_id=None)],
        intentions=[intention("int-x", unknown_id="unk-1",
                              signature="question_non_tranchee")],
        assertions=[], situations=[], claims=[], creer_intention=None)

    assert rapport["totaux"]["evalues"] == 1
    assert rapport["totaux"]["persistants"] == 1
    assert depot.objets["unk-1"]["donnees"]["intention_id"] == "int-x"


# --- paris posés, erreurs, fail-closed ---


def test_need_sans_intention_recoit_un_pari_date():
    depot, clotures, intentions = DepotMemoire(), Clotures(), []
    rapport = verifier(
        depot, clotures, creer_intention=lambda conn, i: intentions.append(i) or {"id": i.id},
        needs=[need(intention_id=None)], unknowns=[], intentions=[],
        assertions=[], situations=[])

    assert rapport["totaux"]["paris_ouverts"] == 1
    assert rapport["totaux"]["evalues"] == 0  # le pari posé n'est pas encore dû
    [pari] = intentions
    assert pari.donnees["need_id"] == "need-1"
    assert pari.donnees["signature"] == "contournement"
    assert depot.objets["need-1"]["donnees"]["intention_id"] == pari.id


def test_pari_desactive_ne_cree_rien():
    depot = DepotMemoire()
    rapport = verifier(
        depot, needs=[need(intention_id=None)], unknowns=[], intentions=[],
        assertions=[], situations=[], creer_intention=None, creer_paris=False)
    assert rapport["totaux"]["paris_ouverts"] == 0 and depot.objets == {}


def test_intention_introuvable_remonte_en_erreurs():
    rapport = verifier(
        DepotMemoire(), needs=[need()], unknowns=[], intentions=[],
        assertions=[], situations=[], creer_intention=None)
    assert rapport["totaux"]["erreurs"] == 1
    assert "introuvable" in rapport["erreurs"][0]["erreur"]


def test_signature_inconnue_remonte_en_erreurs():
    rapport = verifier(
        DepotMemoire(), needs=[need(signature="nimportequoi")], unknowns=[],
        intentions=[intention()], assertions=[], situations=[], creer_intention=None)
    assert rapport["totaux"]["evalues"] == 0
    assert rapport["totaux"]["erreurs"] == 1


# --- Persistance Postgres réelle ---


@besoin_pg
def test_persistance_reelle_corrobore_et_attention(conn):
    need_corrobore = boucle.Need(
        id="need-pg-ok", tenant_id=TENANT, titre="Contournement résorbé",
        porteur="equipe-cartes", exigence="observé et déclaré coïncident",
        ecart="observé hors déclaré", refutable_par="réconcilié 30 jours",
        statut="QUALIFIE", signature="contournement", claim_ids=["claim-1"],
        intention_id="int-pg-ok", twin_ids=["app-cartes"])
    need_expire = boucle.Need(
        id="need-pg-ko", tenant_id=TENANT, titre="Contournement persistant",
        porteur="equipe-cartes", exigence="observé et déclaré coïncident",
        ecart="observé hors déclaré", refutable_par="réconcilié 30 jours",
        statut="QUALIFIE", signature="contournement", claim_ids=["claim-1"],
        intention_id="int-pg-ko", twin_ids=["app-legacy"])
    boucle.enregistrer_boucle(conn, TENANT, [need_corrobore, need_expire])
    # need-pg-ok : aucune assertion → contradiction disparue. need-pg-ko : sujet
    # app-legacy|CONSOMME avec un observed hors declared → signal persistant.
    for need_id, sujet in (("need-pg-ok", "app-cartes|CONSOMME"),
                           ("need-pg-ko", "app-legacy|CONSOMME")):
        ligne = boucle.lire_boucle(conn, TENANT, need_id)
        ligne["donnees"]["sujet_detection"] = sujet
        boucle.enregistrer_boucle(conn, TENANT, ligne)
        memoire_prospective.creer(conn, domaine_prospectif.Intention(
            id=f"int-{need_id[5:]}", tenant_id=TENANT, objet=f"Vérifier {need_id}",
            echeance=(MAINTENANT - timedelta(hours=1)).isoformat(timespec="seconds"),
            scope="tenant", source="test", donnees={"need_id": need_id,
                                                    "signature": "contournement"}))

    from meridian.domain.interfaces import Assertion, InterfaceGraph
    from meridian.adapters.outbound.postgres import interfaces_depot
    interfaces_depot.enregistrer(conn, TENANT, InterfaceGraph(assertions=[
        Assertion(subject="app-legacy", predicate="CONSOMME", object="GET /decl",
                  mode="declared", source="code", locator="spec", environment="prod",
                  confidence=0.9, evidence="contrat"),
        Assertion(subject="app-legacy", predicate="CONSOMME", object="POST /obs",
                  mode="observed", source="runtime", locator="otlp", environment="prod",
                  confidence=0.8, evidence="trace"),
    ]))

    rapport = resolution_besoins.verifier_paris(conn, TENANT, maintenant=MAINTENANT)
    assert rapport["erreurs"] == []
    assert {e["besoin"] for e in rapport["corroborés"]} == {"need-pg-ok"}
    assert {e["besoin"] for e in rapport["persistants"]} == {"need-pg-ko"}

    relu = boucle.lire_boucle(conn, TENANT, "need-pg-ok")
    assert relu["donnees"]["statut"] == "CORROBORE"
    assert memoire_prospective.lire(conn, TENANT, "int-pg-ok")["statut"] == "fait"

    degrade = boucle.lire_boucle(conn, TENANT, "need-pg-ko")
    assert degrade["donnees"]["statut"] == "QUALIFIE"
    assert degrade["donnees"]["attention"]["raison"] == "intention_expiree"
    assert memoire_prospective.lire(conn, TENANT, "int-pg-ko")["statut"] == "expire"

    second = resolution_besoins.verifier_paris(conn, TENANT, maintenant=MAINTENANT)
    assert second["totaux"]["evalues"] == 0  # intentions closes : plus rien à juger


@besoin_pg
def test_persistance_reelle_pari_ouvert_sur_need_detecte(conn):
    """Un NEED B7 (sans intention) reçoit son pari daté à la première passe."""
    need_detecte = boucle.Need(
        id="need-pg-pari", tenant_id=TENANT, titre="Récurrence sans pari",
        porteur="", exigence="pas de situation récurrente", ecart="3 situations",
        refutable_par="<3 situations sur 2 fenêtres", statut="OUVERT",
        signature="recurrence", twin_ids=["app-cartes"],
        preuves=[{"situation_ids": ["s-1"]}])
    boucle.enregistrer_boucle(conn, TENANT, need_detecte)

    rapport = resolution_besoins.verifier_paris(conn, TENANT, maintenant=MAINTENANT)
    assert rapport["erreurs"] == []
    assert rapport["totaux"]["paris_ouverts"] == 1
    relu = boucle.lire_boucle(conn, TENANT, "need-pg-pari")
    intention_id = relu["donnees"]["intention_id"]
    assert intention_id
    intention = memoire_prospective.lire(conn, TENANT, intention_id)
    assert intention is not None and intention["statut"] == "a_faire"
    assert intention["donnees"]["need_id"] == "need-pg-pari"

    second = resolution_besoins.verifier_paris(conn, TENANT, maintenant=MAINTENANT)
    assert second["totaux"]["paris_ouverts"] == 0  # pari déjà posé : idempotent
    assert second["erreurs"] == []
