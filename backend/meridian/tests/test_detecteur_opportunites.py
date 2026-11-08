"""Détecteur d'opportunités B2+D6 : ``duplication``, ``concentration_risque``,
``dette_vs_usage`` — quota commun, dédup et fail-closed.

Deux modes : READ sans base (liens et dépôt injectés) et persistance réelle
(sautée sans ``JUMEAU_PG_DSN``, comme les autres tests Postgres).
"""
import pytest

from meridian.adapters.outbound.postgres import boucle, detecteur_opportunites
from meridian.tests.conftest import besoin_pg

TENANT = "banque"


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


def lien(claim_id, application_id, capacite_id, **champs):
    """Lien confirmé application → capacité (contrat de la requête du détecteur)."""
    return {"claim_id": claim_id, "application_id": application_id,
            "capacite_id": capacite_id, "statut": "ACCEPTED",
            "type_twin": "APPLICATION", **champs}


def relation(claim_id, dependant_id, cible_id, predicat="DEPEND_DE", **champs):
    """Arête confirmée twin → twin (contrat de ``_lire_relations``)."""
    return {"claim_id": claim_id, "dependant_id": dependant_id,
            "cible_id": cible_id, "predicat": predicat,
            "statut": "ACCEPTED", **champs}


def signal_dette(claim_id, twin_id, **champs):
    """Claim de dette récent sur un twin (contrat de ``_lire_signaux_dette``)."""
    return {"claim_id": claim_id, "twin_id": twin_id,
            "type": "RISK", "predicat": "NOTE", "statut": "PROPOSED", **champs}


def situation(objet_id, twin_ids):
    """Ligne ``objet_entreprise`` SITUATION citant des twins (contrat ``_lire_situations``)."""
    return {"id": objet_id, "type": "SITUATION", "donnees": {"twin_ids": list(twin_ids)}}


def detecter(depot, conn=None, **kwargs):
    persister = kwargs.pop("persister", depot)
    return detecteur_opportunites.detecter(
        conn, TENANT, persister=persister, opportunites=[], **kwargs)


def test_deux_applications_meme_capacite_produisent_une_opportunity():
    depot = DepotMemoire()
    claims = [
        lien(11, "app-cartes", "cap-dossiers", capacite_twin_id="cap-dossiers",
             capacite_nom="Gérer les dossiers"),
        lien(22, "app-prets", "cap-dossiers", capacite_twin_id="cap-dossiers",
             capacite_nom="Gérer les dossiers"),
    ]
    rapport = detecter(depot, claims=claims)

    assert rapport["totaux"] == {"crees": 1, "ignores": 0, "erreurs": 0}
    [cree] = rapport["crees"]
    assert cree["signature"] == "duplication" and cree["applications"] == 2
    [opp] = depot.par_type("OPPORTUNITY")
    assert opp["id"] == cree["id"]
    donnees = opp["donnees"]
    assert donnees["signature"] == "duplication"
    assert donnees["capacite_id"] == "cap-dossiers"
    assert donnees["statut"] == "PROPOSED"
    assert donnees["type_opportunite"] == "DUPLICATION"
    assert set(donnees["twin_ids"]) == {"app-cartes", "app-prets", "cap-dossiers"}
    assert set(donnees["claim_ids"]) == {"11", "22"}
    assert opp["mode"] == "INFERRED"


def test_une_seule_application_ne_produit_rien():
    depot = DepotMemoire()
    rapport = detecter(depot, claims=[lien(11, "app-cartes", "cap-dossiers")])
    assert rapport["totaux"]["crees"] == 0 and not depot.objets


def test_trois_applications_produisent_une_seule_opportunity():
    depot = DepotMemoire()
    claims = [lien(n, f"app-{n}", "cap-dossiers") for n in (1, 2, 3)]
    rapport = detecter(depot, claims=claims)

    assert rapport["totaux"]["crees"] == 1
    [opp] = depot.par_type("OPPORTUNITY")
    assert len(opp["donnees"]["claim_ids"]) == 3
    assert set(opp["donnees"]["twin_ids"]) == {"app-1", "app-2", "app-3"}


