"""Mémoire de session : résumé borné, idempotence, import de case, purge et tenant."""
from datetime import datetime, timedelta, timezone
import json

import pytest

from meridian.adapters.outbound.postgres import memoire_durable
from meridian.adapters.outbound.postgres.session_memoire import SessionMemoireInvalide, charger_session, importer_case, lister_sessions, memoriser_session, purger_sessions, resumer_conversation
from meridian.tests.conftest import besoin_pg

TENANT = "banque"
AUTRE_TENANT = "assurance"


def test_resume_garde_les_derniers_messages_utiles():
    messages = [
        {"role": "system", "texte": "consigne système"},
        {"role": "user", "content": [{"type": "text", "text": "Première question"}]},
        {"role": "assistant", "texte": "Première réponse"},
        {"role": "evenement", "texte": "un événement"},
        {"role": "utilisateur", "texte": "Dernière question"},
        {"role": "flore", "content": "Dernière réponse"},
    ]

    resume = resumer_conversation(messages)

    assert "Utilisateur : Dernière question" in resume
    assert "Assistant : Dernière réponse" in resume
    assert "consigne système" not in resume
    assert "un événement" not in resume
    assert resume.index("Dernière question") < resume.index("Dernière réponse")


def test_resume_borne_et_redige_les_secrets():
    messages = [
        {"role": "user", "texte": "Mon mot de passe: hunter2secret"},
        {"role": "assistant", "texte": "api_key=abcdef123456 " + "x" * 5000},
        {"role": "assistant", "texte": "Bearer abcdefghijklmnop et https://user:pass@example.test/x"},
    ]

    resume = resumer_conversation(messages)

    assert len(resume) <= 1200
    assert "hunter2secret" not in resume
    assert "abcdef123456" not in resume
    assert "abcdefghijklmnop" not in resume
    assert "user:pass" not in resume
    assert "***" in resume

    borne = resumer_conversation([{"role": "assistant", "texte": "y" * 5000}], max_chars=80)
    assert len(borne) <= 80
    assert borne.startswith("Assistant : y")


def test_resume_ignore_les_messages_sans_role_connu_et_valide_la_borne():
    assert resumer_conversation(None) == ""
    assert resumer_conversation("pas une conversation") == ""
    assert resumer_conversation([{"role": "system", "texte": "à ignorer"}]) == ""
    assert resumer_conversation([{"role": "user", "texte": "   "}]) == ""

    with pytest.raises(SessionMemoireInvalide):
        resumer_conversation([], max_chars=0)
    with pytest.raises(SessionMemoireInvalide):
        resumer_conversation([], max_chars=True)


@besoin_pg
def test_memoriser_session_portee_provenance_et_resume(conn):
    avant = datetime.now(timezone.utc)
    reponse = "La livraison peut être avancée. " + ("détail " * 400)

    ligne = memoriser_session(
        conn, TENANT, "sess-1", "Comment livrer plus vite ?", reponse,
        acteur="alice", donnees={"canal": "web"},
    )
    apres = datetime.now(timezone.utc)

    assert ligne["scope"] == "session"
    assert ligne["scope_id"] == "sess-1"
    assert ligne["classe"] == "session"
    assert ligne["provenance"] == "session:sess-1"
    assert ligne["contenu"].startswith("Utilisateur : Comment livrer plus vite ?")
    assert "Assistant : La livraison peut être avancée." in ligne["contenu"]
    assert len(ligne["contenu"]) <= 1200
    assert len(ligne["contenu"]) < len(reponse)
    assert ligne["donnees"]["acteur"] == "alice"
    assert ligne["donnees"]["session_id"] == "sess-1"
    assert ligne["donnees"]["canal"] == "web"
    assert ligne["donnees"]["question"] == "Comment livrer plus vite ?"

    expiration = datetime.fromisoformat(ligne["expire_le"])
    assert avant + timedelta(days=7) <= expiration <= apres + timedelta(days=7)
    assert memoire_durable.lire(conn, TENANT, ligne["id"]) == ligne


@besoin_pg
def test_memoriser_session_est_idempotent_et_deterministe(conn):
    premiere = memoriser_session(conn, TENANT, "sess-1", "Question ?", "Réponse A", acteur="alice")
    seconde = memoriser_session(conn, TENANT, "sess-1", "  Question ?  ", "Réponse B", acteur="bob")

    assert seconde["id"] == premiere["id"]
    assert seconde["contenu"] == premiere["contenu"]
    assert seconde["donnees"]["acteur"] == "alice"
    assert len(charger_session(conn, TENANT, "sess-1")) == 1

    autre_session = memoriser_session(conn, TENANT, "sess-2", "Question ?", "Réponse A", acteur="alice")
    assert autre_session["id"] != premiere["id"]


