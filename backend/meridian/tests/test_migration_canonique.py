"""Migration contrôlée Mongo → canonique : mapping pur, dry-run, idempotence, orphelins et isolation tenant."""
import asyncio
import json

import pytest

from meridian.adapters.outbound.postgres import migration_canonique
from meridian.domain.graphe import GrapheMemoire
from meridian.adapters.outbound.postgres.migration_canonique import DocumentInvalide, inspecter, objet_depuis_initiative, objet_depuis_situation, twin_depuis_jumeau

TENANT = "banque"
SECRET = "hunter2-ne-doit-jamais-fuiter"
NOW = "2026-10-30T10:00:00+00:00"

SITUATION = {
    "id": "sit-cartes",
    "tenant_id": TENANT,
    "titre": "Délai de traitement en hausse",
    "resume": "Le délai dépasse la cible de 40 minutes.",
    "statut": "active",
    "priorite": "haute",
    "detectee": "2026-10-30T09:00:00Z",
    "jumeaux": ["paiements", "comptes", "paiements"],
    "password": SECRET,
    "indicateurs": {"confiance": 78, "token": SECRET},
    "preuves": [{"source": "Datadog", "detail": "4 traces concordantes"}],
}

INITIATIVE = {
    "id": "init-contrat",
    "tenant_id": TENANT,
    "titre": "Version du contrat Comptes : v2 ou v3 ?",
    "quand": "2026-08-26T08:41:00Z",
    "statut": "en_attente",
    "urgence": "haute",
    "jumeaux": ["paiements", "comptes"],
    "raison": "Le code et le trafic observé divergent.",
    "travail_id": "case-olympiade",
    "jumeau_cible": "conformite",
    "secret": SECRET,
}

JUMEAU_A = {
    "id": "paiements",
    "tenant_id": TENANT,
    "nom": "Paiements",
    "mission": "Traiter les paiements",
    "domaine": "Paiement",
    "equipe": "equipe-paiements",
    "statut": "actif",
}

JUMEAU_B = {
    "id": "comptes",
    "tenant_id": TENANT,
    "nom": "Comptes",
    "mission": "Tenir les comptes",
    "domaine": "Client",
    "statut": "actif",
}

RELATION = {
    "id": "r-paiements-comptes",
    "source": "paiements",
    "cible": "comptes",
    "type": "structurante",
    "etat": "confirmee",
    "confiance": 82,
    "decouverte_quand": "2026-01-01T00:00:00Z",
    "preuves": [{"id": "p1", "citation": SECRET}],
}


class _CurseurAsync:
    def __init__(self, documents):
        self.documents = documents

    async def to_list(self, length=None):
        return [dict(document) for document in self.documents]


class _Collection:
    def __init__(self, documents):
        self.documents = list(documents)

    async def find(self, filtre=None, projection=None):
        return _CurseurAsync(self.documents)


class _Db:
    def __init__(self, situations=(), initiatives=(), relations=(), jumeaux=()):
        self.situations = _Collection(situations)
        self.initiatives = _Collection(initiatives)
        self.relations = _Collection(relations)
        self.jumeaux = _Collection(jumeaux)


class _Transaction:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _parametre(valeur):
    if valeur.__class__.__name__ == "Jsonb":
        return valeur.obj
    return valeur


class _CurseurObjets:
    def __init__(self, stock):
        self.stock = stock
        self.resultat = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, requete, parametres=None):
        p = parametres or ()
        requete = " ".join(requete.split())
        if requete.startswith("SELECT * FROM objet_entreprise WHERE tenant_id = %s AND id = %s"):
            existant = self.stock.get((p[0], p[1]))
            self.resultat = dict(existant) if existant is not None else None
        elif requete.startswith("INSERT INTO objet_entreprise"):
            ligne = {
                "id": p[0],
                "tenant_id": p[1],
                "famille": p[2],
                "type": p[3],
                "mode": p[4],
                "titre": p[5],
                "donnees": _parametre(p[6]),
                "version": p[7],
                "observe_le": p[8] or NOW,
                "valide_depuis": p[9] or NOW,
                "valide_jusqua": p[10],
                "cree_le": p[12] or NOW,
                "maj_le": NOW,
            }
            self.stock[(ligne["tenant_id"], ligne["id"])] = ligne
            self.resultat = dict(ligne)
        elif requete.startswith("UPDATE objet_entreprise SET"):
            ligne = self.stock[(p[9], p[10])]
            ligne.update({
                "famille": p[0],
                "type": p[1],
                "mode": p[2],
                "titre": p[3],
                "donnees": _parametre(p[4]),
                "version": p[5],
                "observe_le": p[6] or ligne["observe_le"],
                "valide_depuis": p[7] or ligne["valide_depuis"],
                "valide_jusqua": p[8],
                "maj_le": NOW,
            })
            self.resultat = dict(ligne)
        else:
            raise AssertionError(f"requête inattendue : {requete}")
        return self

    def fetchone(self):
        return self.resultat


