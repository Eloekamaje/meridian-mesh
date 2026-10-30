"""Synchronisation canonique Twins/relations : mapping minimal, idempotence, orphelins, tenant et dry-run."""
import json

import pytest

from jumeau.graphe import GrapheMemoire, NoeudTwin
from jumeau.graphe_sync import (
    arete_depuis_relation,
    ecarts,
    reconcilier,
    synchroniser,
    twin_depuis_identite,
)

TENANT = "banque"


def twin(identifiant, type_="APPLICATION", **extra):
    return {"id": identifiant, "tenant_id": TENANT, "type": type_, "nom": identifiant.upper(), **extra}


def relation(identifiant, source, cible, **extra):
    return {
        "id": identifiant,
        "tenant_id": TENANT,
        "source": source,
        "cible": cible,
        "type": "echange",
        "etat": "validation",
        "confiance": 0.7,
        **extra,
    }


def test_twin_depuis_identite_ne_copie_ni_claims_ni_preuves():
    noeud = twin_depuis_identite(TENANT, {
        **twin("tbt", type_="application", mission="Virements", domaine="paiement",
               equipe="DSI", statut="actif"),
        "claims": [{"id": "c1", "objet": "secret"}],
        "preuves": [{"id": "p1", "citation": "secret"}],
        "proprietes": {"claims": [{"id": "c2"}]},
    })
    assert noeud.type == "APPLICATION" and noeud.label == "TBT"
    assert noeud.proprietes == {
        "mission": "Virements", "domaine": "paiement", "equipe": "DSI", "statut": "actif",
    }
    assert "claims" not in noeud.proprietes and "preuves" not in noeud.proprietes
    assert "secret" not in json.dumps(noeud.proprietes)


def test_arete_depuis_relation_lit_le_document_mongo_legacy():
    arete = arete_depuis_relation(TENANT, {
        "id": "rel-gardien-tbt-cdm", "tenant_id": TENANT, "source": "tbt", "cible": "cdm",
        "type": "echange", "etat": "confirmée", "confiance": "0.9",
        "decouverte_quand": "2026-01-01T00:00:00Z", "valid_to": "2026-02-01T00:00:00Z",
        "preuves": [{"id": "p1", "citation": "secret"}, {"preuve_id": "p2"}],
        "claims": ["une formulation qui reste dans Mongo"],
    })
    assert (arete.source, arete.target, arete.type, arete.etat) == ("tbt", "cdm", "echange", "confirmee")
    assert arete.confiance == 0.9
    assert arete.valid_from == "2026-01-01T00:00:00Z"
    assert arete.valid_to == "2026-02-01T00:00:00Z"
    assert arete.preuve_ids == ("p1", "p2")
    assert "secret" not in str(arete.preuve_ids)


def test_relation_inactive_sans_date_est_fermee_sans_inventer_de_date():
    arete = arete_depuis_relation(TENANT, relation("r1", "a", "b", active=False))
    assert arete.valid_to == "inactive" and not arete.active()


def test_synchroniser_ecrit_les_twins_avant_les_relations_et_est_idempotent():
    store = GrapheMemoire()
    twins = [twin("a"), twin("b", type_="PROCESS", mission="Traiter")]
    relations = [relation("r1", "a", "b")]
    attendu = {"twins": 2, "relations": 1, "ignores": [], "erreurs": []}

    assert synchroniser(store, TENANT, twins, relations) == attendu
    assert [voisin["id"] for voisin in store.voisins(TENANT, "a")] == ["b"]
    assert len(store.noeuds) == 2 and len(store.aretes) == 1

    assert synchroniser(store, TENANT, twins, relations) == attendu
    assert len(store.noeuds) == 2 and len(store.aretes) == 1


def test_relation_orpheline_est_ignoree_sans_casser_le_reste():
    store = GrapheMemoire()
    rapport = synchroniser(
        store, TENANT, [twin("a"), twin("b")],
        [relation("r1", "a", "b"), relation("orpheline", "a", "absent"), relation("r3", "b", "a")],
    )
    assert (rapport["twins"], rapport["relations"]) == (2, 2)
    assert rapport["erreurs"] == []
    assert len(rapport["ignores"]) == 1
    assert rapport["ignores"][0]["id"] == "orpheline"
    assert rapport["ignores"][0]["absents"] == ["absent"]
    assert set(store.aretes) == {(TENANT, "r1"), (TENANT, "r3")}


