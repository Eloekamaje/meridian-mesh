"""Couverture d'extraction : Java JAX-RS/servlet, Python, ASP.NET."""
from __future__ import annotations

from meridian.adapters.outbound.connectors.decouverte_composants import extraire_depot
from meridian.domain.liens_composants import SourceDepot


def _depot(fichiers):
    return SourceDepot(application_id="app", composant_id="app-api",
                       environment="prod", fichiers=fichiers)


def test_jax_rs_produit_une_interface_http():
    extraction = extraire_depot(_depot({
        "src/AccountsResource.java": """
import javax.ws.rs.*;
@Path("/accounts")
public class AccountsResource {
    @GET
    @Path("/{id}")
    public String get(@PathParam("id") String id) { return "ok"; }

    @POST
    public String create(String body) { return "ok"; }
}
""",
    }))

    operations = {interface.operation for interface in extraction.interfaces}
    assert "GET /accounts/{id}" in operations
    assert "POST /accounts" in operations


def test_servlet_jee_produit_une_interface_any():
    extraction = extraire_depot(_depot({
        "src/LegacyServlet.java": """
import javax.servlet.annotation.WebServlet;
@WebServlet("/legacy/accounts")
public class LegacyServlet extends HttpServlet {
}
""",
    }))

    assert any(interface.operation == "ANY /legacy/accounts"
               and interface.methode == "ANY" for interface in extraction.interfaces)


def test_jndi_local_produit_un_appel():
    extraction = extraire_depot(_depot({
        "src/PaymentService.java": """
import javax.annotation.Resource;
public class PaymentService {
    @Resource(lookup = "java:comp/env/jms/PaymentEvents")
    private Object events;
}
""",
    }))

    assert any(appel.cible_type == "JNDI"
               and appel.cible == "java:comp/env/jms/PaymentEvents"
               for appel in extraction.appels)


def test_fastapi_produit_une_interface_http():
    extraction = extraire_depot(_depot({
        "app/main.py": """
from fastapi import FastAPI
app = FastAPI()

@app.get("/accounts/{account_id}")
def lire(account_id: str):
    return {"id": account_id}
""",
    }))

    assert any(interface.operation == "GET /accounts/{account_id}"
               for interface in extraction.interfaces)


def test_flask_route_avec_methodes():
    extraction = extraire_depot(_depot({
        "app/vues.py": """
from flask import Flask
app = Flask(__name__)

@app.route("/clients/<identifiant>", methods=["GET", "PUT"])
def client(identifiant):
    return {}
""",
    }))

    operations = {interface.operation for interface in extraction.interfaces}
    assert "GET /clients/<identifiant>" in operations
    assert "PUT /clients/<identifiant>" in operations


def test_requests_et_httpx_sont_des_consommateurs():
    extraction = extraire_depot(_depot({
        "app/client.py": """
import requests, httpx

def lire():
    requests.get("http://comptes-api:8080/accounts/1")
    httpx.post("http://comptes-api:8080/accounts", json={})
""",
    }))

    appels = {(appel.methode, appel.chemin) for appel in extraction.appels}
    assert ("GET", "/accounts/1") in appels
    assert ("POST", "/accounts") in appels


def test_aspnet_route_et_httpclient():
    extraction = extraire_depot(_depot({
        "Controllers/AccountsController.cs": """
[Route("/api/accounts")]
public class AccountsController : ControllerBase {
    [HttpGet("{id}")]
    public string Get(string id) { return "ok"; }

    [HttpPost]
    public string Create() { return "ok"; }
}
""",
        "Services/Client.cs": """
public class Client {
    public async Task Lire() {
        await _http.GetAsync("http://comptes-api:8080/accounts/1");
    }
}
""",
    }))

    operations = {interface.operation for interface in extraction.interfaces}
    assert "GET /api/accounts/{id}" in operations
    assert "POST /api/accounts" in operations
    assert any(appel.methode == "GET" and appel.chemin == "/accounts/1"
               for appel in extraction.appels)


def test_un_producteur_python_et_un_consommateur_python_se_relient():
    from meridian.application.moteur_liens import moteur_liens

    producteur = SourceDepot(
        application_id="comptes", composant_id="comptes-api", environment="prod",
        fichiers={"app/main.py": """
from fastapi import FastAPI
app = FastAPI()
@app.get("/accounts/{account_id}")
def lire(account_id: str):
    return {}
"""})
    consommateur = SourceDepot(
        application_id="antifraude", composant_id="antifraude-api", environment="prod",
        fichiers={"app/client.py": """
import requests
def lire():
    return requests.get("http://comptes-api:8080/accounts/42")
"""})

    rapport = moteur_liens([extraire_depot(producteur), extraire_depot(consommateur)])

    lien = next(lien for lien in rapport.liens
                if lien.operation == "GET /accounts/{account_id}")
    assert lien.nature == "mesh"
    assert lien.fournisseur_composant_id == "comptes-api"


def test_python_ast_resout_prefixe_et_constantes():
    extraction = extraire_depot(_depot({
        "app/vues.py": """
from fastapi import APIRouter
BASE = "http://comptes-api:8080"
router = APIRouter(prefix="/api")

@router.get("/comptes")
def lire():
    return {}

def appeler():
    import requests
    return requests.get(BASE + "/comptes/42")
""",
    }))

    operations = {interface.operation for interface in extraction.interfaces}
    assert "GET /api/comptes" in operations
    assert any(appel.methode == "GET"
               and appel.cible == "http://comptes-api:8080/comptes/42"
               for appel in extraction.appels)


def test_python_ast_ignore_les_commentaires_et_replie_sur_le_texte():
    commente = extraire_depot(_depot({
        "app/main.py": """
# @app.get("/faux")
VALEUR = "pas une route"
""",
    }))
    assert not commente.interfaces

    casse = extraire_depot(_depot({
        "app/casse.py": """
from flask import Flask
app = Flask(__name__)
@app.route("/vrai")
def vrai(:
    pass
""",
    }))
    assert any(interface.operation == "GET /vrai" for interface in casse.interfaces)
    assert any("repli textuel" in diagnostic for diagnostic in casse.diagnostics)
