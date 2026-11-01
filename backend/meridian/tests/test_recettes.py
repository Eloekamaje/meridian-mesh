"""Recettes déterministes (harness v3 §2.1) : pures, sans base, sans réseau, sans modèle."""
import pytest

from meridian.domain.recettes import PREDICATS, recette

V, N = "verifie", "non_appuye"


def test_predicats_et_predicat_sans_recette():
    assert PREDICATS == {"DEPEND_DE", "EXPOSE", "LIT_VARIABLE", "EXECUTE_IMAGE"}
    assert recette("CONNAIT", "x", ["x"]) is None


@pytest.mark.parametrize("predicat", sorted(PREDICATS))
def test_lignes_vides_ou_absentes(predicat):
    assert recette(predicat, "x", []) == N
    assert recette(predicat, "x", ["", "   "]) == N
    assert recette(predicat, "x", None) == N


@pytest.mark.parametrize("objet,lignes,attendu", [
    ("fastapi", ["fastapi==0.110.1"], V),
    ("fastapi", ["FastAPI>=0.1"], V),
    ("uvicorn", ["uvicorn[standard]>=0.29"], V),
    ("python-dotenv", ["python_dotenv==1.0"], V),
    ("react", ['    "react": "^18",'], V),
    ("@types/node", ['"@types/node": "^20"'], V),
    ("fastapi", ["fastapi = \"^0.110\""], V),
    ("github.com/gin-gonic/gin", ["\tgithub.com/gin-gonic/gin v1.9.1"], V),
    ("spring-boot-starter-web", ["<artifactId>spring-boot-starter-web</artifactId>"], V),
    ("fastapi", ["fastapi-users==12"], N),
    ("fastapi", ["my-fastapi==1"], N),
    ("fastapi", ["fastapi_utils==1"], N),
    ("fastapi", ["# fastapi==0.110"], N),
    ("fastapi", ["flask==3.0"], N),
])
def test_depend_de(objet, lignes, attendu):
    assert recette("DEPEND_DE", objet, lignes) == attendu


GET_CX = "GET /connexions/{systeme}/{cxid}/perimetres"


@pytest.mark.parametrize("objet,lignes,attendu", [
    (GET_CX, ['@api_router.get("/connexions/{systeme}/{cxid}/perimetres")'], V),
    (GET_CX, ['@api_router.post("/connexions/{systeme}/{cxid}/perimetres")'], N),
    (GET_CX, ['@api_router.get("/connexions/{systeme}/{cxid}/autre")'], N),
    ("get /a/b", ['@router.get("/a/b")'], V),
    ("DELETE /items/{id}", ["router.delete('/items/:id', handler)"], V),
    ("GET /items/{id}", ['@app.route("/items/<int:id>")'], V),
    ("POST /items", ['@app.route("/items", methods=["GET", "POST"])'], V),
    ("PUT /items", ['@app.route("/items", methods=["GET", "POST"])'], N),
    ("GET /items", ['@app.route("/items")'], V),
    ("PATCH /items", ['@PatchMapping("/items")'], V),
    ("GET /items", ['@PostMapping("/items")'], N),
    ("GET /items", ['@RequestMapping(value = "/items", method = RequestMethod.GET)'], V),
    # préfixe de routeur absent de la ligne : le chemin cité est plus long, la fin correspond
    ("GET /api/v1/users/{id}", ['@router.get("/users/{uid}")'], V),
    ("GET /api/v1/users", ['@router.get("/accounts")'], N),
    # fin alignée sur un segment entier, pas sur une sous-chaîne
    ("GET /api/superusers", ['@router.get("/users")'], N),
    # une ligne dont le chemin est « / » n'appuie rien (trop ambigu)
    ("GET /api/users", ['@router.get("/")'], N),
    # chemin de la ligne plus long que le chemin cité : non appuyé
    ("GET /users", ['@router.get("/api/users")'], N),
    # décorateur sur plusieurs lignes
    ("POST /items", ["@app.route(", '    "/items",', '    methods=["POST"])'], V),
    ("GET", ['@router.get("/x")'], N),
])
def test_expose(objet, lignes, attendu):
    assert recette("EXPOSE", objet, lignes) == attendu


@pytest.mark.parametrize("lignes,attendu", [
    (["      - SMTP_USER=${SMTP_USER}"], V),
    (["      SMTP_USER: ${SMTP_USER}"], V),
    (["SMTP_USER=bob"], V),
    (['  - "SMTP_USER=bob"'], V),
    (['user = os.environ["SMTP_USER"]'], V),
    (["user = os.environ.get('SMTP_USER', '')"], V),
    (['user = os.getenv("SMTP_USER")'], V),
    (["const u = process.env.SMTP_USER;"], V),
    (['const u = process.env["SMTP_USER"];'], V),
    (['u := os.Getenv("SMTP_USER")'], V),
    (["      SMTP_USERNAME: x"], N),
    (["      MY_SMTP_USER: x"], N),
    (["      smtp_user: x"], N),
    (["process.env.SMTP_USERNAME"], N),
    (["# SMTP_USER est lu ailleurs"], N),
])
def test_lit_variable(lignes, attendu):
    assert recette("LIT_VARIABLE", "SMTP_USER", lignes) == attendu


@pytest.mark.parametrize("objet,lignes,attendu", [
    ("docker.io/library/traefik", ["    image: traefik:v3.1"], V),
    ("docker.io/library/traefik", ["    image: 'docker.io/library/traefik:v3.1'"], V),
    ("traefik", ["image: library/traefik"], V),
    ("docker.io/library/python", ["FROM python:3.11-slim"], V),
    ("python", ["from --platform=linux/amd64 python:3.11 AS build"], V),
    ("ghcr.io/org/app", ["image: ghcr.io/org/app@sha256:abc123"], V),
    ("localhost:5000/app", ["image: localhost:5000/app:2"], V),
    ("docker.io/library/traefik", ["    image: traefik-forward-auth:1"], N),
    ("docker.io/library/traefik", ["    image: nginx:1.25"], N),
    ("docker.io/library/traefik", ["    # image: traefik:v3"], N),
    ("ghcr.io/org/app", ["image: docker.io/org/app:1"], N),
    ("python", ["RUN pip install python"], N),
])
def test_execute_image(objet, lignes, attendu):
    assert recette("EXECUTE_IMAGE", objet, lignes) == attendu


def test_expose_la_racine_seulement_pour_la_racine():
    assert recette("EXPOSE", "GET /", ['@api_router.get("/")']) == "verifie"
    assert recette("EXPOSE", "GET /dossiers", ['@api_router.get("/")']) == "non_appuye"