def test_claims_non_confirmes_ne_produisent_rien():
    depot = DepotMemoire()
    claims = [
        lien(11, "app-a", "cap-x", statut="PROPOSED"),
        lien(22, "app-b", "cap-x", statut="PROPOSED"),
        lien(33, "app-c", "cap-y", statut="CONTESTED"),
        lien(44, "app-d", "cap-y", statut="CONTESTED"),
    ]
    rapport = detecter(depot, claims=claims)
    assert rapport["totaux"]["crees"] == 0 and not depot.objets


def test_twins_non_applicatifs_ne_comptent_pas():
    depot = DepotMemoire()
    claims = [
        lien(11, "app-a", "cap-x"),
        lien(22, "process-b", "cap-x", type_twin="PROCESS"),
    ]
    rapport = detecter(depot, claims=claims)
    assert rapport["totaux"]["crees"] == 0


def test_dedup_opportunity_existante():
    depot = DepotMemoire()
    existante = {"id": "opp-ancienne", "donnees": {
        "signature": "duplication", "capacite_id": "cap-dossiers", "statut": "QUALIFIEE"}}
    rapport = detecteur_opportunites.detecter(
        None, TENANT, persister=depot,
        claims=[lien(1, "app-a", "cap-dossiers"), lien(2, "app-b", "cap-dossiers")],
        opportunites=[existante])
    assert rapport["totaux"]["crees"] == 0
    assert rapport["ignores"][0]["signature"] == "duplication"


def test_second_run_ne_cree_rien():
    depot = DepotMemoire()
    claims = [lien(1, "app-a", "cap-x"), lien(2, "app-b", "cap-x")]
    premier = detecteur_opportunites.detecter(
        None, TENANT, persister=depot, claims=claims, opportunites=[])
    assert premier["totaux"]["crees"] == 1

    # le run suivant voit le contenu du dépôt — même signature, même capacité
    second = detecteur_opportunites.detecter(
        None, TENANT, persister=depot, claims=claims,
        opportunites=depot.par_type("OPPORTUNITY"))
    assert second["totaux"]["crees"] == 0
    assert second["totaux"]["ignores"] == 1


def test_quota_borne_le_nombre_d_opportunites():
    depot = DepotMemoire()
    claims = []
    for rang in range(5):
        claims += [lien(rang * 2 + 1, f"app-a-{rang}", f"cap-{rang}"),
                   lien(rang * 2 + 2, f"app-b-{rang}", f"cap-{rang}")]
    rapport = detecter(depot, claims=claims, quota=2)
    assert rapport["totaux"]["crees"] == 2
    assert len(depot.par_type("OPPORTUNITY")) == 2


def test_min_overlap_releve_le_seuil():
    depot = DepotMemoire()
    claims = [lien(1, "app-a", "cap-x"), lien(2, "app-b", "cap-x")]
    assert detecter(depot, claims=claims, min_overlap=3)["totaux"]["crees"] == 0
    assert detecter(depot, claims=claims, min_overlap=2)["totaux"]["crees"] == 1


def test_parametres_invalides_refuses():
    depot = DepotMemoire()
    with pytest.raises(detecteur_opportunites.DetectionInvalide):
        detecteur_opportunites.detecter(None, " ", persister=depot, claims=[])
    with pytest.raises(detecteur_opportunites.DetectionInvalide):
        detecteur_opportunites.detecter(None, TENANT, persister=depot, claims=[], quota=0)
    with pytest.raises(detecteur_opportunites.DetectionInvalide):
        detecteur_opportunites.detecter(None, TENANT, persister=depot, claims=[], min_overlap=1)


def test_echec_persistance_remonte_en_erreurs():
    def persister_en_echec(conn, tenant, objets):
        raise RuntimeError("écriture refusée")
    rapport = detecteur_opportunites.detecter(
        None, TENANT, persister=persister_en_echec, opportunites=[],
        claims=[lien(1, "app-a", "cap-x"), lien(2, "app-b", "cap-x")])
    assert rapport["totaux"]["crees"] == 0
    assert rapport["totaux"]["erreurs"] == 1
    assert "refusée" in rapport["erreurs"][0]["erreur"]


# --- Persistance Postgres réelle ---


