"""Contexte tenant : demo explicite, production sans repli, et absence non concluante."""
from datetime import date, datetime, timezone
import json

import pytest
from fastapi import APIRouter, FastAPI, Request
from fastapi.testclient import TestClient

import boucle_routes
from meridian.domain.graphe import Arete, GrapheMemoire, NoeudTwin
from meridian.domain.tenant import TenantContext, TenantInvalide, TenantRequis, absence, exiger_tenant, normaliser_slug, resoudre_tenant


@pytest.fixture(autouse=True)
def _environnement(monkeypatch):
    monkeypatch.delenv("AUTH_MODE", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)


def test_en_demo_un_tenant_absent_devient_local_explicitement():
    contexte = resoudre_tenant(None, auth_mode="demo")

    assert isinstance(contexte, TenantContext)
    assert contexte.id == "local"
    assert contexte.demo is True
    assert contexte.source == "defaut"
    assert contexte.tenant == contexte.id
    assert str(contexte) == "local"
    assert contexte.as_dict() == {"id": "local", "demo": True, "source": "defaut"}


@pytest.mark.parametrize("valeur", ["", "   ", "\t\n"])
def test_un_tenant_vide_est_refuse_meme_en_demo(valeur):
    with pytest.raises(TenantInvalide, match="vide"):
        resoudre_tenant(valeur, auth_mode="demo")


@pytest.mark.parametrize("valeur", [
    "Banque Client",
    "banque/autre",
    "banque:autre",
    "banque!",
    "-banque",
    "banque-",
    "banque..autre",
    "a" * 65,
    42,
    ["banque"],
])
def test_un_slug_invalide_est_refuse(valeur):
    with pytest.raises(TenantInvalide):
        resoudre_tenant(valeur, auth_mode="demo")


def test_un_slug_valide_est_canonise_et_porte_sa_source():
    contexte = resoudre_tenant("  Banque_Client  ", auth_mode="demo")

    assert contexte.id == "banque_client"
    assert contexte.demo is True
    assert contexte.source == "entete"


def test_normaliser_slug_accepte_les_separateurs_simples_et_abaisse_la_casse():
    assert normaliser_slug(" Banque-Client ") == "banque-client"
    assert normaliser_slug("Banque.Client") == "banque.client"
    assert normaliser_slug("Banque_Client") == "banque_client"
    assert normaliser_slug("Banqué") == "banque"
    with pytest.raises(TenantInvalide):
        normaliser_slug(None)


@pytest.mark.parametrize("mode", ["production", "proxy", "oidc", "inconnu"])
def test_hors_demo_un_tenant_absent_est_refuse_sans_repli(mode):
    with pytest.raises(TenantRequis) as erreur:
        resoudre_tenant(None, auth_mode=mode)

    assert "local" not in str(erreur.value)
    assert erreur.value.status_code in (401, 403)


def test_app_env_production_interdit_le_repli_demo_meme_si_auth_mode_demo(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "demo")
    monkeypatch.setenv("APP_ENV", "production")

    with pytest.raises(TenantRequis):
        resoudre_tenant(None)

    contexte = resoudre_tenant("banque", auth_mode="demo")
    assert contexte.id == "banque"
    assert contexte.demo is False


def test_un_tenant_explicite_est_accepte_en_production():
    contexte = resoudre_tenant("banque", auth_mode="production")

    assert contexte.id == "banque"
    assert contexte.demo is False
    assert contexte.source == "entete"


def test_exiger_tenant_ne_fabrique_jamais_de_defaut():
    assert exiger_tenant("banque").id == "banque"
    contexte = TenantContext(id="assurance", demo=False, source="identite")
    assert exiger_tenant(contexte) is contexte

    with pytest.raises(TenantRequis):
        exiger_tenant(None)
    with pytest.raises(TenantInvalide):
        exiger_tenant("Banque Client")


def test_l_absence_est_bornee_et_non_concluante():
    resultat = absence(
        "CMDB du tenant banque",
        ["cmdb", "catalogue de services"],
        "2026-10-30",
        case_id="case-42",
    )

    assert resultat["scope"] == "CMDB du tenant banque"
    assert resultat["sources"] == ["cmdb", "catalogue de services"]
    assert resultat["date"] == "2026-10-30"
    assert resultat["case_id"] == "case-42"
    assert resultat["observed"] is False
    assert resultat["phrase"] == (
        "non observé dans CMDB du tenant banque au 2026-10-30 ; ce n'est pas une preuve d'absence"
    )
    assert resultat["wording"] == resultat["phrase"]
    assert "n'existe pas" not in resultat["phrase"]
    assert json.loads(json.dumps(resultat, ensure_ascii=False)) == resultat


def test_l_absence_accepte_les_dates_et_une_source_unique():
    resultat = absence("inventaire", "cmdb", date(2026, 10, 30))

    assert resultat["sources"] == ["cmdb"]
    assert "au 2026-10-30" in resultat["phrase"]

    horodatage = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
    assert absence("inventaire", [], horodatage)["date"] == horodatage.isoformat()


def test_une_absence_sans_perimetre_ou_sans_date_est_refusee():
    with pytest.raises(TenantInvalide, match="scope"):
        absence("   ", ["cmdb"], "2026-10-30")
    with pytest.raises(TenantInvalide, match="date"):
        absence("inventaire", ["cmdb"], "")


