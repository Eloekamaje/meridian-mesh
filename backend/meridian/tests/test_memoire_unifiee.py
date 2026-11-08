"""Façade mémoire D5 : 4 couches peuplées, bornes, manques, fail-soft, déterminisme."""
import pytest
from psycopg.types.json import Jsonb

from meridian.adapters.outbound.postgres import depot
from meridian.adapters.outbound.postgres import entreprise_depot
from meridian.adapters.outbound.postgres import evenements_requete
from meridian.adapters.outbound.postgres import journal_episodes
from meridian.adapters.outbound.postgres import memoire_unifiee
from meridian.tests.conftest import besoin_pg

TENANT = "banque"
QUESTION = "Quel délai pour les paiements par carte ?"
EPISODE = "ep-paiements"


def _jumeau(conn, jid="app-paiements", tenant=TENANT):
    conn.execute(
        "INSERT INTO jumeau (id, tenant_id, nom, equipe) VALUES (%s, %s, %s, 'e')",
        (jid, tenant, jid))


def _claim_accepte(conn, jid, source_id, objet, *, tenant=TENANT):
    """Claim ACCEPTED par la voie normale : PROPOSED + SUPPORT + revue humaine."""
    cid = conn.execute(
        "INSERT INTO claim (tenant_id, jumeau_id, sujet, predicat, objet, type, "
        "confiance) VALUES (%s, %s, 'paiements', 'REALISE_CAPACITE', %s, "
        "'CAPABILITY', 0.9) RETURNING id",
        (tenant, jid, objet)).fetchone()[0]
    pid = conn.execute(
        "INSERT INTO preuve (tenant_id, source_id, type, locator, chemin, sha, "
        "ligne_debut, ligne_fin, hash, activite) "
        "VALUES (%s, %s, 'DOC', %s, 'guide.md', 's1', 1, 1, 'h', %s) RETURNING id",
        (tenant, source_id, f"guide.md#{objet}",
         Jsonb({"extracteur": "test"}))).fetchone()[0]
    conn.execute(
        "INSERT INTO claim_preuve (claim_id, preuve_id, role) VALUES (%s, %s, 'SUPPORT')",
        (cid, pid))
    depot.reviser(conn, cid, "alice", "ACCEPTED", "revue faite")
    return cid


def _objet(conn, identifiant, famille, type_, donnees, titre="", tenant=TENANT):
    return entreprise_depot.enregistrer_objet(conn, tenant, {
        "id": identifiant, "famille": famille, "type": type_, "mode": "INFERRED",
        "titre": titre, "donnees": donnees})


def _peupler_connaissance(conn, tenant=TENANT):
    _jumeau(conn, tenant=tenant)
    source_id = conn.execute(
        "INSERT INTO source (tenant_id, jumeau_id, type, nom, emplacement) "
        "VALUES (%s, 'app-paiements', 'DOCUMENTATION', 'guide', 'doc://guide') "
        "RETURNING id", (tenant,)).fetchone()[0]
    _claim_accepte(
        conn, "app-paiements", source_id,
        "le délai de traitement des paiements", tenant=tenant)
    _claim_accepte(
        conn, "app-paiements", source_id, "le plafond des paiements", tenant=tenant)
    _objet(conn, "belief-delai", "connaissance", "BELIEF",
           {"enonce": "Le délai des paiements par carte est tenu",
            "source": "HUMAIN", "statut": "ACTIF"}, tenant=tenant)


def _peupler_episodes(conn, tenant=TENANT):
    for objet_type, objet_id in (("SITUATION", "sit-delai"), ("INVESTIGATION", "inv-delai")):
        journal_episodes.consigner(conn, tenant, {
            "episode_id": EPISODE, "objet_type": objet_type,
            "objet_id": objet_id, "action": "cree"})
    evenements_requete.consigner(conn, tenant, evenements_requete.construire(
        {"comportement": "reponse", "reponse": "Les paiements passent par quatre jours."},
        question=QUESTION, episode_id=EPISODE))
    evenements_requete.consigner(conn, tenant, evenements_requete.construire(
        {"comportement": "reponse", "reponse": "autre sujet"},
        question="Question sans lien", episode_id="ep-autre"))