def _preparer_duplication(conn):
    """Deux applications ACCEPTED sur la même capacité twin ; rend les ids créés."""
    from meridian.adapters.outbound.postgres import depot, twins_types
    for app_id, nom in (("app-cartes", "Cartes"), ("app-prets", "Prêts")):
        twins_types.creer_twin(conn, TENANT, app_id, "APPLICATION", nom, acteur="alice")
    twins_types.creer_twin(
        conn, TENANT, "cap-dossiers", "CAPABILITY", "Gérer les dossiers", acteur="alice")
    claim_ids = []
    for app_id in ("app-cartes", "app-prets"):
        claim = twins_types.creer_claim(
            conn, TENANT, app_id, "REALISE_CAPACITE", "cap-dossiers",
            source="referentiel", preuve="docs/capacites.md#L1",
            acteur="alice", texte=f"{app_id} réalise la capacité")
        depot.reviser(conn, claim["id"], "bob", "ACCEPTED", "vu en comité")
        claim_ids.append(claim["id"])
    return claim_ids


@besoin_pg
def test_persistance_reelle_duplication(conn):
    claim_ids = _preparer_duplication(conn)

    rapport = detecteur_opportunites.detecter(conn, TENANT)
    assert rapport["erreurs"] == []
    [cree] = rapport["crees"]
    assert sorted(str(c) for c in cree["claim_ids"]) == sorted(str(c) for c in claim_ids)

    relu = boucle.lire_boucle(conn, TENANT, cree["id"])
    assert relu["type"] == "OPPORTUNITY" and relu["famille"] == "emergence"
    donnees = relu["donnees"]
    assert donnees["signature"] == "duplication" and donnees["capacite_id"] == "cap-dossiers"
    assert set(donnees["twin_ids"]) == {"app-cartes", "app-prets", "cap-dossiers"}
    assert donnees["statut"] == "PROPOSED"

    second = detecteur_opportunites.detecter(conn, TENANT)
    assert second["crees"] == [] and second["erreurs"] == []
    assert second["totaux"]["ignores"] == 1


@besoin_pg
def test_persistance_reelle_une_seule_application(conn):
    from meridian.adapters.outbound.postgres import depot, twins_types
    twins_types.creer_twin(conn, TENANT, "app-seule", "APPLICATION", "Seule", acteur="alice")
    claim = twins_types.creer_claim(
        conn, TENANT, "app-seule", "REALISE_CAPACITE", "cap-dossiers",
        source="referentiel", preuve="docs/capacites.md#L1", acteur="alice")
    depot.reviser(conn, claim["id"], "bob", "ACCEPTED", None)

    rapport = detecteur_opportunites.detecter(conn, TENANT)
    assert rapport["totaux"] == {"crees": 0, "ignores": 0, "erreurs": 0}
    assert not conn.execute(
        "SELECT 1 FROM objet_entreprise WHERE type = 'OPPORTUNITY'").fetchone()


@besoin_pg
def test_persistance_reelle_claims_proposes_seuls_ne_produisent_rien(conn):
    from meridian.adapters.outbound.postgres import twins_types
    for app_id in ("app-x", "app-y"):
        twins_types.creer_twin(conn, TENANT, app_id, "APPLICATION", app_id, acteur="alice")
        twins_types.creer_claim(
            conn, TENANT, app_id, "REALISE_CAPACITE", "cap-partagee",
            source="referentiel", preuve="docs/capacites.md#L1", acteur="alice")

    rapport = detecteur_opportunites.detecter(conn, TENANT)
    assert rapport["totaux"]["crees"] == 0  # PROPOSED n'est pas confirmé : pas d'opportunité


# --- Signature concentration_risque (D6) ---


def test_twin_tres_connecte_produit_une_concentration():
    depot = DepotMemoire()
    relations = [relation(n, f"app-{n}", "app-noyau") for n in range(1, 6)]
    rapport = detecter(depot, relations=relations)

    assert rapport["totaux"] == {"crees": 1, "ignores": 0, "erreurs": 0}
    [cree] = rapport["crees"]
    assert cree["signature"] == "concentration_risque"
    assert cree["sujet"] == "app-noyau" and cree["dependants"] == 5
    [opp] = depot.par_type("OPPORTUNITY")
    donnees = opp["donnees"]
    assert donnees["signature"] == "concentration_risque"
    assert donnees["type_opportunite"] == "CONCENTRATION_RISQUE"
    assert donnees["sujet_detection"] == "app-noyau"
    assert donnees["degre_entrant"] == 5
    assert set(donnees["twin_ids"]) == {"app-noyau", *(f"app-{n}" for n in range(1, 6))}
    assert len(donnees["claim_ids"]) == 5
    assert "point unique" in donnees["description"]


