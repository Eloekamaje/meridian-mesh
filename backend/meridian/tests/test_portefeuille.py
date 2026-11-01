"""Portefeuille : agrégation bornée, valeur business et aucune causalité inventée."""
from meridian.adapters.outbound.postgres import portefeuille


class _Conn:
    pass


def _objet(identifiant, type_, titre, domaine="Paiement", **donnees):
    return {"id": identifiant, "type": type_, "titre": titre,
            "domaine": domaine, "donnees": {"domaine": domaine, **donnees}}


def test_agrege_les_objets_et_calcule_la_valeur(monkeypatch):
    objets = {
        "SITUATION": [_objet("s1", "SITUATION", "Latence", priorite="HAUTE", resume="r"),
                      _objet("s2", "SITUATION", "Bruit", priorite="BASSE", domaine="Client")],
        "DECISION": [_objet("d1", "DECISION", "Arbitrer")],
        "INITIATIVE": [_objet("i1", "INITIATIVE", "Réduire", resume="r")],
        "OUTCOME": [_objet("o1", "OUTCOME", "Gain", valeur_observee=10)],
        "LEARNING": [_objet("l1", "LEARNING", "Leçon", enonce="Apprendre")],
    }
    monkeypatch.setattr(portefeuille.entreprise_depot, "lister_objets",
                        lambda conn, tenant, type_, limite: objets[type_])
    resultat = portefeuille.agreger(_Conn(), "demo", domaine="Paiement", limite=10)

    assert resultat["scope"] == {"kind": "portfolio", "domaine": "Paiement"}
    assert resultat["valeur"] == {
        "situations": 1, "situations_haute": 1, "decisions": 1,
        "initiatives": 1, "outcomes": 1, "learnings": 1, "benefices_renseignes": 1}
    assert {p["type"] for p in resultat["propositions"]} == {
        "RISQUE", "CONSTAT", "ACTION", "OUTCOME", "LEARNING"}
    assert all(p["specialiste"] == "portefeuille" for p in resultat["propositions"])


def test_un_portefeuille_global_n_invente_pas_de_domaine(monkeypatch):
    monkeypatch.setattr(portefeuille.entreprise_depot, "lister_objets",
                        lambda conn, tenant, type_, limite: [])
    resultat = portefeuille.agreger(_Conn(), "demo", limite=5)
    assert resultat["scope"] == {"kind": "enterprise", "domaine": None}
    assert resultat["propositions"] == [] and resultat["valeur"]["situations"] == 0