def test_tenant_isolation_refuse_les_twins_et_relations_d_un_autre_tenant():
    store = GrapheMemoire()
    store.upsert_twin(NoeudTwin("x", "autre", "APPLICATION", "X"))
    rapport = synchroniser(
        store, TENANT,
        [twin("a"), {"id": "x", "tenant_id": "autre", "type": "APPLICATION", "nom": "X"}],
        [relation("r1", "a", "x")],
    )
    assert rapport["twins"] == 1
    assert len(rapport["erreurs"]) == 1 and "autre tenant" in rapport["erreurs"][0]["raison"]
    assert len(rapport["ignores"]) == 1 and rapport["ignores"][0]["absents"] == ["x"]
    assert (TENANT, "x") not in store.noeuds and (TENANT, "r1") not in store.aretes

    with pytest.raises(PermissionError):
        twin_depuis_identite(TENANT, {"id": "x", "tenant_id": "autre", "nom": "X"})
    with pytest.raises(PermissionError):
        arete_depuis_relation(TENANT, {"id": "r", "tenant_id": "autre", "source": "a", "cible": "x"})


def test_types_et_etats_invalides_sont_comptes_sans_interrompre_la_sync():
    store = GrapheMemoire()
    rapport = synchroniser(
        store, TENANT,
        [twin("a"), twin("b"), {"id": "x", "tenant_id": TENANT, "type": "SATELLITE", "nom": "X"}],
        [relation("r1", "a", "b"), relation("r2", "a", "b", etat="inconnu")],
    )
    assert (rapport["twins"], rapport["relations"]) == (2, 1)
    assert {erreur["type"] for erreur in rapport["erreurs"]} == {"twin", "relation"}
    assert len(rapport["erreurs"]) == 2

    with pytest.raises(ValueError):
        twin_depuis_identite(TENANT, {"id": "x", "tenant_id": TENANT, "type": "SATELLITE", "nom": "X"})
    with pytest.raises(ValueError):
        arete_depuis_relation(TENANT, relation("r", "a", "b", etat="inconnu"))
    with pytest.raises(ValueError):
        arete_depuis_relation(TENANT, relation("r", "a", "b", type="!!!"))


def test_dry_run_compte_sans_ecrire_dans_le_store():
    store = GrapheMemoire()
    rapport = synchroniser(
        store, TENANT, [twin("a"), twin("b")], [relation("r1", "a", "b")], dry_run=True,
    )
    assert rapport == {"twins": 2, "relations": 1, "ignores": [], "erreurs": []}
    assert store.noeuds == {} and store.aretes == {}


def test_reconcilier_detecte_les_orphelines_sans_ecrire_et_respecte_le_store():
    store = GrapheMemoire()
    store.upsert_twin(NoeudTwin("c", TENANT, "APPLICATION", "C"))
    avant = store.as_dict()
    twins = [twin("a"), twin("b")]
    relations = [
        relation("r1", "a", "b"),
        relation("r2", "a", "absent"),
        relation("r3", "a", "c"),
    ]

    rapport = reconcilier(store, TENANT, twins, relations)
    assert (rapport["twins"], rapport["relations"]) == (2, 3)
    assert [ecart["id"] for ecart in rapport["ecarts"]] == ["r2"]
    assert rapport["ecarts"][0]["absents"] == ["absent"]
    assert rapport["erreurs"] == []
    assert ecarts(store, TENANT, twins, relations) == rapport["ecarts"]
    assert store.as_dict() == avant


def test_rapport_est_json_avec_les_quatre_cles_attendues():
    rapport = synchroniser(
        GrapheMemoire(), TENANT, [twin("a")], [relation("r1", "a", "absent")],
    )
    assert set(rapport) == {"twins", "relations", "ignores", "erreurs"}
    assert json.loads(json.dumps(rapport, ensure_ascii=False)) == rapport


def test_une_confiance_en_pourcentage_est_normalisee():
    from jumeau.graphe_sync import arete_depuis_relation

    arete = arete_depuis_relation("banque", {
        "id": "r", "source": "a", "cible": "b", "type": "echange", "confiance": 82,
    })
    assert arete.confiance == 0.82


def test_une_periode_non_iso_est_abandonnee_pas_interpretee():
    from jumeau.graphe_sync import arete_depuis_relation

    arete = arete_depuis_relation("banque", {
        "id": "r", "source": "a", "cible": "b", "type": "echange",
        "valid_from": "il y a 8 mois", "valid_to": "2026-10-30T00:00:00Z",
    })
    assert arete.valid_from is None
    assert arete.valid_to == "2026-10-30T00:00:00Z"