class _Connexion:
    """Connexion Postgres factice : suffit au contrat de `entreprise_depot.enregistrer_objet`."""

    def __init__(self):
        self.stock = {}

    def transaction(self):
        return _Transaction()

    def cursor(self, row_factory=None):
        return _CurseurObjets(self.stock)


def _inspecter(db, dry_run=True, conn=None, store=None):
    return asyncio.run(inspecter(db, TENANT, dry_run=dry_run, conn=conn, store=store))


def test_mapping_situation_normalise_statuts_dates_et_liens_sans_secret():
    objet = objet_depuis_situation(SITUATION, TENANT)

    assert (objet["id"], objet["famille"], objet["type"], objet["mode"]) == (
        "sit-cartes", "emergence", "SITUATION", "DECLARED")
    assert objet["titre"] == SITUATION["titre"]
    assert objet["observe_le"] == "2026-10-30T09:00:00+00:00"
    assert objet["valide_depuis"] == "2026-10-30T09:00:00+00:00"
    assert objet["version"] == 1
    assert objet["donnees"]["statut"] == "ACTIVE"
    assert objet["donnees"]["priorite"] == "HAUTE"
    assert objet["donnees"]["twin_ids"] == ["paiements", "comptes"]
    assert objet["donnees"]["resume"] == SITUATION["resume"]

    texte = json.dumps(objet, ensure_ascii=False)
    assert SECRET not in texte and "token" not in objet["donnees"]["indicateurs"]


def test_mapping_initiative_conserve_les_liens_declares_et_rien_d_autre():
    objet = objet_depuis_initiative(INITIATIVE, TENANT)

    assert (objet["id"], objet["famille"], objet["type"], objet["mode"]) == (
        "init-contrat", "decision", "INITIATIVE", "DECLARED")
    assert objet["observe_le"] == "2026-08-26T08:41:00+00:00"
    assert objet["donnees"]["statut"] == "EN_ATTENTE"
    assert objet["donnees"]["urgence"] == "HAUTE"
    assert objet["donnees"]["twin_ids"] == ["paiements", "comptes"]
    assert objet["donnees"]["travail_id"] == "case-olympiade"
    assert objet["donnees"]["jumeau_cible"] == "conformite"
    assert "decision_id" not in objet["donnees"]
    assert SECRET not in json.dumps(objet, ensure_ascii=False)


def test_mapping_refuse_un_autre_tenant_et_un_document_sans_id():
    with pytest.raises(PermissionError):
        objet_depuis_situation({**SITUATION, "tenant_id": "autre"}, TENANT)
    with pytest.raises(PermissionError):
        objet_depuis_initiative({**INITIATIVE, "tenant_id": "autre"}, TENANT)
    with pytest.raises(DocumentInvalide):
        objet_depuis_situation({"titre": "sans identifiant"}, TENANT)
    with pytest.raises(PermissionError):
        twin_depuis_jumeau({**JUMEAU_A, "tenant_id": "autre"}, TENANT)


def test_twin_depuis_jumeau_passe_par_graphe_sync_sans_copier_les_secrets():
    noeud = twin_depuis_jumeau({**JUMEAU_A, "claims": [{"token": SECRET}]}, TENANT)
    meme_noeud = twin_depuis_jumeau(TENANT, JUMEAU_A)

    assert (noeud.id, noeud.tenant_id, noeud.type, noeud.label) == (
        "paiements", TENANT, "APPLICATION", "Paiements")
    assert noeud.proprietes["mission"] == "Traiter les paiements"
    assert SECRET not in json.dumps(noeud.proprietes)
    assert (meme_noeud.id, meme_noeud.label) == ("paiements", "Paiements")


def test_dry_run_compte_sans_ecrire_dans_postgres_ni_dans_le_graphe():
    db = _Db(situations=[SITUATION], initiatives=[INITIATIVE], jumeaux=[JUMEAU_A, JUMEAU_B],
             relations=[RELATION])
    conn, store = _Connexion(), GrapheMemoire()

    rapport = _inspecter(db, dry_run=True, conn=conn, store=store)

    assert rapport == {
        "tenant": TENANT,
        "dry_run": True,
        "situations": 1,
        "initiatives": 1,
        "relations": 1,
        "ignores": [],
        "erreurs": [],
    }
    assert conn.stock == {}
    assert store.noeuds == {} and store.aretes == {}