def test_quatre_dependants_sous_le_seuil_ne_produisent_rien():
    depot = DepotMemoire()
    relations = [relation(n, f"app-{n}", "app-noyau") for n in range(1, 5)]
    rapport = detecter(depot, relations=relations)
    assert rapport["totaux"]["crees"] == 0 and not depot.objets


def test_dependants_distincts_seuls_comptent():
    """Deux claims du même twin vers la cible ne gonflent pas le degré entrant."""
    depot = DepotMemoire()
    relations = [
        relation(1, "app-a", "app-noyau", predicat="DEPEND_DE"),
        relation(2, "app-a", "app-noyau", predicat="APPELLE"),
        *[relation(2 + n, f"app-{n}", "app-noyau") for n in range(2, 5)],
    ]
    # app-a + app-2..app-4 = 4 dependants distincts < 5
    assert detecter(depot, relations=relations)["totaux"]["crees"] == 0
    depot2 = DepotMemoire()
    rapport = detecter(depot2, relations=relations, min_dependants=4)
    assert rapport["totaux"]["crees"] == 1


def test_degre_entrant_pilote_impact_et_severite():
    depot = DepotMemoire()
    relations = [relation(n, f"app-{n}", "app-noyau") for n in range(1, 11)]
    rapport = detecter(depot, relations=relations)
    [opp] = depot.par_type("OPPORTUNITY")
    donnees = opp["donnees"]
    assert donnees["degre_entrant"] == 10
    assert donnees["severite"] == "CRITIQUE" and donnees["impact"] == 1.0
    assert rapport["crees"][0]["severite"] == "CRITIQUE"


def test_relations_non_confirmees_ne_concentrent_pas():
    depot = DepotMemoire()
    relations = [relation(n, f"app-{n}", "app-noyau", statut="PROPOSED")
                 for n in range(1, 6)]
    assert detecter(depot, relations=relations)["totaux"]["crees"] == 0


# --- Signature dette_vs_usage (D6) ---


def test_dette_et_usage_produisent_une_opportunity_dette_critique():
    depot = DepotMemoire()
    relations = [relation(1, "app-a", "app-dette", predicat="APPELLE"),
                 relation(2, "app-b", "app-dette", predicat="APPELLE")]
    signaux = [signal_dette(10, "app-dette")]
    rapport = detecter(depot, relations=relations, signaux=signaux)

    assert rapport["totaux"] == {"crees": 1, "ignores": 0, "erreurs": 0}
    [cree] = rapport["crees"]
    assert cree["signature"] == "dette_vs_usage" and cree["sujet"] == "app-dette"
    assert cree["usage"] == 2 and cree["signaux_dette"] == 1
    [opp] = depot.par_type("OPPORTUNITY")
    donnees = opp["donnees"]
    assert donnees["type_opportunite"] == "DETTE_CRITIQUE"
    assert donnees["sujet_detection"] == "app-dette"
    assert set(donnees["twin_ids"]) == {"app-dette", "app-a", "app-b"}
    assert set(donnees["claim_ids"]) == {"1", "2", "10"}
    assert donnees["claim_ids_dette"] == ["10"]


def test_dette_sans_usage_ne_produit_rien():
    depot = DepotMemoire()
    rapport = detecter(depot, signaux=[signal_dette(10, "app-dette")])
    assert rapport["totaux"]["crees"] == 0 and not depot.objets


def test_usage_sans_dette_ne_produit_rien():
    depot = DepotMemoire()
    relations = [relation(n, f"app-{n}", "app-saine", predicat="APPELLE")
                 for n in range(1, 4)]
    rapport = detecter(depot, relations=relations, min_dependants=10)
    assert not any(c["signature"] == "dette_vs_usage" for c in rapport["crees"])


def test_situations_recentes_comptent_comme_usage():
    depot = DepotMemoire()
    signaux = [signal_dette(10, "app-dette")]
    situations = [situation("sit-1", ["app-dette", "autre"]),
                  situation("sit-2", ["app-dette"])]
    rapport = detecter(depot, signaux=signaux, situations=situations)
    assert rapport["totaux"]["crees"] == 1
    donnees = depot.par_type("OPPORTUNITY")[0]["donnees"]
    assert sorted(donnees["situation_ids"]) == ["sit-1", "sit-2"]
    assert donnees["usage"] == 2