@besoin_pg
def test_memoriser_session_ne_copie_pas_la_reponse_et_redige_les_secrets(conn):
    question = "Mon mot de passe: hunter2secret, que faire ?"
    reponse = "api_key=abcdef123456 termine. " + ("suite " * 5000) + "FIN-UNIQUE"

    ligne = memoriser_session(conn, TENANT, "sess-1", question, reponse, acteur="alice")

    texte = json.dumps(ligne, ensure_ascii=False)
    assert "hunter2secret" not in texte
    assert "abcdef123456" not in texte
    assert len(ligne["contenu"]) <= 1200
    assert len(ligne["contenu"]) < len(reponse)
    assert "FIN-UNIQUE" not in ligne["contenu"]
    assert "question" in ligne["donnees"]


@besoin_pg
def test_memoriser_session_borne_au_tenant_et_respecte_expire_jours(conn):
    avant = datetime.now(timezone.utc)
    local = memoriser_session(conn, TENANT, "sess-1", "Question ?", "Réponse", acteur="alice",
                              expire_jours=2)
    apres = datetime.now(timezone.utc)
    autre = memoriser_session(conn, AUTRE_TENANT, "sess-1", "Question ?", "Réponse", acteur="bob")

    assert local["id"] != autre["id"]
    assert memoire_durable.lire(conn, AUTRE_TENANT, local["id"]) is None
    assert memoire_durable.lire(conn, TENANT, autre["id"]) is None
    assert [ligne["id"] for ligne in charger_session(conn, TENANT, "sess-1")] == [local["id"]]
    assert [ligne["id"] for ligne in charger_session(conn, AUTRE_TENANT, "sess-1")] == [autre["id"]]

    expiration = datetime.fromisoformat(local["expire_le"])
    assert avant + timedelta(days=2) <= expiration <= apres + timedelta(days=2)

    with pytest.raises(SessionMemoireInvalide):
        memoriser_session(conn, "Banque !", "sess-1", "Question ?", "Réponse", acteur="alice")
    with pytest.raises(SessionMemoireInvalide):
        charger_session(conn, "Banque !", "sess-1")


@besoin_pg
@pytest.mark.parametrize("jours", [0, -1, 3651, True])
def test_memoriser_session_refuse_une_expiration_invalide(conn, jours):
    with pytest.raises(SessionMemoireInvalide):
        memoriser_session(conn, TENANT, "sess-1", "Question ?", "Réponse", acteur="alice",
                          expire_jours=jours)


@besoin_pg
def test_memoriser_session_refuse_les_secrets_dans_donnees(conn):
    with pytest.raises(memoire_durable.MemoireDurableInvalide):
        memoriser_session(
            conn, TENANT, "sess-1", "Question ?", "Réponse", acteur="alice",
            donnees={"token": "abcdef123456"},
        )


@besoin_pg
def test_charger_session_et_lister_sessions_groupent_par_scope(conn):
    premier = memoriser_session(conn, TENANT, "sess-1", "Q1", "R1", acteur="alice")
    second = memoriser_session(conn, TENANT, "sess-1", "Q2", "R2", acteur="alice")
    troisieme = memoriser_session(conn, TENANT, "sess-2", "Q3", "R3", acteur="alice")
    memoriser_session(conn, AUTRE_TENANT, "sess-3", "Q4", "R4", acteur="bob")

    chargees = charger_session(conn, TENANT, "sess-1")
    assert {ligne["id"] for ligne in chargees} == {premier["id"], second["id"]}
    assert all(ligne["scope"] == "session" for ligne in chargees)
    assert all(ligne["scope_id"] == "sess-1" for ligne in chargees)

    bornees = charger_session(conn, TENANT, "sess-1", limite=1)
    assert len(bornees) == 1
    assert bornees[0]["scope_id"] == "sess-1"

    sessions = lister_sessions(conn, TENANT)
    par_id = {session["session_id"]: session for session in sessions}
    assert set(par_id) == {"sess-1", "sess-2"}
    assert par_id["sess-1"]["nombre"] == 2
    assert par_id["sess-2"]["nombre"] == 1
    assert par_id["sess-1"]["scope_id"] == "sess-1"
    assert par_id["sess-1"]["premier"] is not None
    assert par_id["sess-1"]["dernier"] is not None
    assert troisieme["scope_id"] == "sess-2"

    une_seule = lister_sessions(conn, TENANT, limite=1)
    assert len(une_seule) == 1
    assert une_seule[0]["session_id"] in {"sess-1", "sess-2"}


