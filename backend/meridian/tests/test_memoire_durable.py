"""Mémoire durable : contrat, portée tenant, consentement, rétention et export."""
from datetime import datetime, timedelta, timezone
import json

import pytest
from psycopg.types.json import Jsonb

from meridian.adapters.outbound.postgres import memoire_durable
from meridian.tests.conftest import besoin_pg

TENANT = "banque"
AUTRE_TENANT = "assurance"

SCHEMA_MEMOIRE = """
CREATE TABLE IF NOT EXISTS memoire_durable (
    id          text NOT NULL,
    tenant_id   text NOT NULL,
    scope       text NOT NULL,
    scope_id    text NOT NULL,
    classe      text NOT NULL,
    contenu     text NOT NULL,
    provenance  text NOT NULL,
    consentement boolean NOT NULL DEFAULT false,
    consenti_le timestamptz,
    expire_le   timestamptz,
    confiance   double precision NOT NULL DEFAULT 0.5,
    donnees     jsonb NOT NULL DEFAULT '{}'::jsonb,
    cree_le     timestamptz NOT NULL DEFAULT now(),
    maj_le      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id)
)
"""


@pytest.fixture
def conn_memoire(conn):
    """Crée la table dans le schéma jetable du test, sans toucher au schéma partagé."""
    conn.execute(SCHEMA_MEMOIRE)
    return conn


def _creer(conn, **changements):
    parametres = {
        "scope": "session",
        "scope_id": "sess-1",
        "classe": "contexte",
        "contenu": "Le client préfère les livraisons le matin",
        "provenance": "test",
        "confiance": 0.7,
    }
    parametres.update(changements)
    return memoire_durable.creer(conn, TENANT, **parametres)


@besoin_pg
def test_creer_et_lire_avec_valeurs_par_defaut(conn_memoire):
    avant = datetime.now(timezone.utc)
    ligne = _creer(conn_memoire, donnees={"canal": "web"})
    apres = datetime.now(timezone.utc)

    assert ligne["id"].startswith("memoire-")
    assert ligne["tenant_id"] == TENANT
    assert ligne["scope"] == "session"
    assert ligne["scope_id"] == "sess-1"
    assert ligne["classe"] == "contexte"
    assert ligne["consentement"] is False
    assert ligne["consenti_le"] is None
    assert ligne["confiance"] == 0.7
    assert ligne["donnees"] == {"canal": "web"}
    assert ligne["cree_le"] == ligne["maj_le"]

    expiration = datetime.fromisoformat(ligne["expire_le"])
    assert avant + timedelta(days=30) <= expiration <= apres + timedelta(days=30)
    assert memoire_durable.lire(conn_memoire, TENANT, ligne["id"]) == ligne
    assert memoire_durable.lire(conn_memoire, AUTRE_TENANT, ligne["id"]) is None


@besoin_pg
def test_id_fourni_est_stable_et_doublon_refuse_sans_ecrasement(conn_memoire):
    ligne = _creer(conn_memoire, id="memo-1", contenu="version initiale")
    assert ligne["id"] == "memo-1"

    with pytest.raises(memoire_durable.MemoireDurableInvalide, match="existe déjà"):
        _creer(conn_memoire, id="memo-1", contenu="version concurrente")

    assert memoire_durable.lire(conn_memoire, TENANT, "memo-1")["contenu"] == "version initiale"

    autre = memoire_durable.creer(
        conn_memoire, AUTRE_TENANT, id="memo-1", scope="session", scope_id="sess-1",
        classe="contexte", contenu="même identifiant, autre tenant", provenance="test",
    )
    assert autre["tenant_id"] == AUTRE_TENANT


@besoin_pg
def test_scope_user_exige_le_consentement(conn_memoire):
    with pytest.raises(memoire_durable.MemoireDurableInvalide, match="consentement"):
        _creer(conn_memoire, scope="user", scope_id="user-1")

    ligne = _creer(conn_memoire, scope="user", scope_id="user-1", consentement=True)
    assert ligne["consentement"] is True
    assert ligne["consenti_le"] is not None


@besoin_pg
def test_expiration_passee_refusee_et_future_conservee(conn_memoire):
    passe = datetime.now(timezone.utc) - timedelta(seconds=1)
    with pytest.raises(memoire_durable.MemoireDurableInvalide, match="expire_le"):
        _creer(conn_memoire, expire_le=passe)

    future = datetime.now(timezone.utc) + timedelta(days=3)
    ligne = _creer(conn_memoire, expire_le=future)
    assert datetime.fromisoformat(ligne["expire_le"]) == future