def test_situation_expiree_ne_compte_pas_comme_usage():
    depot = DepotMemoire()
    signaux = [signal_dette(10, "app-dette")]
    vieille = {"id": "sit-vieille", "type": "SITUATION",
               "observe_le": "2020-01-01T00:00:00+00:00",
               "donnees": {"twin_ids": ["app-dette"]}}
    rapport = detecter(depot, signaux=signaux, situations=[vieille])
    assert rapport["totaux"]["crees"] == 0


def test_statut_conteste_est_un_signal_de_dette():
    depot = DepotMemoire()
    relations = [relation(1, "app-a", "app-dette", predicat="APPELLE"),
                 relation(2, "app-b", "app-dette", predicat="APPELLE")]
    signaux = [signal_dette(10, "app-dette", type="DEPENDENCY",
                            predicat="DEPEND_DE", statut="CONTESTED")]
    rapport = detecter(depot, relations=relations, signaux=signaux)
    assert rapport["totaux"]["crees"] == 1


# --- Quota commun, filtre signature et dédup multi-signatures ---


def test_quota_partage_entre_signatures():
    """Le quota borne le total du run ; ``duplication`` est jouée en premier."""
    depot = DepotMemoire()
    claims = [lien(1, "app-a", "cap-x"), lien(2, "app-b", "cap-x")]
    relations = [relation(10 + n, f"dep-{n}", "app-noyau") for n in range(1, 6)]
    rapport = detecter(depot, claims=claims, relations=relations, quota=1)
    assert rapport["totaux"]["crees"] == 1
    assert rapport["crees"][0]["signature"] == "duplication"


def test_filtre_signature_ne_joue_qu_un_detecteur():
    depot = DepotMemoire()
    claims = [lien(1, "app-a", "cap-x"), lien(2, "app-b", "cap-x")]
    relations = [relation(10 + n, f"dep-{n}", "app-noyau") for n in range(1, 6)]
    rapport = detecter(depot, claims=claims, relations=relations,
                       signature="concentration_risque")
    assert rapport["totaux"]["crees"] == 1
    assert rapport["crees"][0]["signature"] == "concentration_risque"
    assert rapport["signatures"] == ["concentration_risque"]


def test_signature_inconnue_refusee():
    depot = DepotMemoire()
    with pytest.raises(detecteur_opportunites.DetectionInvalide):
        detecter(depot, claims=[], signature="inconnue")


def test_second_run_ne_recree_aucune_signature():
    depot = DepotMemoire()
    relations = [relation(n, f"app-{n}", "app-noyau") for n in range(1, 6)]
    signaux = [signal_dette(50, "app-dette")]
    relations_usage = [relation(60 + n, f"cli-{n}", "app-dette", predicat="APPELLE")
                       for n in range(1, 3)]
    kwargs = dict(relations=relations + relations_usage, signaux=signaux)
    premier = detecteur_opportunites.detecter(
        None, TENANT, persister=depot, opportunites=[], **kwargs)
    assert premier["totaux"]["crees"] == 2
    assert {c["signature"] for c in premier["crees"]} == {
        "concentration_risque", "dette_vs_usage"}

    second = detecteur_opportunites.detecter(
        None, TENANT, persister=depot,
        opportunites=depot.par_type("OPPORTUNITY"), **kwargs)
    assert second["totaux"]["crees"] == 0
    assert second["totaux"]["ignores"] == 2


def test_dedup_concentration_existante_tous_statuts():
    """Une concentration déjà QUALIFIEE n'est pas rouverte."""
    depot = DepotMemoire()
    existante = {"id": "opp-ancienne", "donnees": {
        "signature": "concentration_risque", "sujet_detection": "app-noyau",
        "statut": "QUALIFIEE"}}
    relations = [relation(n, f"app-{n}", "app-noyau") for n in range(1, 6)]
    rapport = detecteur_opportunites.detecter(
        None, TENANT, persister=depot, relations=relations, opportunites=[existante])
    assert rapport["totaux"]["crees"] == 0
    assert rapport["ignores"][0]["signature"] == "concentration_risque"


# --- Persistance Postgres réelle (D6) ---