@besoin_pg
def test_purger_sessions_supprime_les_echues_de_session_seulement(conn):
    session = memoriser_session(conn, TENANT, "sess-1", "Q", "R", acteur="alice")
    autre = memoriser_session(conn, AUTRE_TENANT, "sess-1", "Q", "R", acteur="bob")
    preference = memoire_durable.creer(
        conn, TENANT, id="user-1", scope="user", scope_id="u-1", classe="preference",
        contenu="préférence", provenance="test", consentement=True,
    )
    passe = datetime.now(timezone.utc) - timedelta(days=1)
    for tenant, identifiant in (
        (TENANT, session["id"]), (AUTRE_TENANT, autre["id"]), (TENANT, preference["id"]),
    ):
        conn.execute(
            "UPDATE memoire_durable SET expire_le = %s WHERE tenant_id = %s AND id = %s",
            (passe, tenant, identifiant),
        )

    assert purger_sessions(conn, TENANT) == 1
    assert memoire_durable.lire(conn, TENANT, session["id"]) is None
    assert memoire_durable.lire(conn, TENANT, preference["id"]) is not None
    assert memoire_durable.lire(conn, AUTRE_TENANT, autre["id"]) is not None

    future = memoriser_session(conn, TENANT, "sess-2", "Q2", "R2", acteur="alice")
    assert purger_sessions(conn, TENANT) == 0
    assert memoire_durable.lire(conn, TENANT, future["id"]) is not None

    dans_huit_jours = datetime.now(timezone.utc) + timedelta(days=8)
    assert purger_sessions(conn, TENANT, avant=dans_huit_jours) == 1
    assert memoire_durable.lire(conn, TENANT, future["id"]) is None

    with pytest.raises(SessionMemoireInvalide):
        purger_sessions(conn, TENANT, avant="pas une date")


@besoin_pg
def test_importer_case_resume_sans_pieces_ni_conversation_complete(conn):
    case = {
        "id": "case-42",
        "_id": "ignoré",
        "titre": "Carte bloquée",
        "resume": "Le client demande une carte.",
        "pieces": [{"texte": "PIECE-SECRETE"}],
        "tokens": {"access_token": "TOKEN-SECRET"},
        "conversation": [
            *[
                {"role": "utilisateur", "texte": f"ANCIEN-{rang:02d} à ne pas copier"}
                for rang in range(20)
            ],
            {"role": "evenement", "texte": "bruit"},
            {"role": "flore", "texte": "Dernière réponse " + "x" * 5000 + "FIN-UNIQUE"},
        ],
    }

    ligne = importer_case(conn, TENANT, case, acteur="alice")

    assert ligne["scope"] == "session"
    assert ligne["scope_id"] == "case:case-42"
    assert ligne["provenance"] == "session:case:case-42"
    assert ligne["classe"] == "session"
    assert "Carte bloquée" in ligne["contenu"]
    assert "Le client demande une carte." in ligne["contenu"]
    assert "Dernière réponse" in ligne["contenu"]
    assert len(ligne["contenu"]) <= 1200
    assert "ANCIEN-00" not in ligne["contenu"]
    assert "x" * 5000 not in ligne["contenu"]
    assert "FIN-UNIQUE" not in ligne["contenu"]

    donnees = json.dumps(ligne["donnees"], ensure_ascii=False)
    assert "PIECE-SECRETE" not in donnees
    assert "TOKEN-SECRET" not in donnees
    assert "ANCIEN-00" not in donnees
    assert ligne["donnees"]["case_id"] == "case-42"
    assert ligne["donnees"]["acteur"] == "alice"
    assert ligne["donnees"]["session_id"] == "case:case-42"

    encore = importer_case(conn, TENANT, dict(case, titre="Autre titre"), acteur="bob")
    assert encore["id"] == ligne["id"]
    assert encore["contenu"] == ligne["contenu"]
    assert len(charger_session(conn, TENANT, "case:case-42")) == 1

    ailleurs = importer_case(conn, AUTRE_TENANT, case, acteur="bob")
    assert ailleurs["id"] != ligne["id"]
    assert memoire_durable.lire(conn, AUTRE_TENANT, ligne["id"]) is None


@besoin_pg
def test_importer_case_redige_les_secrets(conn):
    case = {
        "id": "case-secret",
        "titre": "mot de passe: hunter2secret",
        "resume": "api_key=abcdef123456",
        "conversation": [{"role": "flore", "texte": "Bearer abcdefghijklmnop"}],
    }

    ligne = importer_case(conn, TENANT, case, acteur="alice")

    texte = json.dumps(ligne, ensure_ascii=False)
    assert "hunter2secret" not in texte
    assert "abcdef123456" not in texte
    assert "abcdefghijklmnop" not in texte


@besoin_pg
def test_importer_case_refuse_un_case_invalide(conn):
    with pytest.raises(SessionMemoireInvalide):
        importer_case(conn, TENANT, "pas un mapping", acteur="alice")
    with pytest.raises(SessionMemoireInvalide):
        importer_case(conn, TENANT, {"titre": "Sans id"}, acteur="alice")
    with pytest.raises(SessionMemoireInvalide):
        importer_case(conn, TENANT, {"id": "vide", "conversation": []}, acteur="alice")