@besoin_pg
@pytest.mark.parametrize(
    "champ,valeur",
    [
        ("scope", "monde"),
        ("classe", "inconnue"),
        ("scope_id", "   "),
        ("contenu", ""),
        ("provenance", "  "),
    ],
)
def test_champs_invalides_refuses(conn_memoire, champ, valeur):
    with pytest.raises(memoire_durable.MemoireDurableInvalide):
        _creer(conn_memoire, **{champ: valeur})


@besoin_pg
def test_tenant_invalide_refuse(conn_memoire):
    with pytest.raises(memoire_durable.MemoireDurableInvalide):
        memoire_durable.creer(
            conn_memoire, "Banque !", scope="session", scope_id="s-1",
            classe="contexte", contenu="note", provenance="test",
        )


@besoin_pg
@pytest.mark.parametrize("valeur", [-0.01, 1.01, float("nan"), "beaucoup", True])
def test_confiance_hors_contrat_refusee(conn_memoire, valeur):
    with pytest.raises(memoire_durable.MemoireDurableInvalide, match="confiance"):
        _creer(conn_memoire, confiance=valeur)


@besoin_pg
@pytest.mark.parametrize(
    "changements",
    [
        {"contenu": "mot de passe: hunter2secret"},
        {"provenance": "api_key=abcdef123456"},
        {"scope_id": "bearer abcdefghijklmnop"},
        {"donnees": {"token": "abcdef123456"}},
        {"donnees": {"nested": {"client_secret": "s3cr3t"}}},
        {"donnees": {"url": "https://user:pass@example.test/rapport"}},
        {"contenu": "voir https://user:pass@example.test/rapport"},
    ],
)
def test_secrets_refuses_a_l_ecriture(conn_memoire, changements):
    with pytest.raises(memoire_durable.MemoireDurableInvalide, match="secret|sensible"):
        _creer(conn_memoire, **changements)


@besoin_pg
def test_lister_filtre_et_borne_sans_fuite_inter_tenant(conn_memoire):
    _creer(conn_memoire, id="user", scope="user", scope_id="u-1", classe="preference",
           consentement=True)
    _creer(conn_memoire, id="sess-1", scope="session", scope_id="s-1", classe="contexte")
    _creer(conn_memoire, id="sess-2", scope="session", scope_id="s-2", classe="contexte")
    memoire_durable.creer(
        conn_memoire, AUTRE_TENANT, id="ailleurs", scope="session", scope_id="s-1",
        classe="contexte", contenu="hors tenant", provenance="test",
    )

    assert {ligne["id"] for ligne in memoire_durable.lister(conn_memoire, TENANT)} == {
        "user", "sess-1", "sess-2"}
    assert {ligne["id"] for ligne in memoire_durable.lister(
        conn_memoire, TENANT, scope="session")} == {"sess-1", "sess-2"}
    assert [ligne["id"] for ligne in memoire_durable.lister(
        conn_memoire, TENANT, scope_id="s-1")] == ["sess-1"]
    assert [ligne["id"] for ligne in memoire_durable.lister(
        conn_memoire, TENANT, classe="preference")] == ["user"]
    assert len(memoire_durable.lister(conn_memoire, TENANT, limite=1)) == 1


@besoin_pg
def test_chercher_lexical_deterministe_et_borne_au_tenant(conn_memoire):
    _creer(conn_memoire, id="carte", contenu="Le délai de carte bancaire baisse", scope_id="s-1")
    _creer(conn_memoire, id="graphique", contenu="La carte graphique chauffe", scope_id="s-1")
    _creer(conn_memoire, id="livraison", contenu="Livraison le matin", scope_id="s-2")
    memoire_durable.creer(
        conn_memoire, AUTRE_TENANT, id="ailleurs", scope="session", scope_id="s-1",
        classe="contexte", contenu="Le délai de carte bancaire baisse", provenance="test",
    )

    assert [ligne["id"] for ligne in memoire_durable.chercher(
        conn_memoire, TENANT, "delai carte")] == ["carte"]
    assert {ligne["id"] for ligne in memoire_durable.chercher(
        conn_memoire, TENANT, "carte")} == {"carte", "graphique"}
    premier = [ligne["id"] for ligne in memoire_durable.chercher(conn_memoire, TENANT, "carte")]
    second = [ligne["id"] for ligne in memoire_durable.chercher(conn_memoire, TENANT, "carte")]
    assert premier == second

    assert memoire_durable.chercher(conn_memoire, TENANT, "") == []
    assert [ligne["id"] for ligne in memoire_durable.chercher(
        conn_memoire, TENANT, "livraison", scope_id="s-2")] == ["livraison"]
    assert memoire_durable.chercher(conn_memoire, TENANT, "livraison", scope_id="s-1") == []