def _creer_dependances_acceptees(conn, dependants, cible, predicat="DEPEND_DE"):
    """``dependants`` déclarent ``predicat`` → ``cible``, claims ACCEPTED ; rend les claim ids."""
    from meridian.adapters.outbound.postgres import depot, twins_types
    twins_types.creer_twin(conn, TENANT, cible, "APPLICATION", "Noyau", acteur="alice")
    claim_ids = []
    for rang, dependant in enumerate(dependants):
        twins_types.creer_twin(
            conn, TENANT, dependant, "APPLICATION", dependant, acteur="alice")
        claim = twins_types.creer_claim(
            conn, TENANT, dependant, predicat, cible,
            source="referentiel", preuve=f"docs/dep.md#L{rang + 1}",
            acteur="alice", texte=f"{dependant} dépend de {cible}")
        depot.reviser(conn, claim["id"], "bob", "ACCEPTED", "vu en comité")
        claim_ids.append(claim["id"])
    return claim_ids


@besoin_pg
def test_persistance_reelle_concentration_risque(conn):
    dependants = [f"app-dep-{n}" for n in range(1, 6)]
    claim_ids = _creer_dependances_acceptees(conn, dependants, "app-noyau")

    rapport = detecteur_opportunites.detecter(conn, TENANT)
    assert rapport["erreurs"] == []
    [cree] = rapport["crees"]
    assert cree["signature"] == "concentration_risque" and cree["dependants"] == 5
    assert sorted(str(c) for c in cree["claim_ids"]) == sorted(str(c) for c in claim_ids)

    relu = boucle.lire_boucle(conn, TENANT, cree["id"])
    assert relu["type"] == "OPPORTUNITY" and relu["famille"] == "emergence"
    donnees = relu["donnees"]
    assert donnees["signature"] == "concentration_risque"
    assert donnees["sujet_detection"] == "app-noyau"
    assert donnees["degre_entrant"] == 5 and donnees["statut"] == "PROPOSED"
    assert set(donnees["twin_ids"]) == {"app-noyau", *dependants}

    second = detecteur_opportunites.detecter(conn, TENANT)
    assert second["crees"] == [] and second["erreurs"] == []
    assert second["totaux"]["ignores"] == 1


@besoin_pg
def test_persistance_reelle_dette_vs_usage(conn):
    from meridian.adapters.outbound.postgres import twins_types
    # usage : deux appelants confirmés vers le twin endetté
    _creer_dependances_acceptees(conn, ["app-cli-1", "app-cli-2"], "app-dette",
                                 predicat="APPELLE")
    # dette : un claim de type RISK sur le twin (PROPOSED suffit — le signal reste valide)
    claim = twins_types.creer_claim(
        conn, TENANT, "app-dette", "NOTE", "refactor à prévoir",
        source="referentiel", preuve="docs/dette.md#L1",
        acteur="alice", texte="dette technique identifiée")
    conn.execute("UPDATE claim SET type = 'RISK' WHERE id = %s", (claim["id"],))
    # témoin négatif : dette sans usage → rien
    twins_types.creer_twin(conn, TENANT, "app-fantome", "APPLICATION", "Fantôme",
                           acteur="alice")
    claim_fantome = twins_types.creer_claim(
        conn, TENANT, "app-fantome", "NOTE", "dette orpheline",
        source="referentiel", preuve="docs/dette.md#L9", acteur="alice")
    conn.execute("UPDATE claim SET type = 'RISK' WHERE id = %s", (claim_fantome["id"],))

    rapport = detecteur_opportunites.detecter(conn, TENANT)
    assert rapport["erreurs"] == []
    dettes = [c for c in rapport["crees"] if c["signature"] == "dette_vs_usage"]
    assert len(dettes) == 1
    [cree] = dettes
    assert cree["sujet"] == "app-dette" and cree["usage"] == 2

    relu = boucle.lire_boucle(conn, TENANT, cree["id"])
    donnees = relu["donnees"]
    assert donnees["type_opportunite"] == "DETTE_CRITIQUE"
    assert set(donnees["twin_ids"]) == {"app-dette", "app-cli-1", "app-cli-2"}
    assert str(claim["id"]) in [str(c) for c in donnees["claim_ids"]]

    second = detecteur_opportunites.detecter(conn, TENANT)
    assert not [c for c in second["crees"] if c["signature"] == "dette_vs_usage"]