def _peupler_recettes(conn, tenant=TENANT):
    _objet(conn, "lea-delai", "resultat_apprentissage", "LEARNING",
           {"enonce": "Automatiser réduit le délai des paiements"},
           titre="Automatiser réduit le délai des paiements", tenant=tenant)
    _objet(conn, "need-1", "emergence", "NEED",
           {"signature": "contournement", "statut": "CORROBORE",
            "porteur": "equipe-cartes"}, tenant=tenant)
    _objet(conn, "need-2", "emergence", "NEED",
           {"signature": "contournement", "statut": "REFUTE"}, tenant=tenant)


def _peupler_documents(conn, tenant=TENANT):
    conn.execute(
        "INSERT INTO document_chunk (tenant_id, source_id, twin_id, document_ref, "
        "version, ordinal, section, titre, texte, texte_hash, locator) "
        "VALUES (%s, NULL, NULL, 'doc-paiements', 'v1', 0, 'Traitement', "
        "'Guide des paiements', "
        "'Le traitement des paiements par carte prend quatre jours.', 'h1', "
        "'doc://doc-paiements#L1-L1')",
        (tenant,))


def _peupler_tout(conn, tenant=TENANT):
    _peupler_connaissance(conn, tenant)
    _peupler_episodes(conn, tenant)
    _peupler_recettes(conn, tenant)
    _peupler_documents(conn, tenant)


@besoin_pg
def test_quatre_couches_peuplees_repondent_bornees(conn):
    _peupler_tout(conn)

    resultat = memoire_unifiee.memoire(conn, TENANT, QUESTION)

    assert set(("connaissance", "episodes", "recettes", "documents",
                "totaux", "manques", "erreurs")) <= set(resultat)
    assert resultat["erreurs"] == {}
    assert resultat["manques"] == []
    for nom in memoire_unifiee.COUCHES:
        assert 0 < len(resultat[nom]) <= 5
        assert resultat["totaux"][nom] == len(resultat[nom])
    # connaissance : claims ACCEPTED + belief, bornés et pertinents
    genres = {e["genre"] for e in resultat["connaissance"]}
    assert genres == {"claim", "belief"}
    assert all(e["couverture"] > 0 for e in resultat["connaissance"])
    # épisodes : la requête de même empreinte est liée, l'épisode remonte sa trace
    assert resultat["episodes"][0].get("lie_question") or \
        resultat["episodes"][0].get("meme_question")
    requete = next(e for e in resultat["episodes"] if e["genre"] == "requete"
                   and e["meme_question"])
    assert requete["meme_question"] is True
    episode = next(e for e in resultat["episodes"] if e["genre"] == "episode")
    assert episode["lie_question"] is True
    assert {t["objet"] for t in episode["trace"]} == {
        "SITUATION:sit-delai", "INVESTIGATION:inv-delai"}
    # recettes : learning canonique + signature mesurée
    assert {e["genre"] for e in resultat["recettes"]} == {"learning", "signature"}
    signature = next(e for e in resultat["recettes"] if e["genre"] == "signature")
    assert signature["signature"] == "contournement"
    assert signature["juges"] == 2 and signature["confirmes"] == 1
    assert signature["taux_confirme"] == 0.5
    # documents : le chunk pertinent, extrait borné
    assert resultat["documents"][0]["document_ref"] == "doc-paiements"
    assert resultat["documents"][0]["couverture"] > 0
    assert len(resultat["documents"][0]["extrait"]) <= 240


@besoin_pg
def test_couche_vide_est_citee_dans_manques(conn):
    _peupler_connaissance(conn)
    _peupler_documents(conn)

    resultat = memoire_unifiee.memoire(conn, TENANT, QUESTION)

    assert resultat["connaissance"] and resultat["documents"]
    assert resultat["episodes"] == [] and resultat["recettes"] == []
    assert sorted(resultat["manques"]) == ["episodes", "recettes"]
    assert resultat["erreurs"] == {}


@besoin_pg
def test_couche_en_panne_nempeche_pas_les_autres(conn):
    _peupler_tout(conn)
    # la panne est réelle : la colonne lue par journal_episodes.episodes disparaît
    conn.execute("ALTER TABLE evenement_episode DROP COLUMN episode_id")

    resultat = memoire_unifiee.memoire(conn, TENANT, QUESTION)

    assert "episodes" in resultat["erreurs"]
    assert resultat["episodes"] == []
    assert "episodes" in resultat["manques"]
    assert resultat["connaissance"] and resultat["recettes"] and resultat["documents"]
    # la transaction appelante n'est pas contaminée par le savepoint de la couche
    assert conn.execute("SELECT 1").fetchone() == (1,)