class _Curseur:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, _sql, _params=()):
        return self

    def fetchall(self):
        return []


class _Connexion:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def cursor(self, row_factory=None):
        return _Curseur()


def _client(monkeypatch, tenant_authentifie=None):
    monkeypatch.setenv("JUMEAU_PG_DSN", "postgresql://test/test")
    monkeypatch.setattr(boucle_routes.psycopg, "connect", lambda *_, **__: _Connexion())

    app = FastAPI()
    if tenant_authentifie is not None:
        @app.middleware("http")
        async def poser_identite(request: Request, call_next):
            request.state.tenant = tenant_authentifie
            request.state.auth_mode = "production"
            return await call_next(request)

    api = APIRouter(prefix="/api")
    api.include_router(boucle_routes.router)
    app.include_router(api)
    return TestClient(app)


def test_les_routes_boucle_utilisent_le_tenant_demo_ou_l_entete(monkeypatch):
    client = _client(monkeypatch)

    assert client.get("/api/boucle/synthese").json()["tenant"] == "local"
    assert client.get("/api/boucle/synthese", headers={"X-Tenant": "banque"}).json()["tenant"] == "banque"


def test_les_routes_boucle_refusent_un_tenant_vide_ou_invalide(monkeypatch):
    client = _client(monkeypatch)

    assert client.get("/api/boucle/synthese", headers={"X-Tenant": "   "}).status_code == 400
    assert client.get("/api/boucle/synthese", headers={"X-Tenant": "Banque Client"}).status_code == 400


def test_les_routes_boucle_refusent_la_production_sans_tenant(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "production")
    client = _client(monkeypatch)

    reponse = client.get("/api/boucle/synthese")
    assert reponse.status_code in (401, 403)
    assert "local" not in reponse.json()["detail"]

    assert client.get("/api/boucle/synthese", headers={"X-Tenant": "banque"}).json()["tenant"] == "banque"


def test_les_routes_boucle_ne_laissent_pas_le_client_choisir_en_production(monkeypatch):
    client = _client(monkeypatch, tenant_authentifie="banque")

    assert client.get("/api/boucle/synthese").json()["tenant"] == "banque"
    assert client.get("/api/boucle/synthese", headers={"X-Tenant": "assurance"}).status_code == 403
    assert client.get("/api/boucle/synthese", headers={"X-Tenant": "banque"}).json()["tenant"] == "banque"


def test_les_routes_graphe_sont_bornees_au_tenant(monkeypatch):
    store = GrapheMemoire()
    store.upsert_twin(NoeudTwin("a", "banque", "APPLICATION", "A"))
    store.upsert_twin(NoeudTwin("b", "banque", "APPLICATION", "B"))
    store.upsert_relation(Arete("r1", "banque", "a", "b", "echange", "confirmee"))
    monkeypatch.setattr(boucle_routes.graph_store, "ouvrir", lambda: {
        "store": store, "mode": "memoire", "fermer": lambda: None})
    client = _client(monkeypatch)

    voisins = client.get("/api/boucle/graphe/a/voisins", headers={"X-Tenant": "banque"})
    assert voisins.status_code == 200
    assert voisins.json()["tenant"] == "banque" and voisins.json()["voisins"][0]["id"] == "b"

    autre = client.get("/api/boucle/graphe/a/voisins", headers={"X-Tenant": "assurance"})
    assert autre.status_code == 200 and autre.json()["voisins"] == []

    impact = client.get("/api/boucle/graphe/a/impact", headers={"X-Tenant": "banque"})
    assert impact.status_code == 200 and impact.json()["impact"]["aval"][0]["id"] == "b"

    chemins = client.get("/api/boucle/graphe/chemins?source=a&cible=b",
                         headers={"X-Tenant": "banque"})
    assert chemins.status_code == 200 and chemins.json()["chemins"] == [["a", "b"]]


def test_les_routes_graphe_valident_les_parametres(monkeypatch):
    monkeypatch.setattr(boucle_routes.graph_store, "ouvrir", lambda: {
        "store": GrapheMemoire(), "mode": "memoire", "fermer": lambda: None})
    client = _client(monkeypatch)

    assert client.get("/api/boucle/graphe/a/voisins?sens=diagonal",
                      headers={"X-Tenant": "banque"}).status_code == 422
    assert client.get("/api/boucle/graphe/a/voisins?profondeur=9",
                      headers={"X-Tenant": "banque"}).status_code == 422


def test_le_resume_graphe_compte_les_noeuds_du_tenant(monkeypatch):
    store = GrapheMemoire()
    store.upsert_twin(NoeudTwin("a", "banque", "APPLICATION", "A"))
    store.upsert_twin(NoeudTwin("b", "banque", "APPLICATION", "B"))
    store.upsert_relation(Arete("r1", "banque", "a", "b"))
    monkeypatch.setattr(boucle_routes.graph_store, "ouvrir", lambda: {
        "store": store, "mode": "memoire", "fermer": lambda: None})
    client = _client(monkeypatch)

    reponse = client.get("/api/boucle/graphe/resume", headers={"X-Tenant": "banque"})
    assert reponse.status_code == 200
    assert reponse.json()["twins"] == 2 and reponse.json()["relations"] == 1