def test_mode_reel_ecrit_les_objets_et_les_relations():
    db = _Db(situations=[SITUATION], initiatives=[INITIATIVE], jumeaux=[JUMEAU_A, JUMEAU_B],
             relations=[RELATION])
    conn, store = _Connexion(), GrapheMemoire()

    rapport = _inspecter(db, dry_run=False, conn=conn, store=store)

    assert (rapport["situations"], rapport["initiatives"], rapport["relations"]) == (1, 1, 1)
    assert rapport["ignores"] == [] and rapport["erreurs"] == []
    assert set(conn.stock) == {(TENANT, "sit-cartes"), (TENANT, "init-contrat")}
    situation = conn.stock[(TENANT, "sit-cartes")]
    assert (situation["famille"], situation["type"], situation["mode"]) == (
        "emergence", "SITUATION", "DECLARED")
    assert situation["donnees"]["twin_ids"] == ["paiements", "comptes"]

    assert set(store.noeuds) == {(TENANT, "paiements"), (TENANT, "comptes")}
    assert set(store.aretes) == {(TENANT, "r-paiements-comptes")}
    arete = store.aretes[(TENANT, "r-paiements-comptes")]
    assert (arete.source, arete.target, arete.confiance) == ("paiements", "comptes", 0.82)
    assert arete.preuve_ids == ("p1",)


def test_relation_orpheline_est_comptee_sans_casser_les_valides():
    orpheline = {**RELATION, "id": "r-orpheline", "cible": "absent"}
    db = _Db(jumeaux=[JUMEAU_A, JUMEAU_B], relations=[RELATION, orpheline])
    conn, store = _Connexion(), GrapheMemoire()

    rapport = _inspecter(db, dry_run=False, conn=conn, store=store)

    assert rapport["relations"] == 1
    assert rapport["erreurs"] == []
    assert [ignore["id"] for ignore in rapport["ignores"]] == ["r-orpheline"]
    assert rapport["ignores"][0]["absents"] == ["absent"]
    assert set(store.aretes) == {(TENANT, "r-paiements-comptes")}


def test_deux_passages_sont_idempotents_et_ne_font_pas_monter_la_version():
    db = _Db(situations=[SITUATION], initiatives=[INITIATIVE], jumeaux=[JUMEAU_A, JUMEAU_B],
             relations=[RELATION])
    conn, store = _Connexion(), GrapheMemoire()

    premier = _inspecter(db, dry_run=False, conn=conn, store=store)
    second = _inspecter(db, dry_run=False, conn=conn, store=store)

    assert premier == second
    assert len(conn.stock) == 2
    assert {ligne["version"] for ligne in conn.stock.values()} == {1}
    assert len(store.noeuds) == 2 and len(store.aretes) == 1


def test_isolation_tenant_ignore_les_documents_etrangers():
    autre = "assurance"
    db = _Db(
        situations=[{**SITUATION, "tenant_id": autre}],
        initiatives=[{**INITIATIVE, "tenant_id": autre}],
        jumeaux=[{**JUMEAU_A, "tenant_id": autre}],
        relations=[{**RELATION, "tenant_id": autre}],
    )
    conn, store = _Connexion(), GrapheMemoire()

    rapport = _inspecter(db, dry_run=False, conn=conn, store=store)

    assert (rapport["situations"], rapport["initiatives"], rapport["relations"]) == (0, 0, 0)
    assert {ignore["type"] for ignore in rapport["ignores"]} == {
        "situation", "initiative", "jumeau", "relation"}
    assert conn.stock == {} and store.noeuds == {} and store.aretes == {}
    assert all(ignore["raison"] == "autre tenant" for ignore in rapport["ignores"])


def test_document_invalide_est_ignore_sans_fuite_de_secret():
    invalide = {"id": "sit-invalide", "titre": {"token": SECRET}, "password": SECRET}
    sans_id = {"titre": "sans identifiant", "token": SECRET}
    db = _Db(situations=[invalide, sans_id, SITUATION])
    conn, store = _Connexion(), GrapheMemoire()

    rapport = _inspecter(db, dry_run=False, conn=conn, store=store)

    assert rapport["situations"] == 1
    assert len(rapport["ignores"]) == 2
    assert set(conn.stock) == {(TENANT, "sit-cartes")}
    assert SECRET not in json.dumps(rapport, ensure_ascii=False)
    assert SECRET not in json.dumps(list(conn.stock.values()), ensure_ascii=False, default=str)
    assert rapport["erreurs"] == []


def test_relations_vers_graphe_ne_recopie_pas_les_citations_de_preuve():
    aretes, erreurs = migration_canonique.relations_vers_graphe([RELATION], TENANT)
    memes_aretes, memes_erreurs = migration_canonique.relations_vers_graphe(TENANT, [RELATION])

    assert erreurs == [] and len(aretes) == 1
    assert memes_erreurs == [] and memes_aretes == aretes
    assert aretes[0].preuve_ids == ("p1",)
    assert SECRET not in json.dumps(list(aretes[0].preuve_ids))
