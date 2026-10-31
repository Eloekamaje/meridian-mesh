"""Récupération mémoire : classement pur, portées et tenant, enrichissement et secrets."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from jumeau import connaissance, contexte, depot, entreprise_depot, memoire_durable, memoire_org
from jumeau.retrieval_memoire import (
    CandidatMemoire,
    RetrievalMemoireInvalide,
    enrichir_pack,
    recuperer,
)
from jumeau.tests.conftest import besoin_pg

TENANT = "banque"
AUTRE_TENANT = "assurance"
DATE = "2026-10-01T08:00:00+00:00"

CLAIM = {
    "id": 7,
    "sujet": "Système",
    "predicat": "IMPACTE",
    "objet": "delai carte",
    "type": "IMPACT",
    "confiance": 0.9,
    "preuve": "git://tbt@sha1:src/carte.py#L1-L2",
    "statut": "ACCEPTED",
    "maturite": "M3",
    "verification": {"etat": "selon", "methode": "recoupement"},
}


def _durable(
    identifiant, contenu, *, scope="twin", scope_id="twin-1", confiance=0.7,
    expire_le=None, provenance="revue", donnees=None, cree_le=DATE,
):
    return {
        "id": identifiant,
        "scope": scope,
        "scope_id": scope_id,
        "classe": "contexte",
        "contenu": contenu,
        "provenance": provenance,
        "confiance": confiance,
        "expire_le": expire_le,
        "donnees": dict(donnees or {}),
        "cree_le": cree_le,
    }


def _annotation(
    identifiant, contenu, *, twins=(), situations=(), confiance=0.7,
    source="revue", donnees=None, cree_le=DATE,
):
    charge = {
        "contenu": contenu,
        "genre": "note",
        "source": source,
        "twin_ids": list(twins),
        "situation_ids": list(situations),
        "confiance": confiance,
    }
    charge.update(donnees or {})
    return {"id": identifiant, "titre": contenu, "cree_le": cree_le, "donnees": charge}


def _learning(
    identifiant, enonce, *, twins=(), situations=(), confiance=0.7,
    acteur="revue", cree_le=DATE,
):
    return {
        "id": identifiant,
        "type": "LEARNING",
        "titre": enonce,
        "cree_le": cree_le,
        "donnees": {
            "enonce": enonce,
            "twin_ids": list(twins),
            "situation_ids": list(situations),
            "confiance": confiance,
            "acteur": acteur,
        },
    }


@pytest.fixture
def sources_factices(monkeypatch):
    """Remplace les quatre lectures par des sources en mémoire, sans base ni réseau."""
    etat = {
        "durables": [], "annotations": [], "learnings": [], "claims": {},
        "twins": {}, "appels": [],
    }

    def lister(conn, tenant, **options):
        etat["appels"].append(("durable", tenant, options))
        return list(etat["durables"])

    def objets(conn, tenant, type_=None, **options):
        etat["appels"].append((type_, tenant, options))
        if type_ == "ANNOTATION":
            return list(etat["annotations"])
        if type_ == "LEARNING":
            return list(etat["learnings"])
        return []

    def connaissances(conn, jumeau_id, **options):
        etat["appels"].append(("claim", jumeau_id, options))
        return list(etat["claims"].get(jumeau_id, []))

    def jumeau(conn, jumeau_id):
        return etat["twins"].get(jumeau_id)

    monkeypatch.setattr(memoire_durable, "lister", lister)
    monkeypatch.setattr(entreprise_depot, "lister_objets", objets)
    monkeypatch.setattr(connaissance, "connaissances", connaissances)
    monkeypatch.setattr(depot, "jumeau_par_id", jumeau)
    return etat


def test_classement_phrase_couverture_autorite_et_determinisme(sources_factices):
    etat = sources_factices
    etat["twins"]["twin-1"] = {"id": "twin-1", "tenant_id": TENANT}
    etat["durables"] = [_durable("durable", "Le delai de carte baisse")]
    etat["annotations"] = [
        _annotation("annotation-exact", "Le delai de carte baisse", twins=["twin-1"]),
        _annotation("annotation-partiel", "Le delai de carte graphique chauffe", twins=["twin-1"]),
    ]
    etat["learnings"] = [_learning("learning", "Le delai de carte baisse", twins=["twin-1"])]
    etat["claims"]["twin-1"] = [CLAIM]

    premier = recuperer(
        object(), TENANT, question="delai carte", twin_ids=["twin-1"],
        scope="twin", scope_id="twin-1", limite=10)
    second = recuperer(
        object(), TENANT, question="delai carte", twin_ids=["twin-1"],
        scope="twin", scope_id="twin-1", limite=10)

    ids = [candidat.id for candidat in premier]
    assert ids[0] == "7"
    assert ids.index("learning") < ids.index("annotation-exact") < ids.index("durable")
    assert ids.index("annotation-exact") < ids.index("annotation-partiel")
    assert ids == [candidat.id for candidat in second]
    assert [candidat.score for candidat in premier] == sorted(
        (candidat.score for candidat in premier), reverse=True)
    assert "phrase exacte" in premier[0].raisons
    assert all(candidat.source in {"durable", "annotation", "learning", "claim"}
               for candidat in premier)


def test_recuperer_filtre_lexical_expiration_et_learnings_ancres(sources_factices):
    etat = sources_factices
    etat["twins"]["twin-1"] = {"id": "twin-1", "tenant_id": TENANT}
    etat["durables"] = [
        _durable("frais", "Le delai de carte baisse"),
        _durable("expire", "Le delai de carte ancien", expire_le="2020-01-01T00:00:00+00:00"),
        _durable("hors-sujet", "La meteo est douce"),
    ]
    etat["annotations"] = [
        _annotation("annotation-match", "Le delai de carte", twins=["twin-1"]),
        _annotation("annotation-hors", "La meteo est douce", twins=["twin-1"]),
    ]
    etat["learnings"] = [
        _learning("learning-ancre", "Sans mots communs", twins=["twin-1"]),
        _learning("learning-hors", "Sans mots communs", twins=["twin-2"]),
    ]

    resultat = recuperer(object(), TENANT, question="delai carte", twin_ids=["twin-1"])
    ids = {candidat.id for candidat in resultat}

    assert {"frais", "annotation-match", "learning-ancre"} <= ids
    assert "expire" not in ids
    assert "hors-sujet" not in ids
    assert "annotation-hors" not in ids
    assert "learning-hors" not in ids
    assert all(candidat.source != "claim" for candidat in resultat)

    appels_durables = [appel for appel in etat["appels"] if appel[0] == "durable"]
    assert appels_durables[-1][2]["limite"] == 100


def test_claims_seulement_sur_twins_explicites_et_du_tenant(sources_factices):
    etat = sources_factices
    etat["twins"]["twin-1"] = {"id": "twin-1", "tenant_id": TENANT}
    etat["twins"]["twin-autre"] = {"id": "twin-autre", "tenant_id": AUTRE_TENANT}
    etat["claims"]["twin-1"] = [CLAIM]
    etat["claims"]["twin-autre"] = [{**CLAIM, "id": 8, "objet": "delai carte autre"}]

    sans_twin = recuperer(object(), TENANT, question="delai carte")
    assert sans_twin == []
    assert not any(appel[0] == "claim" for appel in etat["appels"])

    etat["appels"].clear()
    resultat = recuperer(
        object(), TENANT, question="delai carte", twin_ids=["twin-1", "twin-autre"])

    assert [candidat.id for candidat in resultat if candidat.source == "claim"] == ["7"]
    appels_claims = [appel for appel in etat["appels"] if appel[0] == "claim"]
    assert [appel[1] for appel in appels_claims] == ["twin-1"]


def test_aucun_secret_dans_les_candidats(sources_factices):
    etat = sources_factices
    etat["twins"]["twin-1"] = {"id": "twin-1", "tenant_id": TENANT}
    etat["durables"] = [_durable(
        "durable", "Livraison token=abcdef123456",
        provenance="api_key=zzzzzzzz",
        donnees={"client_secret": "s3cr3t", "canal": "web"})]
    etat["annotations"] = [_annotation(
        "annotation", "Le mot de passe: hunter2 est noté",
        source="bearer abcdefghijklmnop", twins=["twin-1"])]
    etat["learnings"] = [_learning(
        "learning", "Voir https://user:pass@example.test/rapport", twins=["twin-1"])]
    etat["claims"]["twin-1"] = [{
        **CLAIM,
        "sujet": "token=abcdef123456",
        "objet": "https://user:pass@example.test/rapport",
    }]

    resultat = recuperer(object(), TENANT, question="", twin_ids=["twin-1"], limite=10)
    charge = json.dumps([candidat.as_dict() for candidat in resultat], ensure_ascii=False)

    for secret in ("abcdef123456", "zzzzzzzz", "s3cr3t", "hunter2", "user:pass"):
        assert secret not in charge
    assert "***" in charge


def test_enrichir_pack_copie_borne_et_empreinte_stable():
    pack = {
        "tenant": "banque",
        "faits": [{"titre": "f"}],
        "budget": {"faits": 1},
        "memoire": ["ancienne"],
    }
    original = deepcopy(pack)
    candidats = [
        CandidatMemoire(
            id="b", source="durable", classe="contexte", contenu="Deuxieme",
            provenance="revue", score=2.0),
        CandidatMemoire(
            id="a", source="claim", classe="dependency", contenu="Premier",
            provenance="claim:twin", score=3.0),
        {
            "id": "c", "source": "annotation", "classe": "note", "contenu": "Troisieme",
            "provenance": "revue", "score": 1.0, "donnees": {"token": "secret123"},
        },
    ]

    resultat = enrichir_pack(pack, candidats, max_ajouts=2)
    assert pack == original
    assert [entree["id"] for entree in resultat["memoire"]] == ["b", "a"]
    assert len(resultat["fingerprint_memoire"]) == 64
    assert resultat["tenant"] == "banque"

    inverse = enrichir_pack({"tenant": "banque"}, [candidats[1], candidats[0]], max_ajouts=2)
    assert inverse["fingerprint_memoire"] == resultat["fingerprint_memoire"]

    complet = enrichir_pack({}, candidats, max_ajouts=10)
    charge = json.dumps(complet, ensure_ascii=False)
    assert "secret123" not in charge
    assert len(complet["memoire"]) == 3
    assert complet["memoire"][2]["donnees"] == {}


def test_enrichir_pack_accepte_context_pack_et_namespace_sans_mutation():
    pack = contexte.ContextePack(
        tenant="banque", question="Pourquoi ?", profil_id="dev", autorite="lecture")
    avant = pack.as_dict()

    resultat = enrichir_pack(pack, [CandidatMemoire(
        id="m1", source="learning", classe="apprentissage", contenu="Leçon",
        provenance="revue")])

    assert pack.as_dict() == avant
    assert "memoire" not in pack.as_dict()
    assert resultat["tenant"] == "banque"
    assert resultat["memoire"][0]["id"] == "m1"

    espace = SimpleNamespace(tenant="demo", faits=[{"titre": "f"}])
    copie = enrichir_pack(espace, [], max_ajouts=3)

    assert copie["tenant"] == "demo"
    assert copie["memoire"] == [] and copie["fingerprint_memoire"]
    assert not hasattr(espace, "memoire")
    assert espace.faits == [{"titre": "f"}]


def test_parametres_invalides_refuses(sources_factices):
    with pytest.raises(RetrievalMemoireInvalide):
        recuperer(object(), "Tenant !", question="delai")
    with pytest.raises(RetrievalMemoireInvalide):
        recuperer(object(), TENANT, question="delai", scope="monde")
    with pytest.raises(RetrievalMemoireInvalide):
        recuperer(object(), TENANT, question="delai", limite=0)
    with pytest.raises(RetrievalMemoireInvalide):
        enrichir_pack({}, [], max_ajouts=-1)


@besoin_pg
def test_recuperer_relie_les_sources_et_isole_tenant_et_portee(conn):
    memoire_durable.creer(
        conn, TENANT, id="d-sit", scope="situation", scope_id="sit-1",
        classe="contexte", contenu="Le delai de carte baisse", provenance="revue",
        confiance=0.8)
    memoire_durable.creer(
        conn, TENANT, id="d-session", scope="session", scope_id="s-1",
        classe="contexte", contenu="Le delai de carte baisse", provenance="revue",
        confiance=0.8)
    memoire_durable.creer(
        conn, AUTRE_TENANT, id="d-hors", scope="situation", scope_id="sit-1",
        classe="contexte", contenu="Le delai de carte baisse", provenance="revue",
        confiance=0.8)

    annotation = memoire_org.memoriser(
        conn, TENANT, "Le delai de carte baisse", genre="note", source="revue",
        twin_ids=["twin-1"], situation_ids=["sit-1"])
    hors_annotation = memoire_org.memoriser(
        conn, AUTRE_TENANT, "Le delai de carte baisse", genre="note", source="revue",
        twin_ids=["twin-1"], situation_ids=["sit-1"])
    memoire_org.memoriser(
        conn, TENANT, "Le delai de carte baisse", genre="note", source="revue",
        twin_ids=["twin-2"], situation_ids=["sit-2"])

    learning = entreprise_depot.enregistrer_objet(conn, TENANT, {
        "id": "l-1", "famille": "resultat_apprentissage", "type": "LEARNING",
        "mode": "DECLARED", "titre": "Le delai de carte baisse",
        "donnees": {
            "enonce": "Le delai de carte baisse",
            "twin_ids": ["twin-1"],
            "situation_ids": ["sit-1"],
            "preuve_ids": ["preuve-1"],
            "acteur": "revue",
        },
    })
    entreprise_depot.enregistrer_objet(conn, AUTRE_TENANT, {
        "id": "l-hors", "famille": "resultat_apprentissage", "type": "LEARNING",
        "mode": "DECLARED", "titre": "Le delai de carte baisse",
        "donnees": {
            "enonce": "Le delai de carte baisse",
            "twin_ids": ["twin-1"],
            "situation_ids": ["sit-1"],
            "acteur": "revue",
        },
    })

    depot.creer_jumeau(conn, {
        "id": "twin-1", "tenant_id": TENANT, "nom": "Carte", "equipe": "equipe-carte"})
    depot.creer_jumeau(conn, {
        "id": "twin-autre", "tenant_id": AUTRE_TENANT, "nom": "Carte assurance",
        "equipe": "equipe-assurance"})
    claim_tenant = conn.execute(
        "INSERT INTO claim (tenant_id, jumeau_id, sujet, predicat, objet, type, confiance) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (TENANT, "twin-1", "Paiement", "DEPEND_DE", "Carte", "DEPENDENCY", 0.9),
    ).fetchone()[0]
    claim_autre = conn.execute(
        "INSERT INTO claim (tenant_id, jumeau_id, sujet, predicat, objet, type, confiance) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (AUTRE_TENANT, "twin-autre", "Paiement", "DEPEND_DE", "Carte", "DEPENDENCY", 0.9),
    ).fetchone()[0]

    resultat = recuperer(
        conn, TENANT, question="delai carte", twin_ids=["twin-1", "twin-autre"],
        situation_id="sit-1", scope="situation", scope_id="sit-1", limite=20)
    cles = {(candidat.source, candidat.id) for candidat in resultat}

    assert ("durable", "d-sit") in cles
    assert ("durable", "d-session") not in cles
    assert ("durable", "d-hors") not in cles
    assert ("annotation", annotation["id"]) in cles
    assert ("annotation", hors_annotation["id"]) not in cles
    assert ("learning", learning["id"]) in cles
    assert ("learning", "l-hors") not in cles
    assert ("claim", str(claim_tenant)) in cles
    assert ("claim", str(claim_autre)) not in cles
    assert "assurance" not in json.dumps(
        [candidat.as_dict() for candidat in resultat], ensure_ascii=False)


@besoin_pg
def test_recuperer_ignore_une_memoire_durable_expiree(conn):
    memoire_durable.creer(
        conn, TENANT, id="expire", scope="situation", scope_id="sit-1",
        classe="contexte", contenu="Le delai de carte baisse", provenance="revue")
    conn.execute(
        "UPDATE memoire_durable SET expire_le = now() - interval '1 day' "
        "WHERE tenant_id = %s AND id = 'expire'", (TENANT,))

    assert recuperer(
        conn, TENANT, question="delai carte", scope="situation", scope_id="sit-1") == []