class _ConnCassee:
    """Connexion injectée en panne : toute couche échoue, la façade répond."""

    def transaction(self):
        raise RuntimeError("connexion coupée")

    def cursor(self, *args, **kwargs):
        raise RuntimeError("connexion coupée")

    def execute(self, *args, **kwargs):
        raise RuntimeError("connexion coupée")


@besoin_pg
def test_connexion_cassee_rend_manques_et_erreurs(conn):
    _peupler_tout(conn)

    resultat = memoire_unifiee.memoire(_ConnCassee(), TENANT, QUESTION)

    assert sorted(resultat["manques"]) == sorted(memoire_unifiee.COUCHES)
    assert set(resultat["erreurs"]) == set(memoire_unifiee.COUCHES)
    assert all(resultat[nom] == [] for nom in memoire_unifiee.COUCHES)
    assert resultat["totaux"]["total"] == 0


@besoin_pg
def test_limite_par_couche_et_ordre_deterministe(conn):
    _jumeau(conn)
    source_id = conn.execute(
        "INSERT INTO source (tenant_id, jumeau_id, type, nom, emplacement) "
        "VALUES (%s, 'app-paiements', 'DOCUMENTATION', 'guide', 'doc://guide') "
        "RETURNING id", (TENANT,)).fetchone()[0]
    for index in range(8):
        _claim_accepte(
            conn, "app-paiements", source_id,
            f"le délai des paiements mesure {index}")
        conn.execute(
            "INSERT INTO document_chunk (tenant_id, document_ref, version, ordinal, "
            "titre, texte, locator) VALUES (%s, %s, 'v1', %s, %s, %s, %s)",
            (TENANT, f"doc-{index}", index, "Guide",
             f"Les paiements par carte, note {index}.", f"doc://{index}#L1"))
        _objet(conn, f"lea-{index}", "resultat_apprentissage", "LEARNING",
               {"enonce": f"Le délai des paiements, leçon {index}"})
    _peupler_episodes(conn)

    premier = memoire_unifiee.memoire(conn, TENANT, QUESTION, limite_par_couche=3)
    second = memoire_unifiee.memoire(conn, TENANT, QUESTION, limite_par_couche=3)

    assert premier == second
    for nom in memoire_unifiee.COUCHES:
        assert len(premier[nom]) <= 3
    assert len(premier["documents"]) == 3
    assert len(premier["connaissance"]) == 3
    assert premier["totaux"]["total"] == sum(
        len(premier[nom]) for nom in memoire_unifiee.COUCHES)


@besoin_pg
def test_selection_couches_ninterroge_que_les_demandees(conn):
    _peupler_tout(conn)

    resultat = memoire_unifiee.memoire(conn, TENANT, QUESTION, couches=["documents"])

    assert resultat["documents"]
    for nom in ("connaissance", "episodes", "recettes"):
        assert resultat[nom] == []
    assert resultat["manques"] == []


@besoin_pg
def test_parametres_invalides_sont_refuses(conn):
    with pytest.raises(memoire_unifiee.MemoireUnifieeInvalide):
        memoire_unifiee.memoire(conn, "  ", QUESTION)
    with pytest.raises(memoire_unifiee.MemoireUnifieeInvalide):
        memoire_unifiee.memoire(conn, TENANT, QUESTION, couches=["inconnue"])
    with pytest.raises(memoire_unifiee.MemoireUnifieeInvalide):
        memoire_unifiee.memoire(conn, TENANT, QUESTION, limite_par_couche="abc")
    # la limite est bornée, jamais prise au mot
    _peupler_documents(conn)
    resultat = memoire_unifiee.memoire(conn, TENANT, QUESTION, limite_par_couche=9999)
    assert len(resultat["documents"]) <= 50


@besoin_pg
def test_question_vide_rest_bornee_et_deterministe(conn):
    _peupler_tout(conn)

    resultat = memoire_unifiee.memoire(conn, TENANT, "", limite_par_couche=4)

    assert resultat["documents"]  # récence bornée sans filtre lexical
    assert all(e["meme_question"] is False
               for e in resultat["episodes"] if e["genre"] == "requete")
    assert resultat == memoire_unifiee.memoire(conn, TENANT, "", limite_par_couche=4)