@besoin_pg
def test_chercher_ignore_les_entrees_expirees_non_purgees(conn_memoire):
    _creer(conn_memoire, id="echue", contenu="Livraison le matin")
    conn_memoire.execute(
        "UPDATE memoire_durable SET expire_le = %s WHERE tenant_id = %s AND id = %s",
        (datetime.now(timezone.utc) - timedelta(days=1), TENANT, "echue"),
    )

    assert memoire_durable.chercher(conn_memoire, TENANT, "livraison") == []
    assert memoire_durable.lire(conn_memoire, TENANT, "echue") is not None


@besoin_pg
def test_exporter_borne_au_tenant_et_redige_les_secrets(conn_memoire):
    _creer(conn_memoire, id="propre", donnees={"canal": "web"})
    memoire_durable.creer(
        conn_memoire, AUTRE_TENANT, id="ailleurs", scope="session", scope_id="s-1",
        classe="contexte", contenu="hors tenant", provenance="test",
    )
    conn_memoire.execute(
        "INSERT INTO memoire_durable "
        "(id, tenant_id, scope, scope_id, classe, contenu, provenance, consentement, expire_le, "
        " confiance, donnees, cree_le, maj_le) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now() + interval '1 day', %s, %s, now(), now())",
        ("brut", TENANT, "session", "s-1", "contexte", "password=superhunter2", "test",
         False, 0.5, Jsonb({"password": "superhunter2", "note": "token=abcdef123456"})),
    )

    export = memoire_durable.exporter(conn_memoire, TENANT)
    assert {ligne["id"] for ligne in export} == {"propre", "brut"}
    texte = json.dumps(export, ensure_ascii=False)
    assert "superhunter2" not in texte
    assert "abcdef123456" not in texte
    assert all("password" not in (ligne.get("donnees") or {}) for ligne in export)
    assert [ligne["id"] for ligne in memoire_durable.exporter(
        conn_memoire, AUTRE_TENANT)] == ["ailleurs"]


@besoin_pg
def test_supprimer_borne_au_tenant(conn_memoire):
    _creer(conn_memoire, id="a-supprimer")

    assert memoire_durable.supprimer(conn_memoire, AUTRE_TENANT, "a-supprimer") is False
    assert memoire_durable.lire(conn_memoire, TENANT, "a-supprimer") is not None
    assert memoire_durable.supprimer(conn_memoire, TENANT, "a-supprimer") is True
    assert memoire_durable.supprimer(conn_memoire, TENANT, "a-supprimer") is False
    assert memoire_durable.lire(conn_memoire, TENANT, "a-supprimer") is None


@besoin_pg
def test_purger_supprime_les_expirees_du_tenant_seulement(conn_memoire):
    _creer(conn_memoire, id="future")
    _creer(conn_memoire, id="echue")
    memoire_durable.creer(
        conn_memoire, AUTRE_TENANT, id="echue-autre", scope="session", scope_id="s-1",
        classe="contexte", contenu="hors tenant", provenance="test",
    )
    passe = datetime.now(timezone.utc) - timedelta(days=1)
    for tenant, identifiant in ((TENANT, "echue"), (AUTRE_TENANT, "echue-autre")):
        conn_memoire.execute(
            "UPDATE memoire_durable SET expire_le = %s WHERE tenant_id = %s AND id = %s",
            (passe, tenant, identifiant),
        )

    assert memoire_durable.purger(conn_memoire, TENANT) == 1
    assert memoire_durable.lire(conn_memoire, TENANT, "echue") is None
    assert memoire_durable.lire(conn_memoire, TENANT, "future") is not None
    assert memoire_durable.lire(conn_memoire, AUTRE_TENANT, "echue-autre") is not None


@besoin_pg
def test_consentir_enregistre_l_acteur_et_reste_idempotent(conn_memoire):
    _creer(conn_memoire, id="a-consentir", provenance="import")

    maj = memoire_durable.consentir(conn_memoire, TENANT, "a-consentir", "alice")
    assert maj["consentement"] is True
    assert maj["consenti_le"] is not None
    assert "alice" in maj["provenance"]

    encore = memoire_durable.consentir(conn_memoire, TENANT, "a-consentir", "alice")
    assert encore["provenance"].count("alice") == 1
    assert encore["consenti_le"] == maj["consenti_le"]

    assert memoire_durable.consentir(conn_memoire, AUTRE_TENANT, "a-consentir", "bob") is None
    assert memoire_durable.consentir(conn_memoire, TENANT, "absente", "bob") is None
